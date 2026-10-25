"""Usługi zewnętrzne bez internetu: odpowiedzi GUGiK/OSM zastąpione danymi testowymi,
oraz czyste funkcje (NIP, formatowanie nazw, normalizacja ulic, rejony)."""
import json

import pytest

from generator_wt import geocoder, rejestry, slowniki, ulice
from generator_wt.model import Wierzcholek


# ------------------------------------------------------------------ geokodowanie

class _Odp:
    def __init__(self, tekst="", dane=None):
        self.text, self._dane, self.status_code = tekst, dane, 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._dane


class _Sesja:
    def __init__(self):
        self.zapytania = 0

    def get(self, url, params=None, timeout=None):
        self.zapytania += 1
        if url == geocoder.ULDK_URL:
            return _Odp("0\n146501_2.0001.123|mazowieckie|miński|Jakubów|Rządza|123/4")
        return _Odp(dane={"results": {"1": {"city": "Rządza", "street": "Leśna",
                                            "code": "05-306", "number": "5",
                                            "distance": 12.0}}})


def test_geokodowanie_i_cache(tmp_path):
    cache = tmp_path / "cache.json"
    g = geocoder.Geokoder(2178, plik_cache=cache)
    g.sesja = _Sesja()
    slupy = [Wierzcholek(id=i, x=7541000 + i * 30, y=5787000) for i in range(5)]
    assert geocoder.uzupelnij(slupy, g, watki=2, zapis_co=2) == 0
    w = slupy[0]
    assert (w.miejscowosc, w.ulica, w.gmina, w.dzialka, w.kod) == \
           ("Rządza", "Leśna", "Jakubów", "123/4", "05-306")
    assert g.sesja.zapytania == 10  # ULDK + UUG dla każdego słupa
    assert len(json.loads(cache.read_text(encoding="utf-8"))) == 5

    g2 = geocoder.Geokoder(2178, plik_cache=cache)
    g2.sesja = _Sesja()
    geocoder.uzupelnij(slupy, g2)
    assert g2.sesja.zapytania == 0  # wszystko z cache


def test_blad_uslugi_nie_trafia_do_cache(tmp_path):
    import requests

    class _Zla(_Sesja):
        def get(self, *a, **k):
            raise requests.ConnectionError("brak sieci")

    g = geocoder.Geokoder(2178, plik_cache=tmp_path / "c.json")
    g.sesja = _Zla()
    slupy = [Wierzcholek(id=0, x=7541000, y=5787000)]
    assert geocoder.uzupelnij(slupy, g) == 1
    assert "Błąd geokodowania" in slupy[0].uwagi
    assert g.cache == {}


# ------------------------------------------------------------------ sprawdzanie ulic

def test_sprawdzanie_ulic(monkeypatch):
    from pyproj import Transformer
    do_wgs = Transformer.from_crs(2178, 4326, always_xy=True)

    def droga(nazwa, pts):
        geo = []
        for x, y in pts:
            lon, lat = do_wgs.transform(x, y)
            geo.append({"lon": lon, "lat": lat})
        return {"tags": {"name": nazwa}, "geometry": geo}

    x0, y0 = 7541000, 5787000
    drogi = [droga("Leśna", [(x0 - 100, y0 + 10), (x0 + 100, y0 + 10)]),
             droga("Polna", [(x0 + 500, y0 - 100), (x0 + 500, y0 + 100)])]
    monkeypatch.setattr(ulice, "_pobierz_drogi", lambda *a, **k: drogi)
    slupy = [Wierzcholek(id=0, x=x0, y=y0, ulica="ul. Leśna"),
             Wierzcholek(id=1, x=x0 + 20, y=y0, ulica="Kwiatowa"),
             Wierzcholek(id=2, x=x0 + 300, y=y0, ulica="Kwiatowa")]
    w = {r.slup.id: r for r in ulice.sprawdz(slupy, 2178, 30.0)}
    assert w[0].zgodna is True
    assert w[1].zgodna is False and w[1].ulica_droga == "Leśna"
    assert w[2].zgodna is None  # brak nazwanej drogi w pobliżu


@pytest.mark.parametrize("a, b", [("ul. Leśna", "Leśna"), ("Aleja Róż", "al. Róż"),
                                  ("Jana Pawła II", "jana pawła ii"),
                                  ("Gen.-Hallera", "gen hallera")])
def test_normalizacja_ulic(a, b):
    assert ulice.norm(a) == ulice.norm(b)


# ------------------------------------------------------------------ rejestry

def test_nip_poprawny():
    assert rejestry.oczysc_nip("822-234-93-74") == "8222349374"


@pytest.mark.parametrize("nip", ["8222349375", "12345", ""])
def test_nip_bledny(nip):
    with pytest.raises(rejestry.BladRejestru):
        rejestry.oczysc_nip(nip)


@pytest.mark.parametrize("surowa, ladna", [
    ("INTERWAN SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ", "Interwan Sp. z o.o."),
    ("ISP SERWIS SPÓŁKA AKCYJNA", "ISP Serwis S.A."),  # krótkie wersaliki = skrót
    ("KOWALSKI-NOWAK SPÓŁKA JAWNA", "Kowalski-Nowak Sp.j."),
    ("TELEKOM", "Telekom"),
])
def test_ladna_nazwa(surowa, ladna):
    assert rejestry.ladna_nazwa(surowa) == ladna


@pytest.mark.parametrize("surowa, ladna", [("LAZUROWA", "ul. Lazurowa"),
                                           ("AL. JEROZOLIMSKIE", "al. Jerozolimskie"),
                                           ("PLAC WOLNOŚCI", "Plac Wolności")])
def test_ladna_ulica(surowa, ladna):
    assert rejestry.ladna_ulica(surowa) == ladna


# ------------------------------------------------------------------ słowniki

def test_rejon_dla_gminy():
    rejony = [{"Nazwa": "Rejon A", "Gminy": "Jakubów; Dębe Wielkie"},
              {"Nazwa": "Rejon B", "Gminy": "Otwock,Józefów"}]
    assert slowniki.rejon_dla_gminy(rejony, "jakubów")["Nazwa"] == "Rejon A"
    assert slowniki.rejon_dla_gminy(rejony, "Józefów")["Nazwa"] == "Rejon B"
    assert slowniki.rejon_dla_gminy(rejony, "Warszawa") is None
    assert slowniki.rejon_dla_gminy(rejony, None) is None


def test_slowniki_zapis_operatora(tmp_path):
    plik = tmp_path / "s.xlsx"
    slowniki.utworz_szablon(plik)
    wpis = {"Nazwa": "Testnet", "NIP": "822-234-93-74", "Regon": "1"}
    assert slowniki.zapisz_operatora(plik, wpis) == "zaktualizowano"  # NIP z szablonu
    assert slowniki.zapisz_operatora(plik, {"Nazwa": "Inny", "NIP": "5260250274"}) == "dodano"
    lista = slowniki.wczytaj_liste(plik, slowniki.ARKUSZ_OPERATORZY)
    assert [o["Nazwa"] for o in lista] == ["Testnet", "Inny"]
