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


async def test_openapi_operation_ids_are_stable_and_unique(client) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()

    operation_ids: list[str] = []
    for path_item in data.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}:
                continue
            assert isinstance(operation, dict)
            operation_id = operation.get("operationId")
            assert isinstance(operation_id, str)
            operation_ids.append(operation_id)

    assert len(operation_ids) == len(set(operation_ids))
    paths = data["paths"]
    assert paths["/api/v1/health"]["get"]["operationId"] == "get_api_v1_health"
    assert paths["/health"]["get"]["operationId"] == "get_health"
