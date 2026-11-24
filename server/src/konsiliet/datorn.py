"""Datorkopplingen. Mac minin loggar när jag sitter vid den och vilket slags program som är i fokus.

Varje minut sparas en mätpunkt per aktiv kategori: dator_kod, dator_spel, dator_chatt, dator_webb,
dator_annat (värde 1 = aktiv den minuten). Då kan teamet se puls och HRV under kodpass och spelkvällar.
Inget lämnar datorn och inga fönstertitlar eller innehåll sparas, bara kategorin.

Kräver inga extra behörigheter: ioreg för inaktivitetstid och lsappinfo för programmet i fokus.
"""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import time

from . import db

log = logging.getLogger("datorn")

KATEGORIER = {
    "kod": ("terminal", "iterm", "code", "cursor", "claude", "xcode", "zed", "pycharm", "intellij", "warp",
            "ghostty", "antigravity", "android studio", "sublime"),
    "spel": ("steam", "minecraft", "league", "battle.net", "epic", "crossover", "parallels", "geforce", "moonlight"),
    "chatt": ("discord", "messages", "meddelanden", "slack", "telegram", "whatsapp", "signal"),
    "webb": ("chrome", "safari", "firefox", "arc", "brave", "edge"),
}
AKTIV_GRANS_S = 120  # räknas som vid datorn om tangentbord/mus använts senaste 2 minuterna


def _idle_seconds() -> float:
    out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True).stdout
    m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
    return int(m.group(1)) / 1e9 if m else 1e9


def _front_app() -> str:
    front = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True).stdout.strip()
    out = subprocess.run(["lsappinfo", "info", "-only", "name", front], capture_output=True, text=True).stdout
    m = re.search(r'"LSDisplayName"\s*=\s*"([^"]+)"', out)
    return m.group(1) if m else ""


def kategori(app: str) -> str:
    a = app.lower()
    for kat, nycklar in KATEGORIER.items():
        if any(n in a for n in nycklar):
            return kat
    return "annat"


def _loop() -> None:
    while True:
        try:
            if _idle_seconds() < AKTIV_GRANS_S:
                kat = kategori(_front_app())
                minut = int(time.time() // 60 * 60)
                db.insert_samples([(minut, f"dator_{kat}", 1.0, "macmini")])
        except Exception:
            log.exception("datorloggning")
        time.sleep(60)


_started = False


def start() -> None:
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_loop, name="datorn", daemon=True).start()
