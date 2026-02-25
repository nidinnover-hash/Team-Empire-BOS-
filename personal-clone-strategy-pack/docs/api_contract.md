# API Contract

## Version
- `X-API-Contract-Version` response header
- Error payload field: `contract_version`

Current value: `2026-02-23`

## Error Envelope
All API errors follow:

```json
{
  "code": "validation_error",
  "detail": [],
  "request_id": "uuid",
  "contract_version": "2026-02-23"
}
```

## Stability Notes
- `code` is the stable machine field.
- `detail` may vary by endpoint or validation source.
- `request_id` links client-visible failures to server logs.
