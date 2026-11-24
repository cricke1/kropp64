"""Latens per steg i kedjan, för nördpanelen. Ringbuffert med de senaste 500 mätningarna per steg."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Iterator

_data: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=500))
_lock = threading.Lock()
ORDNING = ["Mottagning (ingest)", "Vakt, regelkoll", "Specialist, per modellanrop", "Granskning",
           "Hela konsiliet", "Morgonbrief"]


def record(step: str, ms: float) -> None:
    with _lock:
        _data[step].append(ms)


@contextmanager
def tid(step: str) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        record(step, (time.perf_counter() - t0) * 1000)


def sammanstall() -> list[dict[str, float | int | str]]:
    with _lock:
        items = {k: sorted(v) for k, v in _data.items() if v}
    keys = [k for k in ORDNING if k in items] + [k for k in items if k not in ORDNING]
    out = []
    for k in keys:
        v = items[k]
        out.append({"step": k, "p50_ms": round(v[len(v) // 2], 1),
                    "p95_ms": round(v[min(len(v) - 1, int(len(v) * 0.95))], 1), "n": len(v)})
    return out
