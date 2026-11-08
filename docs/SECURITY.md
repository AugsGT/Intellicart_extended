# Security

## In place (tested)

- Private by default: every endpoint requires login unless it opts in to being public. Role classes `IsStaffRole`, `IsAdminRole`, `IsAdminOrReadOnly`, `IsOwnerOrStaff`. Roles are read from the database per request.
- Passwords hashed and validated; login gives the same error for unknown email / wrong password / disabled account. JWT access 30 min, refresh 7 days with rotation and blacklist.
- Rate limiting on every endpoint, tighter on login, register and the assistants. For several server processes set `CACHE_URL` (Redis) so counters are shared.
- Request validation, request-size limit (413), generic 500 responses (no stack traces or SQL to clients; details are logged).
- Production defaults when `DJANGO_DEBUG=False`: HTTPS redirect, secure cookies, HSTS (1 year), nosniff, same-origin referrer policy, proxy SSL header. `manage.py check --deploy` reports only the optional HSTS-preload notice.
- CORS limited to `CORS_ALLOWED_ORIGINS`.
- Append-only **audit log** (`/audit/`, ADMIN only): logins, registrations, product/category/stock/order changes, ops assistant use. The model refuses `update()` and `delete()`.
- Checkout is concurrency-safe (row locks) and idempotent; no oversell, no duplicate order on retry.
- AI safety: the shopping advisor can change the cart only after explicit confirmation; the ops assistant has read-only tools and refuses action requests; rescue messages are filtered so they cannot promise discounts or reserved stock.
- Secrets come from the environment; `.env` is git-ignored. Demo accounts exist only through `seed_demo --with-demo-users` and only with `DJANGO_DEBUG=True`.

## Known risks

- Tokens are stored in `localStorage`, so a cross-site-scripting bug could steal them. Mitigation if needed: httpOnly cookies for the refresh token.
- The access token stays valid until it expires (30 min) after logout.
- The payment gateway is a mock. No real card data should ever be sent.
- The audit log is only as complete as its hooks; new sensitive endpoints must call `audit.services.record`.
- Not penetration tested. Dependencies are not scanned automatically; run `pip-audit` / `npm audit` before release.
