"""One shared classroom password for the Internet-facing demonstration."""
import base64
import os
import secrets
import database

from starlette.responses import JSONResponse


def enabled():
    return bool(os.getenv("RENDER")) or os.getenv("CAP_AVENIR_REQUIRE_AUTH") == "1"


def validate_configuration():
    if enabled() and not os.getenv("CAP_AVENIR_ADMIN_PASSWORD"):
        raise RuntimeError("Configure CAP_AVENIR_ADMIN_PASSWORD before exposing the service.")
    if os.getenv("RENDER") and not database.postgres_url():
        raise RuntimeError("Configure DATABASE_URL with the persistent Render PostgreSQL database.")


async def protect(request, call_next):
    if not enabled() or request.url.path == "/api/health":
        return await call_next(request)
    valid = False
    try:
        scheme, value = request.headers.get("authorization", "").split(" ", 1)
        username, password = base64.b64decode(value, validate=True).decode("utf-8").split(":", 1)
        valid = scheme.lower() == "basic" and secrets.compare_digest(username.encode(), os.getenv("CAP_AVENIR_ADMIN_USER", "admin").encode()) and secrets.compare_digest(password.encode(), os.getenv("CAP_AVENIR_ADMIN_PASSWORD", "").encode())
    except (ValueError, UnicodeError):
        pass
    if not valid:
        return JSONResponse({"detail": "Accès réservé à la démonstration du TP."}, status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Cap Avenir", charset="UTF-8"', "Cache-Control": "no-store"})
    return await call_next(request)
