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


def test_siffra_fran_vakten_godkanns_nar_larmet_citeras():
    assert ok("Medianpulsen var 151 slag/min under 10 minuter.", ["U:utlosare"])

def test_larmets_siffra_kraver_att_larmet_citeras():
    # tidigare räknades larmtexten in i varje källa; nu måste larmet anges som källa
    assert not ok("Medianpulsen var 151 slag/min under 10 minuter.", ["S:hr:1-2"])

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


# ---- fusk som granskaren ska fånga (ett test per fusk)

def mote2() -> Mote:
    m = mote()
    m.refs.update({
        "S:hr:1795450202-1795536602": {"ref": "S:hr:1795450202-1795536602", "metric": "hr", "median": 65.0,
                                       "start": 1795450202},
        "S:steps:1-2": {"ref": "S:steps:1-2", "metric": "steps", "median": 0.0, "summa": 12},
        "S:skin_temp:1-2": {"ref": "S:skin_temp:1-2", "metric": "skin_temp", "median": 34.4},
        "F:natter": {"ref": "F:natter", "natter": [{"hrv_median_ms": 31, "hudtemp_median_c": 34.9}],
                     "baslinje_natt": {"hrv_median_ms": 56, "hudtemp_median_c": 34.1},
                     "skillnad_senaste_3_natter_mot_baslinje": {"hrv_median_ms": -22.0, "hudtemp_median_c": 0.6}},
    })
    return m


def ok2(text: str, kallor: list[str]) -> bool:
    return len(granska(mote2(), "x", {"pastaenden": [{"text": text, "kallor": kallor}]})) == 1


def test_tidsstampel_i_ref_ar_inte_ett_matvarde():
    assert not ok2("Pulsen var 1795450202 i perioden.", ["S:hr:1795450202-1795536602"])

def test_tidsstampel_i_data_ar_inte_ett_matvarde():
    assert not ok2("Värdet 1795450202 sågs.", ["S:hr:1795450202-1795536602"])

def test_siffra_fran_fel_matvarde_stryks():
    # 65 finns i pulsserien men är inget HRV-värde
    assert not ok2("HRV var 65 ms.", ["S:hr:1795450202-1795536602"])

def test_observerat_varde_kallat_baslinje_stryks():
    # felet från riktiga körningen: observerade 65 kallades baslinje när baslinjen var 72,5
    assert not ok("Baslinjen är 65 slag/min.", ["S:hr:1-2", "B:hr:h16"])

def test_ratt_baslinje_godkanns():
    assert ok("Pulsen 65 slag/min ligger under baslinjen 72,5 slag/min.", ["S:hr:1-2", "B:hr:h16"])

def test_sma_tal_kontrolleras():
    # under den gamla gränsen (>= 3) slapp små påhittade tal igenom
    assert not ok2("Hudtemperaturen har stigit 2,5 grader.", ["F:natter"])
    assert ok2("Hudtemperaturen har stigit 0,6 grader mot baslinjen.", ["F:natter"])

def test_slutsats_utan_ratt_kalla_stryks():
    assert not ok2("Det tyder på en begynnande infektion.", ["S:steps:1-2"])
    assert ok2("Det kan tyda på en begynnande infektion.", ["S:skin_temp:1-2"])

def test_jarnbrist_kraver_provsvar():
    assert not ok2("Tröttheten beror troligen på järnbrist.", ["F:natter"])

def test_slutsatsens_siffror_granskas():
    from konsiliet.konsiliet import granska_slutsats
    m = mote2()
    godk = [{"text": "HRV 31 ms", "kallor": ["F:natter"], "av": "x"}]
    v = granska_slutsats(m, {"sammanfattning": "HRV är 31 ms. Pulsen är 99 slag/min.", "rad": ["Vila 3 dagar", "Drick 7 liter"],
                             "fragor_till_varden": []}, godk)
    assert "99" not in v["sammanfattning"] and "31" in v["sammanfattning"]
    assert v["rad"] == ["Vila 3 dagar"]

def test_skillnad_med_fel_tecken_stryks():
    # riktiga körningen 2026-11-24: källan sa +4,3 ms, specialisten skrev "sjunkit med 4,3 ms"
    m = mote2()
    m.refs["F:natter"]["skillnad_senaste_3_natter_mot_baslinje"]["hrv_median_ms"] = 4.3
    g = granska(m, "x", {"pastaenden": [{"text": "HRV har sjunkit med 4,3 ms mot baslinjen.", "kallor": ["F:natter"]}]})
    assert g == []

def test_skillnad_med_ratt_tecken_godkanns():
    assert ok2("HRV har sjunkit med 22 ms mot baslinjen.", ["F:natter"])
    assert ok2("HRV är 22 ms lägre än baslinjen.", ["F:natter"])
    assert not ok2("HRV har ökat med 22 ms.", ["F:natter"])

def test_niva_efter_sjunkit_till_godkanns():
    assert ok2("HRV har sjunkit till 31 ms.", ["F:natter"])

def test_falt_med_grans_i_namnet_och_tusental():
    m = mote2()
    m.refs["F:puls"] = {"ref": "F:puls", "minuter_over_140": 46, "max": 171}
    m.refs["F:dagar"] = {"ref": "F:dagar", "dagar": [{"steg": 13148}], "baslinje_steg_per_dag": 5971}
    def g(t, k):
        return len(granska(m, "x", {"pastaenden": [{"text": t, "kallor": k}]})) == 1
    assert g("46 minuter över 140 slag/min.", ["F:puls"])
    assert g("13 148 steg idag mot baslinjen 5 971 steg.", ["F:dagar"])
    assert g("En 18-åring med 13 148 steg.", ["F:dagar"])

def test_intervall_ar_inte_negativt_tal():
    m = mote2()
    m.refs["F:natter"]["natter"] = [{"nattpuls_lagsta_10min": 51}, {"nattpuls_lagsta_10min": 55}]
    assert len(granska(m, "x", {"pastaenden": [{"text": "Nattpulsen 51-55 slag/min.", "kallor": ["F:natter"]}]})) == 1

def test_stor_period_kontrolleras():
    # riktiga körningen: steg (4525) kallades "minuter framför datorn"; perioder får inte gömma stora tal
    m = mote2()
    m.refs["F:dagar"] = {"ref": "F:dagar", "dagar": [{"steg": 4525, "minuter_vid_datorn_per_kategori": {"spel": 210}}]}
    g = lambda t: len(granska(m, "x", {"pastaenden": [{"text": t, "kallor": ["F:dagar"]}]})) == 1
    assert g("210 minuter spel i går.")
    assert not g("Personen satt 4600 minuter vid datorn.")
    assert not g("Personen satt 4525 minuter vid datorn.")

def test_citerat_faltnamn_ar_inte_en_siffra():
    assert ok2("Enligt skillnad_senaste_3_natter_mot_baslinje är HRV 22 ms lägre.", ["F:natter"])

def test_tid_i_timmar_och_minuter():
    m = mote2()
    m.refs["F:natter"]["natter"] = [{"somn_timmar": 8.2}]
    m.refs["F:puls"] = {"ref": "F:puls", "minuter_over_140": 46}
    g = lambda t, k: len(granska(m, "x", {"pastaenden": [{"text": t, "kallor": k}]})) == 1
    assert g("Sömnen var 8,2 timmar.", ["F:natter"])
    assert g("46 minuter över 140 slag/min.", ["F:puls"])

def test_decimal_efter_baslinje():
    assert ok("Baslinjen är 72.5 slag/min och pulsen 65.", ["S:hr:1-2", "B:hr:h16"])

def test_decimalkomma_efter_baslinje():
    assert ok("Pulsen 65 ligger under baslinjen på 72,5 slag/min.", ["S:hr:1-2", "B:hr:h16"])

def test_somnskuld_kvallar_och_belastning_godkanns():
    m = mote2()
    m.refs["F:somnskuld"] = {"ref": "F:somnskuld", "somnbehov_timmar": 8.0, "somnskuld_timmar_senaste_7_natter": 15.3,
                             "medel_somn_timmar_senaste_7": 5.8, "natter_med_datorn_efter_midnatt": 7}
    m.refs["F:kvallar"] = {"ref": "F:kvallar", "kvallar_med_datorn_efter_23": 6,
                           "kvallar": [{"minuter_vid_datorn_efter_23": 125, "sista_datorminut": "01:04"}]}
    m.refs["F:belastning"] = {"ref": "F:belastning", "antal_traningspass": 3, "traningsminuter_totalt": 180}
    g = lambda t, k: len(granska(m, "x", {"pastaenden": [{"text": t, "kallor": k}]})) == 1
    assert g("Sömnskulden är 15,3 timmar på sju nätter, med 5,8 timmars sömn i snitt mot behovet 8 timmar.", ["F:somnskuld"])
    assert g("Datorn var igång 125 minuter efter 23 och sista minuten var 01:04.", ["F:kvallar"])
    assert g("3 träningspass på 180 minuter senaste veckan.", ["F:belastning"])
    assert not g("Sömnskulden är 21 timmar.", ["F:somnskuld"])
    assert not g("Du har sömnskuld.", ["F:belastning"])

def test_fel_rad_i_faktabladet_ratttas_om_bara_en_rad_passar():
    m = mote2()
    m.refs["F:somnskuld"] = {"ref": "F:somnskuld", "somnskuld_timmar_senaste_7_natter": 15.3}
    g = granska(m, "x", {"pastaenden": [{"text": "HRV är 22 ms lägre än baslinjen.", "kallor": ["F:somnskuld"]}]})
    assert len(g) == 1 and g[0]["kalla_tillagd_av_granskaren"] == "F:natter"
    # en påhittad siffra räddas inte
    assert granska(m, "x", {"pastaenden": [{"text": "HRV är 23 ms lägre än baslinjen.", "kallor": ["F:somnskuld"]}]}) == []
