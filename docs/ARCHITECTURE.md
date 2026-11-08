# Architecture

Intellicart is a **modular monolith**: one Django project, split into apps with clear jobs, plus one React frontend. (The earlier FastAPI system was removed from the repository; it remains in git history before the Django migration commit.)

```
 Browser (React: storefront + /ops console)
        |  JSON over HTTP, JWT bearer token, X-Session-Id for anonymous carts
        v
 Django + DRF  ---- PostgreSQL (all state)
   |  writes OutboxEvent in the SAME transaction as the change
   v
 Outbox relay (SKIP LOCKED) --> RabbitMQ --> idempotent consumer --> Event table
   |                                                  |
 Celery beat: relay, abandoned carts, demand signals  +--> analytics, intent scores, interventions
 Ollama (optional): shopping advisor, ops assistant, rescue-message wording
```

## Apps (`backend/apps/`)

| App | Responsibility |
|---|---|
| `accounts` | Custom user with a `role` (CUSTOMER / OPERATIONS / ADMIN), JWT login, register, logout, profile |
| `products`, `categories` | Catalogue, search/filter, staff CRUD |
| `inventory` | Stock ledger (`StockMovement`), adjustments, low-stock alerts |
| `cart` | Cart owned by a user or an anonymous session, merged on login |
| `orders` | Row-locked checkout, mock payment gateway, order lifecycle, idempotent checkout |
| `events` | Event contracts (18 types), outbox, relay, consumer, retries, dead letters |
| `analytics` | Revenue, orders, top products, funnel (successful orders only) |
| `recommendations`, `customer_intelligence` | Similar / popular / personalised products; intent scores |
| `demand_intelligence` | Trend, spike and stock-cover statistics; stock alerts (descriptive, not forecasting) |
| `interventions` | Abandoned-cart detection and rescue messages |
| `ai_assistant` | Shopping advisor and staff operations assistant |
| `audit` | Append-only audit log of sensitive actions |
| `notifications` | Empty placeholder |

## Key rules

- **Checkout** locks the user and the products (in id order), re-checks stock, writes the order, the stock movements and the outbox events in one transaction. An `Idempotency-Key` header makes a retried request return the original order instead of a second one.
- **"Successful order"** = paid and not cancelled/failed. All purchase and demand statistics use `Order.objects.successful()`.
- **Events are at-least-once**; the consumer is idempotent (unique `event_id`). Failures retry, then go to a dead-letter table.
- **Roles are read from the database on every request**; a demoted user loses access immediately.
- **AI never invents numbers.** Rankings and statistics are computed in code; the model only words or routes. Cart changes need user confirmation; the ops assistant is read-only.

## Frontend

`frontend/src`: storefront pages, `ops/` (console pages, scoped CSS under `.ops-shell`, SVG charts), `RequireRole` for route guarding, `api/client.ts` (token refresh, error shaping). Tokens live in localStorage (a known trade-off, see `SECURITY.md`).

## Configuration

Everything comes from environment variables (`backend/.env.example`). `EVENT_TRANSPORT=local` delivers events in-process for development; `rabbitmq` is for deployment.
