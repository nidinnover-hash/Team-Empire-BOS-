"""Official signal topics for the BOS runtime."""

# --- Approval lifecycle ---
APPROVAL_REQUESTED = "approval.requested"
APPROVAL_APPROVED = "approval.approved"
APPROVAL_REJECTED = "approval.rejected"

# --- Execution lifecycle ---
EXECUTION_STARTED = "execution.started"
EXECUTION_COMPLETED = "execution.completed"
EXECUTION_FAILED = "execution.failed"

# --- Webhooks ---
WEBHOOK_DELIVERY_SUCCEEDED = "webhook.delivery.succeeded"
WEBHOOK_DELIVERY_FAILED = "webhook.delivery.failed"

# --- Scheduler ---
SCHEDULER_JOB_COMPLETED = "scheduler.job.completed"
SCHEDULER_JOB_FAILED = "scheduler.job.failed"

# --- AI ---
AI_CALL_COMPLETED = "ai.call.completed"
AI_CALL_FAILED = "ai.call.failed"

# --- CRM / Contacts ---
CONTACT_CREATED = "contact.created"
CONTACT_UPDATED = "contact.updated"
CONTACT_DELETED = "contact.deleted"
CONTACT_ROUTED = "contact.routed"

# --- CRM / Quotes ---
QUOTE_CREATED = "quote.created"
QUOTE_UPDATED = "quote.updated"
QUOTE_LINE_ITEM_ADDED = "quote.line_item.added"
QUOTE_LINE_ITEM_REMOVED = "quote.line_item.removed"

# --- CRM / Sales Playbooks ---
PLAYBOOK_CREATED = "playbook.created"
PLAYBOOK_UPDATED = "playbook.updated"
PLAYBOOK_STEP_EXECUTED = "playbook.step.executed"

# --- CRM / Surveys ---
SURVEY_DEFINITION_CREATED = "survey.definition.created"
SURVEY_RESPONSE_SUBMITTED = "survey.response.submitted"

# --- Finance ---
FINANCE_INVOICE_CREATED = "finance.invoice.created"
FINANCE_PAYMENT_RECEIVED = "finance.payment.received"
FINANCE_EXPENSE_RECORDED = "finance.expense.recorded"

# --- Integrations ---
INTEGRATION_CONNECTED = "integration.connected"
INTEGRATION_DISCONNECTED = "integration.disconnected"
INTEGRATION_SYNC_COMPLETED = "integration.sync.completed"
INTEGRATION_SYNC_FAILED = "integration.sync.failed"

# --- Memory / Intelligence ---
MEMORY_UPDATED = "memory.updated"
KNOWLEDGE_SAVE_FAILED = "intelligence.knowledge.save_failed"

# --- User / Auth ---
USER_LOGIN = "user.login"
USER_LOGOUT = "user.logout"

# --- Workflow ---
WORKFLOW_DEFINITION_CREATED = "workflow.definition.created"
WORKFLOW_DEFINITION_UPDATED = "workflow.definition.updated"
WORKFLOW_DEFINITION_PUBLISHED = "workflow.definition.published"
WORKFLOW_PLAN_GENERATED = "workflow.plan.generated"
WORKFLOW_RUN_CREATED = "workflow.run.created"
WORKFLOW_RUN_AWAITING_APPROVAL = "workflow.run.awaiting_approval"
WORKFLOW_RUN_STARTED = "workflow.run.started"
WORKFLOW_RUN_COMPLETED = "workflow.run.completed"
WORKFLOW_RUN_FAILED = "workflow.run.failed"
WORKFLOW_STEP_STARTED = "workflow.step.started"
WORKFLOW_STEP_COMPLETED = "workflow.step.completed"
WORKFLOW_STEP_FAILED = "workflow.step.failed"
WORKFLOW_STEP_BLOCKED = "workflow.step.blocked"

# --- SLO ---
SLO_BREACH_DETECTED = "slo.breach.detected"

# --- Anomaly ---
ANOMALY_DETECTED = "anomaly.detected"

# --- Recruitment (EmpireO) ---
RECRUITMENT_PLACEMENT_CONFIRMED = "recruitment.placement.confirmed"

# --- Dead-letter ---
DEAD_LETTER_CAPTURED = "dead_letter.captured"
DEAD_LETTER_RETRIED = "dead_letter.retried"
DEAD_LETTER_RESOLVED = "dead_letter.resolved"
