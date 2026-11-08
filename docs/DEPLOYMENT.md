# Deployment preparation

**Status: built and run locally on 2026-11-11** with Docker Desktop (28.3.2): all images build, the stack starts, and an order placed through nginx flows through the outbox, RabbitMQ and the consumer. Not tested: TLS, a real domain, multiple replicas, load, upgrade/rollback, data volume backup inside Docker. `check --deploy` run with `DJANGO_DEBUG=False` is clean apart from HSTS preload, but the local `.env` deliberately turns off SSL redirect and secure cookies, which raises extra warnings - never do that in production.

## Files

- `backend/Dockerfile` - gunicorn image, used for `web`, `worker`, `beat`
- `frontend/Dockerfile`, `frontend/nginx.conf` - builds the React app, serves it, forwards `/api/` to Django
- `docker-compose.yml` - db (Postgres 17), redis, rabbitmq, web, worker, consumer (RabbitMQ events), beat, frontend (nginx; published on port 8080)
- `deploy/.env.example` - copy to `deploy/.env` (git-ignored) and fill in secrets

## First deployment

1. `cp deploy/.env.example deploy/.env`; set a long random `DJANGO_SECRET_KEY`, real passwords, real host names.
2. `docker compose --env-file deploy/.env up --build` (the `web` service runs `migrate` first). Open http://localhost:8080. For plain-http testing set `DJANGO_SECURE_SSL_REDIRECT=False` and `DJANGO_SECURE_COOKIES=False` in `deploy/.env`; remove both for production.
3. Create the first admin: `docker compose exec web python manage.py createsuperuser`, a superuser created this way automatically gets the ADMIN role. **Do not run `seed_demo --with-demo-users` in production.**
4. Put TLS in front (load balancer or a reverse proxy); the app redirects http to https and trusts `X-Forwarded-Proto`.
5. Run Ollama separately if the assistants are wanted; set `OLLAMA_URL`. Without it the assistants degrade gracefully.

## Verify after the first start (not yet done)

- `GET /api/health/` returns 200; the ops System Health page shows the queue and worker state.
- Place a test order; the event appears in Operations -> Events (proves outbox -> RabbitMQ -> consumer).
- Stop RabbitMQ, place an order, restart it: the event must still be delivered (outbox).
- Celery beat is running the 3-second relay, 60-second abandoned-cart scan and 15-minute demand scan.

## Backup and restore (verified locally)

```bash
scripts/backup_db.sh                     # writes backups/<db>_<timestamp>.dump
createdb intellicart_copy
pg_restore --no-owner -d intellicart_copy backups/<file>.dump
```
Verified on 2026-11-11: backup of the dev database restored into a scratch database with identical row counts (products, orders, users); scratch database dropped. Schedule the script (cron) and copy dumps off the machine.

## Environment variables

See `backend/.env.example` and `deploy/.env.example`. Notable: `DJANGO_DEBUG` (must be False), `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `EVENT_TRANSPORT` (`rabbitmq` in production), `CACHE_URL` (shared throttle counters), `OLLAMA_URL`, `OLLAMA_MODEL`.
