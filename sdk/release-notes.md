# SDK Release 0.7.0

- Tag: `sdk-v0.7.0`
- Date: `2026-03-02`
- Commit: `6cae7aec46abc1ddd6c71ce4441bcfe1142f0e4a`
- OpenAPI paths: `362`
- OpenAPI operations: `410`

## Highlights
- Added tested PR checklist rule engine (`scripts/pr_checklist_guard.py`) and wired PR workflow to use it.
- Added SDK release notes validation (`scripts/check_sdk_release_notes.py`) to fail release on empty/placeholder notes.
- Added mutating-operation allowlist in SDK client generator to reduce accidental surface expansion risk.
- Expanded SDK generation coverage tests to include mutating operations.
- Extended `dev_gate` with PR checklist guard tests.

