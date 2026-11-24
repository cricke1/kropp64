"""Vakten: realtid, sent inkommande data, nedkylning, källprioritet. Syntetisk testdata i egen databas."""
import os
import random
import time

import pytest


@pytest.fixture()
def miljo(tmp_path, monkeypatch):
    monkeypatch.setenv("KONSILIET_DB", str(tmp_path / "t.db"))
    import importlib

    from konsiliet import config, db, vakt
    importlib.reload(config)
    importlib.reload(db)
    db._initialized = False
    importlib.reload(vakt)
    now = time.time()
    rows = []
    for i in range(14 * 24 * 60, 0, -2):
        ts = now - i * 60
        rows.append((ts, "hr", 60 + random.gauss(0, 3), "watch"))
    db.insert_samples(rows)
    return db, vakt, now


def test_akut_puls_i_vila(miljo):
    db, vakt, now = miljo
    db.insert_samples([(now - 600 + j * 30, "hr", 150, "watch") for j in range(20)])
    assert [f.rule for f in vakt.evaluate() if f.level == "akut"] == ["hr_rest_acute"]


def test_ingen_akut_under_traningspass(miljo):
    db, vakt, now = miljo
    db.insert_samples([(now - 600 + j * 30, "hr", 150, "watch") for j in range(20)])
    with db.tx() as c:
        c.execute("INSERT INTO exercise VALUES ('p', ?, NULL, 'lopning', 'watch')", (now - 1800,))
    assert not [f for f in vakt.evaluate() if f.rule == "hr_rest_acute"]


def test_sent_data_blir_aldrig_akut(miljo):
    db, vakt, now = miljo
    old = now - 3 * 3600
    db.insert_samples([(old - 600 + j * 60, "spo2", 85, "health_connect") for j in range(10)])
    f = [f for f in vakt.evaluate(old) if f.rule == "spo2_low"]
    assert f and f[0].level == "avvikelse" and "efterhand" in f[0].title


def test_nedkylning_sparas_i_databasen(miljo):
    db, vakt, now = miljo
    db.insert_samples([(now - 600 + j * 30, "hr", 150, "watch") for j in range(20)])
    assert vakt.evaluate()
    assert not vakt.evaluate()  # inom nedkylningen
    assert db.conn().execute("SELECT COUNT(*) FROM vakt_state").fetchone()[0] >= 1


def test_kallprioritet_per_minut(miljo):
    db, vakt, now = miljo
    t0 = now - 100000
    db.insert_samples([(t0 + k * 60, "hrv_rmssd", 50, "health_connect") for k in range(5)])
    db.insert_samples([(t0 + k * 60 + 1, "hrv_rmssd", 99, "watch") for k in range(2)])
    assert [v for _, v in db.query_samples("hrv_rmssd", t0 - 1, t0 + 400)] == [99, 99, 50, 50, 50]


def test_testdata_halls_ute(miljo):
    db, vakt, now = miljo
    db.insert_samples([(now - 50, "spo2", 80, "watch-emulator"), (now - 40, "spo2", 81, "dev-syntetisk")])
    assert db.query_samples("spo2", now - 100) == []
