#!/usr/bin/env python3
"""Trailermusiken, syntetiserad i kod (ingen nedladdad musik, ingen AI-musik).

Idén: takten är ett hjärtslag som går från vilopuls till träningspuls. Hjärtslaget (lub-dub) är kicken.
  0-7 s     bara hjärtat, 58 BPM, en låg ton
  7-17 s    pad och arpeggio kommer in, 72 BPM
  17-31 s   uppbyggnad: hi-hats, bas, 96 BPM
  31-45 s   drop: full takt 124 BPM, lead, sidechain
  45-55 s   allt tystnar, hjärtat ensamt som saktar in

  .venv/bin/python musik.py <ut.wav>
"""
import sys, wave
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
LANGD = 55.0
N = int(SR * LANGD)
t_all = np.arange(N) / SR
rng = np.random.default_rng(64)


def bpm(t: float) -> float:
    if t < 7: return 58
    if t < 17: return 58 + (t - 7) / 10 * 14
    if t < 31: return 72 + (t - 17) / 14 * 52
    if t < 45: return 124
    return max(52, 124 - (t - 45) / 10 * 72)


# slagtider genom att integrera tempot
slag, t = [], 0.0
while t < LANGD:
    slag.append(t); t += 60.0 / bpm(t)
slag = np.array(slag)


def env(n, a, d):
    e = np.ones(n); na = max(1, int(a * SR)); e[:na] = np.linspace(0, 1, na)
    return e * np.exp(-np.arange(n) / SR / d)


def lp(x, f, ordning=2):
    return sosfilt(butter(ordning, f, "low", fs=SR, output="sos"), x)


def hp(x, f, ordning=2):
    return sosfilt(butter(ordning, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi):
    return sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), x)


def lagg(buf, sig, t0, gain=1.0):
    i = int(t0 * SR)
    if i >= len(buf): return
    n = min(len(sig), len(buf) - i)
    buf[i:i + n] += sig[:n] * gain


def kick(hard=1.0):
    n = int(0.45 * SR); tt = np.arange(n) / SR
    f = 44 + 150 * np.exp(-tt * 34)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-tt * 7.0)
    klick = bp(rng.standard_normal(n) * np.exp(-tt * 300), 2500, 6500) * 0.75
    punch = np.sin(2 * np.pi * 180 * tt) * np.exp(-tt * 60) * 0.5
    return np.tanh((s + punch + klick * hard) * 1.8)


def dub():
    n = int(0.3 * SR); tt = np.arange(n) / SR
    f = 38 + 70 * np.exp(-tt * 35)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 11) * 0.7


def hat(oppen=False):
    n = int((0.18 if oppen else 0.04) * SR)
    return hp(rng.standard_normal(n), 7500, 4) * env(n, 0.001, 0.06 if oppen else 0.012)


def clap():
    n = int(0.25 * SR); x = bp(rng.standard_normal(n), 900, 4000)
    e = np.zeros(n)
    for k in (0, 0.012, 0.024):
        i = int(k * SR); e[i:] += np.exp(-np.arange(n - i) / SR / 0.05)
    return x * e * 0.5


def saw(f, n, detune=0.0):
    tt = np.arange(n) / SR
    return 2 * ((tt * f * (1 + detune)) % 1.0) - 1


def note(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


# Am - F - C - G, i A-moll
ACK = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]
ROT = [45, 41, 48, 43]

L = np.zeros(N); R = np.zeros(N)
trum = np.zeros(N); sc = np.ones(N)  # sidechain-kurva

# hjärtat: lub (kick) och dub (kort, efter 0.28 slag)
for i, s in enumerate(slag):
    styrka = 0.75 if s < 7 else 0.9 if s < 31 else 1.0
    if 45 <= s:
        styrka = 0.85 * max(0.2, 1 - (s - 45) / 11)
    lagg(trum, kick(0.4 if s < 31 else 1.0), s, styrka)
    lagg(trum, dub(), s + 0.30 * 60 / bpm(s), styrka * (0.8 if s < 31 else 0.55))
    if 17 <= s < 45:
        n = int(0.22 * SR)
        d = 1 - 0.75 * np.exp(-np.arange(n) / SR / 0.09)
        i0 = int(s * SR); m = min(n, N - i0)
        sc[i0:i0 + m] = np.minimum(sc[i0:i0 + m], d[:m])

# hi-hats och clap i uppbyggnad och drop
for i in range(len(slag) - 1):
    a, b = slag[i], slag[i + 1]
    if 17 <= a < 45:
        steg = 2 if a < 25 else 4
        for k in range(steg):
            lagg(trum, hat(oppen=(k == steg // 2 and a >= 31)), a + (b - a) * k / steg, 0.22 if a < 31 else 0.3)
    if 31 <= a < 45 and i % 2 == 1:
        lagg(trum, clap(), a, 0.6)

# ackord per takt (4 slag)
def ackord_vid(t):
    idx = np.searchsorted(slag, t, side="right") - 1
    return (max(idx, 0) // 4) % 4

pad = np.zeros((2, N)); bas = np.zeros(N); arp = np.zeros(N)
takt_start = [slag[i] for i in range(0, len(slag), 4)]
for ti, ts in enumerate(takt_start):
    te = takt_start[ti + 1] if ti + 1 < len(takt_start) else LANGD
    if ts >= 52: break
    a = ACK[ti % 4]; n = int((te - ts) * SR) + int(0.4 * SR)
    if 7 <= ts < 45 or ts < 7:
        g = 0.05 if ts < 7 else 0.11
        for ch, dt in ((0, -0.007), (1, 0.007)):
            x = sum(saw(note(m), n, dt) + saw(note(m), n, -dt * 0.7) for m in a)
            x = lp(x, 900 if ts < 31 else 2200) * env(n, 0.35, 6.0) * g
            lagg(pad[ch], x, ts)
    if 17 <= ts < 45:
        x = saw(note(ROT[ti % 4]), n) * 0.6 + np.sin(2 * np.pi * note(ROT[ti % 4] - 12) * np.arange(n) / SR)
        lagg(bas, lp(x, 300 if ts < 31 else 520) * env(n, 0.01, 4) * 0.32, ts)
    if 7 <= ts < 45:
        sl = [s for s in slag if ts <= s < te]
        steg = 2 if ts < 31 else 4
        k = 0
        for s_i, s in enumerate(sl):
            nxt = sl[s_i + 1] if s_i + 1 < len(sl) else te
            for j in range(steg):
                m = a[k % 3] + 12 * (1 + (k // 3) % 2); k += 1
                nn = int(0.18 * SR)
                fas = (note(m) * np.arange(nn) / SR) % 1.0
                ton = (4 * np.abs(fas - 0.5) - 1) * 0.8 + np.sign(np.sin(2 * np.pi * fas)) * 0.2
                ton = ton * env(nn, 0.003, 0.09)
                lagg(arp, lp(ton, 1700 if ts >= 31 else 1300, 4), s + (nxt - s) * j / steg, 0.075 if ts < 31 else 0.06)

# riser före droppet och nedslag
n = int(4.0 * SR); tt = np.arange(n) / SR
riser = hp(rng.standard_normal(n), 1500) * (tt / 4) ** 2 * 0.18
lagg(trum, riser, 27.0)
lagg(trum, lp(rng.standard_normal(int(2.5 * SR)), 300) * env(int(2.5 * SR), 0.001, 0.8) * 0.5, 31.0)
lagg(trum, kick(1.0) * 1.2, 31.0)

# låg drönare i början
dron = np.sin(2 * np.pi * 55 * t_all) * 0.05 * np.clip(1 - np.abs(t_all - 6) / 8, 0, 1)

# ping-pong-delay på arpeggiot (vänster, höger, vänster ...)
d = int(0.21 * SR)
arpL = arp.copy(); arpR = arp * 0.6
eko = arp.copy()
for k in range(1, 5):
    eko = np.concatenate([np.zeros(d), eko[:-d]]) * 0.42
    if k % 2: arpR += eko
    else: arpL += eko
# rumsklang: exponentiellt avklingande brus, olika i vänster och höger kanal
nir = int(2.4 * SR); tir = np.arange(nir) / SR
irL = rng.standard_normal(nir) * np.exp(-tir / 0.55); irR = rng.standard_normal(nir) * np.exp(-tir / 0.55)
irL /= np.sqrt(np.sum(irL ** 2)); irR /= np.sqrt(np.sum(irR ** 2))
send = lp(pad[0] + pad[1], 5000) * 0.5 + (arpL + arpR) * 0.5
revL = fftconvolve(send, irL)[:N] * 0.35; revR = fftconvolve(send, irR)[:N] * 0.35
L = trum + (pad[0] * 1.1 + bas + arpL) * sc + revL * sc + dron
R = trum + (pad[1] * 1.1 + bas + arpR) * sc + revR * sc + dron
# fade in/ut
fade = np.clip(t_all / 0.3, 0, 1) * np.clip((LANGD - t_all) / 1.5, 0, 1)
st = np.stack([L * fade, R * fade])
st = np.tanh(st * 1.4) / np.tanh(1.4)
st /= np.max(np.abs(st)) / 0.89

ut = sys.argv[1] if len(sys.argv) > 1 else "musik.wav"
with wave.open(ut, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st.T * 32767).astype("<i2").tobytes())
print(ut, len(slag), "slag")
