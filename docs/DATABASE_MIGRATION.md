# Intellicart — Database Plan (fresh start)

## What changed

The original database lived on a laptop that is no longer available, and no dump exists. **There is no production data to migrate.** The Django backend therefore starts with a new PostgreSQL database and normal, fully managed Django migrations. Nothing needs to be mapped onto old tables, and no Alembic coexistence is needed.

The FastAPI schema is kept only as a design reference (below). The old `backend/` folder is not touched by Django.

## Consequences

- No unmanaged models, no `SeparateDatabaseAndState`, no password-hash or token compatibility work. A custom `AbstractUser` model with a `role` field is used from the first migration.
- `Category` is a real table, `Cart` and `Order` have a real `user` foreign key from day one, and constraints (status choices, non-negative stock and price) are enforced in the database.
- The characterization tests in `tests/characterization/` described FastAPI behavior and cannot be run (no data, no working environment). They are kept as a list of behaviors to reproduce, and will be adapted to Django's intentionally changed contract (for example, orders now require login).

## Databases (local development)

| Database | Purpose |
|---|---|
| `intellicart` | Development data |
| `test_intellicart` | Created and destroyed automatically by pytest-django |

Connection settings come from `backend/.env` (gitignored). `backend/.env.example` lists the keys with no secrets.

## Legacy FastAPI schema (reference only)

| Table | Carry into the new design as |
|---|---|
| `users` | `accounts.User` (AbstractUser + `role`: CUSTOMER / OPERATIONS / ADMIN) |
| `token_blocklist` | simplejwt token blacklist |
| `products` | `products.Product` with FK to `categories.Category`, plus structured attributes |
| `cart`, `cart_items` | `cart.Cart` (user or anonymous session), `CartItem` |
| `orders`, `order_items` | `orders.Order` (user FK, status choices), `OrderItem` (price snapshot) |
| `stock_movements` | `inventory.StockMovement` (ledger) |
| `alerts` | `inventory`/`analytics` alerts |
| `events` | `events.Event` plus an `OutboxEvent` table |
| `interventions` | `interventions.Intervention` |
| `customer_intent_scores` | `customer_intelligence.IntentScore` |

## Backups from now on

The new database will hold only development data, so a backup is optional. Before Phase 10 (deployment preparation) a documented `pg_dump` / restore procedure is added and tested. `scripts/backup_db.sh` was written for the old setup and reads `backend/.env`; it will be updated to read `backend/.env`.

## Local setup needed from you (one time)

Create a role and the development database in your own terminal (choose your own password):

```sql
CREATE ROLE intellicart LOGIN PASSWORD 'choose-a-password' CREATEDB;
CREATE DATABASE intellicart OWNER intellicart;
```

`CREATEDB` lets pytest-django create its own test database. Put the same password in `backend/.env`.
