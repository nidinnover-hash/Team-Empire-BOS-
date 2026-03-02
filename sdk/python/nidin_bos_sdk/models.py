from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

# Generated from sdk/openapi/openapi.json by scripts/generate_sdk_models.py

class ApiKeyCreate(TypedDict):
    name: str
    scopes: NotRequired[str]
    expires_in_days: NotRequired[int | None]

class ApiKeyCreateResponse(TypedDict):
    id: int
    name: str
    key: str
    key_prefix: str
    scopes: str
    expires_at: str | None
    created_at: str

class ApiKeyListResponse(TypedDict):
    count: int
    items: list[ApiKeyRead]

class ApiKeyRead(TypedDict):
    id: int
    name: str
    key_prefix: str
    scopes: str
    is_active: bool
    expires_at: str | None
    last_used_at: str | None
    created_at: str

class ApprovalDecision(TypedDict):
    note: NotRequired[str | None]

class ApprovalPatternRead(TypedDict):
    id: int
    approval_type: str
    sample_payload: NotRequired[dict[str, Any]]
    approved_count: NotRequired[int]
    rejected_count: NotRequired[int]
    reject_count: NotRequired[int]
    is_auto_approve_enabled: NotRequired[bool]
    auto_approve_threshold: NotRequired[float]
    confidence_score: NotRequired[float]

class ApprovalPatternUpdate(TypedDict):
    is_auto_approve_enabled: NotRequired[bool | None]
    auto_approve_threshold: NotRequired[float | None]

class ApprovalRead(TypedDict):
    id: int
    organization_id: int
    requested_by: int
    approval_type: str
    payload_json: dict[str, Any]
    status: str
    approved_by: int | None
    approved_at: str | None
    auto_approved_at: NotRequired[str | None]
    confidence_score: NotRequired[float | None]
    executed_at: NotRequired[str | None]
    expires_at: NotRequired[str | None]
    created_at: str

class ApprovalRequestCreate(TypedDict):
    organization_id: int
    approval_type: str
    payload_json: NotRequired[dict[str, Any]]

class ApprovalTimelineItem(TypedDict):
    id: int
    approval_type: str
    status: str
    requested_by: int
    approved_by: int | None
    created_at: str
    approved_at: str | None
    is_risky: bool
    requires_yes_execute: bool

class ApprovalTimelineResponse(TypedDict):
    pending_count: int
    approved_count: int
    rejected_count: int
    items: list[ApprovalTimelineItem]

class FeatureFlagValue(TypedDict):
    enabled: NotRequired[bool]
    rollout_percentage: NotRequired[int]

class HTTPValidationError(TypedDict):
    detail: NotRequired[list[ValidationError]]

class OrganizationCreate(TypedDict):
    name: str
    slug: str
    parent_organization_id: NotRequired[int | None]
    country_code: NotRequired[str | None]
    branch_label: NotRequired[str | None]

class OrganizationFeatureFlagsRead(TypedDict):
    config_version: int
    flags: dict[str, FeatureFlagValue]

class OrganizationFeatureFlagsUpdate(TypedDict):
    expected_config_version: NotRequired[int | None]
    flags: dict[str, FeatureFlagValue]

class OrganizationMembershipCreate(TypedDict):
    user_id: int
    role: NotRequired[Literal['OWNER', 'ADMIN', 'TECH_LEAD', 'OPS_MANAGER', 'DEVELOPER', 'MANAGER', 'STAFF', 'VIEWER']]

class OrganizationMembershipRead(TypedDict):
    id: int
    organization_id: int
    user_id: int
    role: str
    is_active: bool
    created_at: str
    updated_at: str

class OrganizationRead(TypedDict):
    id: int
    parent_organization_id: int | None
    name: str
    slug: str
    country_code: str | None
    branch_label: str | None
    config_version: int
    created_at: str
    updated_at: str

class OrganizationUpdate(TypedDict):
    name: NotRequired[str | None]
    slug: NotRequired[str | None]
    parent_organization_id: NotRequired[int | None]
    country_code: NotRequired[str | None]
    branch_label: NotRequired[str | None]
    expected_config_version: NotRequired[int | None]

class TaskCreate(TypedDict):
    title: str
    description: NotRequired[str | None]
    priority: NotRequired[int]
    category: NotRequired[Literal['personal', 'business', 'health', 'finance', 'other']]
    project_id: NotRequired[int | None]
    due_date: NotRequired[str | None]
    depends_on_task_id: NotRequired[int | None]

class TaskRead(TypedDict):
    id: int
    title: str
    description: str | None
    priority: int
    category: str
    project_id: int | None
    due_date: str | None
    depends_on_task_id: NotRequired[int | None]
    is_done: bool
    created_at: str
    completed_at: str | None

class TaskUpdate(TypedDict):
    is_done: NotRequired[bool | None]
    title: NotRequired[str | None]
    description: NotRequired[str | None]
    priority: NotRequired[int | None]
    category: NotRequired[Literal['personal', 'business', 'health', 'finance', 'other'] | None]
    project_id: NotRequired[int | None]
    due_date: NotRequired[str | None]

class TriggerCreate(TypedDict):
    name: str
    description: NotRequired[str | None]
    source_event: str
    source_integration: NotRequired[str | None]
    filter_json: NotRequired[dict[str, Any]]
    action_type: str
    action_integration: NotRequired[str | None]
    action_params: NotRequired[dict[str, Any]]
    requires_approval: NotRequired[bool]

class TriggerRead(TypedDict):
    id: int
    organization_id: int
    name: str
    description: str | None
    source_event: str
    source_integration: str | None
    filter_json: dict[str, Any]
    action_type: str
    action_integration: str | None
    action_params: dict[str, Any]
    is_active: bool
    requires_approval: bool
    fire_count: int
    last_fired_at: str | None
    created_at: str

class TriggerUpdate(TypedDict):
    name: NotRequired[str | None]
    description: NotRequired[str | None]
    is_active: NotRequired[bool | None]
    filter_json: NotRequired[dict[str, Any] | None]
    action_params: NotRequired[dict[str, Any] | None]
    requires_approval: NotRequired[bool | None]

class UserMeRead(TypedDict):
    id: int
    email: str
    role: str
    org_id: int

class ValidationError(TypedDict):
    loc: list[str | int]
    msg: str
    type: str

class WebhookDeliveryListResponse(TypedDict):
    count: int
    items: list[WebhookDeliveryRead]

class WebhookDeliveryRead(TypedDict):
    id: int
    event: str
    payload_json: dict[str, Any]
    status: str
    response_status_code: int | None
    error_message: str | None
    error_category: NotRequired[str | None]
    duration_ms: int | None
    attempt_count: int
    max_retries: NotRequired[int]
    next_retry_at: NotRequired[str | None]
    created_at: str

class WebhookEndpointCreate(TypedDict):
    url: str
    description: NotRequired[str | None]
    event_types: NotRequired[list[str]]
    max_retry_attempts: NotRequired[int]

class WebhookEndpointCreateResponse(TypedDict):
    id: int
    url: str
    description: str | None
    event_types: list[str]
    is_active: bool
    signing_secret: str
    created_at: str
    updated_at: str

class WebhookEndpointRead(TypedDict):
    id: int
    url: str
    description: str | None
    event_types: list[str]
    is_active: bool
    max_retry_attempts: NotRequired[int]
    created_at: str
    updated_at: str

class WebhookEndpointUpdate(TypedDict):
    url: NotRequired[str | None]
    description: NotRequired[str | None]
    event_types: NotRequired[list[str] | None]
    is_active: NotRequired[bool | None]

class WebhookReplayResponse(TypedDict):
    ok: bool
    replayed_delivery_id: NotRequired[int | None]
    error: NotRequired[str | None]

class WebhookTestResponse(TypedDict):
    ok: bool
    status_code: NotRequired[int | None]
    error: NotRequired[str | None]
    duration_ms: NotRequired[int | None]

class WorkflowCreate(TypedDict):
    name: str
    description: NotRequired[str | None]
    steps: list[WorkflowStepDef]

class WorkflowRead(TypedDict):
    id: int
    organization_id: int
    name: str
    description: str | None
    steps_json: list[Any]
    status: str
    current_step: int
    result_json: dict[str, Any]
    error_text: str | None
    created_by: int | None
    started_at: str | None
    finished_at: str | None
    created_at: str

class WorkflowStepDef(TypedDict):
    name: str
    action_type: str
    integration: NotRequired[str | None]
    params: NotRequired[dict[str, Any]]
    requires_approval: NotRequired[bool]

WebhookEndpointListResponse = list[WebhookEndpointRead]
