"""Tunn klient mot Ollama (lokalt). Räknar tokens och tid per anrop för systempanelen och tokenredovisningen."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import settings


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    per_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, model: str, p: int, o: int, s: float) -> None:
        self.calls += 1
        self.prompt_tokens += p
        self.output_tokens += o
        self.seconds += s
        m = self.per_model.setdefault(model, {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "seconds": 0.0})
        m["calls"] += 1
        m["prompt_tokens"] += p
        m["output_tokens"] += o
        m["seconds"] += s

    def as_dict(self) -> dict[str, Any]:
        return {"calls": self.calls, "prompt_tokens": self.prompt_tokens, "output_tokens": self.output_tokens,
                "seconds": round(self.seconds, 2), "per_model": self.per_model}


# Totalräknare sedan start, för tokenredovisningen i tävlingsbidraget.
total_usage = Usage()
_lock = threading.Lock()
_client = httpx.Client(base_url=settings.ollama_url, timeout=httpx.Timeout(600, connect=5))


@dataclass
class Reply:
    content: str
    tool_calls: list[dict[str, Any]]
    message: dict[str, Any]
    prompt_tokens: int
    output_tokens: int
    seconds: float
    tokens_per_s: float


def chat(model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
         think: bool = False, temperature: float = 0.3, num_ctx: int = 8192,
         usage: Usage | None = None, fmt: dict[str, Any] | None = None, max_tokens: int = 900) -> Reply:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": max_tokens},
    }
    if tools:
        body["tools"] = tools
    if fmt:
        body["format"] = fmt  # strukturerad utdata enligt JSON-schema
    t0 = time.time()
    r = _client.post("/api/chat", json=body)
    if r.status_code >= 500:
        body["options"]["num_predict"] = max_tokens * 2
        r = _client.post("/api/chat", json=body)
    r.raise_for_status()
    d = r.json()
    dt = time.time() - t0
    msg = d.get("message", {})
    p, o = int(d.get("prompt_eval_count", 0)), int(d.get("eval_count", 0))
    eval_s = d.get("eval_duration", 0) / 1e9 or dt
    with _lock:
        total_usage.add(model, p, o, dt)
        if usage is not None:
            usage.add(model, p, o, dt)
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        calls.append({"name": fn.get("name", ""), "arguments": args})
    return Reply(content=msg.get("content", "") or "", tool_calls=calls, message=msg,
                 prompt_tokens=p, output_tokens=o, seconds=dt, tokens_per_s=o / eval_s if eval_s else 0.0)


def loaded_models() -> list[dict[str, Any]]:
    try:
        return _client.get("/api/ps", timeout=5).json().get("models", [])
    except Exception:
        return []
