from fastapi.routing import APIRoute

from app.main import app

_ALLOWLIST_NO_RESPONSE_MODEL: set[str] = {
    "/health",  # plain dict health probe
    "/api/v1/email/callback",  # OAuth callback redirect/cookie flow
    "/api/v1/notifications/stream",  # SSE stream
    "/api/v1/export",  # file export/streaming
    "/api/v1/export/deals",  # multi-format export (JSON/CSV)
    "/api/v1/export/contacts",  # multi-format export (JSON/CSV)
    "/api/v1/export/finance",  # multi-format export (JSON/CSV)
    "/api/v1/media/{attachment_id}/download",  # file response
    "/api/v1/admin/audit/verify",  # internal audit integrity check
    "/api/v1/admin/unlock-account/{user_id}",  # internal admin action
    "/api/v1/empire-digital/leads/export",  # file/streaming export
    "/api/v1/ops/api-usage",  # analytics aggregation dict
    "/api/v1/ops/team-activity",  # activity feed aggregation dict
    "/api/v1/contacts/{contact_id}/merge-history",  # merge history list
    "/api/v1/contacts/{contact_id}/unmerge",  # unmerge action
    "/api/v1/notifications/live",  # SSE stream
    "/api/v1/campaigns/{campaign_id}/summary",  # campaign analytics dict
    "/api/v1/tasks/templates/generate",  # recurring task generation result
    "/api/v1/bulk/import/deals",  # bulk import result dict
    "/api/v1/dashboard/layout",  # widget layout dict (GET)
    "/api/v1/tasks/prioritized",  # scored task list
    "/api/v1/scoring-rules/score/{contact_id}",  # scoring result dict
    "/api/v1/deals/forecast/pipeline",  # pipeline forecast dict
    "/api/v1/deals/forecast/win-rates",  # win rate trends dict
    "/api/v1/campaigns/{campaign_id}/events",  # event creation result
    "/api/v1/campaigns/{campaign_id}/analytics",  # campaign analytics dict
    "/api/v1/notification-rules/evaluate",  # rule evaluation result
    "/api/v1/workspace-perms",  # workspace list dict
    "/api/v1/workspace-perms/my",  # user workspaces dict
    "/api/v1/workspace-perms/{workspace_id}/members",  # member list dict
    "/api/v1/workspace-perms/{workspace_id}/check-access/{user_id}",  # access check dict
    "/api/v1/activity/timeline",  # activity feed dict
    "/api/v1/custom-fields/values",  # set field value result
    "/api/v1/custom-fields/values/{entity_type}/{entity_id}",  # field values list
    "/api/v1/email-templates/{template_id}/render",  # rendered template dict
    "/api/v1/deals/requirements/{req_id}/check/{deal_id}",  # check result dict
    "/api/v1/deals/requirements/checklist/{deal_id}/{stage}",  # checklist dict
    "/api/v1/deals/requirements/validate/{deal_id}/{stage}",  # validation dict
    "/api/v1/contact-segments/{segment_id}/evaluate",  # segment evaluation dict
    "/api/v1/outbound-webhooks/test-match",  # webhook match test dict
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
