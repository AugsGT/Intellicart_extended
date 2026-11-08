# API overview

Base URL (local): `http://localhost:8001`. JSON everywhere. Authenticated calls send `Authorization: Bearer <access token>`. Anonymous carts send `X-Session-Id`. Errors look like `{"detail": "..."}` or `{"field": ["message"]}`; unexpected failures return a generic 500 message with no internals.

Default rate limits: anon 300/min, user 600/min; login 10/min, register 20/hour, assistants 30/min (HTTP 429).

| Prefix | Who | Purpose |
|---|---|---|
| `GET /health/` | public | Liveness |
| `/auth/` | public | `login`, `refresh` (rotating), `logout` |
| `/users/` | public / user | `register`, `me` |
| `/categories/`, `/products/` | read: public; write: ADMIN | Catalogue and search |
| `/inventory/`, `/alerts/` | staff | Stock, adjustments, ledger, alerts |
| `/cart/` | user or session | Cart, items, merge |
| `/orders/` | owner or staff | Checkout (`POST`, optional `Idempotency-Key`: 201 new, 200 replay), list, detail, status changes |
| `/analytics/` | staff | Revenue, orders, products, funnel |
| `/demand/` | staff | Trends, spikes, stock cover, history |
| `/events/` | staff | Event log, dead letters, health |
| `/recommendations/` | public / user | Similar, popular, personalised |
| `/customer-intelligence/` | staff | Intent scores |
| `/interventions/` | user / staff | Cart-recovery messages and results |
| `/assistant/` | user | Shopping advisor conversations |
| `/ops-assistant/` | staff | Operations assistant conversations (read-only) |
| `/audit/` | ADMIN | Audit log (filterable) and action list |
| `/admin/` | Django staff | Django admin |

Roles: CUSTOMER, OPERATIONS (read operations data, adjust stock, manage orders), ADMIN (everything, including catalogue changes and the audit log). Exact per-endpoint permissions are enforced and tested in `backend/tests/` (a systematic sweep covers every endpoint for anonymous, customer, operations and admin callers).
