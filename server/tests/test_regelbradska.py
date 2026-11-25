"""Brådskan efter öppna regler och spärrarna runt den."""
import numpy as np

from konsiliet import fakta
from konsiliet.konsiliet import Mote, bestam_bradska


def larm(**kw):
    d = {"ref": "F:larm", "matvarde": "hr", "observerat_median": 167, "steg_10_min_fore_och_under": 0,
         "traningspass_under_eller_strax_fore": "inget",
         "kvalitet_senaste_timmen": {"andel_hopp_over_25_slag_mellan_minuter": 0.02, "andel_saknade_minuter": 0}}
    d.update(kw)
    return {"F:larm": d}


AKUT = {"kind": "anomaly", "level": "akut", "metric": "hr"}


def test_akut_puls_i_vila_ger_kontakta_vard_nu():
    assert fakta.regelbradska(AKUT, larm())[0] == "kontakta_vard_nu"


def test_akut_puls_under_traning_ger_inte_larm():
    f = larm(traningspass_under_eller_strax_fore=[{"typ": "löpning"}])
    assert fakta.regelbradska(AKUT, f)[0] == "ingen"


def test_hoppiga_varden_ar_matfel():
    f = larm(kvalitet_senaste_timmen={"andel_hopp_over_25_slag_mellan_minuter": 0.4, "andel_saknade_minuter": 0.3})
    assert fakta.regelbradska(AKUT, f)[0] == "bevaka"


def test_avvikelse_kan_aldrig_bli_kontakta_vard_nu():
    t = {"kind": "anomaly", "level": "avvikelse", "metric": "hr"}
    assert fakta.regelbradska(t, larm())[0] != "kontakta_vard_nu"


def test_provsvar_utanfor_referens():
    f = {"F:prover": {"prover": [{"analys": "Ferritin", "varde": "9", "enhet": "µg/L", "dagar_sedan": 20,
                                  "bedomning_mot_referens": "under referensintervallet"}]}}
    assert fakta.regelbradska({"kind": "question"}, f)[0] == "ta_upp_med_varden"


def test_isolerade_spikar_hittas():
    t = np.arange(20) * 60.0
    v = np.full(20, 65.0)
    v[10] = 210
    k = fakta._kvalitet(np.c_[t, v])
    assert k["antal_isolerade_spikar"] == 1 and k["isolerade_spikar"][0]["varde"] == 210


def _mote(level: str, lage: str, regel: str) -> Mote:
    m = Mote("t", {"kind": "anomaly", "level": level})
    m.emit = lambda *a, **k: None  # type: ignore[method-assign]
    m.lage["bradska"] = lage
    m.regel = (regel, [])
    return m


def test_larmsparr_utan_akut_vaktregel():
    m = _mote("avvikelse", "fri", "bevaka")
    assert bestam_bradska(m, "kontakta_vard_nu", [{"text": "x"}])[0] == "ta_upp_med_varden"


def test_inga_belagda_pastaenden_ger_minst_bevaka():
    m = _mote("avvikelse", "fri", "ingen")
    assert bestam_bradska(m, "ingen", [])[0] == "bevaka"


def test_hybrid_sanker_inte_vardfall():
    m = _mote("akut", "hybrid", "kontakta_vard_nu")
    assert bestam_bradska(m, "ingen", [{"text": "x"}])[0] == "kontakta_vard_nu"


def test_hybrid_far_hoja_ett_steg():
    m = _mote("avvikelse", "hybrid", "ingen")
    assert bestam_bradska(m, "ta_upp_med_varden", [{"text": "x"}])[0] == "bevaka"


def test_fraga_med_hog_vilopuls_senaste_timmen_ger_bevaka():
    f = {"F:nu": {"puls_baslinje_samma_timme": 74, "puls_median_senaste_timmen": 106, "steg_senaste_timmen": 0}}
    assert fakta.regelbradska({"kind": "question"}, f)[0] == "bevaka"
    f["F:nu"]["steg_senaste_timmen"] = 2500  # rörelse förklarar pulsen
    assert fakta.regelbradska({"kind": "question"}, f)[0] == "ingen"
