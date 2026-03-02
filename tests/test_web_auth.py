"""
Tests that all authenticated web routes redirect to /web/login when no session cookie is present.

Ensures the _web_page factory and the dashboard route enforce authentication.
"""
import pytest

# All routes that use _web_page() or manual auth checks and should redirect
_AUTHENTICATED_WEB_ROUTES = [
    "/",
    "/web/integrations",
    "/web/talk",
    "/web/data-hub",
    "/web/observe",
    "/web/ops-intel",
    "/web/tasks",
    "/web/webhooks",
    "/web/notifications",
    "/web/security",
    "/web/api-keys",
    "/web/audit",
    "/web/team",
    "/web/health",
    "/web/automations",
    "/web/performance",
    "/web/governance",
    "/web/media",
    "/web/personas",
    "/web/coaching",
    "/web/projects",
    "/web/goals",
    "/web/contacts",
    "/web/finance",
    "/web/maps",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", _AUTHENTICATED_WEB_ROUTES)
async def test_unauthenticated_redirect(client, route):
    """Without a session cookie, hitting an authenticated web route should redirect to /web/login."""
    # Remove Authorization header to simulate an unauthenticated request
    resp = await client.get(route, headers={}, follow_redirects=False)
    assert resp.status_code == 302, f"{route} did not redirect (got {resp.status_code})"
    location = resp.headers.get("location", "")
    assert "/web/login" in location, f"{route} redirected to {location} instead of /web/login"


@pytest.mark.asyncio
async def test_login_page_accessible_without_auth(client):
    """The login page itself must be accessible without authentication."""
    resp = await client.get("/web/login", headers={}, follow_redirects=False)
    assert resp.status_code == 200
