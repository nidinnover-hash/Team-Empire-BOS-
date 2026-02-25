from __future__ import annotations


async def test_openapi_response_contracts(client) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    paths = data["paths"]

    assert paths["/api/v1/briefing/today"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/DailyBriefingResponse"
    assert paths["/api/v1/briefing/team"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/TeamDashboardResponse"
    assert paths["/api/v1/briefing/executive"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ExecutiveBriefingResponse"
    assert paths["/api/v1/observability/summary"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ObservabilitySummaryRead"
    assert paths["/api/v1/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/HealthCheckResponse"
    assert paths["/api/v1/email/auth-url"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/GmailAuthUrlRead"
    assert paths["/api/v1/email/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/GmailHealthRead"
    assert paths["/api/v1/email/{email_id}/summarize"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/EmailSummaryResponse"
    assert paths["/api/v1/email/{email_id}/draft-reply"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/EmailDraftResponse"
    assert paths["/api/v1/email/{email_id}/send"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/EmailSendResponse"
    assert paths["/api/v1/email/{email_id}/strategize"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/EmailStrategyResponse"
    assert paths["/api/v1/email/compose"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/EmailComposeResponse"
