"""Röster till kontoret. Varje läkare läser sina repliker med en egen lokal svensk röst.

Allt körs på Mac minin:
  - Piper (VITS, ONNX på CPU) med de tre svenska rösterna från rhasspy/piper-voices: nst (man), lisa och
    alma (kvinnor). Ungefär 63 MB per röst, laddas först när någon ska prata och släpps efter en stunds tystnad.
  - macOS egen röst Alva via `say` (ingen modell i serverprocessen alls).
Samma talare kan få en annan karaktär med tempo och en liten tonhöjdsförskjutning (ffmpeg).

Rösterna genereras lat, när webben ber om dem (GET /api/rost), aldrig i konsiliets agentloop. En syntes åt
gången och få CPU-trådar, så att språkmodellen inte märker något. Resultatet cachas som mp3 i
~/.konsiliet/rost/cache, med nyckel av röst och normaliserad text.

    uv run python -m konsiliet.rost "SpO2 98 %, sömn 5 h 40 min"           visar texten som den läses
    uv run python -m konsiliet.rost --agent somn --ut fil.mp3 "Hej"         syntes till fil
    uv run python -m konsiliet.rost --forbered rader.json --utkatalog dir   många rader, med manifest
    uv run python -m konsiliet.rost --hamta                                 hämtar Piper-rösterna (190 MB)
"""
from __future__ import annotations

import gc
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

ROT = Path(os.environ.get("KONSILIET_ROST_DIR", Path.home() / ".konsiliet" / "rost"))
MODELLER = ROT / "modeller"
CACHE = ROT / "cache"
CACHE_MAX_MB = 300
LEDIG_S = 300          # släpp en Piper-röst ur minnet efter så här länge utan repliker
TRADAR = 2             # onnxruntime-trådar, så att resten av datorn får vara i fred
MAX_TECKEN = 1500
VERSION = "3"          # höjs när normaliseringen eller rösterna ändras, så att cachen byggs om


# ------------------------------------------------------------------ röster per läkare

@dataclass(frozen=True)
class Rost:
    motor: str            # "piper" eller "say"
    modell: str           # piper: sv_SE-nst-medium, say: Alva
    tempo: float = 1.0    # piper length_scale (större = långsammare), say: ord per minut / 175
    ton: float = 1.0      # tonhöjd som faktor, 1.0 = oförändrad
    variation: float = 0.667  # piper noise_scale, mer = livligare intonation
    rytm: float = 0.8     # piper noise_w

    def nyckel(self) -> str:
        return f"{self.motor}:{self.modell}:{self.tempo}:{self.ton}:{self.variation}:{self.rytm}"


# Fyra lokala grundröster: nst (man), lisa, alma och Alva (kvinnor). Tre läkare delar nst och skiljs åt med
# tempo, tonhöjd och hur livlig intonationen är. Valda efter figurerna i kontoret och rollerna i
# docs/VARUMARKE.md: Trådstartaren (ordforande) äldre och lugn, Trollet (advokat) kaxigt och snabbt,
# Moderatorn (granskare) torr och saklig. Moderatorn är vanlig kod och får datorns egen röst (Alva).
# Tonhöjden hålls inom tio procent, mer än så hörs som en effekt.
ROSTER: dict[str, Rost] = {
    "ordforande": Rost("piper", "sv_SE-nst-medium", tempo=1.12, ton=0.9, variation=0.55),
    "advokat": Rost("piper", "sv_SE-nst-medium", tempo=0.85, ton=1.0, variation=0.9, rytm=0.9),
    "idrott": Rost("piper", "sv_SE-nst-medium", tempo=0.96, ton=1.08, variation=0.7),
    "kardiolog": Rost("piper", "sv_SE-lisa-medium", tempo=1.0),
    "stress": Rost("piper", "sv_SE-lisa-medium", tempo=1.1, ton=0.93, variation=0.55),
    "somn": Rost("piper", "sv_SE-alma-medium", tempo=1.08, ton=0.97, variation=0.6),
    "labb": Rost("piper", "sv_SE-alma-medium", tempo=0.95, ton=1.05, variation=0.75),
    "granskare": Rost("say", "Alva", tempo=1.0),
}
STANDARD = Rost("piper", "sv_SE-nst-medium")


def rost_for(agent: str) -> Rost:
    return ROSTER.get(agent, STANDARD)


# ------------------------------------------------------------------ text till tal

_ENTAL = ["noll", "ett", "två", "tre", "fyra", "fem", "sex", "sju", "åtta", "nio", "tio", "elva", "tolv",
          "tretton", "fjorton", "femton", "sexton", "sjutton", "arton", "nitton"]
_TIOTAL = {2: "tjugo", 3: "trettio", 4: "fyrtio", 5: "femtio", 6: "sextio", 7: "sjuttio", 8: "åttio", 9: "nittio"}
_ORDNING = ["", "första", "andra", "tredje", "fjärde", "femte", "sjätte", "sjunde", "åttonde", "nionde", "tionde",
            "elfte", "tolfte", "trettonde", "fjortonde", "femtonde", "sextonde", "sjuttonde", "artonde", "nittonde",
            "tjugonde"]
_MANAD = ["", "januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober",
          "november", "december"]


def tal(n: int, genus: str = "ett") -> str:
    """Heltal med bokstäver. genus "en" ger "en timme", "ett" ger "ett dygn" (och vid uppräkning)."""
    if n < 0:
        return "minus " + tal(-n, genus)
    if n == 1:
        return genus
    if n < 20:
        return _ENTAL[n]
    if n < 100:
        t, e = divmod(n, 10)
        return _TIOTAL[t] + (_ENTAL[e] if e else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return ("" if h == 1 else _ENTAL[h]) + "hundra" + (tal(r) if r else "")
    if n < 1_000_000:
        t, r = divmod(n, 1000)
        return ("" if t == 1 else tal(t)) + "tusen" + (" " + tal(r) if r else "")
    return " ".join(tal(int(d)) for d in str(n))


def ordningstal(n: int) -> str:
    if n <= 20:
        return _ORDNING[n]
    t, e = divmod(n, 10)
    return _TIOTAL[t] + (_ORDNING[e] if e else "nde")


def _decimal(s: str, genus: str = "ett") -> str:
    s = s.replace(".", ",")
    if "," not in s:
        return tal(int(s), genus)
    hel, dec = s.split(",", 1)
    dec_ord = tal(int(dec)) if len(dec) <= 2 and not dec.startswith("0") else " ".join(_ENTAL[int(d)] for d in dec)
    return f"{tal(int(hel))} komma {dec_ord}"


# enhet: (genus, singular, plural)
_ENHETER: list[tuple[str, tuple[str, str, str]]] = [
    (r"slag\s*/\s*min|slag per minut|bpm|spm", ("ett", "slag per minut", "slag per minut")),
    (r"andetag\s*/\s*min|andetag per minut|/\s*min", ("ett", "per minut", "per minut")),
    (r"mmol\s*/\s*l", ("en", "millimol per liter", "millimol per liter")),
    (r"nmol\s*/\s*l", ("en", "nanomol per liter", "nanomol per liter")),
    (r"µmol\s*/\s*l|umol\s*/\s*l", ("en", "mikromol per liter", "mikromol per liter")),
    (r"mg\s*/\s*l", ("ett", "milligram per liter", "milligram per liter")),
    (r"µg\s*/\s*l|ug\s*/\s*l", ("ett", "mikrogram per liter", "mikrogram per liter")),
    (r"g\s*/\s*l", ("ett", "gram per liter", "gram per liter")),
    (r"mmhg", ("en", "millimeter kvicksilver", "millimeter kvicksilver")),
    (r"ms", ("en", "millisekund", "millisekunder")),
    (r"%", ("en", "procent", "procent")),
    (r"°\s*c|°", ("en", "grad", "grader")),
    (r"h|tim", ("en", "timme", "timmar")),
    (r"min", ("en", "minut", "minuter")),
    (r"s|sek", ("en", "sekund", "sekunder")),
    (r"d", ("en", "dag", "dagar")),
    (r"kg", ("ett", "kilo", "kilo")),
    (r"km", ("en", "kilometer", "kilometer")),
]
_TAL = r"-?\d+(?:[.,]\d+)?"
_ENHET_RE = [(re.compile(rf"(?<![\w,.])({_TAL})\s*(?:{m})(?![\wåäö])", re.I), e) for m, e in _ENHETER]

# Ord och förkortningar som espeak-ng (fonemen bakom Piper) läser fel. Verifierat med fonemdump:
# "muskel" blir [mɵɧəl] med sj-ljud, EKG blir ett enda ord [ɛkɡ].
_ORD = [
    (r"\bSpO\s*[2₂]\b", "syremättnad"),
    (r"\bHRV\b", "H R V"),
    (r"\bBPM\b", "slag per minut"),
    (r"\bKropp64\b", "Kropp sextiofyra"),
    (r"\bAFK\b", "A F K"),
    (r"\bRMSSD\b", "R M S S D"),
    (r"\bHb\b", "H B"),
    (r"\bEKG\b", "E K G"),
    (r"\b1177\b", "elva sjuttiosju"),
    (r"\bt\.\s?ex\.", "till exempel"),
    (r"\bbl\.\s?a\.", "bland annat"),
    (r"\bosv\.?", "och så vidare"),
    (r"\bca\.?(?=\s\d)", "cirka"),
    (r"\bvs\.?(?=\s)", "mot"),
    (r"\bz-poäng", "z poäng"),
    (r"muskel", "musskel"),
    (r"Muskel", "Musskel"),
]
_ORD_RE = [(re.compile(m), r) for m, r in _ORD]
_REF = re.compile(r"\(\s*(?:Ref|Källa|källa)?:?\s*[A-Z]:[^)]*\)|\[\s*[A-Z]:[^\]]*\]|\b(?:Ref:\s*)?[FSBJLNM]:[\w:.\-]+")
_AKRONYM = re.compile(r"\b([A-ZÅÄÖ]{2,5})\b")
_EN_ORD = r"(?:natt|dag|timme|minut|sekund|vecka|månad|gång|mätning|period|kurva|puls|stund)\b"
_TID = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_DATUM = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _klockslag(h: str, m: str) -> str:
    hh, mm = int(h), int(m)
    if mm == 0:
        return tal(hh)
    return f"{tal(hh)} {'noll ' + tal(mm) if mm < 10 else tal(mm)}"


# Engelska ord som espeak läser på svenska. Piper tar råa fonem inom [[ ]], say får en svensk stavning.
_ENGELSKA = [(re.compile(r"\b[Hh]eadroom\b"), "[[ hˈɛdruːm ]]", "heddrum")]


def for_tal(text: str, motor: str = "piper") -> str:
    """Gör en replik läsbar för talsyntesen: inga källreferenser eller markdown, siffror och enheter
    med bokstäver ("5 h 40 min" blir "fem timmar och fyrtio minuter"), förkortningar som de sägs."""
    t = text[:MAX_TECKEN]
    t = _REF.sub("", t)
    t = t.replace("[[", "").replace("]]", "")
    t = re.sub(r"[*_`#>]+", " ", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = re.sub(r"\s*\n+\s*", ". ", t)
    t = re.sub(r"(?<![\w])\+(?=\d)", "plus ", t)
    for r, s in _ORD_RE:
        t = r.sub(s, t)
    t = _DATUM.sub(lambda m: f"{ordningstal(int(m[3]))} {_MANAD[int(m[2])]} {tal(int(m[1]))}"
                   if 1 <= int(m[2]) <= 12 and 1 <= int(m[3]) <= 31 else m[0], t)
    # klockslag och perioder: 02:14-02:31 blir "två fjorton till två trettioett"
    t = re.sub(rf"({_TID.pattern})\s*[-–]\s*(?={_TID.pattern})", lambda m: f"{m[1]} till ", t)
    t = _TID.sub(lambda m: _klockslag(m[1], m[2]), t)
    # 5 h 40 min, 7 h 10 min
    t = re.sub(r"(?<![\w,.])(\d+)\s*h\s+(\d+)\s*min\b",
               lambda m: f"{tal(int(m[1]), 'en')} {'timme' if m[1] == '1' else 'timmar'} och "
                         f"{tal(int(m[2]), 'en')} {'minut' if m[2] == '1' else 'minuter'}", t)
    t = re.sub(r"(?<![\w,.])(\d+)\s*/\s*(\d+)(?=\s*mmhg)", r"\1 över \2", t, flags=re.I)   # blodtryck
    t = re.sub(r"(?<![\w,.])(\d+)\s*/\s*(\d+)(?!\d|[.,]\d)", r"\1 av \2", t)   # headroom 72/100
    # intervall: 68-74 slag/min, 68 till 74
    t = re.sub(r"(?<![\w,.])(\d+(?:[.,]\d+)?)\s*[-–]\s*(?=\d)", r"\1 till ", t)
    for r, (genus, sing, plur) in _ENHET_RE:
        t = r.sub(lambda m: f"{_decimal(m[1].lstrip('-'), genus) if not m[1].startswith('-') else 'minus ' + _decimal(m[1][1:], genus)} "
                            f"{sing if m[1] in ('1', '-1') else plur}", t)
    t = re.sub(rf"(?<![\w,.])1\s+(?={_EN_ORD})", "en ", t)
    t = re.sub(r"\s=\s", " är ", t)
    t = re.sub(r"(?<![\w])(-?)(\d+(?:,\d+)?)(?![\w])",
               lambda m: ("minus " if m[1] else "") + _decimal(m[2]), t)
    t = t.replace("/", " per ")
    t = _AKRONYM.sub(lambda m: " ".join(m[1]) if m[1] not in ("OK", "POST") else {"OK": "okej"}.get(m[1], m[1].lower()), t)
    for r, fon, stavning in _ENGELSKA:
        t = r.sub(fon if motor == "piper" else stavning, t)
    t = re.sub(r"\s+([.,;:!?])", r"\1", t)
    t = re.sub(r"([.!?])(?:\s*[.!?])+", r"\1", t)
    t = re.sub(r"\(\s*\)|\[\s*\]", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;:")
    return t


# ------------------------------------------------------------------ syntes

_las = threading.Lock()
_roster: dict[str, tuple[object, float]] = {}   # modellnamn -> (PiperVoice, senast använd)
_rensare: threading.Thread | None = None


def _piper(modell: str):
    global _rensare
    hit = _roster.get(modell)
    if hit:
        _roster[modell] = (hit[0], time.time())
        return hit[0]
    import onnxruntime
    from piper import PiperVoice
    from piper.config import PiperConfig

    _roster.clear()   # bara en röst i minnet åt gången, att ladda en ny tar 0,2-0,4 s
    gc.collect()
    sti = MODELLER / f"{modell}.onnx"
    if not sti.exists():
        raise FileNotFoundError(f"Saknar rösten {sti}. Hämta med: uv run python -m konsiliet.rost --hamta")
    opt = onnxruntime.SessionOptions()
    opt.intra_op_num_threads = TRADAR
    opt.inter_op_num_threads = 1
    opt.enable_cpu_mem_arena = False   # minnet lämnas tillbaka efter varje replik i stället för att växa
    with open(f"{sti}.json", encoding="utf-8") as f:
        cfg = PiperConfig.from_dict(json.load(f))
    v = PiperVoice(config=cfg, session=onnxruntime.InferenceSession(str(sti), sess_options=opt,
                                                                      providers=["CPUExecutionProvider"]))
    _roster[modell] = (v, time.time())
    if _rensare is None or not _rensare.is_alive():
        _rensare = threading.Thread(target=_rensa_loop, name="rost-rensare", daemon=True)
        _rensare.start()
    return v


def _rensa_loop() -> None:
    while _roster:
        time.sleep(30)
        with _las:
            for k, (_, t) in list(_roster.items()):
                if time.time() - t > LEDIG_S:
                    del _roster[k]
            gc.collect()


def _wav_piper(r: Rost, text: str) -> bytes:
    import numpy as np
    from piper import SynthesisConfig

    v = _piper(r.modell)
    cfg = SynthesisConfig(length_scale=r.tempo, noise_scale=r.variation, noise_w_scale=r.rytm)
    rate = v.config.sample_rate
    paus = np.zeros(int(rate * 0.28), dtype=np.int16)   # mellan meningar, Piper har nästan ingen egen
    delar: list = []
    for chunk in v.synthesize(text, syn_config=cfg):
        if delar:
            delar.append(paus)
        delar.append(chunk.audio_int16_array)
    ljud = np.concatenate(delar) if delar else np.zeros(rate // 4, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(ljud.tobytes())
    return buf.getvalue()


def _wav_say(r: Rost, text: str) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        ut = Path(d) / "a.aiff"
        subprocess.run(["say", "-v", r.modell, "-r", str(round(175 * r.tempo)), "-o", str(ut), "--", text],
                       check=True, timeout=120, capture_output=True)
        return subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(ut), "-f", "wav", "-"],
                              check=True, capture_output=True, timeout=60).stdout


def _till_mp3(wav: bytes, ton: float) -> bytes:
    filt = []
    if abs(ton - 1.0) > 1e-3:
        # tonhöjd utan att ändra tempot: spela upp i annan takt och sträck tillbaka
        filt += [f"asetrate=22050*{ton}", "aresample=22050", f"atempo={1 / ton:.4f}"]
    # jämn ljudnivå mellan rösterna och en kort tystnad först, så att första stavelsen inte klipps
    filt += ["adelay=120", "loudnorm=I=-19:TP=-2:LRA=9", "aresample=24000"]
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "wav", "-i", "-", "-af", ",".join(filt),
                           "-ac", "1", "-c:a", "libmp3lame", "-b:a", "48k", "-f", "mp3", "-"],
                          input=wav, check=True, capture_output=True, timeout=120).stdout


def nyckel(agent: str, text: str) -> tuple[str, str, Rost]:
    r = rost_for(agent)
    talt = for_tal(text, r.motor)
    h = hashlib.sha256(f"{VERSION}|{r.nyckel()}|{talt}".encode()).hexdigest()[:32]
    return h, talt, r


def ljud(agent: str, text: str) -> Path | None:
    """Sökväg till en mp3 med repliken, genererad vid behov. None om det inte finns något att säga."""
    h, talt, r = nyckel(agent, text)
    if not re.search(r"\w", talt):
        return None
    ut = CACHE / f"{h}.mp3"
    if ut.exists():
        os.utime(ut)
        return ut
    with _las:
        if ut.exists():
            return ut
        wav = _wav_say(r, talt) if r.motor == "say" else _wav_piper(r, talt)
        mp3 = _till_mp3(wav, r.ton)
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = ut.with_suffix(".tmp")
        tmp.write_bytes(mp3)
        tmp.replace(ut)
    _stada_cache()
    return ut


def _stada_cache() -> None:
    filer = sorted(CACHE.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in filer)
    while filer and total > CACHE_MAX_MB * 2**20:
        p = filer.pop(0)
        total -= p.stat().st_size
        p.unlink(missing_ok=True)


HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/sv/sv_SE"


def hamta() -> None:
    """Hämtar de tre svenska Piper-rösterna (cirka 190 MB) från rhasspy/piper-voices."""
    import httpx

    MODELLER.mkdir(parents=True, exist_ok=True)
    for modell in sorted({r.modell for r in ROSTER.values() if r.motor == "piper"}):
        namn = modell.split("-")[1]
        for ext in (".onnx", ".onnx.json"):
            ut = MODELLER / f"{modell}{ext}"
            if ut.exists():
                continue
            with httpx.stream("GET", f"{HF}/{namn}/medium/{modell}{ext}", follow_redirects=True, timeout=120) as r:
                r.raise_for_status()
                tmp = ut.with_suffix(".tmp")
                with open(tmp, "wb") as f:
                    for b in r.iter_bytes():
                        f.write(b)
                tmp.replace(ut)
            print("hämtade", ut)


def forbered(rader: list[dict], utkatalog: Path) -> dict[str, str]:
    """Genererar ljud för en lista {agent, text} och kopierar till utkatalog. Manifest: "agent|text" -> fil."""
    utkatalog.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for rad in rader:
        p = ljud(rad["agent"], rad["text"])
        if p:
            (utkatalog / p.name).write_bytes(p.read_bytes())
            manifest[f"{rad['agent']}|{rad['text']}"] = p.name
    (utkatalog / "index.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="?")
    ap.add_argument("--agent", default="ordforande")
    ap.add_argument("--ut")
    ap.add_argument("--forbered")
    ap.add_argument("--utkatalog")
    ap.add_argument("--hamta", action="store_true", help="hämta Piper-rösterna")
    a = ap.parse_args()
    if a.hamta:
        hamta()
    elif a.forbered:
        m = forbered(json.loads(Path(a.forbered).read_text(encoding="utf-8")), Path(a.utkatalog))
        print(f"{len(m)} repliker i {a.utkatalog}")
    elif a.ut:
        p = ljud(a.agent, a.text)
        if p:
            Path(a.ut).write_bytes(p.read_bytes())
        print(for_tal(a.text))
    else:
        print(for_tal(a.text))
