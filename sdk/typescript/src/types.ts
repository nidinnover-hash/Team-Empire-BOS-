// Generated from sdk/openapi/openapi.json by scripts/generate_sdk_models.py

export interface ApiKeyCreate {
  name: string;
  scopes?: string;
  expires_in_days?: number | null;
}

export interface ApiKeyCreateResponse {
  id: number;
  name: string;
  key: string;
  key_prefix: string;
  scopes: string;
  expires_at: string | null;
  created_at: string;
}

export interface ApiKeyListResponse {
  count: number;
  items: ApiKeyRead[];
}

export interface ApiKeyRead {
  id: number;
  name: string;
  key_prefix: string;
  scopes: string;
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

export interface ApprovalDecision {
  note?: string | null;
}

export interface ApprovalPatternRead {
  id: number;
  approval_type: string;
  sample_payload?: Record<string, unknown>;
  approved_count?: number;
  rejected_count?: number;
  reject_count?: number;
  is_auto_approve_enabled?: boolean;
  auto_approve_threshold?: number;
  confidence_score?: number;
}

export interface ApprovalPatternUpdate {
  is_auto_approve_enabled?: boolean | null;
  auto_approve_threshold?: number | null;
}

export interface ApprovalRead {
  id: number;
  organization_id: number;
  requested_by: number;
  approval_type: string;
  payload_json: Record<string, unknown>;
  status: string;
  approved_by: number | null;
  approved_at: string | null;
  auto_approved_at?: string | null;
  confidence_score?: number | null;
  executed_at?: string | null;
  expires_at?: string | null;
  created_at: string;
}

export interface ApprovalRequestCreate {
  organization_id: number;
  approval_type: string;
  payload_json?: Record<string, unknown>;
}

export interface ApprovalTimelineItem {
  id: number;
  approval_type: string;
  status: string;
  requested_by: number;
  approved_by: number | null;
  created_at: string;
  approved_at: string | null;
  is_risky: boolean;
  requires_yes_execute: boolean;
}

export interface ApprovalTimelineResponse {
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  items: ApprovalTimelineItem[];
}

export interface FeatureFlagValue {
  enabled?: boolean;
  rollout_percentage?: number;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

export interface OrganizationCreate {
  name: string;
  slug: string;
  parent_organization_id?: number | null;
  country_code?: string | null;
  branch_label?: string | null;
}

export interface OrganizationFeatureFlagsRead {
  config_version: number;
  flags: Record<string, FeatureFlagValue>;
}

export interface OrganizationFeatureFlagsUpdate {
  expected_config_version?: number | null;
  flags: Record<string, FeatureFlagValue>;
}

export interface OrganizationMembershipCreate {
  user_id: number;
  role?: "OWNER" | "ADMIN" | "TECH_LEAD" | "OPS_MANAGER" | "DEVELOPER" | "MANAGER" | "STAFF" | "VIEWER";
}

export interface OrganizationMembershipRead {
  id: number;
  organization_id: number;
  user_id: number;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrganizationRead {
  id: number;
  parent_organization_id: number | null;
  name: string;
  slug: string;
  country_code: string | null;
  branch_label: string | null;
  config_version: number;
  created_at: string;
  updated_at: string;
}

export interface OrganizationUpdate {
  name?: string | null;
  slug?: string | null;
  parent_organization_id?: number | null;
  country_code?: string | null;
  branch_label?: string | null;
  expected_config_version?: number | null;
}

export interface TaskCreate {
  title: string;
  description?: string | null;
  priority?: number;
  category?: "personal" | "business" | "health" | "finance" | "other";
  project_id?: number | null;
  due_date?: string | null;
  depends_on_task_id?: number | null;
}

export interface TaskRead {
  id: number;
  title: string;
  description: string | null;
  priority: number;
  category: string;
  project_id: number | null;
  due_date: string | null;
  depends_on_task_id?: number | null;
  is_done: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface TaskUpdate {
  is_done?: boolean | null;
  title?: string | null;
  description?: string | null;
  priority?: number | null;
  category?: "personal" | "business" | "health" | "finance" | "other" | null;
  project_id?: number | null;
  due_date?: string | null;
}

export interface TriggerCreate {
  name: string;
  description?: string | null;
  source_event: string;
  source_integration?: string | null;
  filter_json?: Record<string, unknown>;
  action_type: string;
  action_integration?: string | null;
  action_params?: Record<string, unknown>;
  requires_approval?: boolean;
}

export interface TriggerRead {
  id: number;
  organization_id: number;
  name: string;
  description: string | null;
  source_event: string;
  source_integration: string | null;
  filter_json: Record<string, unknown>;
  action_type: string;
  action_integration: string | null;
  action_params: Record<string, unknown>;
  is_active: boolean;
  requires_approval: boolean;
  fire_count: number;
  last_fired_at: string | null;
  created_at: string;
}

export interface TriggerUpdate {
  name?: string | null;
  description?: string | null;
  is_active?: boolean | null;
  filter_json?: Record<string, unknown> | null;
  action_params?: Record<string, unknown> | null;
  requires_approval?: boolean | null;
}

export interface UserMeRead {
  id: number;
  email: string;
  role: string;
  org_id: number;
}

export interface ValidationError {
  loc: string | number[];
  msg: string;
  type: string;
}

export interface WebhookDeliveryListResponse {
  count: number;
  items: WebhookDeliveryRead[];
}

export interface WebhookDeliveryRead {
  id: number;
  event: string;
  payload_json: Record<string, unknown>;
  status: string;
  response_status_code: number | null;
  error_message: string | null;
  error_category?: string | null;
  duration_ms: number | null;
  attempt_count: number;
  max_retries?: number;
  next_retry_at?: string | null;
  created_at: string;
}

export interface WebhookEndpointCreate {
  url: string;
  description?: string | null;
  event_types?: string[];
  max_retry_attempts?: number;
}

export interface WebhookEndpointCreateResponse {
  id: number;
  url: string;
  description: string | null;
  event_types: string[];
  is_active: boolean;
  signing_secret: string;
  created_at: string;
  updated_at: string;
}

export interface WebhookEndpointRead {
  id: number;
  url: string;
  description: string | null;
  event_types: string[];
  is_active: boolean;
  max_retry_attempts?: number;
  created_at: string;
  updated_at: string;
}

export interface WebhookEndpointUpdate {
  url?: string | null;
  description?: string | null;
  event_types?: string[] | null;
  is_active?: boolean | null;
}

export interface WebhookReplayResponse {
  ok: boolean;
  replayed_delivery_id?: number | null;
  error?: string | null;
}

export interface WebhookTestResponse {
  ok: boolean;
  status_code?: number | null;
  error?: string | null;
  duration_ms?: number | null;
}

export interface WorkflowCreate {
  name: string;
  description?: string | null;
  steps: WorkflowStepDef[];
}

export interface WorkflowRead {
  id: number;
  organization_id: number;
  name: string;
  description: string | null;
  steps_json: unknown[];
  status: string;
  current_step: number;
  result_json: Record<string, unknown>;
  error_text: string | null;
  created_by: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface WorkflowStepDef {
  name: string;
  action_type: string;
  integration?: string | null;
  params?: Record<string, unknown>;
  requires_approval?: boolean;
}

export type WebhookEndpointListResponse = WebhookEndpointRead[];

// ── Agent Chat Models ────────────────────────────────────────────────────────

export interface AgentChatRequest {
  message: string;
  force_role?: string | null;
  avatar_mode?: string | null;
  employee_id?: number | null;
}

export interface ProposedAction {
  action_type: string;
  params?: Record<string, unknown>;
}

export interface AgentChatResponse {
  role: string;
  response: string;
  requires_approval: boolean;
  proposed_actions: ProposedAction[];
  confidence_score: number;
  confidence_level: string;
  confidence_reasons: string[];
  needs_human_review: boolean;
  memory_context_chars: number;
  memory_context_truncated: boolean;
  memory_sources: string[];
  memory_source_counts: Record<string, number>;
  policy_score: number;
  blocked_by_policy: boolean;
  policy_reasons: string[];
  policy_blocked_actions: string[];
  policy_matched_rule_ids: number[];
}

export interface StepResult {
  step_number: number;
  description: string;
  role: string;
  response: string;
  requires_approval: boolean;
  proposed_actions: ProposedAction[];
}

export interface MultiTurnResponse {
  steps: StepResult[];
  final_summary: string;
  total_steps: number;
  steps_requiring_approval: number;
  all_proposed_actions: ProposedAction[];
  confidence_score: number;
  confidence_level: string;
  needs_human_review: boolean;
}
