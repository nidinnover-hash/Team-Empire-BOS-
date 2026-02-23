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
