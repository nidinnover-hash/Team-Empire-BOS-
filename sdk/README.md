# Nidin BOS SDKs

This folder contains generated types plus hand-written API clients for:

- `sdk/python` - Python client (`nidin_bos_sdk`)
- `sdk/typescript` - TypeScript client (`@nidin/bos-sdk`)

## Regenerate OpenAPI types

```bash
py -3.12 scripts/export_openapi_schema.py
py -3.12 scripts/generate_sdk_models.py
py -3.12 scripts/generate_sdk_clients.py
```

Generated outputs:

- `sdk/python/nidin_bos_sdk/models.py`
- `sdk/typescript/src/types.ts`
- `sdk/python/nidin_bos_sdk/client.py` (generated operationId methods section)
- `sdk/typescript/src/client.ts` (generated operationId methods section)

## Examples

- Python: `sdk/examples/python/basic_usage.py`
- TypeScript: `sdk/examples/typescript/basic-usage.mjs`

## Retry and 429 handling

Both SDK clients implement:

- exponential backoff retries for `429`, `502`, `503`, `504`
- `Retry-After` header support
- distinct errors for `rate-limit` vs `quota exceeded` responses
- optional per-request observability hooks (`on_request_event` / `onRequestEvent`)

## Semver policy

- `major`: OpenAPI breaking changes (removed operations, stricter required request fields)
- `minor`: additive OpenAPI surface changes (new operations)
- `patch`: internal/client-only fixes without API surface expansion
