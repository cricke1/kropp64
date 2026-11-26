"""Översättande proxy: Ollamas API -> llama.cpp:s llama-server (OpenAI-kompatibelt API).

Varför den finns: för jämförelsen Apple M4 mot RTX 5050 skulle samma pipeline och modell köras på
Lenovons grafikkort. Ollama för Windows (0.40.16/0.40.18) gick inte att använda där: nedladdningar
sade "success" men /api/tags förblev tom ("bad manifest ... cannot find the path specified") och
"ollama create" gav "invalid model name". I stället körs llama-server (ggml-org/llama.cpp, officiellt
Windows-CUDA-bygge) på Lenovon, och den här proxyn låter appens oförändrade klient (server/src/
konsiliet/llm.py, som talar Ollamas eget API) prata med den. Appkoden ändras alltså inte.

Översättning:
    POST /api/chat      -> POST /v1/chat/completions
        think=false     -> chat_template_kwargs.enable_thinking=false
        options         -> temperature, max_tokens (num_predict). num_ctx sätts på servern (-c 8192).
        format (schema) -> response_format {type: json_schema}
        tools           -> tools (samma form), tool_calls tillbaka med argument som objekt
        timings         -> prompt_eval_count/eval_count och *_duration i nanosekunder
    GET  /api/ps        -> modellen som llama-server har laddad (size_vram okänt här, 0)
    POST /api/generate {keep_alive: 0} -> ingen åtgärd (llama-server har modellen laddad hela tiden)
    GET  /api/tags, /api/version -> enkla svar så att hälsokontroller fungerar

Varje chat-anrop loggas som en JSON-rad (--logg) med llama-servers råa timings, så att prompt- och
genereringshastighet kan räknas ut efteråt.

    python3 eval/ollama_proxy.py --upstream http://100.110.236.58:8080 --port 11500 --modell qwen3.5:9b
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

A: argparse.Namespace
_logglas = threading.Lock()


def _till_openai(body: dict[str, Any]) -> dict[str, Any]:
    msgs: list[dict[str, Any]] = []
    vantande: list[str] = []  # id:n för tool_calls som ännu inte fått svar, i ordning
    n = 0
    for m in body.get("messages", []):
        roll = m.get("role")
        if roll == "assistant" and m.get("tool_calls"):
            tcs = []
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                n += 1
                tid = tc.get("id") or f"call_{n}"
                vantande.append(tid)
                tcs.append({"id": tid, "type": "function", "function": {
                    "name": fn.get("name", ""),
                    "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}})
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": tcs})
        elif roll == "tool":
            tid = m.get("tool_call_id") or (vantande.pop(0) if vantande else f"call_{n + 1}")
            msgs.append({"role": "tool", "tool_call_id": tid, "content": m.get("content", "")})
        else:
            msgs.append({"role": roll, "content": m.get("content", "")})
    opt = body.get("options") or {}
    ut: dict[str, Any] = {"model": body.get("model", ""), "messages": msgs, "stream": False,
                          "chat_template_kwargs": {"enable_thinking": bool(body.get("think", False))}}
    if "temperature" in opt:
        ut["temperature"] = opt["temperature"]
    if opt.get("num_predict"):
        ut["max_tokens"] = opt["num_predict"]
    if body.get("tools"):
        ut["tools"] = body["tools"]
    fmt = body.get("format")
    if isinstance(fmt, dict):
        ut["response_format"] = {"type": "json_schema", "json_schema": {"name": "svar", "schema": fmt}}
    elif fmt == "json":
        ut["response_format"] = {"type": "json_object"}
    return ut


def _till_ollama(model: str, d: dict[str, Any]) -> dict[str, Any]:
    ch = (d.get("choices") or [{}])[0]
    m = ch.get("message") or {}
    msg: dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
    if m.get("reasoning_content"):
        msg["thinking"] = m["reasoning_content"]
    if m.get("tool_calls"):
        tcs = []
        for tc in m["tool_calls"]:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    pass  # llm.py tar hand om strängar som inte är JSON
            tcs.append({"id": tc.get("id"), "function": {"name": fn.get("name", ""), "arguments": args}})
        msg["tool_calls"] = tcs
    t = d.get("timings") or {}
    u = d.get("usage") or {}
    return {
        "model": model, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": msg,
        "done": True, "done_reason": ch.get("finish_reason", "stop"),
        # Totalt antal prompttokens (som tokenredovisningen vill ha); durationen gäller de tokens som
        # faktiskt beräknades (prompt_n, resten kom från prefix-cachen). Råvärdena finns i loggen.
        "prompt_eval_count": int(u.get("prompt_tokens", t.get("prompt_n", 0))),
        "eval_count": int(u.get("completion_tokens", t.get("predicted_n", 0))),
        "prompt_eval_duration": int(float(t.get("prompt_ms", 0)) * 1e6),
        "eval_duration": int(float(t.get("predicted_ms", 0)) * 1e6),
        "total_duration": int((float(t.get("prompt_ms", 0)) + float(t.get("predicted_ms", 0))) * 1e6),
    }


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a: Any) -> None:
        pass

    def _svara(self, kod: int, data: Any) -> None:
        b = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self) -> None:
        if self.path.startswith("/api/ps"):
            self._svara(200, {"models": [{"name": A.modell, "model": A.modell, "size_vram": 0}]})
        elif self.path.startswith("/api/tags"):
            self._svara(200, {"models": [{"name": A.modell, "model": A.modell}]})
        elif self.path.startswith("/api/version"):
            self._svara(200, {"version": "proxy-llama.cpp"})
        else:
            self._svara(404, {"error": "okänd väg"})

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path.startswith("/api/generate"):
            self._svara(200, {"model": body.get("model", ""), "response": "", "done": True})
            return
        if not self.path.startswith("/api/chat"):
            self._svara(404, {"error": "okänd väg"})
            return
        req = _till_openai(body)
        t0 = time.time()
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                A.upstream + "/v1/chat/completions", data=json.dumps(req).encode(),
                headers={"Content-Type": "application/json"}), timeout=900)
            d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            fel = e.read().decode(errors="replace")[:2000]
            self._logga({"ts": t0, "fel": e.code, "text": fel})
            self._svara(500 if e.code >= 500 else e.code, {"error": fel})
            return
        except Exception as e:
            self._logga({"ts": t0, "fel": str(e)})
            self._svara(502, {"error": str(e)})
            return
        self._logga({"ts": t0, "s": round(time.time() - t0, 2), "modell": body.get("model"),
                     "timings": d.get("timings"), "usage": d.get("usage"),
                     "finish": (d.get("choices") or [{}])[0].get("finish_reason")})
        self._svara(200, _till_ollama(body.get("model", ""), d))

    def _logga(self, rad: dict[str, Any]) -> None:
        if A.logg:
            with _logglas, open(A.logg, "a") as f:
                f.write(json.dumps(rad, ensure_ascii=False) + "\n")


def main() -> None:
    global A
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", default="http://100.110.236.58:8080")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=11500)
    ap.add_argument("--modell", default="qwen3.5:9b")
    ap.add_argument("--logg", default="")
    A = ap.parse_args()
    ThreadingHTTPServer((A.host, A.port), H).serve_forever()


if __name__ == "__main__":
    main()
