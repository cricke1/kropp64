"""Rösttjänsten på Lenovon: Parambe (Chatterbox Multilingual med svenska vikter) på RTX 5050.

Mac minin har 16 GB och språkmodellen tar runt 9, så de tunga rösterna görs på Lenovons grafikkort.
Allt stannar i hemnätet. Tjänsten är medvetet snål med vad den gör, eftersom den kan få en klonad röst
att säga saker:

  - lyssnar bara på Lenovons Tailscale-adress (--lyssna), aldrig 0.0.0.0 eller LAN
  - tar bara emot anrop från Mac minins Tailscale-adress (--tillat)
  - kräver en delad hemlighet i X-Rost-Hemlighet (fil utanför repot, jämförs i konstant tid)
  - bara röster ur röstbanken, högst 600 tecken per anrop, högst 3 jobb i kö (annars 503)
  - ingen fri text kommer hit från internet: Mac minin skickar bara repliker som redan finns i dess
    händelselogg (GET /api/rost/{event_id}), aldrig text från en klient

Start på Lenovon (miljön med chatterbox-tts 0.1.7 finns redan):
  set HF_HUB_OFFLINE=1
  parambe\\Scripts\\python.exe rost_tjanst.py --lyssna 100.110.236.58 --tillat 100.69.247.16 ^
      --hemlighet-fil %USERPROFILE%\\.konsiliet\\rost_hemlighet --rostbank C:\\Users\\crick\\tts-test\\rostbank

Engångsläge (Mac minins reserv på MPS när språkmodellen inte är laddad, och mätningar):
  python rost_tjanst.py --en-gang jobb.json --ut-mapp ut/ --rostbank ~/Desktop/claude/rostbank
  jobb.json: [{"id": "...", "rost": "Jan", "text": "...", "uttryck": 0.5, "cfg": 0.5}]
"""
from __future__ import annotations

import argparse
import hmac
import io
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.75")
os.environ.setdefault("PYTORCH_MPS_LOW_WATERMARK_RATIO", "0.7")

MAX_TECKEN = 600
MAX_KO = 3


class Parambe:
    def __init__(self, rostbank: Path):
        self.bank = rostbank
        self.roster = json.loads((rostbank / "rostbank.json").read_text(encoding="utf-8"))["roster"]
        self.m = None
        self.enhet = None
        self.villkor: dict[tuple[str, float], object] = {}
        self.las = threading.Lock()

    def ladda(self) -> float:
        import torch
        import perth

        if getattr(perth, "PerthImplicitWatermarker", None) is None:
            class _Ingen:
                def apply_watermark(self, wav, sample_rate=None, **kw):
                    return wav
            perth.PerthImplicitWatermarker = _Ingen
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file

        t0 = time.time()
        self.enhet = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
        m = ChatterboxMultilingualTTS.from_pretrained(device=self.enhet)
        sd = load_file(hf_hub_download("Parambe/Chatterbox-Swedish-Parambe-V1", "parambe_swedish_v1.safetensors"))
        m.t3.load_state_dict({k.replace("t3.", ""): v for k, v in sd.items() if k.startswith("t3.")}, strict=False)
        self.m = m
        return time.time() - t0

    def _meningar(self, text: str) -> list[str]:
        """Chatterbox tappar ord i långa stycken. Högst ungefär 220 tecken per bit, delat vid meningsslut."""
        delar, nu = [], ""
        for s in re.split(r"(?<=[.!?])\s+", text.strip()):
            if nu and len(nu) + len(s) > 220:
                delar.append(nu)
                nu = s
            else:
                nu = f"{nu} {s}".strip()
        if nu:
            delar.append(nu)
        return delar

    def tal(self, rost: str, text: str, uttryck: float = 0.5, cfg: float = 0.5) -> tuple[bytes, float]:
        """WAV (mono, 24 kHz) och ljudlängd i sekunder."""
        import numpy as np
        import soundfile as sf
        import torch

        if rost not in self.roster:
            raise ValueError("okänd röst")
        uttryck = min(0.9, max(0.25, float(uttryck)))
        cfg = min(0.8, max(0.0, float(cfg)))
        with self.las:
            if self.m is None:
                self.ladda()
            nyckel = (rost, uttryck)
            if nyckel not in self.villkor:
                self.m.prepare_conditionals(str(self.bank / self.roster[rost]["fil"]), exaggeration=uttryck)
                self.villkor[nyckel] = self.m.conds
            self.m.conds = self.villkor[nyckel]
            bitar = []
            paus = np.zeros(int(self.m.sr * 0.22), dtype=np.float32)
            with torch.inference_mode():
                for i, mening in enumerate(self._meningar(text)):
                    w = self.m.generate(text=mening, language_id="sv", exaggeration=uttryck, cfg_weight=cfg)
                    if i:
                        bitar.append(paus)
                    bitar.append(w.squeeze().cpu().numpy().astype(np.float32))
            if self.enhet == "mps":
                torch.mps.empty_cache()
        ljud = np.concatenate(bitar)
        buf = io.BytesIO()
        sf.write(buf, ljud, self.m.sr, format="WAV", subtype="PCM_16")
        return buf.getvalue(), len(ljud) / self.m.sr


def server(a: argparse.Namespace) -> None:
    hemlighet = Path(a.hemlighet_fil).expanduser().read_text(encoding="utf-8").strip()
    if len(hemlighet) < 32:
        sys.exit("Hemligheten är för kort (minst 32 tecken).")
    if a.lyssna in ("0.0.0.0", "", "::"):
        sys.exit("Lyssna bara på Tailscale-adressen.")
    motor = Parambe(Path(a.rostbank).expanduser())
    print(f"laddar Parambe ... {motor.ladda():.1f} s på {motor.enhet}", flush=True)
    ko = threading.BoundedSemaphore(MAX_KO)

    class H(BaseHTTPRequestHandler):
        def _svara(self, kod: int, kropp: bytes, typ: str = "application/json") -> None:
            self.send_response(kod)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(kropp)))
            self.end_headers()
            self.wfile.write(kropp)

        def _behorig(self) -> bool:
            if self.client_address[0] not in a.tillat:
                self._svara(403, b'{"fel":"fel avsandare"}')
                return False
            tok = self.headers.get("X-Rost-Hemlighet", "")
            if not hmac.compare_digest(tok.encode(), hemlighet.encode()):
                self._svara(401, b'{"fel":"fel hemlighet"}')
                return False
            return True

        def do_GET(self) -> None:
            if not self._behorig():
                return
            if self.path == "/halsa":
                self._svara(200, json.dumps({"ok": True, "enhet": motor.enhet}).encode())
            else:
                self._svara(404, b"{}")

        def do_POST(self) -> None:
            if not self._behorig():
                return
            if self.path != "/tal":
                self._svara(404, b"{}")
                return
            n = int(self.headers.get("Content-Length") or 0)
            if n > 8000:
                self._svara(413, b'{"fel":"for stort"}')
                return
            try:
                d = json.loads(self.rfile.read(n))
                text = str(d["text"])
                if not text.strip() or len(text) > MAX_TECKEN:
                    raise ValueError("text saknas eller för lång")
            except Exception as e:
                self._svara(400, json.dumps({"fel": str(e)[:100]}).encode())
                return
            if not ko.acquire(blocking=False):
                self._svara(503, b'{"fel":"kon ar full"}')
                return
            try:
                t0 = time.time()
                wav, sek = motor.tal(str(d.get("rost", "")), text, d.get("uttryck", 0.5), d.get("cfg", 0.5))
                dt = time.time() - t0
                print(f"{d.get('rost')} {len(text)} tecken, {sek:.1f} s ljud på {dt:.1f} s (RTF {dt / sek:.2f})", flush=True)
                self._svara(200, wav, "audio/wav")
            except ValueError as e:
                self._svara(400, json.dumps({"fel": str(e)}).encode())
            except Exception as e:
                self._svara(500, json.dumps({"fel": str(e)[:200]}).encode())
            finally:
                ko.release()

        def log_message(self, *args) -> None:
            pass   # repliker loggas inte, bara längd och tid ovan

    ThreadingHTTPServer((a.lyssna, a.port), H).serve_forever()


def en_gang(a: argparse.Namespace) -> None:
    motor = Parambe(Path(a.rostbank).expanduser())
    print(f"MODELL {motor.ladda():.1f} s {motor.enhet}", flush=True)
    ut = Path(a.ut_mapp)
    ut.mkdir(parents=True, exist_ok=True)
    for j in json.loads(Path(a.en_gang).read_text(encoding="utf-8")):
        t0 = time.time()
        wav, sek = motor.tal(j["rost"], j["text"], j.get("uttryck", 0.5), j.get("cfg", 0.5))
        (ut / f"{j['id']}.wav").write_bytes(wav)
        dt = time.time() - t0
        print(f"OK {j['id']} {sek:.1f} s ljud {dt:.1f} s RTF {dt / sek:.2f}", flush=True)
    if motor.enhet == "cuda":
        import torch
        print(f"VRAM max {torch.cuda.max_memory_allocated() / 2**30:.2f} GB", flush=True)
    if sys.platform == "darwin":
        import resource
        print(f"MAXRSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.2f} GB", flush=True)
    print("KLART", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rostbank", required=True)
    ap.add_argument("--lyssna")
    ap.add_argument("--port", type=int, default=8796)
    ap.add_argument("--tillat", nargs="+", default=[])
    ap.add_argument("--hemlighet-fil")
    ap.add_argument("--en-gang")
    ap.add_argument("--ut-mapp")
    a = ap.parse_args()
    en_gang(a) if a.en_gang else server(a)
