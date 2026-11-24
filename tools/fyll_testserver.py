"""SYNTETISK TESTDATA till en SEPARAT testserver (aldrig den riktiga på port 8790).

  cd server && KONSILIET_DB=/tmp/kropp64-test.db KONSILIET_TILLAT_EMULATOR=1 KONSILIET_DATORN=0 \\
      uv run uvicorn konsiliet.api:app --host 0.0.0.0 --port 8801
  python3 tools/fyll_testserver.py --url http://127.0.0.1:8801

Datan beskrivs i tools/syntetisk_person.py. Källan är "syntetisk-vecka" och syns som testdata överallt.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import syntetisk_person as person  # noqa: E402


def post(url: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="testserverns adress, t.ex. http://127.0.0.1:8801")
    a = ap.parse_args()
    url = a.url.rstrip("/")
    if url.endswith(":8790"):
        sys.exit("Port 8790 är den riktiga servern. Syntetisk data får bara gå till en testserver.")
    nu = time.time()
    g = person.generera(nu)
    for s in g["sleep"]:
        post(url, "/api/ingest/sleep", s)
    for e in g["exercise"]:
        post(url, "/api/ingest/exercise", {**e, "end": None})
        post(url, "/api/ingest/exercise", e)
    rows = [{"ts": t, "metric": m, "value": v} for t, m, v in g["samples"]]
    n = 0
    for i in range(0, len(rows), 15000):
        n += post(url, "/api/ingest", {"source": person.KALLA, "samples": rows[i:i + 15000]})["stored"]
    print(f"{n} punkter, {len(g['sleep'])} sömnpass, {len(g['exercise'])} pass till {url} (källa {person.KALLA})")


if __name__ == "__main__":
    main()
