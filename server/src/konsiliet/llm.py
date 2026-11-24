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

    def add(self, model: str, p: int, o: int, s: float, p_s: float = 0.0, o_s: float = 0.0) -> None:
        self.calls += 1
        self.prompt_tokens += p
        self.output_tokens += o
        self.seconds += s
        m = self.per_model.setdefault(model, {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "seconds": 0.0,
                                              "prompt_eval_s": 0.0, "eval_s": 0.0})
        m["prompt_eval_s"] += p_s
        m["eval_s"] += o_s
        m["gen_tokens_per_s"] = round((m["output_tokens"] + o) / m["eval_s"], 1) if m["eval_s"] else 0.0
        m["prompt_tokens_per_s"] = round((m["prompt_tokens"] + p) / m["prompt_eval_s"], 1) if m["prompt_eval_s"] else 0.0
        m["calls"] += 1
        m["prompt_tokens"] += p
        m["output_tokens"] += o
        m["seconds"] += s

    def as_dict(self) -> dict[str, Any]:
        return {"calls": self.calls, "prompt_tokens": self.prompt_tokens, "output_tokens": self.output_tokens,
                "seconds": round(self.seconds, 2), "per_model": self.per_model}


SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    ts REAL NOT NULL, model TEXT NOT NULL, prompt_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
    prompt_s REAL NOT NULL, eval_s REAL NOT NULL, seconds REAL NOT NULL, consult_id TEXT);
CREATE INDEX IF NOT EXISTS llm_calls_ts ON llm_calls(ts);
"""


class _Totalt(Usage):
    """Totalräknare för tokenredovisningen. Läses ur tabellen llm_calls så att den överlever omstart."""

    def as_dict(self) -> dict[str, Any]:
        try:
            from . import db
            c = db.conn()
            c.executescript(SCHEMA)
            rows = c.execute("SELECT model, COUNT(*), SUM(prompt_tokens), SUM(output_tokens), SUM(seconds), "
                             "SUM(prompt_s), SUM(eval_s) FROM llm_calls GROUP BY model").fetchall()
        except Exception:
            return super().as_dict()
        pm = {r[0]: {"calls": r[1], "prompt_tokens": r[2], "output_tokens": r[3], "seconds": round(r[4], 2),
                     "prompt_eval_s": round(r[5], 2), "eval_s": round(r[6], 2),
                     "gen_tokens_per_s": round(r[3] / r[6], 1) if r[6] else 0.0,
                     "prompt_tokens_per_s": round(r[2] / r[5], 1) if r[5] else 0.0} for r in rows}
        return {"calls": sum(v["calls"] for v in pm.values()), "prompt_tokens": sum(v["prompt_tokens"] for v in pm.values()),
                "output_tokens": sum(v["output_tokens"] for v in pm.values()),
                "seconds": round(sum(v["seconds"] for v in pm.values()), 2), "per_model": pm}


def _logga(model: str, p: int, o: int, p_s: float, o_s: float, s: float) -> None:
    try:
        from . import db
        with db.tx() as c:
            c.executescript(SCHEMA)
            c.execute("INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?,?)",
                      (time.time(), model, p, o, p_s, o_s, s, getattr(kontext, "consult_id", None)))
    except Exception:
        pass  # tokenloggen får aldrig stoppa ett möte


# Totalräknare sedan start, för tokenredovisningen i tävlingsbidraget.
total_usage = _Totalt()
kontext = threading.local()  # consult_id för loggen sätts av konsiliet
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
    try:
        r = _client.post("/api/chat", json=body)
    except httpx.TimeoutException:
        r = _client.post("/api/chat", json=body)  # ett nytt försök, t.ex. om modellen laddades om
    if r.status_code >= 500:
        body["options"]["num_predict"] = max_tokens * 2
        r = _client.post("/api/chat", json=body)
    r.raise_for_status()
    d = r.json()
    dt = time.time() - t0
    msg = d.get("message", {})
    p, o = int(d.get("prompt_eval_count", 0)), int(d.get("eval_count", 0))
    eval_s = d.get("eval_duration", 0) / 1e9 or dt
    prompt_s = d.get("prompt_eval_duration", 0) / 1e9
    with _lock:
        total_usage.add(model, p, o, dt, prompt_s, eval_s)
        if usage is not None:
            usage.add(model, p, o, dt, prompt_s, eval_s)
    _logga(model, p, o, prompt_s, eval_s, dt)
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


MAX_MINNE_GIB = 11.0  # qwen3.5:9b tar 8,3 GiB nyladdad men växte till 15,4 GiB under en lång körning (swap)


def lasta_ur_om_for_stor(grans_gib: float = MAX_MINNE_GIB) -> list[str]:
    """Laddar ur modeller som vuxit över gränsen. Nästa anrop laddar om dem rena (några sekunder)
    i stället för att datorn swappar i minuter. Anropas efter varje konsilium."""
    ur = []
    for m in loaded_models():
        if m.get("size_vram", 0) / 2**30 > grans_gib:
            try:
                _client.post("/api/generate", json={"model": m["name"], "keep_alive": 0}, timeout=60)
                ur.append(m["name"])
            except Exception:
                pass
    return ur


def loaded_models() -> list[dict[str, Any]]:
    try:
        return _client.get("/api/ps", timeout=5).json().get("models", [])
    except Exception:
        return []
