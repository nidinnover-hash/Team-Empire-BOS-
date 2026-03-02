# API Key Scopes

This project supports API keys passed as `Authorization: Bearer <key>`.

## Scope formats

Accepted scope tokens:

- `*`
- `read`
- `write`
- `<resource>:read`
- `<resource>:write`
- `<resource>:*`
- `api:read`
- `api:write`
- `api:*`

`<resource>` must use lowercase letters, numbers, or underscore.

Examples:

- `webhooks:read`
- `integrations:write`
- `api_keys:*`

## How enforcement works

At request time, the backend derives the required scope from HTTP method and path:

- `GET/HEAD/OPTIONS` => `:read`
- `POST/PUT/PATCH/DELETE` => `:write`
- `/api/v1/webhooks/...` => resource `webhooks`
- `/api/v1/integrations/...` => resource `integrations`
- `/me` => resource `auth`

A key is accepted if any of these matches:

- `*`
- exact resource scope (`webhooks:read`)
- resource wildcard (`webhooks:*`)
- legacy broad scope (`read`/`write`)
- API-wide scope (`api:read`, `api:*`)

## Migration path from legacy scopes

Use `scripts/migrate_api_key_scopes.py`.

### Phase 1 (safe namespace upgrade)

Converts:

- `read` -> `api:read`
- `write` -> `api:write`
- `read,write` -> `api:*`

Run dry-run:

```bash
python3.12 scripts/migrate_api_key_scopes.py --profile phase1
```

Apply:

```bash
python3.12 scripts/migrate_api_key_scopes.py --profile phase1 --apply
```

### Phase 2 (resource-explicit scopes)

Converts broad scopes to full resource-explicit scopes using a resource list.

Run dry-run:

```bash
python3.12 scripts/migrate_api_key_scopes.py --profile phase2
```

Apply:

```bash
python3.12 scripts/migrate_api_key_scopes.py --profile phase2 --apply
```

Limit to one org:

```bash
python3.12 scripts/migrate_api_key_scopes.py --profile phase2 --organization-id 1 --apply
```

Custom resource set:

```bash
python3.12 scripts/migrate_api_key_scopes.py --profile phase2 --resources "webhooks,integrations,api_keys" --apply
```
