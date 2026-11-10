# Intellicart

An e-commerce platform with a customer storefront, a staff operations console and two AI helpers (a shopping advisor and an operations assistant).

- **Backend:** Django 5.2 + Django REST Framework, PostgreSQL, JWT login
- **Frontend:** one React 19 + TypeScript + Vite app (storefront at `/`, operations console at `/ops`, chosen by user role)
- **Events:** domain events written to a transactional outbox, relayed to RabbitMQ, consumed idempotently
- **Background jobs:** Celery with Redis
- **AI:** Ollama (local models), used only where rules and database queries are not enough

> Status: complete through all ten migration phases and run locally, including real RabbitMQ, Celery, Redis, Ollama and Docker. It uses a **mock payment gateway** and has had no penetration test. Details of what was and was not verified are in [`docs/FEATURE_MATRIX.md`](docs/FEATURE_MATRIX.md).

## What it does

**Customers**
- Browse, search and filter the catalogue; product pages with specifications and stock status
- Cart that works before login (anonymous session) and merges into the account on login
- Checkout with card, UPI or cash on delivery (mock gateway; card `4000000000000002` is declined), order history and order details
- Personalised and similar-product recommendations
- Shopping advisor chat: describe what you need ("a laptop for programming under 60000 with good battery life"); it asks follow-up questions, ranks products by your priorities and explains why. It only changes the cart after you confirm
- Cart-recovery messages for idle carts (written by the model, checked by filters, with fixed templates as a fallback)

**Staff (OPERATIONS and ADMIN roles, at `/ops`)**
- Overview, orders, inventory with a stock ledger and adjustments, stock alerts
- Demand: 7-day trend versus a 28-day baseline, spike detection, stock cover in days (descriptive statistics, not forecasts)
- Events, dead letters and System Health (outbox, queues, consumers)
- Analytics: revenue, funnel, top products. Customer intelligence (intent scores). Interventions and their results
- Operations assistant: answers the ten standard questions ("what is likely to run out?", "what is the cancellation rate?") from real data; read-only, refuses action requests
- **Audit log** (ADMIN only): append-only record of sensitive actions

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Django project. `config/` settings and URLs, `apps/` the feature modules, `tests/` |
| `frontend/` | React app. `src/` storefront, `src/ops/` operations console, `src/api/` API client |
| `docs/` | Architecture, AI design, API, security, deployment, feature matrix, progress log |
| `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `deploy/` | Container deployment |
| `scripts/` | `backup_db.sh` (PostgreSQL backup), `start_dev_brokers.sh` (Redis and RabbitMQ without Docker) |

Backend apps: `accounts`, `products`, `categories`, `inventory`, `cart`, `orders`, `events`, `analytics`, `recommendations`, `customer_intelligence`, `demand_intelligence`, `interventions`, `ai_assistant`, `audit` (and an empty `notifications` placeholder).

## Architecture in one picture

```
Browser (React)  --HTTP/JSON, JWT-->  Django + DRF  ----  PostgreSQL
                                          |
          order, stock, cart change + OutboxEvent in ONE transaction
                                          v
   Celery beat -> Redis -> Celery worker: relay outbox -> RabbitMQ -> event consumer -> Event table,
                                          handlers (analytics, intent scores, recovery messages)
   Ollama (optional): advisor, operations assistant, message wording
```

More in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/AI_ARCHITECTURE.md`](docs/AI_ARCHITECTURE.md).

## Quick start with Docker

Requires Docker with Compose.

```bash
cp deploy/.env.example deploy/.env        # then edit: secret key, passwords, hosts
docker compose --env-file deploy/.env up --build
```

Open http://localhost:8080. The `web` container applies migrations on start. For plain-http testing add `DJANGO_SECURE_SSL_REDIRECT=False` and `DJANGO_SECURE_COOKIES=False` to `deploy/.env` (never in production). Load sample products with:

```bash
docker compose --env-file deploy/.env exec web python manage.py seed_demo
```

Create the first admin with `docker compose --env-file deploy/.env exec web python manage.py createsuperuser` (a superuser created this way gets the ADMIN role, and logs in on the storefront login page with its email). Details and caveats: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Local development (without Docker)

Requirements: Python 3.12, PostgreSQL 17, Node 22+ (this project's author runs Node inside WSL).

**Backend**

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # on Linux/macOS: .venv/bin/python
cp .env.example .env                                              # set DB_* and DJANGO_SECRET_KEY
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py seed_demo --with-demo-users    # sample data and demo accounts (DEBUG only)
.venv/Scripts/python.exe manage.py runserver 8001
.venv/Scripts/python.exe manage.py run_local_worker               # delivers events and runs scans, no brokers needed
```

With `EVENT_TRANSPORT=local` (the development default in `.env.example`) events are delivered in-process, so RabbitMQ, Redis and Celery are not required.

**Frontend**

```bash
cd frontend
npm ci
VITE_API_URL=http://localhost:8001 npx vite        # http://localhost:5173
```

**Demo accounts** (local development only, created by `--with-demo-users`, password `demo-password-123`)

| Account | Role |
|---|---|
| `customer@intellicart.local` | Customer |
| `ops@intellicart.local` | Operations |
| `admin@intellicart.local` | Admin (also sees the Audit Log) |

**Optional extras**
- Real brokers without Docker: `scripts/start_dev_brokers.sh` (instructions inside), then set `EVENT_TRANSPORT=rabbitmq`, `RABBITMQ_URL`, `REDIS_URL`, and run `celery -A config worker -l info --pool=solo`, `celery -A config beat -l info` and `manage.py run_event_consumer`.
- AI features: install [Ollama](https://ollama.com) and pull a tool-capable model, then set `OLLAMA_URL` and `OLLAMA_MODEL` (default `qwen2.5:7b-instruct`). Without Ollama the advisor's rule engine, the ops assistant's ten standard questions and the template messages still work.
- Larger sample data for the demand pages: `manage.py seed_order_history` (invented orders) and `manage.py detect_demand`.

## Configuration

Everything is environment variables; see `backend/.env.example` and `deploy/.env.example`.

| Variable | Meaning |
|---|---|
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Core Django settings. `DEBUG` must be False in production, which turns on HTTPS redirect, secure cookies and HSTS |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL |
| `CORS_ALLOWED_ORIGINS` | Origins allowed to call the API |
| `EVENT_TRANSPORT` | `local` (in-process, development) or `rabbitmq` |
| `RABBITMQ_URL`, `REDIS_URL`, `CACHE_URL` | Brokers; `CACHE_URL` shares rate-limit counters across processes |
| `OLLAMA_URL`, `OLLAMA_MODEL`, `RESCUE_USE_LLM`, `CART_ABANDONMENT_MINUTES` | AI and cart-recovery behaviour |
| `VITE_API_URL` (frontend, build time) | API address; `/api` behind the bundled nginx |

## Testing

```bash
cd backend && .venv/Scripts/python.exe -m pytest        # 407 tests (needs PostgreSQL)
cd frontend && npm test                                  # 33 Vitest tests
cd frontend && npx tsc -b && npx oxlint && npx vite build
```

The backend suite includes concurrency tests for checkout and stock, N+1 query-count guards, a systematic permission sweep over every endpoint, and event-pipeline tests.

## API

Roles are CUSTOMER, OPERATIONS and ADMIN; every endpoint requires login unless it opts in to being public, and rate limits apply everywhere. Checkout accepts an `Idempotency-Key` header so a retried request returns the original order. Endpoint overview: [`docs/API.md`](docs/API.md). Security measures and known risks: [`docs/SECURITY.md`](docs/SECURITY.md).

## Backup and restore

```bash
scripts/backup_db.sh                                   # writes backups/<db>_<timestamp>.dump
createdb intellicart_copy
pg_restore --no-owner -d intellicart_copy backups/<file>.dump
```

Restoring into a scratch database was verified; always restore into a new database first.

## Known limitations

- Payments are a mock gateway; no real card data should ever be sent.
- Tokens are kept in the browser's `localStorage` (a cross-site-scripting bug could expose them); access tokens live 30 minutes and stay valid until expiry after logout.
- AI quality depends on the model. It was tried with `qwen2.5-coder:7b`; the default `qwen2.5:7b-instruct` was not. Rules and database queries, not the model, produce rankings and statistics.
- Not tested: TLS and real domains, load, several replicas or workers, long-running soak, upgrade/rollback.
- Demo accounts and the password above exist only for local development; never enable them in production.

## More documentation

| Document | Contents |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Apps, key rules, data flow |
| [`docs/AI_ARCHITECTURE.md`](docs/AI_ARCHITECTURE.md) | Advisor, operations assistant, rescue messages |
| [`docs/API.md`](docs/API.md) | Endpoint overview |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Protections and known risks |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Docker, first deployment, backups |
| [`docs/FEATURE_MATRIX.md`](docs/FEATURE_MATRIX.md) | Every feature and how it was verified |
| [`docs/RUNNING_LOCALLY.md`](docs/RUNNING_LOCALLY.md) | Windows/WSL notes |
| [`docs/MIGRATION_PROGRESS.md`](docs/MIGRATION_PROGRESS.md) | Phase-by-phase log with evidence |
