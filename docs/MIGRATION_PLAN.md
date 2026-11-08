# Intellicart — Migration Plan (FastAPI → Django + DRF)

Phases run in order. A phase is complete only when its completion criterion is met and recorded in `MIGRATION_PROGRESS.md`.

## Decisions

- **Fresh start.** The old database is lost, so there is no data to migrate (`DATABASE_MIGRATION.md`). Django is a new project in `backend/` with its own database. `backend/` (FastAPI) stays untouched as a reference for business rules until parity is reached; it is archived or removed only with your approval, after which `backend/` is renamed `backend/`.
- **API contract.** Keep the existing URLs and JSON field names where sensible so the React code needs few changes, and keep `{"detail": ...}` errors. Intentional changes (login required for cart/orders, paginated product list, categories) are listed per phase.
- **Auth.** Custom `AbstractUser` with a `role` field and `djangorestframework-simplejwt` (access + refresh, blacklist on logout). No compatibility with old tokens is needed.
- **Shopper identity.** Authenticated user owns cart and orders. Anonymous visitors keep a session cart, merged into the user's cart at login.
- **Business logic** moves into `apps/<name>/services.py`, views stay thin.
- **Asynchronous work.** Celery with Redis as result/scheduling backend; RabbitMQ stays the domain-event transport with the current exchange and queue names.
- **No** Kafka, microservices, Kubernetes, webhooks or autonomous AI writes.

## Phases

| Phase | Scope | Completion criterion | Status |
|---|---|---|---|
| 0 | Baseline docs and behavior list (backup and restore no longer apply) | Existing behavior documented | Done (docs); tests not runnable |
| 1 | Django project, settings from env, DRF, modular app layout, health endpoint | `manage.py check` clean, tests run, server answers `/health/` | **Done** |
| 2 | Users, JWT, refresh, roles, permissions (ownership permission built; enforced on cart/orders in Phase 3) | Accounts authenticate; roles enforced; customer A cannot read customer B's data (proved in Phase 3 with real carts/orders) | **Accounts done** |
| 3 | Categories, products + attributes, search/filter/sort/pagination, cart, checkout with row locks, orders, inventory, purchase history | Core commerce via Django; concurrent checkout cannot oversell | **Done (backend)** |
| 4 | One React app: add role-based routing and move the 9 ops pages into `frontend/`; share one API client | One app serves both roles; ops app removed after parity | **Nearly done**: storefront + all 9 original ops pages migrated; `ops-frontend/` not yet removed (needs your approval); the Phase 9 assistant page is new |
| 5 | Transactional outbox, publisher after commit, idempotent consumers, retries, DLQ, Celery + Redis | Events survive a broker outage and are processed once | **Done with a local transport**; real RabbitMQ / Redis unverified |
| 6 | Port recommendations, intent, rescue engine, scanner, assistant | Existing AI works through Django | **Done** (assistant and message writing verified only with a stubbed model) |
| 7 | Conversational advisor: requirement extraction, tools, comparison, persisted conversations, confirmed add-to-cart | Grounded recommendations from catalogue data | **Done** (model fallback unverified) |
| 8 | Demand intelligence: daily/weekly/monthly sales, moving averages, spikes, depletion, restock suggestions | Dashboard numbers equal SQL on real orders | **Done** |
| 9 | Ops assistant (read-only tools, staff only) | Answers come from tool results | **Done** (model fallback unverified) |
| 10 | Audit log, hardening, query tuning, Docker, docs | Test suite green, docs current | Not started |

## Test strategy

- The FastAPI baseline cannot be run (no data, no working environment), so `tests/characterization/` is now a **specification** of behaviors to reproduce. Tests that describe known weaknesses (`known_gap`) are rewritten to assert the fixed behavior.
- Django tests use pytest-django against a throwaway test database and cover permissions, concurrency, events, AI grounding (with a stubbed model) and demand calculations.

## Risks

- Decimal totals: tax is not rounded in FastAPI; Django will round to 2 places and document it.
- The 7B local model may follow tool-calling instructions unreliably; the advisor needs deterministic fallbacks and tests that stub the model.
