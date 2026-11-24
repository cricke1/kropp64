"""1177-tolkningen: modellens svar kontrolleras mot sidtexten. Fiktiv journalsida, ingen riktig persondata."""
import importlib
import json

import pytest

SIDA = """Provsvar
Provtagning 2026-03-12 Vårdcentralen Exempel
Ferritin 14 µg/L 15 - 150
Hemoglobin (Hb) 141 g/L 134 - 170
Anteckningar
2026-03-12 Läkare
Patienten söker för trötthet sedan två månader. Sover dåligt. Planerar blodprover."""


class Svar:
    def __init__(self, d):
        self.content = json.dumps(d, ensure_ascii=False)


@pytest.fixture()
def h(tmp_path, monkeypatch):
    monkeypatch.setenv("KONSILIET_DB", str(tmp_path / "t.db"))
    from konsiliet import config, db, hamtare1177, llm
    importlib.reload(config); importlib.reload(db); db._initialized = False
    importlib.reload(hamtare1177)
    modellsvar = {
        "anteckningar": [
            {"datum": "2026-03-12", "text": "Patienten söker för trötthet sedan två månader. Sover dåligt."},
            {"datum": "2026-03-12", "text": "Patienten har diabetes och behöver insulin."},  # påhittad
            {"datum": "2026-04-01", "text": "Patienten söker för trötthet sedan två månader."}],  # fel datum
        "provsvar": [
            {"analys": "Ferritin", "varde": "14 µg/L", "referens": "15 - 150"},
            {"analys": "Ferritin", "varde": "141 g/L"},  # felparat: Hb:s värde
            {"analys": "TSH", "varde": "2,1 mIE/L"}]}  # finns inte
    monkeypatch.setattr(llm, "chat", lambda *a, **k: Svar(modellsvar))
    return hamtare1177, db


def test_bara_avskrivet_och_ratt_parat_godkanns(h):
    mod, _ = h
    ant, prov = mod._llm_tolka(SIDA, "Journal")
    assert [a["text"][:20] for a in ant] == ["Patienten söker för "]
    assert [(p["analys"], p["varde"]) for p in prov] == [("Ferritin", "14 µg/L")]


def test_provsvar_flaggas_mot_referens_och_likadana_slas_inte_ihop(h):
    mod, db = h
    rad = {"datum": "2026-03-12", "analys": "Ferritin", "varde": "14 µg/L", "referens": "15 - 150"}
    assert mod.tolka_provsvar([rad, dict(rad)]) == 2
    rows = db.conn().execute("SELECT flag FROM labs").fetchall()
    assert [r[0] for r in rows] == ["L", "L"]


def test_ny_hamtning_ger_inga_dubbletter(h):
    mod, db = h
    p = [{"rubrik": "2026-03-12", "text": "Patienten söker för trötthet sedan två månader."}]
    mod.tolka_anteckningar(p, "anteckningar")
    mod.tolka_anteckningar(p, "Anteckningar ")  # annan kategorietikett, samma post
    assert db.conn().execute("SELECT COUNT(*) FROM journal").fetchone()[0] == 1
