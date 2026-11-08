# Running Intellicart locally (Windows)

## Backend (Django, Windows Python)

```bash
cd backend
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py seed_demo --with-demo-users   # sample data + demo accounts (dev only)
.venv/Scripts/python.exe manage.py runserver 8001
.venv/Scripts/python.exe manage.py run_local_worker          # delivers events and scans for abandoned carts (stand-in for Celery beat)
.venv/Scripts/python.exe -m pytest                                # tests
```

Settings come from `backend/.env` (copy `.env.example`). PostgreSQL must be running with the `DB_*` values from that file.

Demo accounts (created only by `--with-demo-users`, only when `DJANGO_DEBUG=True`; the password is defined in `apps/products/management/commands/seed_demo.py`):
`admin@intellicart.local`, `ops@intellicart.local`, `customer@intellicart.local`.

## Frontend (React, runs inside WSL)

On this machine npm cannot download packages from Windows, so Node.js 24.13.0 is installed in WSL (`~/node`, unpacked from the official tarball with its checksum verified) and `frontend/node_modules` holds **Linux** builds. Run every npm command inside WSL:

```bash
wsl -d Ubuntu-22.04
export PATH="$HOME/node/bin:$PATH"
cd /mnt/c/Storage/Intellicart/frontend
npm ci
VITE_API_URL=http://localhost:8001 npx vite --host 0.0.0.0 --port 5173
npx tsc -b && npx oxlint && npx vite build      # checks
```

Open http://localhost:5173 in the Windows browser (WSL forwards the port). The API address comes from `VITE_API_URL`.

## Events without RabbitMQ / Redis / Docker

Docker does not work on this machine and neither broker is installed, so development uses `EVENT_TRANSPORT=local` (see `.env.example`). Keep `relay_outbox --loop` running next to the server; events then appear in the operations console (Events, System Health).

For deployment: `EVENT_TRANSPORT=rabbitmq`, run `manage.py run_event_consumer`, and Celery (`celery -A config worker` and `celery -A config beat`; on Windows add `--pool=solo` for the worker). These paths have not been run against real RabbitMQ or Redis yet.

## AI features

Recommendations, intent scoring and cart recovery need only the database and `run_local_worker`. The shopping assistant and AI-written recovery messages need Ollama (`OLLAMA_URL`, `OLLAMA_MODEL`, default `qwen2.5:7b-instruct`). Without it the assistant says it is unavailable and recovery messages use fixed templates. To see a recovery banner quickly, start the worker with `CART_ABANDONMENT_MINUTES=0`.

## Demand dashboards

```bash
.venv/Scripts/python.exe manage.py seed_demo --with-demo-users
.venv/Scripts/python.exe manage.py seed_order_history            # 90 days of invented orders (add --replace to regenerate)
.venv/Scripts/python.exe manage.py detect_demand                 # raise spike / stockout alerts now (run_local_worker does this every 5 minutes)
```
Then open Operations -> Demand and Analytics. The history is sample data and its dates are relative to today, so it stays "recent".
