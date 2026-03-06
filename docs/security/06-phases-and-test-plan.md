# Phase-by-Phase Implementation & Test Plan

## Phase 1: Lambda Authorizer + Auth0 JWT

**Scope**: Add Lambda authorizer for Runtime API; validate Auth0 JWT.

**Implementation**:
- Create `auth_authorizer_lambda.py` (or similar)
- Configure API Gateway to use authorizer for `/v1/execute`, `/v1/ai/execute`


**Test plan**:
| # | Test | Steps | Expected |
|---|------|-------|----------|
| 1.1 | Valid JWT | Call with Bearer token | 200 |
| 1.2 | Invalid JWT | Wrong token | 401 |
| 1.3 | Expired JWT | Expired token | 401 |
| 1.4 | Missing auth | No header | 401 |

---

## Phase 2: Per-Consumer API Keys

**Scope**: Support per-consumer API keys for Runtime API.

**Implementation**:
- Runtime consumers use JWT (vendor_api_keys table removed)
- Auth path: JWT (Authorization: Bearer)
- Document key creation flow

**Test plan**:
| # | Test | Steps | Expected |
|---|------|-------|----------|
| 2.1 | Valid key | Valid JWT | 200 |
| 2.2 | Invalid key | Wrong key | 401 |
| 2.3 | Revoked key | Inactive key | 401 |
| 2.4 | Hash only in DB | Inspect DB | No plaintext |

---

## Phase 3: mTLS Support

**Scope**: Accept mTLS client certificates for Apache registrar.

**Implementation**:
- Custom domain with mTLS (trust store in S3)
- Map cert identity to trusted gateway; accept sourceVendor from body

**Test plan**:
| # | Test | Steps | Expected |
|---|------|-------|----------|
| 3.1 | Valid cert | Call with valid cert | 200 |
| 3.2 | No cert | Call without cert | 403 |
| 3.3 | Invalid cert | Wrong cert | 403 |

---

## Phase 4: Request Signing (Optional)

**Scope**: Optional request signing for high-value consumers.

**Implementation**:
- Signing spec (method, path, timestamp, body hash)
- Verify in auth layer; reject invalid/expired

**Test plan**:
| # | Test | Steps | Expected |
|---|------|-------|----------|
| 4.1 | Valid signature | Correct HMAC | 200 |
| 4.2 | Tampered body | Change body | 401 |
| 4.3 | Old timestamp | >5 min | 401 |

---

## Phase 5: Error Handling & Audit

**Scope**: Enforce error handling rule; ensure audit logging.

**Implementation**:
- Audit all Lambda error responses for canonical structure
- Ensure consumer identity in audit events

**Test plan**:
| # | Test | Steps | Expected |
|---|------|-------|----------|
| 5.1 | 401 response | Invalid auth | No stack trace |
| 5.2 | 500 response | Force error | Generic message only |
| 5.3 | Audit row | Success + failure | consumer_id present |
