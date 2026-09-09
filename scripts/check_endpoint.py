#!/usr/bin/env python3
"""
Run this FIRST. It tells you whether your endpoint can actually drive an agent loop.

    python scripts/check_endpoint.py

Everything else in this project depends on the three checks below passing.

The streamed check reuses the same accumulator the server runs on, so a bug in
tool-call reassembly shows up here rather than only in production.
"""

import json
import sys

import httpx

from agent_console.clients.streaming import ToolCallAccumulator, parse_sse_line
from agent_console.config import get_settings

TIMEOUT = 120

PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


def ok(message: str) -> None:
    print(f"  \033[32mPASS\033[0m  {message}")


def bad(message: str, hint: str = "") -> None:
    print(f"  \033[31mFAIL\033[0m  {message}")
    for line in hint.strip().splitlines():
        if line:
            print(f"        {line}")


def check_models(base: str, configured_model: str | None) -> str:
    print("1. Model listing")
    try:
        response = httpx.get(f"{base}/models", timeout=15)
        response.raise_for_status()
        models = [m["id"] for m in response.json().get("data", [])]
    except Exception as exc:
        bad(
            f"cannot reach {base}/models — {exc}",
            "Is the server running and bound to 0.0.0.0 rather than 127.0.0.1?\n"
            "In LM Studio: Developer tab > Settings > Serve on Local Network.",
        )
        sys.exit(1)

    if not models:
        bad("server responded but no model is loaded")
        sys.exit(1)

    ok(f"{len(models)} model(s): {', '.join(models)}")
    model = configured_model or models[0]
    print(f"        testing with: {model}\n")
    return model


def check_unstreamed(base: str, body: dict) -> None:
    print("2. Tool calling (non-streamed)")
    try:
        response = httpx.post(f"{base}/chat/completions", json=body, timeout=TIMEOUT)
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
    except Exception as exc:
        bad(f"request failed — {exc}")
        sys.exit(1)

    calls = message.get("tool_calls")
    if not calls:
        bad(
            "model returned prose instead of a tool_calls array",
            f"content was: {(message.get('content') or '')[:160]!r}\n"
            "Either the server has no tool-call parser configured, or the model\n"
            "wasn't trained for tool use. For vLLM you need:\n"
            "  --enable-auto-tool-choice --tool-call-parser hermes\n"
            "(swap 'hermes' for llama3_json / mistral / pythonic to match your model)",
        )
        sys.exit(1)

    function = calls[0]["function"]
    try:
        arguments = json.loads(function["arguments"])
    except Exception:
        bad(
            f"arguments are not valid JSON: {function['arguments']!r}",
            "Add constrained decoding (vLLM: --guided-decoding-backend xgrammar).",
        )
        sys.exit(1)
    ok(f"called {function['name']}({arguments})")


def check_streamed(base: str, body: dict) -> None:
    print("\n3. Tool calling (streamed)")
    accumulator = ToolCallAccumulator()
    streamed_text = ""

    try:
        with httpx.stream("POST", f"{base}/chat/completions", json=body, timeout=TIMEOUT) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                delta = parse_sse_line(line)
                if delta is None:
                    continue
                streamed_text += delta.get("content") or ""
                accumulator.add(delta.get("tool_calls"))
    except Exception as exc:
        bad(f"stream failed — {exc}")
        sys.exit(1)

    if not accumulator:
        bad(
            "no tool_calls in the stream, though the non-streamed call worked",
            f"streamed content was: {streamed_text[:160]!r}\n"
            "Some servers only parse tool calls when stream=False. If so, run the\n"
            "agent loop non-streamed and stream only the final answer.",
        )
        sys.exit(1)

    for call in accumulator.result():
        try:
            json.loads(call.function.arguments)
        except Exception:
            bad(f"streamed arguments never became valid JSON: {call.function.arguments!r}")
            sys.exit(1)
        ok(f"streamed {call.function.name}({call.function.arguments})")


def main() -> None:
    settings = get_settings()
    base = settings.upstream
    print(f"\nEndpoint: {base}\n")

    model = check_models(base, settings.model)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "What's the weather in Amman right now?"}],
        "tools": [PROBE_TOOL],
        "tool_choice": "auto",
        "stream": False,
    }

    check_unstreamed(base, body)
    check_streamed(base, {**body, "stream": True})

    print("\nAll three passed. Start the server:  fastapi run\n")


if __name__ == "__main__":
    main()
