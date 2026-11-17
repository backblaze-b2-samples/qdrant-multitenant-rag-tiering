import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.types import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Thread-safe in-process metrics counters
_lock = Lock()
_request_count: dict[str, int] = defaultdict(int)
_request_duration_sum: dict[str, float] = defaultdict(float)
_park_count = 0
_restore_count = 0


def record_request(method: str, path: str, status: int, duration: float) -> None:
    # Use | separator to avoid ambiguity with underscores in paths
    key = f"{method}|{path}|{status}"
    with _lock:
        _request_count[key] += 1
        _request_duration_sum[key] += duration


def record_park() -> None:
    global _park_count
    with _lock:
        _park_count += 1


def record_restore() -> None:
    global _restore_count
    with _lock:
        _restore_count += 1


@router.get("/metrics")
async def metrics():
    lines = []
    lines.append("# HELP http_requests_total Total HTTP requests")
    lines.append("# TYPE http_requests_total counter")
    with _lock:
        for key, count in sorted(_request_count.items()):
            parts = key.split("|")
            method = parts[0] if len(parts) == 3 else "unknown"
            path = parts[1] if len(parts) == 3 else key
            status = parts[2] if len(parts) == 3 else "unknown"
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )

        lines.append("# HELP http_request_duration_seconds Total request duration")
        lines.append("# TYPE http_request_duration_seconds counter")
        for key, duration in sorted(_request_duration_sum.items()):
            parts = key.split("|")
            method = parts[0] if len(parts) == 3 else "unknown"
            path = parts[1] if len(parts) == 3 else key
            status = parts[2] if len(parts) == 3 else "unknown"
            lines.append(
                f'http_request_duration_seconds{{method="{method}",path="{path}",status="{status}"}} {duration:.6f}'
            )

        lines.append("# HELP tenant_parks_total Tenants parked to B2 (verified)")
        lines.append("# TYPE tenant_parks_total counter")
        lines.append(f"tenant_parks_total {_park_count}")

        lines.append("# HELP tenant_restores_total Tenants restored from B2")
        lines.append("# TYPE tenant_restores_total counter")
        lines.append(f"tenant_restores_total {_restore_count}")

    return Response(content="\n".join(lines) + "\n", media_type="text/plain")


async def timing_middleware(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        # Catch-all: convert any uncaught exception into a safe, typed 500.
        #
        # This catch is the platform's single source of truth for unhandled
        # errors. It is deliberately INNER to CORSMiddleware (see middleware
        # registration order in main.py): because the 500 response is produced
        # here, it still flows back out through CORSMiddleware, which attaches
        # `Access-Control-Allow-Origin`. If this catch lived outside CORS (or we
        # let the exception bubble to Starlette's ServerErrorMiddleware, which
        # always sits OUTSIDE CORS), the browser would block the 500 and the UI
        # would only see an opaque "network error" — hiding the real bug.
        logger.error(
            "Unhandled exception: %s %s",
            request.method,
            request.url.path,
            exc_info=True,
        )
        response = JSONResponse(
            status_code=500,
            content=ErrorResponse().model_dump(),
        )
    # Baseline security headers on every API response. `nosniff` stops browsers
    # MIME-sniffing a response into something executable; `no-referrer` avoids
    # leaking URLs (which can carry keys) to third parties.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"

    duration = time.time() - start
    # Use the matched route template to avoid unbounded cardinality. Requests
    # that never routed (404s, or 429s short-circuited by the rate limiter)
    # have no route — collapse them to one label instead of the raw URL, or a
    # flood of distinct rejected paths would mint a metric series each.
    route = request.scope.get("route")
    path = route.path if route else "<unmatched>"
    record_request(
        request.method,
        path,
        response.status_code,
        duration,
    )
    return response
