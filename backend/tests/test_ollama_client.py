"""The Ollama client, with the HTTP call replaced by a canned response."""
import io
import json
import urllib.request

from apps.ai_assistant import ollama

TOOLS = [{"type": "function", "function": {"name": "search_products", "parameters": {}}}]


def fake_server(monkeypatch, message):
    body = json.dumps({"message": message}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: io.BytesIO(body))


def test_a_structured_tool_call_is_left_alone(monkeypatch):
    call = {"function": {"name": "search_products", "arguments": {"category": "tv"}}}
    fake_server(monkeypatch, {"role": "assistant", "content": "", "tool_calls": [call]})
    assert ollama.chat([], tools=TOOLS)["message"]["tool_calls"] == [call]


def test_a_tool_call_written_as_text_is_recovered(monkeypatch):
    fake_server(monkeypatch, {"role": "assistant", "content": '{"name": "search_products", "arguments": {"category": "tv"}}'})
    message = ollama.chat([], tools=TOOLS)["message"]
    assert message["tool_calls"] == [{"function": {"name": "search_products", "arguments": {"category": "tv"}}}]
    assert message["content"] == ""          # the customer never sees the raw JSON


def test_json_for_a_tool_we_did_not_offer_is_ordinary_text(monkeypatch):
    fake_server(monkeypatch, {"role": "assistant", "content": '{"name": "delete_everything", "arguments": {}}'})
    message = ollama.chat([], tools=TOOLS)["message"]
    assert "tool_calls" not in message


def test_normal_prose_is_untouched(monkeypatch):
    fake_server(monkeypatch, {"role": "assistant", "content": "SSDs are faster than HDDs."})
    message = ollama.chat([], tools=TOOLS)["message"]
    assert message["content"] == "SSDs are faster than HDDs." and "tool_calls" not in message


def test_without_tools_nothing_is_converted(monkeypatch):
    fake_server(monkeypatch, {"role": "assistant", "content": '{"name": "search_products", "arguments": {}}'})
    assert "tool_calls" not in ollama.chat([])["message"]
