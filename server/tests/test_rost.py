"""Rösterna: API:t läser bara upp repliker som finns i händelseloggen, aldrig fri text. Och normaliseringen."""
import importlib

import pytest


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setenv("KONSILIET_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("KONSILIET_ROST_DIR", str(tmp_path / "rost"))
    from konsiliet import config, db, rost
    importlib.reload(config)
    importlib.reload(db)
    db._initialized = False
    importlib.reload(rost)
    from fastapi.testclient import TestClient

    from konsiliet import api
    importlib.reload(api)
    anrop = []

    def falsk_ljud(agent, text, **_):
        anrop.append((agent, text))
        f = tmp_path / "x.ogg"
        f.write_bytes(b"OggS")
        return f

    monkeypatch.setattr(rost, "ljud", falsk_ljud)
    monkeypatch.setattr(rost, "forvarm", lambda: None)
    return TestClient(api.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)), db, anrop


def test_fri_text_avvisas(klient):
    c, db, anrop = klient
    for url in ("/api/rost?agent=kardiolog&text=Hej", "/api/rost/?text=Hej", "/api/rost/abc?text=Hej"):
        assert c.get(url).status_code in (404, 405, 422)
    assert anrop == []


def test_bara_agent_say_i_loggen(klient):
    c, db, anrop = klient
    start = db.add_event("consult.start", {"consult_id": "x", "trigger": "t", "members": []})
    say = db.add_event("agent.say", {"consult_id": "x", "agent": "kardiolog", "to": "alla", "text": "Pulsen låg på 68."})
    assert c.get(f"/api/rost/{start['id']}").status_code == 404
    assert c.get("/api/rost/999999").status_code == 404
    # extra parametrar ignoreras: det är loggens text som läses upp, inte klientens
    r = c.get(f"/api/rost/{say['id']}?text=Något%20annat&agent=advokat")
    assert r.status_code == 200
    assert anrop == [("kardiolog", "Pulsen låg på 68.")]


def test_hastighetsgrans(klient):
    c, db, anrop = klient
    from konsiliet import rost
    say = db.add_event("agent.say", {"agent": "somn", "text": "Kort sömn."})
    koder = [c.get(f"/api/rost/{say['id']}").status_code for _ in range(rost.PER_MINUT + 3)]
    assert koder.count(200) == rost.PER_MINUT and koder[-1] == 429


def test_via_tunnel_utan_token(klient):
    c, db, _ = klient
    say = db.add_event("agent.say", {"agent": "somn", "text": "Kort sömn."})
    assert c.get(f"/api/rost/{say['id']}", headers={"Cf-Connecting-Ip": "1.2.3.4"}).status_code == 401


def test_normalisering():
    from konsiliet.rost import for_tal
    assert for_tal("Sömnen: 5 h 40 min.") == "Sömnen: fem timmar och fyrtio minuter."
    assert "syremättnad nittiosju procent" in for_tal("SpO2 97 %")
    assert "H R V" in for_tal("HRV låg")
    assert "sextioåtta slag per minut" in for_tal("puls 68 slag/min")
    assert "sextiosju slag per minut" in for_tal("67 BPM")
    assert "Kropp sextiofyra" in for_tal("Kropp64")
    assert "S:hr" not in for_tal("Enligt källan S:hr:1795450202-1795536602 (Ref: S:hr:1-2) är det så.")
    assert "en natt" in for_tal("1 natt") and "ett dygn" in for_tal("1 dygn")
    assert "musskel" in for_tal("muskel", "piper") and "muskel" in for_tal("muskel", "parambe")
