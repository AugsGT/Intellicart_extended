# Intellicart — AI Architecture (baseline)

## What exists

| Component | File | How it works | Honest label |
|---|---|---|---|
| Intent score | `backend/app/services/intent.py` | Weighted sum of event counts per session (views ×2 cap 10, searches ×1 cap 5, cart adds ×5, checkout +15, returning customer +10). HIGH ≥ 40, MEDIUM ≥ 15. Every run is stored with its `basis`. | Rule-based, explainable. Not a model. |
| Rescue engine | `backend/app/services/rescue_engine.py` | Context (cart value, stock, views, checkout started, prior abandonments, intent tier) → ordered rule table → one `interventions` row per decision. Also back-in-stock notices from `STOCK_RESTOCKED`. | Rule-based. Messages are fixed strings. |
| Abandonment detection | `backend/abandonment_scanner.py` | Cart idle for `CART_ABANDONMENT_MINUTES` (default 15), measured from the newest cart item, de-duplicated with `cart.abandonment_flagged_at`. | Timer-based. |
| Recommendations | `backend/app/services/recommendations.py` | Same-category similar items, co-purchase counts, in-stock substitutes ranked by price closeness, recently viewed, cart-category suggestions. | Rule-based. Co-purchase wrongly includes failed/cancelled orders. |
| Shopping assistant | `backend/app/services/shopping_assistant.py`, `api/assistant.py`, `frontend/src/components/ShoppingAssistant.tsx` | Calls Ollama `/api/chat` (`qwen2.5:7b-instruct`) with 4 read-only tools: `search_products`, `get_product_details`, `get_similar_products`, `get_cart_recommendations`. Up to 4 tool rounds. Client sends the history on each request. Returns the reply plus a tool log. | Real LLM tool calling, but stateless and narrow. |

## Settings (already in `app/config.py`)

`OLLAMA_URL` (default `http://localhost:11434`), `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS` (30), `CART_ABANDONMENT_MINUTES`.

## Design rules worth keeping

- The model never touches the database; it calls fixed tools and the tool results are the only source of prices, stock and names (system prompt rule).
- Tools are read-only.
- Each rescue decision stores the signals and rule that produced it.
- Ollama runs as a separate server, never inside the web process.

## Known problems

- `/assistant/chat` is open to anyone who sends an `X-Session-Id`; the conversation lives only in the browser.
- The assistant does not extract structured requirements, compare products or act on the cart.
- No product attributes exist, so warranty, battery and similar questions cannot be answered from data.
- No tests, including no check that replies stay grounded in tool results.
- Rescue copy mentions discounts and reservations that the business logic does not provide.

## Carry-over plan

The rule tables, intent weights and Ollama call carry over as plain Python into Django app modules (`recommendations`, `customer_intelligence`, `interventions`, `ai_assistant`) with their ORM queries rewritten. The behavior is kept until Phase 6 verifies parity; improvements come after (Phases 7 and 9).


## Shopping advisor (Django, Phase 7)

```
customer message
   -> orchestrator (apps/ai_assistant/orchestrator.py)
        confirm / cancel a pending cart action        (deterministic)
        add to cart -> PROPOSE only, wait for Confirm (deterministic)
        compare / details of products already shown   (deterministic)
        requirements.extract + merge -> ask, or recommend
              advisor.recommend: search real products -> check each against the
              requirements -> rank by priorities in order -> explain from catalogue data
        anything else -> llm.answer (Ollama + read-only tools), or guidance if Ollama is down
   -> saved Message with cards / comparison / pending_action
```

Rules enforced in code: the advisor never orders or pays; the cart changes only after the customer confirms; tools are read-only and never take a user id; all state belongs to the logged-in customer; subjective qualities are reported as catalogue facts, never as verdicts; missing data is reported as missing.


## Operations assistant (Django, Phase 9)

```
staff question
   -> permission: ADMIN or OPERATIONS (role read from the database on every request)
   -> ops_orchestrator
        imperative request ("cancel order 1")  -> plain refusal, nothing looked up
        standard question (10 rules)           -> read-only tool(s) -> answer text built from the returned numbers + a table
        pronoun follow-up about a product      -> inventory explanation for that product
        anything else                          -> llm_answer: Ollama with the same read-only tools, or the list of supported questions
   -> saved Message with the table and the tools used
```

Tools (`ops_tools.py`): order analytics, inventory statistics, demand trends, product performance, stock alerts, sales history, system health, event statistics. None can write. Every answer states its period and definition and lists the tools it used.
