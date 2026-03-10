# BOS Staging Deployment Runbook

**Date**: 2026-03-11
**Branch**: `main`
**Scope**: Blocker fixes (B1 IDOR, B2 migrations, B3 audit middleware) + adjacent fixes
**Server**: `/opt/nidin-bos` via `deploy` user, systemd `nidin-bos` service

---

## Phase 1 — Pre-Deploy Safety

### 1.1 Commit all working tree changes (run on dev machine)

```bash
cd /d/Personal\ Clone

# Verify what will be committed
git status
git diff --stat HEAD

# Stage all changes
git add \
  alembic/env.py \
  alembic/versions/20260310_0086_add_crm_quote_playbook_survey_tables.py \
  alembic/versions/20260310_0087_add_batch_17_18_19_20_tables.py \
  app/api/v1/endpoints/automation_definitions.py \
  app/api/v1/endpoints/playbooks.py \
  app/api/v1/endpoints/product_bundles.py \
  app/api/v1/endpoints/quotes.py \
  app/api/v1/endpoints/surveys.py \
  app/application/automation/bootstrap.py \
  app/application/crm/__init__.py \
  app/application/crm/bootstrap.py \
  app/core/audit_middleware.py \
  app/core/config.py \
  app/main.py \
  app/services/conversion_funnel.py \
  app/services/deal_split.py \
  app/services/feature_flags.py \
  app/services/forecast_rollup.py \
  app/services/product_bundle.py \
  app/services/quote.py \
  app/services/quote_approval.py \
  app/services/sales_playbook.py \
  app/services/survey.py \
  tests/test_alembic_batch17_20.py \
  tests/test_automation_definitions_guards.py \
  tests/test_batch15_20_audit_contract.py \
  tests/test_batch16_features.py \
  tests/test_crm_feature_flags_and_audit.py \
  tests/test_feature_flags_service.py \
  tests/test_production_safety.py \
  tests/test_protected_field_overwrite_guards.py \
  tests/test_quote_approval_state_guard.py \
  tests/test_upsert_idempotency_batch19.py

# Commit
git commit -m "$(cat <<'EOF'
fix: staging blockers — IDOR tenant isolation, migration chain, centralized audit middleware

B1: product_bundle.list_items now requires org_id, verifies bundle ownership
B2: migration 0086 (CRM tables) + 0087 (35 batch 17-20 tables) with proper FK ordering
B3: MutationAuditMiddleware auto-audits all /api/v1/ mutations, skip list for 41 explicit-audit endpoints

Adjacent: upsert idempotency (forecast_rollup, conversion_funnel), quote_approval pending guard,
protected field guards (quote, bundle, split), automation_definitions db/await regression fix,
feature flags for quotes/playbooks/surveys

Tests: 48 blocker verification tests across 6 new test files
Full suite: 1718 passed, 1 pre-existing flaky, 5 skipped

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

### 1.2 Record the commit SHA

```bash
DEPLOY_SHA=$(git rev-parse HEAD)
echo "Deploying: $DEPLOY_SHA"
```

### 1.3 Push to remote

```bash
git push origin main
```

### 1.4 Verify migration files exist in the commit

```bash
git show --stat HEAD | grep -E "0086|0087"
# Expected: both migration files listed
```

---

## Phase 2 — Deploy to Staging

### 2.1 SSH into staging server

```bash
ssh deploy@<STAGING_HOST>
```

### 2.2 Dry-run deploy (validates prerequisites without changing anything)

```bash
sudo bash /opt/nidin-bos/deploy/deploy.sh --dry-run /opt/nidin-bos nidin-bos /opt/nidin-bos/.env
```

### 2.3 Set feature flags in staging .env

```bash
# Edit the staging .env file
sudo -u deploy nano /opt/nidin-bos/.env

# Add/update these lines:
# FEATURE_QUOTES=true
# FEATURE_PLAYBOOKS=true
# FEATURE_SURVEYS=true
```

### 2.4 Run full deploy (pull, pip install, preflight, backup, migrate, reload, health check)

```bash
sudo bash /opt/nidin-bos/deploy/deploy.sh --require-backup /opt/nidin-bos nidin-bos /opt/nidin-bos/.env
```

The deploy script will:
1. `git pull --ff-only origin main`
2. `pip install -r requirements.txt`
3. Run `scripts/preflight_deploy.py`
4. `pg_dump` pre-migration backup to `/opt/nidin-bos/Data/backups/`
5. `alembic upgrade head` (runs both 0086 and 0087)
6. `systemctl reload nidin-bos` + restart scheduler
7. Health check with retries
8. Auto-rollback on failure

### 2.5 Verify deploy completed

```bash
# Check service status
sudo systemctl status nidin-bos
sudo systemctl status nidin-bos-scheduler

# Check which commit is deployed
cd /opt/nidin-bos && git rev-parse HEAD
```

---

## Phase 3 — Migration Verification

### 3.1 Confirm alembic_version

```bash
cd /opt/nidin-bos
source venv/bin/activate
source .env

psql "$DATABASE_URL" -c "SELECT version_num FROM alembic_version;"
```

**Expected**: `20260310_0087`

### 3.2 Verify new tables exist (batch 17-20 sample)

```bash
psql "$DATABASE_URL" -c "
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN (
  'product_bundles', 'bundle_items', 'forecast_rollups',
  'conversion_funnels', 'deal_splits', 'quote_approvals',
  'call_logs', 'drip_step_events', 'contact_merge_logs',
  'customer_health_scores', 'stage_gates', 'activity_goals',
  'subscriptions', 'drip_campaigns', 'lead_score_rules',
  'audit_entries', 'win_loss_records'
)
ORDER BY table_name;
"
```

**Expected**: 17 rows

### 3.3 Verify CRM tables from migration 0086

```bash
psql "$DATABASE_URL" -c "
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN (
  'quotes', 'quote_line_items', 'sales_playbooks',
  'playbook_steps', 'surveys', 'survey_questions',
  'survey_responses', 'survey_response_answers'
)
ORDER BY table_name;
"
```

**Expected**: 8 rows

### 3.4 Verify schema integrity — foreign keys

```bash
psql "$DATABASE_URL" -c "
SELECT tc.table_name, tc.constraint_name, ccu.table_name AS references_table
FROM information_schema.table_constraints tc
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
AND tc.table_name IN ('bundle_items', 'quote_approvals', 'stage_gate_overrides', 'drip_steps')
ORDER BY tc.table_name;
"
```

---

## Phase 4 — Smoke Tests

Set up variables first:

```bash
# Get a bearer token (adjust credentials as needed)
HOST="http://127.0.0.1:8000"

TOKEN=$(curl -s -X POST "$HOST/web/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"nidinnover@gmail.com","password":"'$ADMIN_PASSWORD'"}' \
  -c - | grep pc_session | awk '{print $NF}')

# Or use the API token endpoint
API_TOKEN=$(curl -s "$HOST/web/api-token" \
  -H "Cookie: pc_session=$TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

AUTH="Authorization: Bearer $API_TOKEN"

echo "Token obtained: ${API_TOKEN:0:20}..."
```

### 4.1 Tenant Isolation — Product Bundle Items (B1)

```bash
# Create a bundle
BUNDLE=$(curl -s -X POST "$HOST/api/v1/product-bundles" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Smoke Test Bundle","bundle_price":99.99}')
echo "Create bundle: $BUNDLE"
BUNDLE_ID=$(echo "$BUNDLE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Add an item
ITEM=$(curl -s -X POST "$HOST/api/v1/product-bundles/$BUNDLE_ID/items" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"product_id":1,"quantity":2,"unit_price":49.99}')
echo "Add item: $ITEM"

# List items (should return the item)
LIST=$(curl -s "$HOST/api/v1/product-bundles/$BUNDLE_ID/items" -H "$AUTH")
echo "List items (own org): $LIST"
# PASS if: returns array with 1 item
```

### 4.2 Quote Approval Pending Guard

```bash
# Create a quote first
QUOTE=$(curl -s -X POST "$HOST/api/v1/quotes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Smoke Test Quote"}')
echo "Create quote: $QUOTE"
QUOTE_ID=$(echo "$QUOTE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Request approval
APPROVAL=$(curl -s -X POST "$HOST/api/v1/quotes/$QUOTE_ID/approvals" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"approver_user_id":1,"level":1}')
echo "Request approval: $APPROVAL"
APPROVAL_ID=$(echo "$APPROVAL" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# First decide: approve (should succeed)
DECIDE1=$(curl -s -X PUT "$HOST/api/v1/quotes/approvals/$APPROVAL_ID/decide" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"status":"approved","reason":"Smoke test"}')
echo "First decide (approve): $DECIDE1"
# PASS if: status 200, status="approved"

# Second decide: try to reject same approval (should fail — 404)
DECIDE2=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$HOST/api/v1/quotes/approvals/$APPROVAL_ID/decide" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"status":"rejected","reason":"Too late"}')
echo "Second decide (should be 404): HTTP $DECIDE2"
# PASS if: HTTP 404
```

### 4.3 Forecast Rollup Upsert Idempotency

```bash
# First upsert
R1=$(curl -s -X POST "$HOST/api/v1/forecast-rollups" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"period":"2026-Q1","group_by":"team","group_value":"sales-a","committed":100000,"best_case":150000,"pipeline":200000,"closed_won":50000,"target":120000}')
echo "First upsert: $R1"
ID1=$(echo "$R1" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Second upsert (same natural key, different values)
R2=$(curl -s -X POST "$HOST/api/v1/forecast-rollups" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"period":"2026-Q1","group_by":"team","group_value":"sales-a","committed":110000,"best_case":160000,"pipeline":210000,"closed_won":60000,"target":120000}')
echo "Second upsert: $R2"
ID2=$(echo "$R2" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "IDs match (should be same): $ID1 == $ID2"
# PASS if: ID1 == ID2, committed updated to 110000
```

### 4.4 Conversion Funnel Upsert Idempotency

```bash
# First upsert
F1=$(curl -s -X POST "$HOST/api/v1/conversion-funnels" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"period":"2026-Q1","from_stage":"lead","to_stage":"qualified","entered":100,"converted":40}')
echo "First upsert: $F1"
FID1=$(echo "$F1" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Second upsert (same natural key)
F2=$(curl -s -X POST "$HOST/api/v1/conversion-funnels" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"period":"2026-Q1","from_stage":"lead","to_stage":"qualified","entered":120,"converted":50}')
echo "Second upsert: $F2"
FID2=$(echo "$F2" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "IDs match (should be same): $FID1 == $FID2"
# PASS if: FID1 == FID2, entered updated to 120
```

### 4.5 Automation Templates Endpoint

```bash
# GET templates (should return 200, not 500)
TEMPLATES=$(curl -s -o /dev/null -w "%{http_code}" "$HOST/api/v1/automations/templates" -H "$AUTH")
echo "GET /automations/templates: HTTP $TEMPLATES"
# PASS if: HTTP 200
```

### 4.6 Protected Field Immutability

```bash
# Create a quote
PQ=$(curl -s -X POST "$HOST/api/v1/quotes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Protected Field Test"}')
echo "Create: $PQ"
PQ_ID=$(echo "$PQ" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
PQ_ORG=$(echo "$PQ" | python3 -c "import sys,json; print(json.load(sys.stdin)['organization_id'])")

# Try to overwrite protected fields
PQ_UPD=$(curl -s -X PUT "$HOST/api/v1/quotes/$PQ_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Updated Title","organization_id":999,"created_by_user_id":999,"id":9999}')
echo "Update with protected fields: $PQ_UPD"
UPD_ORG=$(echo "$PQ_UPD" | python3 -c "import sys,json; print(json.load(sys.stdin)['organization_id'])")
UPD_ID=$(echo "$PQ_UPD" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
UPD_TITLE=$(echo "$PQ_UPD" | python3 -c "import sys,json; print(json.load(sys.stdin)['title'])")

echo "org_id unchanged: $PQ_ORG == $UPD_ORG"
echo "id unchanged: $PQ_ID == $UPD_ID"
echo "title changed: $UPD_TITLE"
# PASS if: org_id unchanged, id unchanged, title = "Updated Title"
```

### 4.7 Audit Middleware Logging

```bash
# Create a call log (new endpoint, no explicit audit — middleware should cover)
CLOG=$(curl -s -X POST "$HOST/api/v1/call-logs" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"contact_id":1,"direction":"outbound","duration_seconds":120,"outcome":"connected","notes":"Smoke test call"}')
echo "Create call log: $CLOG"
# PASS if: HTTP 201

# Check audit_entries for the middleware-generated event
sleep 2
psql "$DATABASE_URL" -c "
SELECT id, event_type, entity_type, created_at
FROM audit_entries
WHERE event_type = 'call_log_created'
ORDER BY created_at DESC LIMIT 3;
"
# PASS if: at least 1 row with event_type='call_log_created'
```

---

## Phase 5 — Audit Verification

### 5.1 Audit rows created by middleware

```bash
psql "$DATABASE_URL" -c "
SELECT event_type, count(*) AS cnt
FROM audit_entries
WHERE created_at > now() - interval '1 hour'
GROUP BY event_type
ORDER BY cnt DESC
LIMIT 20;
"
```

### 5.2 Duplicate audit detection

```bash
psql "$DATABASE_URL" -c "
SELECT
  event_type,
  (payload_json->>'path') AS path,
  (payload_json->>'method') AS method,
  actor_user_id,
  created_at,
  count(*) OVER (
    PARTITION BY event_type, entity_id, actor_user_id,
    date_trunc('second', created_at)
  ) AS dupes_in_same_second
FROM audit_entries
WHERE created_at > now() - interval '1 hour'
ORDER BY created_at DESC
LIMIT 30;
"
```

If any row shows `dupes_in_same_second > 1`, there is a duplicate audit issue.

### 5.3 Focused duplicate check (quotes — has explicit audit + middleware skip)

```bash
psql "$DATABASE_URL" -c "
SELECT event_type, entity_id, actor_user_id,
       date_trunc('second', created_at) AS ts,
       count(*) AS cnt
FROM audit_entries
WHERE event_type LIKE 'quote%'
AND created_at > now() - interval '1 hour'
GROUP BY event_type, entity_id, actor_user_id, date_trunc('second', created_at)
HAVING count(*) > 1;
"
```

**Expected**: 0 rows (no duplicates — `/api/v1/quotes` is in `_SKIP_PREFIXES`)

### 5.4 Middleware coverage for new endpoints (should have audit rows)

```bash
psql "$DATABASE_URL" -c "
SELECT DISTINCT event_type
FROM audit_entries
WHERE event_type IN (
  'call_log_created',
  'forecast_rollup_created', 'forecast_rollup_updated',
  'conversion_funnel_created', 'conversion_funnel_updated',
  'product_bundle_created', 'deal_split_created'
)
ORDER BY event_type;
"
```

**Expected**: Events present for any endpoints you smoke-tested above

---

## Phase 6 — Monitoring During Staging

### 6.1 Watch application logs live

```bash
sudo journalctl -u nidin-bos -f --since "now"
```

### 6.2 Detect middleware errors

```bash
sudo journalctl -u nidin-bos --since "1 hour ago" | grep -i "Mutation audit failed"
```

**Expected**: 0 occurrences. Any matches indicate middleware error (JWT decode failure, DB issue).

### 6.3 Detect schema issues

```bash
sudo journalctl -u nidin-bos --since "1 hour ago" | grep -iE "relation.*does not exist|column.*does not exist|UndefinedTable|ProgrammingError"
```

**Expected**: 0 occurrences.

### 6.4 Detect latency spikes (if access logs enabled)

```bash
# Check Gunicorn access log for slow requests (>2s)
sudo journalctl -u nidin-bos --since "1 hour ago" | grep -oP 'request_time=\K[0-9.]+' | awk '$1 > 2.0 {print "SLOW: "$1"s"}'
```

### 6.5 Check service health periodically

```bash
# Quick health check
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

---

## Phase 7 — Evidence Collection

Paste results into `STAGING_VERIFICATION_NOTES.md`. Template follows.

---

## Phase 8 — Production Gate Preparation

### Evidence required for Codex production decision:

| # | Evidence | Source |
|---|----------|--------|
| 1 | Commit SHA deployed | `git rev-parse HEAD` on staging |
| 2 | `alembic_version` = `20260310_0087` | Phase 3.1 SQL output |
| 3 | Table count (25+ new tables exist) | Phase 3.2 + 3.3 SQL output |
| 4 | Tenant isolation PASS | Phase 4.1 curl output |
| 5 | Pending guard PASS (404 on re-decide) | Phase 4.2 curl output |
| 6 | Upsert idempotency PASS (IDs match) | Phase 4.3 + 4.4 curl output |
| 7 | Automation templates 200 | Phase 4.5 curl output |
| 8 | Protected fields unchanged | Phase 4.6 curl output |
| 9 | Audit row created by middleware | Phase 4.7 SQL output |
| 10 | Zero duplicate audit rows | Phase 5.2 + 5.3 SQL output |
| 11 | Zero middleware errors in logs | Phase 6.2 grep output |
| 12 | Zero schema errors in logs | Phase 6.3 grep output |
| 13 | 24h soak — no regressions | Monitoring over time |
| 14 | Full test suite: 1718 passed | CI or local run output |

### Before promoting to production:

1. All 14 evidence items above collected and pasted into `STAGING_VERIFICATION_NOTES.md`
2. 24-hour staging soak with no new errors
3. Alembic multiple heads at `0074`/`0076` merged (non-blocking but cleaner): `alembic merge 0074 0076 -m "merge heads"`
4. Feature flags confirmed in production `.env`: `FEATURE_QUOTES=true`, `FEATURE_PLAYBOOKS=true`, `FEATURE_SURVEYS=true`
5. Pre-migration backup plan confirmed for production DB
6. Codex review of this evidence file — approval required before `deploy.sh` runs on production
