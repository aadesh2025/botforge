"""Import-boundary rules for `app/`, checked statically (AST, no imports executed).

Each rule encodes something true of the codebase today so it cannot quietly rot. Where the code
has a known, deliberate exception it is listed in an allowlist *with the reason*; adding to an
allowlist is a design decision, not a way to make this test pass.

Only module-level imports count for cycle detection (a function-level import is how a cycle is
already being broken). `if TYPE_CHECKING:` imports are ignored.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
REPO = Path(__file__).resolve().parents[3]

Import = tuple[str, str | None, int]  # (target module, imported name, lineno)


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(APP.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package(module: str) -> str:
    """`app.modules.agents.service` -> `app.modules.agents`; `app.chat.runtime` -> `app.chat`."""
    parts = module.split(".")
    return ".".join(parts[:3] if len(parts) >= 3 and parts[1] == "modules" else parts[:2])


class _Imports(ast.NodeVisitor):
    def __init__(self, module: str, is_init: bool) -> None:
        self.module, self.is_init = module, is_init
        self.top: list[Import] = []
        self.lazy: list[Import] = []
        self._depth = 0
        self._type_checking = 0

    def _fn(self, node: ast.AST) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_FunctionDef = visit_AsyncFunctionDef = _fn

    def visit_If(self, node: ast.If) -> None:
        guarded = "TYPE_CHECKING" in ast.unparse(node.test)
        self._type_checking += guarded
        self.generic_visit(node)
        self._type_checking -= guarded

    def _add(self, target: str, name: str | None, lineno: int) -> None:
        if self._type_checking or not target.startswith("app"):
            return
        (self.lazy if self._depth else self.top).append((target, name, lineno))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._add(alias.name, None, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = node.module or ""
        if node.level:
            pkg = self.module.split(".")
            if not self.is_init:
                pkg = pkg[:-1]
            pkg = pkg[: len(pkg) - (node.level - 1)]
            base = ".".join(pkg + ([base] if base else []))
        for alias in node.names:
            self._add(base, alias.name, node.lineno)


def _scan() -> dict[str, _Imports]:
    out: dict[str, _Imports] = {}
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = _module_name(path)
        visitor = _Imports(module, path.name == "__init__.py")
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        out[module] = visitor
    return out


SCAN = _scan()
MODULES = set(SCAN)


def _resolve(target: str, name: str | None) -> str:
    """`from app.x import y` targets module `app.x.y` when that is a module, else `app.x`."""
    if name and f"{target}.{name}" in MODULES:
        return f"{target}.{name}"
    return target


def _sccs(graph: dict[str, set[str]]) -> list[frozenset[str]]:
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    found: list[frozenset[str]] = []
    counter = [0]

    def visit(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                found.append(frozenset(comp))

    for v in list(graph):
        if v not in index:
            visit(v)
    return found


def _top_level_graph(granularity: str) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for module, imports in SCAN.items():
        src = module if granularity == "file" else _package(module)
        graph[src]
        for target, name, _ in imports.top:
            dst = _resolve(target, name)
            if dst not in MODULES:
                continue
            dst = dst if granularity == "file" else _package(dst)
            if dst != src:
                graph[src].add(dst)
    return graph


# ── 1. cycles ───────────────────────────────────────────────────────────────────────────────
def test_no_import_cycle_between_files() -> None:
    assert _sccs(_top_level_graph("file")) == []


# Package-level cycles that exist today and are accepted. Each is held together by one shared
# primitive that lives in the "wrong" package (chat.pii, chat.guardrails, webhooks.dispatch,
# modules.orgs.deps); none is a cycle between files. A *new* package cycle fails this test.
ACCEPTED_PACKAGE_CYCLES: set[frozenset[str]] = {
    # core.audit -> models; models -> db.base; db.session -> core.config
    frozenset({"app.core", "app.db", "app.models"}),
    # chat <-> rag (guardrails/pii/retrieval), both -> webhooks.dispatch, webhooks -> orgs.deps,
    # orgs.schemas -> chat.pii
    frozenset({"app.chat", "app.rag", "app.webhooks", "app.modules.orgs"}),
    # contacts.service -> channels.base types; channels.service -> contacts
    frozenset({"app.channels", "app.contacts"}),
}


def test_no_new_package_import_cycle() -> None:
    assert set(_sccs(_top_level_graph("package"))) <= ACCEPTED_PACKAGE_CYCLES


# ── 2. layering ─────────────────────────────────────────────────────────────────────────────
def _imports_of(package: str) -> list[tuple[str, str, int]]:
    """(module, imported package, lineno) for every app.* import made by files in `package`."""
    rows = []
    for module, imports in SCAN.items():
        if _package(module) != package:
            continue
        for target, name, lineno in imports.top + imports.lazy:
            dst = _package(_resolve(target, name)) if target != "app" else "app"
            if dst != package:
                rows.append((module, dst, lineno))
    return rows


def test_models_depend_only_on_db_base() -> None:
    for module, imports in SCAN.items():
        if _package(module) != "app.models":
            continue
        for target, name, lineno in imports.top + imports.lazy:
            resolved = _resolve(target, name)
            if _package(resolved) == "app.models":
                continue
            assert resolved == "app.db.base", f"{module}:{lineno} imports {resolved}"


def test_llm_providers_do_not_reach_into_features() -> None:
    bad = [(m, p) for m, p, _ in _imports_of("app.llm") if p not in {"app.core", "app.models"}]
    assert not bad, bad


# core is cross-cutting infrastructure: it must not import feature code. Known exceptions:
CORE_ALLOWED = {
    ("app.core.audit", "app.models"),  # writes AuditLog rows
    ("app.core.metrics", "app"),  # reads app.__version__
    ("app.core.email", "app.worker"),  # lazy: enqueues the send task
}


def test_core_does_not_import_features() -> None:
    bad = sorted(
        (m, p) for m, p, _ in _imports_of("app.core") if (m, p) not in CORE_ALLOWED
    )
    assert not bad, f"core imports feature code: {bad}"


# ── 3. no reaching into another package's private names ─────────────────────────────────────
# Ratchet: these cross-package imports of `_private` helpers exist today (chiefly the turn
# pipeline in conversations.service / agents.service / workflows.service being reused by chat,
# the worker and the *_tests modules). They are debt, not design: the fix is to promote the
# helper to a public name, then delete its line here. A new entry is refused; a stale one fails
# too, so this list can only shrink.
KNOWN_PRIVATE_IMPORTS: set[tuple[str, str]] = {
    ("app.chat.inbound", "app.modules.conversations.service._build_chat_request"),
    ("app.chat.inbound", "app.modules.conversations.service._enqueue_finalize_turn"),
    ("app.chat.inbound", "app.modules.conversations.service._finalize_turn"),
    ("app.chat.inbound", "app.modules.conversations.service._load_history"),
    ("app.chat.inbound", "app.modules.conversations.service._persist_user_message"),
    ("app.chat.inbound", "app.modules.conversations.service._resolve_provider"),
    ("app.modules.agent_tests.service", "app.modules.agents.service._build_request"),
    ("app.modules.agent_tests.service", "app.modules.agents.service._get_agent"),
    ("app.modules.agent_tests.service", "app.modules.agents.service._latest_version"),
    ("app.modules.agent_tests.service", "app.modules.agents.service._playground_tooling"),
    ("app.modules.agent_tests.service", "app.modules.agents.service._resolve_playground_provider"),
    ("app.modules.agent_tests.service", "app.modules.agents.service._retrieve_context"),
    ("app.modules.conversations.router", "app.modules.orgs.deps._load_context"),
    ("app.modules.inbox.router", "app.modules.orgs.deps._load_context"),
    ("app.modules.inbox.service", "app.modules.conversations.service._message_out"),
    ("app.modules.public.service", "app.modules.conversations.service._live_version"),
    ("app.modules.workflow_tests.service", "app.workflows.service._agent_executor_for"),
    ("app.modules.workflow_tests.service", "app.workflows.service._get_workflow"),
    ("app.modules.workflow_tests.service", "app.workflows.service._latest_workflow_version"),
    ("app.modules.workflow_tests.service", "app.workflows.service._sub_workflow_executor_for"),
    ("app.modules.workflow_tests.service", "app.workflows.service._tool_executor_for"),
    ("app.worker.tasks", "app.modules.conversations.service._finalize_turn"),
    ("app.worker.tasks", "app.modules.conversations.service._persist_user_message"),
}


def test_no_new_cross_package_import_of_underscore_names() -> None:
    found = set()
    for module, imports in SCAN.items():
        for target, name, _ in imports.top + imports.lazy:
            private = name and name.startswith("_") and not name.startswith("__")
            if private and f"{target}.{name}" not in MODULES and _package(target) != _package(module):
                found.add((module, f"{target}.{name}"))
    new, stale = found - KNOWN_PRIVATE_IMPORTS, KNOWN_PRIVATE_IMPORTS - found
    assert not new, f"new private cross-package import: {sorted(new)}"
    assert not stale, f"fixed, remove from the list: {sorted(stale)}"


# ── 4. routers stay thin ────────────────────────────────────────────────────────────────────
ROUTERS_MAY_QUERY = {"app.modules.audit.router"}  # one read-only listing, no service layer
QUERY_BUILDERS = {"select", "update", "delete", "insert", "text"}


def test_routers_do_not_build_queries() -> None:
    bad = []
    for module in SCAN:
        if not module.endswith("router") or module in ROUTERS_MAY_QUERY:
            continue
        tree = ast.parse((APP.parent / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy":
                if QUERY_BUILDERS & {a.name for a in node.names}:
                    bad.append(module)
    assert not bad, f"routers importing query builders: {bad}"


# ── 5. the widget stays independently shippable; components do not import routes ────────────
def test_widget_has_no_module_imports() -> None:
    src = (REPO / "packages" / "widget" / "src" / "widget.js").read_text(encoding="utf-8")
    assert not [ln for ln in src.splitlines() if ln.lstrip().startswith(("import ", "require("))]


def test_web_components_do_not_import_route_files() -> None:
    bad = [
        str(p.relative_to(REPO))
        for p in (REPO / "apps" / "web" / "src" / "components").rglob("*.ts*")
        if '"@/app/' in p.read_text(encoding="utf-8")
    ]
    assert not bad, bad
