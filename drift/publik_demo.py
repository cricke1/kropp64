"""ASGI-app för den publika demon. Startas av drift/publik-demo.sh, aldrig direkt mot den riktiga databasen.

Samma serverkod som den riktiga instansen, men:
  - egen engångsdatabas (KONSILIET_DB sätts av skriptet) med syntetisk data från web/dev/ingest.mjs
  - vakt, rutiner och datorkopplingen startas inte
  - språkmodellen går inte att anropa (llm.chat kastar fel), så ingen kan starta ett konsilium på Mac minin
  - webben serveras från web/dist-demo (byggd med KONSILIET_PUBLIK_DEMO=1, låst i demoläge)
  - utifrån (via tunnel) går bara läsande GET mot ett fåtal endpoints. WebSocket är stängd.
  - POST /api/ingest* tas bara emot från localhost utan tunnelheader, för att fylla på demodatan
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DB = os.environ.get("KONSILIET_DB", "")
if not DB or os.path.realpath(os.path.expanduser(DB)) == os.path.realpath(os.path.expanduser("~/.konsiliet/konsiliet.db")):
    raise SystemExit("Publik demo vägrar starta utan egen databas (KONSILIET_DB). Använd drift/publik-demo.sh.")
if os.environ.get("KONSILIET_DATORN", "1") != "0":
    raise SystemExit("Publik demo kräver KONSILIET_DATORN=0.")

from konsiliet import api, datorn, llm, rutiner, vakt  # noqa: E402


def _avstangd(*_a, **_k):
    raise RuntimeError("Språkmodellen är avstängd i den publika demon.")


llm.chat = _avstangd
vakt.start = lambda: None
rutiner.start = lambda: None
datorn.start = lambda: None

# Behörigheten ersätts av vitlistan nedan. Allt som släpps igenom är läsande och visar bara demodatan.
api.app.dependency_overrides[api.auth] = lambda: None

WEB = Path(__file__).resolve().parents[1] / "web" / "dist-demo"
if not (WEB / "index.html").exists():
    raise SystemExit(f"Saknar {WEB}. Kör: cd web && npm run build:demo")

from fastapi.staticfiles import StaticFiles  # noqa: E402

api.app.router.routes = [r for r in api.app.router.routes if getattr(r, "name", None) != "web"]
api.app.mount("/", StaticFiles(directory=WEB, html=True), name="web-demo")

LASA = re.compile(r"^/api/(health|metrics|series/[a-z0-9_]+|sleep|events|journal|aterhamtning|datorn|system)$")
FYLLA = re.compile(r"^/api/ingest(/sleep)?$")


def _lokal(scope) -> bool:
    host = (scope.get("client") or ("", 0))[0]
    headers = {k.decode().lower() for k, _ in scope.get("headers", [])}
    return host in ("127.0.0.1", "::1") and "cf-connecting-ip" not in headers


async def _nej(send, status: int, text: str) -> None:
    body = json.dumps({"detail": text}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


async def app(scope, receive, send):
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 4403})
        return
    if scope["type"] == "http":
        path, method = scope["path"], scope["method"]
        if path.startswith("/api") or path == "/ws":
            if method in ("GET", "HEAD") and LASA.match(path):
                pass
            elif method == "POST" and FYLLA.match(path) and _lokal(scope):
                pass
            else:
                await _nej(send, 403, "Inte tillgängligt i den publika demon.")
                return
    await api.app(scope, receive, send)
