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

Start på Lenovon (miljön med chatterbox-tts 0.1.7 finns redan), i praktiken via en .bat som startar om
tjänsten efter 60 s om den faller (vid start kan Lenovon sakna minne när andra jobb kör där):
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
BF16 = os.environ.get("ROST_BF16", "0") == "1"


def _tensorer(fil: str, enhet: str):
    """Läser en safetensors-fil tensor för tensor med vanliga filläsningar, utan minnesmappning.
    På Lenovon kraschade både load_file och safe_open (access violation i den mappade filen) när
    datorn hade ont om minne. Det här håller bara en tensor åt gången i RAM."""
    import torch

    typer = {"F32": torch.float32, "F16": torch.float16, "BF16": torch.bfloat16, "I64": torch.int64,
             "I32": torch.int32, "I16": torch.int16, "I8": torch.int8, "U8": torch.uint8, "BOOL": torch.bool,
             "F64": torch.float64}
    with open(fil, "rb") as f:
        n = int.from_bytes(f.read(8), "little")
        huvud = json.loads(f.read(n))
        bas = 8 + n
        for namn, info in huvud.items():
            if namn == "__metadata__":
                continue
            a, b = info["data_offsets"]
            f.seek(bas + a)
            buf = bytearray(f.read(b - a))
            t = torch.frombuffer(buf, dtype=typer[info["dtype"]]) if buf else torch.empty(0, dtype=typer[info["dtype"]])
            yield namn, t.reshape(info["shape"]).to(enhet)


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

        t0 = time.time()
        self.enhet = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
        fil = hf_hub_download("Parambe/Chatterbox-Swedish-Parambe-V1", "parambe_swedish_v1.safetensors")
        if self.enhet == "cuda":
            m = self._snal_laddning(fil)
        else:
            m = ChatterboxMultilingualTTS.from_pretrained(device=self.enhet)
            self._svenska_vikter(m.t3, fil)
        self.m = m
        return time.time() - t0

    @staticmethod
    def _svenska_vikter(t3, fil: str) -> None:
        """Parambes svenska T3-vikter ovanpå originalet, en tensor i taget."""
        import torch

        sd, n = t3.state_dict(), 0
        dev = next(t3.parameters()).device
        with torch.no_grad():
            for k, v in _tensorer(fil, str(dev)):
                if k.startswith("t3.") and k[3:] in sd:
                    sd[k[3:]].copy_(v)
                    n += 1
        if n < 100:
            raise RuntimeError(f"bara {n} svenska vikter lästes in")

    def _snal_laddning(self, parambe: str):
        """Som ChatterboxMultilingualTTS.from_local, men modellerna byggs direkt på grafikkortet och vikterna
        läses en tensor i taget. Originalet lägger allt i RAM först, och på Lenovon tog sidfilen slut
        ("The paging file is too small") när andra jobb körde där samtidigt."""
        import torch
        from chatterbox.models.s3gen import S3Gen
        from chatterbox.models.t3 import T3
        from chatterbox.models.t3.modules.t3_config import T3Config
        from chatterbox.models.tokenizers import MTLTokenizer
        from chatterbox.models.voice_encoder import VoiceEncoder
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS, Conditionals
        from huggingface_hub import snapshot_download

        d = Path(snapshot_download("ResembleAI/chatterbox", allow_patterns=[
            "ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json", "conds.pt",
            "Cangjie5_TC.json"]))
        dev = torch.device("cuda")
        with dev:
            ve = VoiceEncoder()
            t3 = T3(T3Config.multilingual())
            s3gen = S3Gen()
        ve.load_state_dict(torch.load(d / "ve.pt", map_location=dev, weights_only=True))
        sd = t3.state_dict()
        with torch.no_grad():
            for k, v in _tensorer(str(d / "t3_mtl23ls_v2.safetensors"), "cuda"):
                if k in sd:
                    sd[k].copy_(v)
        self._svenska_vikter(t3, parambe)
        s3gen.load_state_dict(torch.load(d / "s3gen.pt", map_location=dev, weights_only=True))
        conds = Conditionals.load(d / "conds.pt", map_location=dev).to(dev) if (d / "conds.pt").exists() else None
        return ChatterboxMultilingualTTS(t3.eval(), s3gen.eval(), ve.eval(),
                                         MTLTokenizer(str(d / "grapheme_mtl_merged_expanded_v1.json")), dev, conds=conds)

    def _generera(self, text: str, uttryck: float, cfg: float):
        """Som ChatterboxMultilingualTTS.generate, men med ett tak för antalet taltoken efter textens längd.
        Originalet har alltid 1000, och ibland hittar modellen inget slut: då blev 7 s tal 119 s arbete."""
        import torch
        import torch.nn.functional as F
        from chatterbox.models.s3tokenizer import drop_invalid_tokens
        from chatterbox.models.t3.modules.cond_enc import T3Cond
        from chatterbox.mtl_tts import punc_norm

        m = self.m
        if float(uttryck) != float(m.conds.t3.emotion_adv[0, 0, 0].item()):
            c = m.conds.t3
            m.conds.t3 = T3Cond(speaker_emb=c.speaker_emb, cond_prompt_speech_tokens=c.cond_prompt_speech_tokens,
                                emotion_adv=uttryck * torch.ones(1, 1, 1)).to(device=m.device)
        tt = m.tokenizer.text_to_tokens(punc_norm(text), language_id="sv").to(m.device)
        tt = torch.cat([tt, tt], dim=0)
        tt = F.pad(F.pad(tt, (1, 0), value=m.t3.hp.start_text_token), (0, 1), value=m.t3.hp.stop_text_token)
        # 25 taltoken per sekund, svenska runt 14 tecken per sekund, dubbel marginal
        tak = min(1000, int(80 + 25 * len(text) / 14 * 2))
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=self.enhet == "cuda" and BF16):
            st = m.t3.inference(t3_cond=m.conds.t3, text_tokens=tt, max_new_tokens=tak, temperature=0.8,
                                cfg_weight=cfg, repetition_penalty=2.0, min_p=0.05, top_p=1.0)
        st = drop_invalid_tokens(st[0]).to(m.device)
        wav, _ = m.s3gen.inference(speech_tokens=st, ref_dict=m.conds.gen)
        wav = wav.squeeze(0).detach().float().cpu().numpy()
        # Chatterbox vattenmärke (Perth) behålls: ljudet går att känna igen som syntetiskt
        return torch.from_numpy(m.watermarker.apply_watermark(wav, sample_rate=m.sr))

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
                    w = self._generera(mening, uttryck, cfg)
                    if i:
                        bitar.append(paus)
                    bitar.append(w.numpy().astype(np.float32))
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
