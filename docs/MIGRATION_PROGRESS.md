# Intellicart — Migration Progress

Updated 2026-11-10. Only mark a task Done when its completion criterion was actually checked.

## Decision log

- 2026-11-10: The original database (on a laptop that no longer works) is unrecoverable. Plan changed to a **fresh Django build with a new database**; no data migration, no backup/restore of legacy data. See `DATABASE_MIGRATION.md`.

## Phase 0 — Baseline: DONE (documentation only)

| Task | Status | Files |
|---|---|---|
| Repository inspected | Done | — |
| Architecture, feature, AI docs | Done | `docs/ARCHITECTURE.md`, `FEATURE_MATRIX.md`, `AI_ARCHITECTURE.md` |
| Plans | Done, revised | `docs/MIGRATION_PLAN.md`, `DATABASE_MIGRATION.md` |
| Behavior list | Done | `tests/characterization/` (19 tests, never run; now a specification) |
| Legacy backup | Not applicable | — |

## Phase 1 — Django foundation: DONE

Completion criterion (project runs, checks clean, tests pass against PostgreSQL) was verified on 2026-11-10.

| Task | Status | Evidence |
|---|---|---|
| Python venv + dependencies | Done | `backend/.venv` (gitignored), `requirements.txt`, `requirements-dev.txt`; Django 5.2.19, DRF 3.18.3, simplejwt 5.5.1 |
| Project + modular apps | Done | `backend/config/`, 15 empty app packages under `apps/`; only `accounts` has a model |
| Settings from env, DRF, JWT | Done | `config/settings.py`; private-by-default permissions, pagination, JWT lifetimes, CORS. `manage.py check`: no issues |
| `/health/` endpoint + test | Done | `tests/test_health.py` passes (2 tests); server answered 200 on port 8001 |
| PostgreSQL connection | Done | Local role `intellicart` / database `intellicart` already existed (empty); `migrate` applied, test DB created by pytest |
| Custom user model | Done early | `apps/accounts/models.py` + `0001_initial` (needed before the first migrate) |

## Phase 2 — Authentication: DONE for accounts; ownership enforcement moves to Phase 3

| Task | Status | Evidence |
|---|---|---|
| Registration (`POST /users/register/`) | Done | Role forced to CUSTOMER; password validated and hashed; duplicate email rejected case-insensitively |
| Login by email (`POST /auth/login/`) | Done | Same 401 message for unknown email, wrong password, disabled account |
| Refresh with rotation + blacklist (`POST /auth/refresh/`) | Done | Reusing an old refresh token returns 401 |
| Logout (`POST /auth/logout/`) | Done | Blacklists the refresh token. The 30-minute access token stays valid until it expires (stateless) |
| Login rate limit | Done | 10/min per IP, 11th attempt returns 429 |
| Profile (`GET/PATCH /users/me/`) | Done | Customers cannot change their role |
| Admin user management (`/users/`, `/users/<id>/`) | Done | ADMIN only; DELETE deactivates, cannot deactivate yourself; role changes apply immediately because permissions read the database, not the token |
| Role permissions | Done | `IsAdminRole`, `IsStaffRole`, `IsOwnerOrStaff` in `apps/accounts/permissions.py` |
| Cart and order ownership | **Not yet** | `IsOwnerOrStaff` is unit-tested, but carts and orders do not exist in Django until Phase 3. The cross-customer isolation tests are written there |
| Tests | 25 passing | `tests/test_accounts.py`, `tests/test_health.py` |

Changes from the FastAPI contract (the frontend must follow in Phase 4): registration is `POST /users/register/`; login returns `{access, refresh}` instead of `access_token`; URLs end with `/`; user list is paginated.

Outstanding: password reset and email verification are not implemented (out of the listed scope).

## Phase 3 — Commerce: DONE (backend). Frontend still talks to FastAPI until Phase 4

Verified with 96 passing pytest tests (`backend/tests/`), a live smoke test on port 8001 against seeded sample data, and a mutation check: removing the row lock from checkout makes the concurrency tests fail, restoring it makes them pass.

| Area | Status | Where / evidence |
|---|---|---|
| Categories (real table, tree) | Done | `apps/categories`; public read, ADMIN write; cycle and delete-with-products blocked |
| Structured attributes | Done | `AttributeDefinition` per category (parents inherit), `ProductAttribute`; a phone cannot get `processor`. Brand is a product column |
| Products, archive instead of delete | Done | `apps/products`; stock cannot be edited through product update |
| Search, filter, sort, pagination | Done | `GET /products/?q=&category=&brand=&min_price=&max_price=&in_stock=&ordering=&page=&page_size=` (category includes subcategories; page size max 100). Used by the Phase 7 advisor tools |
| Inventory ledger, restock, adjust, alerts | Done | `apps/inventory`; every stock change has a ledger row; negatives refused; one open low-stock alert per product, escalates to high at 0 and closes after restock |
| Cart (anonymous + user), merge on login | Done | `apps/cart`; owner always comes from the token or the caller's own session key; `POST /cart/merge/` |
| Checkout with row locks | Done | `apps/orders/services.py::checkout`: one transaction, products locked in id order |
| Order lifecycle + cancellation | Done | CONFIRMED→SHIPPED→DELIVERED, cancel from CONFIRMED/SHIPPED restocks and marks REFUNDED (mock); customers may cancel only while CONFIRMED |
| Payment | **MOCK** | `apps/orders/payments.py`: always succeeds except card 4000000000000002. No real money moves |
| Ownership and isolation | Done | Tests prove customer B cannot read, cancel or change customer A's cart items or orders (404), and cannot see them in lists or history |
| Purchase history | Done | `GET /customer-intelligence/me/purchase-history/` (+ staff view). `Order.objects.successful()` = paid and not cancelled/failed; cancelled and failed are counted separately |
| Sample data | Done | `python manage.py seed_demo` (invented products and specs, clearly labelled as sample data) |

### Contract differences from FastAPI (frontend work in Phase 4)
Login required for checkout and orders; cart is `/cart/` + `/cart/items/` with trailing slashes; checkout returns 201, or 402 with the FAILED order when the card is declined; order and product statuses are upper-case; product has `category` (id), `category_name`, `brand`, `attributes`; lists are paginated (`results`); money is always a string.

### Known limits / not done in Phase 3
- No domain events yet (cart, order, stock events arrive with the outbox in Phase 5). Order `ORDER_*` / `STOCK_*` publishing is therefore not wired.
- Checkout has no idempotency key; a double-submit could create two orders if the cart is refilled between them.
- Anonymous carts are protected only by the secrecy of the random session key (they hold no personal data).
- Product images are a URL/path string; no upload handling.
- Product search uses `icontains`; a PostgreSQL trigram index can be added if the catalogue grows.
- Order status changes are not audit-logged yet (Phase 10).

## Phase 4 — Frontend consolidation: PARTIAL (storefront done, 4 of 9 ops pages moved)

Verified in the browser (Django on :8001, Vite on :5173) and by `tsc -b` (clean), `oxlint` (0 errors, 7 style warnings), `vite build` (ok).

| Task | Status | Evidence |
|---|---|---|
| One React app, role-based routing | Done | `frontend/src/App.tsx`: storefront layout + `/ops/*` behind `RequireRole`; staff see an Operations link, customers who open `/ops` are sent home |
| Shared API client with JWT refresh | Done | `api/client.ts`: Bearer token, `X-Session-Id`, one automatic refresh on 401, readable DRF error messages |
| Storefront on Django | Done | Products with server-side search / category / sort / pagination; guest cart; login merges the guest cart; checkout (login required, 402 decline shows the failed-order page); order detail with cancel; profile with purchase stats |
| Role enforcement | Done | Customer opening `/ops/orders` is redirected, and the API returns 403 for the same customer token |
| Ops pages moved | **4 of 9** | Overview, Orders (only valid next statuses offered), Inventory (restock for ADMIN only), Alerts. Ops CSS is scoped under `.ops-shell` so it cannot restyle the storefront |
| Ops pages not moved yet | Waiting on backend | Events (Phase 5), Interventions and Customer Intelligence (Phase 6), Analytics and Demand (Phase 8), System Health (Phase 5/10), Operations assistant (Phase 9) |
| Remove `ops-frontend/` | **Not done** | Brief requires it only after all its pages are migrated and verified. Not yet true |

Features switched off in `frontend/src/features.ts` until their Django endpoints exist (no requests are made while off): event tracking (Phase 5), recommendations and interventions banner (Phase 6), shopping assistant (Phase 6/7). The FastAPI versions exist but nothing calls them.

### Not verified
- Cancelling an order and the declined-card path were covered by backend tests but not clicked through in the browser.
- Mobile layout was not re-checked after the merge.
- No frontend unit tests exist (Phase 10).

### Environment notes
- `frontend/node_modules` was Linux-built (copied from the old laptop) and npm on Windows cannot download packages here, so Node 24.13.0 was installed in WSL from the official tarball (checksum verified) and `npm ci` was run there. See `docs/RUNNING_LOCALLY.md`. `.claude/launch.json` (Windows npm) will not start the frontend.
- Default API address is now `http://localhost:8001` (Django); set `VITE_API_URL` to change it.

## Phase 5 — Event infrastructure: DONE for the code and local use; real RabbitMQ and Redis NOT verified

Decision (2026-11-10): Docker does not work on this machine and RabbitMQ / Redis are not installed, so events run through a **local transport** in development. Verified by 133 passing backend tests and a live browser run (search, product views and a cart add travelled outbox -> relay -> consumer -> event log -> ops Events page; System Health showed 0 waiting, 0 dead letters).

| Requirement | Status | Where / evidence |
|---|---|---|
| Transactional outbox | Done | `apps/events/models.py::OutboxEvent`, written by `events.services.emit()` inside the business transaction. Tests: rollback removes the event; a failed checkout leaves no events |
| Not published before commit | Done | Nothing is sent in `emit()`; the relay only sees committed rows |
| Structured, versioned payloads | Done | `apps/events/contracts.py`: 18 event types, required payload keys, version 1; unknown types / missing keys rejected |
| Required events emitted | **Partly** | Emitted now: ORDER_CREATED / COMPLETED / CANCELLED, PAYMENT_SUCCEEDED / FAILED, INVENTORY_UPDATED, STOCK_LOW (once per crossing), STOCK_RESTOCKED, CART_ITEM_ADDED / REMOVED, PRODUCT_VIEWED, PRODUCT_SEARCHED, CHECKOUT_STARTED. Defined but emitted later: CART_ABANDONED, RECOMMENDATION_* (Phase 6), DEMAND_SPIKE_DETECTED (Phase 8) |
| Relay with outage tolerance | Done | `relay.py`: SKIP LOCKED batches, stops at first failure to keep order; test shows events survive an outage and are sent after recovery |
| Idempotent consumer | Done | `consumer.py::process_message`: unique `event_id` in the event log; duplicates skipped; handlers share the transaction so failures roll back |
| Retry handling | Done | Failure -> republished with `x-retry-count` (RabbitMQ) or retried in-process (local); `EVENTS_MAX_RETRIES` = 3 |
| Dead-letter handling | Done | Exhausted messages rejected into the DLQ and recorded in `DeadLetterEvent`; `manage.py replay_dead_letters`; listed on System Health |
| Event logging | Done | `Event` table; `GET /events/` (staff) and the ops Events page |
| Celery | **Configured, not run** | `config/celery.py`, beat schedule `relay-outbox` every 3 s, task `apps.events.tasks.relay_outbox`. Needs Redis; never started here. `manage.py relay_outbox --loop` does the same job without it |
| RabbitMQ | **Not verified against a real broker** | `broker.py` (pika, publisher confirms, original exchange/queue names) and the consumer callback are tested only against a fake channel. First real run may need small fixes |
| Ops UI | Done | Events and System Health pages (6 of 9 ops pages now moved) |

### How events run locally
`EVENT_TRANSPORT=local` (set in `backend/.env`): the relay passes each event straight to the consumer logic in-process. Start `manage.py relay_outbox --loop` next to the server. Deployment uses `EVENT_TRANSPORT=rabbitmq` with `manage.py run_event_consumer` and Celery beat/worker (on Windows use `celery -A config worker --pool=solo`).

### Known limits
- Product views and searches are an outbox insert on a GET request (small write on a read path).
- In development, React StrictMode runs effects twice, so each product view is recorded twice; production builds do not.
- Queue depth on System Health needs the RabbitMQ management API settings; without them it says "not available".
- No handlers are registered yet beyond logging (Phase 6 adds the rescue engine).

## Phase 6 — Existing AI migration: DONE, with the Ollama model never run for real

Verified by 200 passing backend tests (67 new) and a live browser run: a customer's idle cart was flagged by the scanner, travelled through the outbox, consumer and rescue engine, and appeared as a banner; the click was recorded; the ops pages showed the decision and the intent score (checked by hand: 2 views + 1 cart add + 1 prior order = 19, MEDIUM).

| Capability | Status | Where / evidence |
|---|---|---|
| Similar products | Done | `apps/recommendations/services.py`: same category, in-stock first, nearest price; each result has a plain-language `reason` |
| Frequently bought together | Done, **bug fixed** | Counts only `Order.objects.successful()`; the old version counted failed and cancelled orders (test proves they are ignored) |
| Substitutes | Done | Only for low or out-of-stock products; in-stock same-category, nearest price |
| Recently viewed, cart-based | Done | Recently viewed reads the event log by user or session; cart-based prefers co-purchases, then same category |
| Personalized (new) | Done | Logged-in only; weights categories by purchases 3, cart adds 2, views 1; skips already-bought products; cancelled orders ignored |
| Recommendation tracking | Done | RECOMMENDATION_GENERATED when a list is served, `POST /recommendations/click/` -> CLICKED, purchase within 7 days of a click -> PURCHASED (handler), staff `GET /recommendations/stats/` with click and purchase rates. "Served" is a proxy for impressions; attribution is by click, not proof of cause |
| Intent engine | Done | `apps/customer_intelligence/intent.py`: same weights as before plus cart removals (weight 1, cap 3, my judgement call); every score stored with its basis; follows a user across browsers |
| Abandonment scanner | Done | `apps/interventions/scanner.py`: idle measured from the newest cart item, flagged once, eligible again after new activity. Celery task + `manage.py scan_abandoned_carts` |
| Rescue engine | Done, **behavior changed on purpose** | Rules and audit rows kept. Removed the SMALL_DISCOUNT and TIME_LIMITED_OFFER actions: they promised "10% off" and a 2-hour cart reservation that do not exist. Actions now: REMINDER, CHECKOUT_REMINDER, STOCK_ALTERNATIVE, BACK_IN_STOCK_ALERT, NO_ACTION |
| Ollama-written messages | Done, **unverified against the real model** | `interventions/messages.py`: model writes one sentence from verified facts; text is rejected (and a fixed template used) if empty, long, multi-line, or mentioning discounts, offers, prices, deadlines or reservations. A bug caught by tests: a template containing "off" tripped the filter and was reworded. Live run used templates because Ollama is not running |
| Interaction + recovery tracking | Done | click and dismiss endpoints; ORDER_COMPLETED marks cart reminders RECOVERED (back-in-stock alerts only if that product was bought) |
| Back-in-stock alerts | Done | On STOCK_RESTOCKED, customers who viewed the product in the last 14 days (max 50, once each) |
| Shopping assistant | Done (parity), **not run with a real model** | `apps/ai_assistant/shopping.py`: same 4 read-only tools on Django ORM, tool arguments validated, 4-round cap, friendly message when Ollama is down, rate limit 30/min, history validated (no injected system messages). Tests use a scripted model; live check confirmed the "unavailable" fallback |
| Ollama integration | Done | `apps/ai_assistant/ollama.py` is the only client; model, URL and timeouts from settings; weights are never loaded in Django |
| Frontend | Done | Recommendations (with reasons and click tracking), personalized row, recovery banner, assistant button re-enabled; ops Interventions and Customer Intelligence pages (8 of 9 ops pages moved) |

### Bugs found by this phase's own tests and live run
- `GET /interventions/active/` returned an empty body when nothing was waiting, which would break the frontend; it now returns JSON `null`.
- One fixed rescue template contained the word "off" and was rejected by the safety filter.

### Not done / limits
- The assistant is still the Phase 6 parity version: no structured requirements, comparison or cart actions (Phase 7).
- Intent is scored only when a cart is flagged, not continuously.
- `manage.py run_local_worker` replaces Celery beat locally; real Celery was never run.
- Rescue message wording quality from a real model is untested.

## Phase 7 — Conversational shopping advisor: DONE, language-model parts never run for real

Verified by 245 passing backend tests (45 new for the advisor) and a live browser run on desktop and mobile width: suggested prompt -> explained recommendations -> comparison table -> "add the second one to my cart" -> Confirm; the cart changed only after Confirm (1 -> 2 items), no order was created.

**Design decision:** the parts that must be right every time are rule-based and deterministic (understanding requirements, searching, ranking, comparing, confirmed cart actions). Ollama is only a fallback for open-ended questions, using read-only tools. So the advisor's core works and is tested without a model; what is *not* verified is real-model behaviour on the fallback path.

| Requirement | Status | Where / evidence |
|---|---|---|
| Natural-language requirements | Done | `apps/ai_assistant/requirements.py`: category (everyday synonyms + real category names), budget (under / between / 60k / 1.5 lakh / bare ₹ amounts), brand (from catalogue), usage, ordered priorities, spec minimums (RAM, storage, warranty, battery hours), "X matters more than Y". The brief's four example sentences are tests |
| Requests the catalogue cannot check | Done | e.g. "two days of battery life" is reported as not verifiable (catalogue has mAh / claimed hours) |
| Catalogue-grounded retrieval | Done | `advisor.py` uses the real product search; every card is a database product. Out-of-stock and over-budget items are excluded and counted in the reply |
| Ten named tools | Done | `tools.py`: search_products, get_product_details, filter_by_budget, compare_products, get_product_specifications, get_warranty_information, check_stock, get_similar_products, get_personalized_recommendations, get_customer_purchase_history. All read-only; none takes a user id (history is always the logged-in customer's) |
| Explained recommendations | Done | Each card: fits budget, requirements met, not met, unknown, advantages, limitations, warranty exactly as catalogued ("not available" when missing), stock |
| No invented scores or quality claims | Done | No numeric score. Ranking is lexicographic by the customer's priorities in the order given, ties: fewer unknowns, better-documented, lower price. Numeric priorities are judged against the other options (within 80% of the best). Durability, reliability and gaming suitability are shown as catalogue facts only, never as verdicts |
| Multi-turn context | Done | `Conversation.requirements` persists; priorities can be reordered ("battery matters more than gaming" re-ranks); category change keeps budget; reset; each question asked at most once |
| Comparison | Done | Facts side by side, leader per attribute, explicitly no overall winner |
| Stored conversations | Done | `Conversation`/`Message` models, per logged-in customer; other customers' ids are 404; delete; 200-message cap |
| Add to cart only after confirmation | Done | Pending action (10-minute expiry) executed only by Confirm or "yes"; uses the normal cart service for the customer's own cart. No code path orders or pays. "I want to buy a laptop" is a search, not a cart command |
| UI | Done | Suggested prompts, history picker, "looking for" summary, product cards with expandable reasons, comparison table, Confirm/Cancel bar, loading and error states, full-screen on phones |
| Tracking | Done | RECOMMENDATION_GENERATED (kind `advisor`) and clicks use the existing recommendation tracking |
| Ollama preserved | Done | `ollama.py` unchanged; `llm.py` runs the tool-calling loop for open questions with the conversation state in the prompt; without Ollama the customer gets guidance instead |

### Bugs found by this phase's tests
- Catalogue numbers were `Decimal` and could not be saved in the conversation JSON; now plain numbers.
- A product with no catalogue data could outrank products that have data when no priorities were given; ties now prefer fewer unknowns and better-documented products.
- Word-boundary regexes were silently corrupted by a tooling escape problem and were caught by the "office chair is not an office usage" test.

### Limits
- Guests cannot use the advisor (conversations belong to an account); the old guest `/assistant/chat/` endpoint was removed.
- "Good battery life" is relative to the options found, not an absolute standard, because the catalogue has no basis for one.
- The extractor is keyword based: unusual phrasing may be missed (the customer is then asked, or the model fallback answers if available).
- Catalogue data is sample data; real warranty and service claims need real product metadata.
- Language-model fallback quality, tool-call reliability of the 7B model and phrasing are untested.

## Phase 8 — Demand intelligence: DONE

Verified by 304 passing backend tests (59 new) and a live browser run against 90 days of generated sample history: the dashboard showed each deliberately planted pattern, and the daily chart made the spike obvious.

**Important framing:** this is descriptive statistics with fixed, documented thresholds, **not forecasting**. The only forward-looking number is "days of cover" = stock / recent selling pace, and the page says it assumes that pace continues.

| Requirement | Status | Where / evidence |
|---|---|---|
| Historical product sales; daily, weekly, monthly | Done | `data.py` reads `OrderItem` joined to `Order.objects.successful()`; `GET /demand/products/<id>/` (90 daily points, 13 weeks, 6 months), `GET /demand/sales/?granularity=day|week|month`. Weeks start Monday, days are UTC, today is excluded (incomplete) |
| Only real demand counts | Done | Tests prove cancelled, failed and today's orders are ignored |
| Moving average, percentage change, historical baseline | Done | `statistics.py`: 7-day trailing moving average (chart line), last 7 days vs the previous 28, comparison with the previous week and the usual week |
| Increasing / decreasing demand | Done | Needs a change of at least 25% **and** statistical significance (z >= 2 against normal Poisson week-to-week variation). Found necessary: at about 1 sale a day, swings of +-50% were just noise and steady products flipped between "increasing" and "decreasing" |
| Sudden spikes | Done | Last 3 days: >= 6 units, >= 2x the usual pace, and above mean + 3 standard deviations. Raises one alert and one `DEMAND_SPIKE_DETECTED` event, not repeated while the alert is open, closes itself when the spike ends |
| Sales velocity, stock depletion, stockout identification | Done | Planning velocity = the fastest of recent, baseline and (during a spike) burst pace, the cautious choice. Days of cover, predicted date, risk bands (critical < 7 days, running down < 14) |
| Restocking recommendations | Done | Enough to cover 30 days at the planning pace, urgency urgent/soon, with the arithmetic in plain words. Staff-only `GET /demand/restock/` |
| Kept distinct | Done | Four separately labelled signals: demand spike, demand rising/falling, stock shortage (already at its low-stock level), predicted stockout (will run out soon at the current pace). Tests cover each in isolation |
| Alerts | Done | New alert types DEMAND_SPIKE and STOCKOUT_RISK appear on the existing Alerts page; Celery task every 15 minutes, `manage.py detect_demand`, also in `run_local_worker` |
| Dashboard | Done | Ops "Demand" page: how-to-read panel, counts, spikes, running-out list, restock table, total sales (daily/weekly/monthly), product table with trend/spike/stock-risk badges, and a per-product drill-down with chart, weekly and monthly bars and a history comparison. SVG charts, no new library |
| Analytics page migrated | Done | `GET /analytics/products/` (most viewed / added / searched) and `/analytics/sales/` (average order value, sales by category, checkout drop-off, view-to-purchase) |
| Sample data | Done | `manage.py seed_order_history [--days N] [--seed N] [--replace]`: reproducible, invented orders, ledger and browsing events with planted patterns (rising, falling, spike, about to run out, already low), plus some cancelled and failed orders |

### Bugs found while building this
- Trend labels fired on random noise at low volume (fixed with the significance test above).
- A query alias `name` clashed with `OrderItem.name` and would have broken the Analytics page.
- View-to-purchase showed 0.0% because a logged-in viewer and their own purchase were treated as different customers; matching now uses account or session. Remaining limit: someone who browses anonymously, then logs in before buying, still counts as two customers.

### Limits
- Thresholds (25%, z 2, spike rule, 7-day lead time, 30-day target) are sensible defaults, not tuned to real data, and live as named constants in `statistics.py`.
- Seasonality, promotions and price changes are not modelled.
- Revenue per period uses the price paid on each order line.
- Everything is computed on demand from the orders table (one query for all products); fine at this scale, would want a cache or summary table for a large catalogue.
- Generated history is invented, so the dashboards show demonstration data until real orders accumulate.

## Phase 9 — Operations AI assistant: DONE, language-model path never run for real

Verified by 359 passing backend tests (55 new for this assistant) and a live browser run: a customer was bounced from `/ops/assistant` and received 403 from every endpoint; as an OPERATIONS user the issue summary, a product stock explanation and write requests behaved as designed, and the database was unchanged afterwards.

**Design decision (same as the shopping advisor):** the ten standard questions are routed by rules to read-only tools and the answer text is written straight from the numbers the tools return, so they need no language model and cannot contain a statistic that is not in the data. Ollama is only a fallback for open-ended questions and may only use the same read-only tools.

| Requirement | Status | Where / evidence |
|---|---|---|
| Separate staff-only experience | Done | `apps/ai_assistant/ops_*`, endpoints `/ops-assistant/...`, page **Operations -> Assistant**. Anonymous 401, customer 403, OPERATIONS and ADMIN allowed. The role is read from the database on every request, so a demoted user loses access immediately (tested with a real login token). Conversations are private to their owner and separate from shopping conversations (new `Conversation.kind`) |
| Controlled tools | Done | `get_order_analytics`, `get_inventory_statistics`, `get_demand_trends`, `get_product_performance`, `get_stock_alerts`, `get_sales_history`, `get_system_health`, `get_event_statistics`. Each re-checks that the caller is staff, clamps its arguments, and rejects unknown tool names |
| All figures from real data | Done | Tests compare answers with hand-computed database totals: cancellation rate 20.0% (2 of 10 accepted), top-seller units and revenue, 30-day totals and change vs the previous 30 days, inventory movements by reason. Each answer lists the tools and arguments it used ("Data used") |
| The ten example questions | Done | Sudden demand increase, declining sales, likely to run out, why inventory decreased (overall or for a named product, with follow-ups like "why is it lower?"), restocking, top sellers, demand change over N days, unusual patterns, cancellation rate, operational issues needing attention. Each has a test that it is answered by its tool without a model |
| Read-only | Done | No tool writes. Test: asking all ten questions plus eight write-style requests leaves every key table unchanged. Imperative requests ("cancel order 1", "set the stock to 500", "restock X") get an explicit refusal pointing to the console instead of being mistaken for questions. Any future write action must need confirmation and server-side authorization (documented in `ops_tools.py`) |
| Honest when there is no data | Done | e.g. "No product has a sudden demand increase", "n/a (no orders in the period)"; definitions and periods are stated in the answer |
| Ollama preserved | Done, unverified | `ops_orchestrator.llm_answer`: tool-calling loop with a system prompt requiring every number to come from a tool, max 4 rounds; without Ollama the user gets the list of questions it can answer. Tested against a scripted model only |
| Rate limit, validation | Done | 30 requests/minute, 1000-character questions, 200-message conversations |

### Bugs found while building this
- A pronoun follow-up ("why is it lower?") was not understood without the word "stock"; fixed with a context rule using the product just discussed.
- "Cancel order 1 and refund it" was answered with cancellation statistics (it matched the cancellation-rate rule) without saying it cannot cancel anything; fixed with explicit refusal of action requests.
- Seed data had an incoherent ledger chronology (starting stock dated today, sales dated months ago), which made one stock explanation look contradictory; the seeder now backdates the catalogue's starting stock. Amounts now use Indian digit grouping (₹1,09,43,371) everywhere, including the shopping advisor.
- A shell-escaping problem again corrupted a regex (backslash-b became a control character); found by the follow-up test, repaired, and the codebase scanned for any others.

### Limits
- Question understanding is keyword based; unusual phrasing falls to the model, or to a list of supported questions when Ollama is not running.
- Cancellation rate is defined as cancelled / accepted (paid) orders; the definition is shown with every answer.
- Answers for "this week / this month / last N days" use whole days; today is excluded for demand figures because it is unfinished.
- No audit table yet: each answer's tool use is stored in the conversation message; the central audit log is Phase 10.

## Phase 10 — Hardening, tests, deployment preparation: DONE except items marked unverified

| Task | Status | Evidence |
|---|---|---|
| Audit log | Done | Append-only `audit` app (model refuses update/delete), hooks in accounts, products, categories, inventory, orders, ops assistant; ADMIN-only `/audit/` and an Audit page in the console. 16 tests |
| API security | Done | Default throttles plus tighter login/register/assistant limits; 413 for oversized bodies, 400 for suspicious input, generic 500; production security settings; `check --deploy` shows only the optional HSTS-preload notice |
| Idempotent checkout | Done | `Idempotency-Key` header, unique constraint, replay returns the original order (200); frontend sends a key per payment attempt |
| Query optimisation | Done | Indexes (migrations audit 0001, events 0002, orders 0002, inventory 0003); N+1 query-count tests that fail if a list endpoint starts querying per row (checked by mutation) |
| Backend tests | Done | 402 pass (`pytest`), including a systematic endpoint-permission sweep |
| Frontend tests | Done | 33 Vitest tests: API client (token refresh, shared refresh, error shaping), RequireRole, charts, formatting, idempotency header. Found and fixed a real bug: chart axis ticks had duplicate React keys when the maximum was 1 |
| Docker / compose / nginx | Written, **not built or run** | `docker-compose.yml`, both Dockerfiles, `frontend/nginx.conf`, `deploy/.env.example` (Docker unavailable on this machine) |
| Backup and restore | Done | `scripts/backup_db.sh` now reads `backend/.env`, uses IPv4 and `-w` (the old version hung forever on a password prompt through `localhost`/IPv6). Backup restored into a scratch database: identical counts (9 products, 736 orders, 15 users); scratch DB dropped |
| Documentation | Done | `README.md`, `ARCHITECTURE`, `FEATURE_MATRIX`, `API`, `SECURITY`, `DEPLOYMENT` |

### Not verified (stated plainly)
Real Ollama behaviour; RabbitMQ, Celery and Redis; Docker builds; the model fallback paths of the advisor and ops assistant; no penetration test or dependency vulnerability scan.

### Cleanup (approved by the owner)
The old FastAPI `backend/`, `ops-frontend/` and `tests/characterization/` were removed, and `backend-django` was renamed to `backend`. Earlier sections of this log say `backend-django`/`backend` as they were at the time: in them, "old backend" means the FastAPI code now in git history.


## Real Ollama run (2026-11-11)

Ollama 0.40.16 (Windows) with `qwen2.5-coder:7b` via `OLLAMA_MODEL`; the configured default `qwen2.5:7b-instruct` is not installed. Probe ran inside a rolled-back transaction.

| Path | Result |
|---|---|
| Rescue messages (3 kinds) | Worked, ~3 s each after a 77 s cold load. Messages passed the filter. "Get it now" in one message is mildly urgent - the filter only blocks listed words |
| Advisor free-form question | Worked |
| Advisor tool use | Worked after fix (below). Searched "headphones", truthfully reported none (the catalogue calls them earbuds) |
| Advisor asked to add to cart and order | Did not act; told the user to ask for a cart addition (confirmation flow) |
| Ops assistant open-ended question | Called a tool and answered after fix. Quality is poor: asked for a *category* it answered with a *product*, and amounts lack Indian grouping |

**Bug found:** this model writes tool calls as JSON text instead of `tool_calls`, so the tool loop never ran and raw JSON would have reached users. `ollama.chat` now recovers a message that is exactly one call to an offered tool (5 tests in `test_ollama_client.py`). Ops prompt now says amounts are rupees (the model had written `$`).

Backend suite: 407 passed. Not yet verified: the default model, answer accuracy at scale, RabbitMQ, Celery, Redis.


## Real broker run (2026-11-11)

RabbitMQ 4.4.0 (Erlang 29) and Redis installed in WSL user space through micromamba (`scripts/start_dev_brokers.sh`); Celery 5.7 worker (`--pool=solo`), Celery beat and `run_event_consumer` ran on Windows against them with `EVENT_TRANSPORT=rabbitmq`.

| Check | Result |
|---|---|
| Beat -> Redis -> worker runs the relay every 3 s | Worked |
| Backlog of 16 events left from local-transport days | Delivered in one pass (`sent: 16`) and consumed |
| Real order (COD) through the API | ORDER_CREATED, PAYMENT_SUCCEEDED, INVENTORY_UPDATED, ORDER_COMPLETED each published and consumed once |
| RabbitMQ stopped, order placed | Checkout still returned 201; 4 events stayed in the outbox, attempts rising |
| RabbitMQ restarted | All 4 delivered, exactly one `Event` row each; the consumer reconnected by itself |
| Poison messages (invalid JSON; unknown type) | Dead-lettered with the reason recorded; DLQ depth and unresolved count correct. Test rows removed afterwards |
| Redis as Django cache (`CACHE_URL`) | Round trip works (shared throttle counters) |
| System Health endpoint with the management API | Real queue depths and consumer count |

**Issues found:** the outbox `last_error` was blank during the outage because pika's connection error has an empty message; it now stores the exception type too. WSL RabbitMQ listens on IPv6 loopback only, so Windows must use `[::1]` (documented in the script).

**Still not verified:** more than one worker/consumer, long-running soak, abandoned-cart scan and demand scan firing from beat over hours, Docker. Two probe orders (2926, 2927) remain in the dev database.


## Docker run (2026-11-11)

Docker Desktop would not start: its `AppData/Local/Docker/run` folder held two stale Unix-socket placeholders (`dockerInference`, `userAnalyticsOtlpHttp.sock`) that Windows refuses to delete ("The file cannot be accessed by the system"). Renaming the folder to `run.stale-20261111` let Docker recreate it, and the daemon started. All Docker commands used the CLI.

| Check | Result |
|---|---|
| `docker compose config`, `build` (backend, frontend) | OK |
| Stack: Postgres 17, Redis 7, RabbitMQ 3, web (gunicorn, runs migrate), Celery worker, beat, frontend (nginx on 8080) | Up |
| `/api/health/`, storefront and product list through nginx | OK, seen in the browser |
| Register -> login -> add to cart -> checkout (with idempotency key) -> events consumed | OK: 14 events consumed, outbox pending 0 |
| Customer calling a staff endpoint | 403 |
| Ollama from a container | Reachable at `host.docker.internal:11434` |

**Bugs found only by running Docker (all fixed):**
1. `packaging` was missing from `requirements.txt`; Celery's Redis transport crashed on start in a clean image (it only worked locally by accident).
2. Compose had no service running `run_event_consumer`, so events would never have been processed. Added `consumer`.
3. The compose RabbitMQ URL ended in `//`, which pika reads as an empty vhost; changed to `%2F`.
4. Frontend published on 8080 instead of 80 (80 is often taken).

**Not tested:** TLS, load, several replicas, rolling upgrades, volume backups, the demo-user seeding in containers (intentionally disabled outside DEBUG).
