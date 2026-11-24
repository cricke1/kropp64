"""Vardagen: dagens beslut, notisbudget, snooze, åtgärder och idrottsläkarens gränser. Syntetisk data i egen databas."""
import json
import time
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def v(tmp_path, monkeypatch):
    monkeypatch.setenv("KONSILIET_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("KONSILIET_TILLAT_EMULATOR", "1")
    import importlib

    from konsiliet import config, db, rutiner, vakt, vardag
    importlib.reload(config)
    importlib.reload(db)
    db._initialized = False
    importlib.reload(vakt)
    importlib.reload(rutiner)
    importlib.reload(vardag)
    pub = []
    vardag.publicera = lambda k, p: pub.append((k, p))
    return db, vardag, pub


def _somn(db, slut: float, timmar: float, sid: str = "s"):
    with db.tx() as c:
        c.execute("INSERT INTO sleep VALUES (?,?,?,?,?)", (sid, slut - timmar * 3600, slut, "[]", "test"))


def _morgon() -> float:
    d = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    while d.weekday() not in (0, 2, 5):  # en passdag
        d -= timedelta(days=1)
    return d.timestamp()


def test_kort_somn_ger_vila_och_plan_med_enheter(v):
    db, vardag, _ = v
    nu = _morgon()
    _somn(db, nu - 3600, 4.5)
    i = vardag.idag(nu)
    assert i["beslut"] == "vila" and "4 h 30 min" in i["varfor"]
    assert "BPM" in i["plan"]["text"] and i["plan"]["minuter"] <= 20


def test_bra_natt_passdag_ger_trana_i_zon_2(v):
    db, vardag, _ = v
    nu = _morgon()
    _somn(db, nu - 3600, 8.2)
    i = vardag.idag(nu)
    assert i["beslut"] == "trana"
    assert i["plan"]["zon"] == 2 and (i["plan"]["puls_lo"], i["plan"]["puls_hi"]) == (117, 135)


def test_zoner_fran_alder():
    from konsiliet import vardag
    z = vardag.zoner({**vardag.STANDARD}, time.time())
    assert z["maxpuls"] == 195 and z["zoner"][1]["lo"] == 117


def test_budget_tysta_timmar_och_snooze(v):
    db, vardag, pub = v
    dag = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0).timestamp()
    for k in range(6):
        vardag.notis("afk", "t", "b", dag + k * 60)
    # två platser sparas åt läggdags och pass: AFK stoppas efter 4
    assert len(pub) == 4
    assert vardag.notis("pass", "t", "b", dag + 600)
    natt = datetime.now().replace(hour=2, minute=0, second=0, microsecond=0).timestamp()
    assert not vardag.notis("pass", "t", "b", natt)
    vardag.svara("pass", "snooze", 60, dag + 700)
    assert not vardag.notis("pass", "t", "b", dag + 800)
    st = vardag.notis_statistik(dag + 900, 1)
    assert st["idag"] == 5


def test_fokuslage_stoppar_afk_men_inte_lagg(v):
    db, vardag, pub = v
    dag = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0).timestamp()
    vardag.svara("fokus", "fokus", 120, dag)
    assert not vardag.notis("afk", "t", "b", dag + 60)
    assert vardag.notis("sova", "t", "b", dag + 60)
    vardag.svara("fokus", "av", None, dag + 120)
    assert vardag.notis("afk", "t", "b", dag + 180)


def test_atgarder_ta_upp_borjar_med_vardcentralen(v):
    db, vardag, _ = v
    a = vardag.atgarder({}, {"bradska": "ta_upp_med_varden", "rad": ["Sov åtta timmar i natt.", "Drick vatten"]})
    assert 1 <= len(a) <= 3 and a[0].startswith("Boka en tid") and "Sov åtta timmar i natt." in a


def test_idrottslakarens_granser():
    from konsiliet.rutiner import _inom_granser
    plan = {"minuter": 30, "puls_lo": 117, "puls_hi": 135}
    assert _inom_granser("Jogga 30 min med puls 117-135 BPM.", plan) is None
    assert _inom_granser("Kör 60 min.", plan)
    assert _inom_granser("Håll pulsen runt 150 BPM.", plan)


def test_efter_pass_zoner_och_rad(v):
    db, vardag, pub = v
    nu = time.time()
    st = nu - 1800
    db.insert_samples([(st + k * 5, "hr", 125, "test") for k in range(360)])
    with db.tx() as c:
        c.execute("INSERT INTO exercise VALUES ('p', ?, ?, 'löpning', 'test')", (st, nu - 60))
    s = vardag.efter_pass("p", nu)
    assert s["zon_minuter"][1] >= 28 and s["malzon"] == 2
    assert pub and pub[-1][0] == "pass.klart" and "zon 2" in pub[-1][1]["body"]
