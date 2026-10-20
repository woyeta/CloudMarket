"""
Health check endpoint.

The database is required, so a DB failure returns 503.
Redis is only a cache (search works without it), so a Redis failure
is reported as "degraded" but still returns 200.
"""

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from marketplace.services import cache


@never_cache
@require_GET
def healthz(request):
    checks = {}
    http_status = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "down"
        http_status = 503

    checks["redis"] = cache.ping()

    return JsonResponse(
        {"status": "ok" if http_status == 200 else "down", "checks": checks},
        status=http_status,
    )
