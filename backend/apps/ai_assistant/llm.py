"""Language-model fallback for questions the rule-based advisor cannot classify
("does it have a good keyboard?", "why did you rank that first?").

The model works through the read-only tools in tools.py and is told what the
conversation has established. If Ollama is not running the caller shows a helpful
message instead; nothing else depends on the model.
"""
import json
import logging

from apps.ai_assistant import ollama, requirements, tools
from apps.ai_assistant.models import Conversation

logger = logging.getLogger("intellicart.assistant")

MAX_TOOL_ROUNDS = 4
HISTORY_TURNS = 10
UNAVAILABLE = "I can't answer that open-ended question right now because the language model is not available."
GIVE_UP = "I could not settle on an answer to that. Could you rephrase it, or tell me the product type, budget and what matters most?"

SYSTEM_PROMPT = (
    "You are Intellicart's shopping advisor. Prices are in Indian Rupees (INR).\n"
    "Rules:\n"
    "- State a price, stock level, specification, warranty or product name ONLY if it came back from a tool call. "
    "Never invent or guess one.\n"
    "- If the catalogue does not say something (for example a warranty or battery life in days), say it is not available.\n"
    "- Do not call a product 'the best' or 'reliable' or 'durable' unless a tool result supports it; report facts instead.\n"
    "- You cannot add to a cart, place orders or take payments. If asked, tell the customer to ask to add an item "
    "to their cart, which they will then be asked to confirm.\n"
    "- Keep replies short and concrete."
)


def _context(conversation: Conversation) -> str:
    state = conversation.requirements or {}
    lines = [f"What the customer has told us so far: {requirements.describe(state)}."]
    labels = requirements.priority_labels(state)
    if labels:
        lines.append("Their priorities, most important first: " + ", ".join(labels) + ".")
    if conversation.last_results:
        from apps.products.models import Product

        names = dict(Product.objects.filter(id__in=conversation.last_results).values_list("id", "name"))
        shown = [f"{i + 1}. {names[pid]} (id {pid})" for i, pid in enumerate(conversation.last_results) if pid in names]
        lines.append("Products currently shown to the customer, in order: " + "; ".join(shown) + ".")
    return "\n".join(lines)


def answer(user, conversation: Conversation, text: str) -> str | None:
    """Answer with the tool-calling loop. Returns None if the model is unavailable."""
    previous = list(conversation.messages.order_by("-id")[:HISTORY_TURNS])[::-1]
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _context(conversation)}]
    messages += [{"role": m.role, "content": m.content} for m in previous if m.content]
    messages.append({"role": "user", "content": text})

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = ollama.chat(messages, tools=tools.TOOLS)
        except ollama.OllamaUnavailable:
            logger.warning("Ollama is unavailable")
            return None

        reply = response.get("message", {})
        calls = reply.get("tool_calls") or []
        if not calls:
            return (reply.get("content") or "").strip() or GIVE_UP

        messages.append(reply)
        for call in calls:
            function = call.get("function", {})
            name, args = function.get("name"), function.get("arguments") or {}
            result = tools.dispatch(name, args, user=user)
            messages.append({"role": "tool", "content": json.dumps(result), "tool_call_id": call.get("id", name)})
    return GIVE_UP
