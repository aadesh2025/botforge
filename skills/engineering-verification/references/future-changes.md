# Feature safety: impact analysis and change locality

Use before implementing any non-trivial feature or behavior change. Skip for a one-line fix whose location and
effect are obvious.

## 1. Order of work

1. Restate the request and the acceptance criteria.
2. Find the owning domain (where this concern already lives).
3. Search for existing abstractions and implementations to reuse.
4. Write the impact plan below.
5. Analyze security, authorization and tenant impact.
6. Implement in small steps, running the narrowest relevant check after each.
7. Test the behavior, the failure cases and the security boundary.
8. Run the broader checks; review the diff against the plan.
9. Write the feature report.

Do not create files first. Search first.

## 2. Find the owning domain

Follow the request to where the same kind of thing is already done: the closest existing feature, the module
whose data or vocabulary it uses, the tests of similar behavior, the documentation that describes it. Use the
repository's existing names; do not introduce synonyms for existing concepts. If two places could own it,
choose the one that already owns the data, and say why.

## 3. Search for existing abstractions

Before writing a service, manager, helper, utility, provider, client, repository, adapter, hook, context,
middleware, validator or configuration mechanism, search for:

- the same concept under other names (grep for verbs and nouns the feature involves, not only your planned
  name);
- the same behavior (who already calls this API, parses this format, checks this permission, reads this
  setting, retries this call);
- the interface a new implementation should satisfy (existing provider or adapter contracts);
- sibling implementations, to copy their structure and tests;
- the shared or core area, and the documentation of it.

Record what you searched. If you reuse something, name it. If you cannot, give one sentence why. An
adapter for an external system belongs in that system's existing adapter layer; a new implementation of an
existing contract should not require changes outside the contract's own area.

## 4. Impact plan

Fill `templates/feature-impact.md` before editing. It must name:

- expected files to change, and files that must **not** change (be specific: the neighboring domains a careless
  implementation would be tempted to touch);
- API, data (tables, migrations, indexes, ownership, deletion), security, authorization, tenant,
  integration, frontend, background-job impact;
- tests required (unit, integration, security boundary, regression) and documentation to update;
- ripple effects: who else calls what you change; shared types; configuration and environment variables;
  deployment.

Migrations: never edit historical migrations; add new ones; check for compatibility with existing data.
New configuration: document it where the project documents configuration and give it a safe default.

## 5. Change locality

`feature -> owning domain -> existing interface -> minimal dependencies.`

Examples of good locality: a new channel or provider touches that channel's or provider's area and its tests
and docs, and perhaps one configuration entry; a new dashboard view touches its feature area and reuses the
shared client and components; a new field touches the model, its migration, the one validation point and the
tests.

Signals to stop: the plan said 4 files and the diff has 15; an unrelated domain is being edited to make a
type fit; a shared module is being modified by a feature that only one domain uses; you are working around a
boundary rather than through it.

When you stop, write the dependency chain that pulled each extra file in, then decide with the user among:
reuse an existing abstraction; a boundary is misplaced (propose a separate change to fix it); the feature
genuinely crosses domains (widen the plan explicitly); the edit is accidental (revert it).

## 6. Security, access and tenancy for the new surface

For every new entry point, input, outbound request, file, job or stored value, decide: who may call it and how
that is enforced; what identifies the owner and how ownership is checked; what an unauthorized caller sees;
what is validated; what could be abused for server-side requests, injection or resource exhaustion; what is
logged and whether it may contain secrets. If the product is multi-tenant, derive tenant context from the
authenticated session or a trusted relation, never from a client-supplied value, and add a cross-tenant test.
Method: `security.md`.

## 7. Implementation discipline

- Follow the style of the surrounding code: naming, comments, structure.
- Add the minimum abstraction the feature needs.
- Keep the feature separate from refactors, upgrades and migrations of frameworks.
- Update documentation only where its truth changed. Record a decision when a boundary or abstraction changes.
- Do not fix unrelated problems you notice; list them under follow-up.

## 8. Feature report

Use the report section of `templates/feature-impact.md`. Compare the final change set with the plan: list any
file that changed and was not in the plan and explain it. State remaining risks, including anything not
verified.
