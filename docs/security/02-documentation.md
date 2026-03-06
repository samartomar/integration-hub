# API & Integration Documentation

## Base URLs

| Environment | Base URL |
|-------------|----------|
| Local | `http://localhost:8080` |
| Staging | (from stack output) |
| Prod | (from stack output / custom domain) |

## Auth headers

### JWT
```
Authorization: Bearer <access_token>
```

### JWT (vendor / execute)
```
Authorization: Bearer <jwt_token>
```

### Request signing (optional)
```
x-request-timestamp: <unix_epoch_seconds>
x-request-signature: <hmac-sha256_hex>
x-signature-version: v1
```

### mTLS
Client certificate required on connection (custom domain with mTLS enabled).

## Request bodies

See `docs/runtime-api.md` for full request/response schemas.

## Error response format

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable message",
  "category": "AUTH|VALIDATION|PLATFORM|...",
  "retryable": false,
  "details": {}
}
```
