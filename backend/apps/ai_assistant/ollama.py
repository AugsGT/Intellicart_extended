"""The only place that talks to Ollama (a separate local server; model weights
are never loaded inside Django). Everything else calls chat()."""
import json
import urllib.error
import urllib.request

from django.conf import settings


class OllamaUnavailable(Exception):
    """Ollama is not running, timed out, or answered with something unusable."""


def chat(messages: list[dict], tools: list[dict] | None = None, timeout: int | None = None) -> dict:
    """One /api/chat call (non-streaming). Returns Ollama's JSON response."""
    body = {"model": settings.OLLAMA_MODEL, "stream": False, "messages": messages}
    if tools:
        body["tools"] = tools
    request = urllib.request.Request(
        f"{settings.OLLAMA_URL.rstrip('/')}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout or settings.OLLAMA_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, OSError) as error:
        raise OllamaUnavailable(str(error)) from error
    if tools:
        _recover_text_tool_call(result, {t["function"]["name"] for t in tools})
    return result


def _recover_text_tool_call(result: dict, known_tools: set[str]) -> None:
    """Some models (seen with qwen2.5-coder) write the tool call as JSON text in `content`
    instead of returning `tool_calls`. Without this the customer would be shown raw JSON.
    Only a message that is exactly one call to a tool we offered is converted."""
    message = result.get("message") or {}
    if message.get("tool_calls"):
        return
    try:
        data = json.loads((message.get("content") or "").strip())
    except ValueError:
        return
    if isinstance(data, dict) and data.get("name") in known_tools and isinstance(data.get("arguments", {}), dict):
        message["tool_calls"] = [{"function": {"name": data["name"], "arguments": data.get("arguments", {})}}]
        message["content"] = ""
