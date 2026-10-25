"""Plik stanu projektu (.wt.json): poprawki i wykluczenia przeżywają ponowną analizę."""
import json

from generator_wt import stan
from tests.conftest import nowy_projekt


def test_brak_pliku_stanu_nic_nie_tworzy(dxf):
    p = nowy_projekt(dxf)
    assert not p.plik_stanu.exists()
    assert p.plik_stanu.name == "projekt.wt.json"


def test_poprawki_po_ponownej_analizie(dxf):
    p = nowy_projekt(dxf)
    a, b = p.plan[5], p.plan[9]
    p.ustaw_pole(a, "ulica", "Testowa")
    p.ustaw_pole(a, "miejscowosc", "Testowo")
    p.ustaw_pole(a, "uwagi", "sprawdzić w terenie")
    p.ustaw_wykluczenie(b, True)
    assert p.plik_stanu.exists() and p.blad_stanu is None

    q = nowy_projekt(dxf)
    a2 = next(w for w in q.slupy if (w.x, w.y) == (a.x, a.y))
    b2 = next(w for w in q.slupy if (w.x, w.y) == (b.x, b.y))
    assert (a2.ulica, a2.miejscowosc, a2.uwagi) == ("Testowa", "Testowo", "sprawdzić w terenie")
    assert b2.wykluczony and b2 not in q.plan
    assert q.poprawek_zastosowanych == 2 and q.poprawek_niedopasowanych == []


def test_wlaczenie_usuwa_wpis(dxf):
    p = nowy_projekt(dxf)
    w = p.plan[3]
    p.ustaw_wykluczenie(w, True)
    p.ustaw_wykluczenie(w, False)
    dane = json.loads(p.plik_stanu.read_text(encoding="utf-8"))
    assert dane["slupy"] == {}


def test_ustawienia(dxf):
    p = nowy_projekt(dxf)
    p.zapisz_ustawienia({"prefiks": "S", "zakladka": 25})
    assert nowy_projekt(dxf).ustawienia_stanu() == {"prefiks": "S", "zakladka": 25}


def test_niedopasowana_poprawka_zostaje(dxf):
    p = nowy_projekt(dxf)
    p.stan["slupy"]["1.00;2.00"] = {"ulica": "Nigdzie"}
    p.zapisz_stan()
    q = nowy_projekt(dxf)
    assert q.poprawek_niedopasowanych == ["1.00;2.00"]
    assert any("nie pasuje" in o for o in q.ostrzezenia)
    q.zapisz_stan()
    assert "1.00;2.00" in json.loads(q.plik_stanu.read_text(encoding="utf-8"))["slupy"]


def test_dopasowanie_przesunietego_slupa(dxf):
    p = nowy_projekt(dxf)
    w = p.plan[0]
    stary = stan.klucz(w.x + 0.3, w.y)  # słup przesunięty w rysunku o 30 cm
    p.stan["slupy"][stary] = {"ulica": "Przesunięta"}
    p.zapisz_stan()
    q = nowy_projekt(dxf)
    w2 = next(s for s in q.slupy if (s.x, s.y) == (w.x, w.y))
    assert w2.ulica == "Przesunięta"
    assert stan.klucz(w.x, w.y) in q.stan["slupy"] and stary not in q.stan["slupy"]


def test_uszkodzony_plik(dxf):
    stan.plik_stanu(dxf).write_text("{to nie json", encoding="utf-8")
    p = nowy_projekt(dxf)
    assert p.stan == stan.pusty() and len(p.plan) == 151


def test_zapis_atomowy(tmp_path):
    plik = tmp_path / "a.wt.json"
    stan.zapisz(plik, stan.pusty())
    assert stan.wczytaj(plik) == stan.pusty()
    assert not (tmp_path / "a.wt.json.tmp").exists()


def test_ulica_zgodna_po_poprawce(dxf):
    p = nowy_projekt(dxf)
    w = p.plan[0]
    w.ulica_droga, w.ulica_zgodna = "Leśna", False
    p.ustaw_pole(w, "ulica", "ul. Leśna")
    assert w.ulica_zgodna is True
    p.ustaw_pole(w, "ulica", "Polna")
    assert w.ulica_zgodna is None  # decyzja użytkownika - nie zgłaszaj
