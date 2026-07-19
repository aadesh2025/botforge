"""Minimal, dependency-free Prometheus metrics.

Enough for a Prometheus/Grafana scrape without pulling in a client library: a request counter
by method/status, a latency histogram, and app/build info. Exposed at ``GET /metrics``.
"""

from __future__ import annotations

import threading
import time

from app import __version__
from app.core.config import settings

# Standard Prometheus histogram buckets (seconds).
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_lock = threading.Lock()
_start = time.time()
# (method, status_class) -> count, e.g. ("GET", "2xx")
_requests: dict[tuple[str, str], int] = {}
# request latency histogram
_bucket_counts: list[int] = [0] * len(_BUCKETS)
_hist_count = 0
_hist_sum = 0.0


def _status_class(status: int) -> str:
    return f"{status // 100}xx"


def observe_request(method: str, status: int, duration_seconds: float) -> None:
    global _hist_count, _hist_sum
    key = (method.upper(), _status_class(status))
    with _lock:
        _requests[key] = _requests.get(key, 0) + 1
        _hist_count += 1
        _hist_sum += duration_seconds
        for i, edge in enumerate(_BUCKETS):
            if duration_seconds <= edge:
                _bucket_counts[i] += 1


def render() -> str:
    lines: list[str] = []
    lines.append("# HELP botforge_build_info Build/version info.")
    lines.append("# TYPE botforge_build_info gauge")
    lines.append(f'botforge_build_info{{version="{__version__}",env="{settings.env}"}} 1')

    lines.append("# HELP botforge_uptime_seconds Process uptime in seconds.")
    lines.append("# TYPE botforge_uptime_seconds gauge")
    lines.append(f"botforge_uptime_seconds {time.time() - _start:.1f}")

    lines.append("# HELP botforge_http_requests_total Total HTTP requests by method and status class.")
    lines.append("# TYPE botforge_http_requests_total counter")
    with _lock:
        for (method, klass), count in sorted(_requests.items()):
            lines.append(f'botforge_http_requests_total{{method="{method}",status="{klass}"}} {count}')

        lines.append("# HELP botforge_http_request_duration_seconds HTTP request latency.")
        lines.append("# TYPE botforge_http_request_duration_seconds histogram")
        # _bucket_counts[i] is already the cumulative count of observations <= edge[i].
        for i, edge in enumerate(_BUCKETS):
            lines.append(f'botforge_http_request_duration_seconds_bucket{{le="{edge}"}} {_bucket_counts[i]}')
        lines.append(f'botforge_http_request_duration_seconds_bucket{{le="+Inf"}} {_hist_count}')
        lines.append(f"botforge_http_request_duration_seconds_sum {_hist_sum:.4f}")
        lines.append(f"botforge_http_request_duration_seconds_count {_hist_count}")

    return "\n".join(lines) + "\n"
