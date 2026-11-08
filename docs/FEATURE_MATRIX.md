# Feature matrix (Django build)

"Verified" means an automated test and/or a live browser check was run on this machine. "Unverified" means written but never exercised against the real service.

| Area | Status | Evidence / caveat |
|---|---|---|
| Registration, login, refresh, logout, roles | Verified | `test_accounts`, browser |
| Catalogue, search, filters, staff CRUD | Verified | `test_catalogue`, browser |
| Cart (user + anonymous, merge on login) | Verified | `test_cart`, browser |
| Checkout, stock locking, mock payment, declines | Verified | `test_orders` incl. concurrency tests |
| Idempotent checkout (retry-safe) | Verified | `test_hardening`, frontend `orders.test.ts` |
| Inventory ledger, adjustments, low-stock alerts | Verified | `test_inventory` |
| Event outbox, relay, idempotent consumer, retries, dead letters | Verified with `EVENT_TRANSPORT=local` | `test_events`, `test_event_transport` |
| RabbitMQ delivery, Celery worker + beat, Redis (broker and throttle cache) | Verified once locally (2026-11-11) | Real RabbitMQ 4.4.0, Redis, Celery 5.7 (solo pool on Windows). See `MIGRATION_PROGRESS.md` "Real broker run". Not verified: multiple workers, long runs, load |
| Analytics (revenue, funnel, top products) | Verified | `test_analytics`, browser |
| Recommendations, intent scores | Verified | `test_recommendations` |
| Cart-recovery interventions | Verified (template path) | `test_rescue` |
| Demand intelligence (trend, spike, stock cover) | Verified | `test_demand_*`; descriptive statistics, not forecasts |
| Shopping advisor (rule-based engine, confirmed cart actions) | Verified | `test_advisor_*`, browser |
| Ops assistant (ten standard questions, read-only) | Verified | `test_ops_assistant`, browser |
| Ollama model paths (advisor, ops assistant, rescue wording) | Verified once against real Ollama (`qwen2.5-coder:7b`) on 2026-11-11 | See `MIGRATION_PROGRESS.md` "Real Ollama run". Answer quality with a small model is limited; the default model `qwen2.5:7b-instruct` was not tried (not installed) |
| Audit log (append-only, ADMIN page) | Verified | `test_audit` (16 tests), browser |
| API hardening (throttles, 413/500 handling, N+1 guards) | Verified | `test_hardening`, `test_query_counts` |
| Frontend role routing, API client, charts, formatting | Verified | 33 Vitest tests |
| Docker / compose / nginx | Verified locally (2026-11-11) | Images build; stack runs; register, login, order and event delivery work through nginx; Ollama reachable from containers via `host.docker.internal`. No TLS/load/multi-replica testing |
| Backup and restore | Verified | restored into a scratch database, counts matched |
| Notifications app | Not implemented | empty placeholder |
| Real payment provider | Not implemented | mock gateway only |

Test totals after the broker, Ollama and Docker runs: backend 407 passed, frontend 33 passed, `tsc -b` clean, `oxlint` 0 errors (10 warnings), `vite build` succeeds.
