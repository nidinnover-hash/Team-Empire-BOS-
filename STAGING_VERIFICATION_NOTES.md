# BOS Staging Verification Notes

**Deploy date**: _______________
**Commit SHA**: _______________
**Deployed by**: _______________

---

## 1. MIGRATION VERIFICATION

### alembic_version
```sql
-- PASTE: psql output of SELECT version_num FROM alembic_version
```

### New tables (batch 17-20)
```sql
-- PASTE: psql output of Phase 3.2 query
```

### CRM tables (migration 0086)
```sql
-- PASTE: psql output of Phase 3.3 query
```

### Foreign key integrity
```sql
-- PASTE: psql output of Phase 3.4 query
```

---

## 2. TENANT ISOLATION (B1)

### Create bundle
```json

```

### Add item
```json

```

### List items (own org)
```json

```

**PASS / FAIL**: ___

---

## 3. QUOTE APPROVAL PENDING GUARD

### Create quote + request approval
```json

```

### First decide (approve)
```json

```

### Second decide (should be 404)
```
HTTP status: ___
```

**PASS / FAIL**: ___

---

## 4. FORECAST ROLLUP UPSERT

### First upsert
```json

```

### Second upsert (same natural key)
```json

```

### IDs match?
```
ID1: ___  ID2: ___  Match: YES / NO
```

**PASS / FAIL**: ___

---

## 5. CONVERSION FUNNEL UPSERT

### First upsert
```json

```

### Second upsert (same natural key)
```json

```

### IDs match?
```
ID1: ___  ID2: ___  Match: YES / NO
```

**PASS / FAIL**: ___

---

## 6. AUTOMATION TEMPLATES ENDPOINT

### GET /automations/templates
```
HTTP status: ___
```

**PASS / FAIL**: ___

---

## 7. PROTECTED FIELD IMMUTABILITY

### Create quote
```json

```

### Update with protected fields
```json

```

### Verification
```
org_id unchanged: ___
id unchanged: ___
title changed to "Updated Title": ___
```

**PASS / FAIL**: ___

---

## 8. AUDIT MIDDLEWARE (B3)

### Call log creation
```json

```

### Audit entry for call_log_created
```sql

```

**PASS / FAIL**: ___

---

## 9. AUDIT DUPLICATION CHECK

### Recent audit events
```sql

```

### Duplicate detector (should be 0 rows)
```sql

```

### Quote-specific duplicate check (should be 0 rows)
```sql

```

**PASS / FAIL**: ___

---

## 10. MIDDLEWARE COVERAGE

### New endpoint audit events present
```sql

```

**PASS / FAIL**: ___

---

## 11. LOG MONITORING

### Middleware errors (should be 0)
```
grep count: ___
```

### Schema errors (should be 0)
```
grep count: ___
```

### Latency spikes (should be 0)
```

```

**PASS / FAIL**: ___

---

## 12. SERVICE HEALTH

### Health endpoint
```json

```

### systemctl status
```

```

---

## SUMMARY

| # | Check | Result |
|---|-------|--------|
| 1 | Migration to 0087 | |
| 2 | 25+ new tables exist | |
| 3 | Tenant isolation (B1) | |
| 4 | Pending guard | |
| 5 | Forecast upsert idempotency | |
| 6 | Conversion upsert idempotency | |
| 7 | Automation templates 200 | |
| 8 | Protected field immutability | |
| 9 | Audit middleware creates rows (B3) | |
| 10 | Zero duplicate audit entries | |
| 11 | Zero middleware errors | |
| 12 | Zero schema errors | |
| 13 | Service healthy | |

**Overall staging verdict**: PASS / FAIL

**Ready for production**: YES / NO

**Blocker notes** (if any):
```

```

**Signed off by**: _______________
**Date**: _______________
