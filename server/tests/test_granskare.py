"""Granskaren testad mot riktiga påståenden från första konsiliekörningen 2026-11-24."""
from konsiliet.konsiliet import Mote, granska

KALLA = {"ref": "S:hr:1-2", "median": 65.0, "max": [156.9, "2026-11-24 16:10"], "min": [58.2, "x"]}
BAS = {"ref": "B:hr:h16", "median": 72.5, "p10": 64.4, "p90": 79.1}
SOMN = {"ref": "N:a", "total_min": 450}


def mote() -> Mote:
    m = Mote("t", {"kind": "anomaly", "metric": "hr", "title": "Hög puls", "detail": "Medianpuls 151 slag/min de senaste 10 minuterna."})
    m.refs = {"S:hr:1-2": KALLA, "B:hr:h16": BAS, "N:a": SOMN,
              "U:utlosare": {"ref": "U:utlosare", "detalj": "Medianpuls 151 slag/min de senaste 10 minuterna."}}
    m.emit = lambda *a, **k: None  # type: ignore[method-assign]
    return m


def ok(text: str, kallor: list[str]) -> bool:
    return len(granska(mote(), "x", {"pastaenden": [{"text": text, "kallor": kallor}]})) == 1


def test_siffra_fran_vakten_godkanns():
    assert ok("Medianpulsen var 151 slag/min under 10 minuter.", ["S:hr:1-2"])

def test_klockslag_och_period_ar_inte_matvarden():
    assert ok("Pulsen toppade på 156,9 vid 16:10 de senaste 24 timmarna.", ["S:hr:1-2"])

def test_omrakning_minuter_till_timmar():
    assert ok("Sömnen var 7,5 timmar.", ["N:a"])

def test_pahittad_baslinje_stryks():
    assert not ok("Baslinjen vid timme 16 är 73,2 slag/min.", ["B:hr:h16"])

def test_utan_kalla_stryks():
    assert not ok("Det är troligen ett sensorfel.", [])

def test_kalla_som_inte_hamtats_stryks():
    assert not ok("Pulsen var 65.", ["S:hr:999-1000"])
