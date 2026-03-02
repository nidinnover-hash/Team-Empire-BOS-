from fastapi.routing import APIRoute

from app.main import app

_ALLOWLIST_NO_RESPONSE_MODEL: set[str] = {
    "/health",  # plain dict health probe
    "/api/v1/email/callback",  # OAuth callback redirect/cookie flow
    "/api/v1/notifications/stream",  # SSE stream
    "/api/v1/export",  # file export/streaming
    "/api/v1/media/{attachment_id}/download",  # file response
}


def test_public_api_routes_have_response_models() -> None:
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        if not route.include_in_schema:
            continue
        if route.status_code == 204:
            continue
        methods = set(route.methods or ()) - {"HEAD", "OPTIONS"}
        if not methods:
            continue
        if route.path in _ALLOWLIST_NO_RESPONSE_MODEL:
            continue
        if route.response_model is None:
            missing.append(f"{route.path} methods={sorted(methods)} name={route.name}")
    assert not missing, "Missing response_model on public API routes:\n" + "\n".join(sorted(missing))
