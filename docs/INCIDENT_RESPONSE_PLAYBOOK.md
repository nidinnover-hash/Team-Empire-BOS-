# Incident Response Playbook

## Severity levels
- `SEV-1`: Full outage, data corruption risk, cross-tenant data exposure.
- `SEV-2`: Major feature degraded, no known data leak.
- `SEV-3`: Partial degradation with workaround.

## First 15 minutes
1. Acknowledge incident and assign an incident commander.
2. Set status channel and open incident timeline doc.
3. Capture:
   - first alert time
   - impacted endpoints/orgs
   - current deploy SHA
4. Apply immediate safety controls if needed:
   - set rollout kill switch
   - disable auto-approval if trust boundary is unclear
   - pause schedulers for failing integration loops

## Containment actions
1. Validate tenant isolation first for any auth/data incident.
2. Roll back to previous known-good release when impact is broad.
3. Rotate affected credentials if token compromise is possible.
4. Snapshot logs and audit events for forensics.

## Communication
1. Internal update every 15 minutes for `SEV-1`, every 30 minutes for `SEV-2`.
2. Customer update includes:
   - scope
   - mitigation status
   - next update time
3. Do not share raw stack traces or provider secrets.

## Recovery and verification
1. Confirm `/health` and critical endpoints recovered.
2. Confirm pending approval queue and execution idempotency are healthy.
3. Confirm backup jobs and sync scheduler resume cleanly.
4. Close incident only after 30 minutes stable metrics.

## Postmortem (within 48 hours)
1. Timeline with UTC timestamps.
2. Root cause and trigger.
3. Why controls failed or were missing.
4. Corrective actions with owners and due dates.
