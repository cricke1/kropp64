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


# ------------------------------------------------ kalibrering mot personens egen baslinje

def _vanliga_natter(db, sista_morgon: datetime, natter: int = 21, timmar: float = 7.2, seed: int = 1):
    """Syntetiska nätter som för en 18-åring som sover ungefär 7 timmar: puls, HRV och sömnpass."""
    import random
    r = random.Random(seed)
    rows = []
    for d in range(natter, 0, -1):
        slut = (sista_morgon - timedelta(days=d - 1)).replace(hour=7, minute=45).timestamp()
        h = timmar + r.uniform(-0.3, 0.3)
        start = slut - h * 3600
        with db.tx() as c:
            c.execute("INSERT OR REPLACE INTO sleep VALUES (?,?,?,?,?)", (f"n{d}", start, slut, "[]", "test"))
        for k in range(int(h * 60)):
            ts = start + k * 60
            rows.append((ts, "hr", 54 + r.gauss(0, 2), "test"))
            if k % 5 == 0:
                rows.append((ts, "hrv_rmssd", 55 + r.gauss(0, 6), "test"))
    db.insert_samples(rows)


def _forra_mandag() -> datetime:
    d = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday() + 7)


def test_vanlig_vecka_ger_traning_tre_dagar(v):
    """En vanlig vecka för honom (7,2 h sömn, Headroom under 55 men som vanligt) ska ge träning mån, ons och lör."""
    db, vardag, _ = v
    mon = _forra_mandag()
    _vanliga_natter(db, mon + timedelta(days=6))
    trana = []
    for dag in range(7):
        t = mon + timedelta(days=dag, hours=17, minutes=30)
        i = vardag.idag(t.timestamp())
        if i["beslut"] == "trana":
            trana.append(dag)
            with db.tx() as c:  # han kör passet
                c.execute("INSERT INTO exercise VALUES (?,?,?,?,?)", (f"p{dag}", t.timestamp() + 600, t.timestamp() + 2400, "löpning", "test"))
    assert trana == [0, 2, 5]
    assert i["headroom_baslinje"] is not None


def test_dalig_natt_ger_lugnt_eller_vila(v):
    db, vardag, _ = v
    mon = _forra_mandag()
    _vanliga_natter(db, mon)
    # natten mot måndag: 5 h 30 min i stället för drygt 7
    slut = mon.replace(hour=7, minute=45).timestamp()
    with db.tx() as c:
        c.execute("UPDATE sleep SET start=? WHERE end=?", (slut - 5.5 * 3600, slut))
    i = vardag.idag((mon + timedelta(hours=17, minutes=30)).timestamp())
    assert i["beslut"] == "lugnt" and "sömn" in i["varfor"]
    with db.tx() as c:
        c.execute("UPDATE sleep SET start=? WHERE end=?", (slut - 4.5 * 3600, slut))
    assert vardag.idag((mon + timedelta(hours=17, minutes=31)).timestamp())["beslut"] == "vila"


def test_sjukdomstecken_ger_vila(v):
    """Hög vilopuls och låg HRV samma natt (som vid en förkylning) ger vila, även på en passdag."""
    db, vardag, _ = v
    mon = _forra_mandag()
    _vanliga_natter(db, mon)
    slut = mon.replace(hour=7, minute=45).timestamp()
    with db.tx() as c:
        c.execute("DELETE FROM samples WHERE ts > ? AND ts < ?", (slut - 8 * 3600, slut))
    db.insert_samples([(slut - 7 * 3600 + k * 60, "hr", 68, "test") for k in range(420)] +
                      [(slut - 7 * 3600 + k * 300, "hrv_rmssd", 32, "test") for k in range(84)])
    i = vardag.idag((mon + timedelta(hours=17, minutes=30)).timestamp())
    assert i["beslut"] == "vila"
    # hudtemperatur +1,2 °C räcker också
    db2 = db
    with db2.tx() as c:
        c.execute("DELETE FROM samples WHERE ts > ? AND ts < ? AND metric IN ('hr','hrv_rmssd')", (slut - 8 * 3600, slut))
    db.insert_samples([(slut - 3600 * k, "skin_temp_delta", 1.2, "test") for k in (1, 3, 5)])
    assert vardag.idag((mon + timedelta(hours=17, minutes=31)).timestamp())["beslut"] == "vila"
