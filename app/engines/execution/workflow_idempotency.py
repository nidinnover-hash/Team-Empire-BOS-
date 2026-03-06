def build_workflow_step_idempotency_key(*, workflow_run_id: int, step_index: int, attempt_count: int) -> str:
    return f"workflow-run:{workflow_run_id}:step:{step_index}:attempt:{attempt_count}"
