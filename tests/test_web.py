"""Okno webowe: API (bez przeglądarki) i lokalny serwer (token, pliki, metody)."""
import json
import urllib.error
import urllib.request

import pytest

from generator_wt.web.api import METODY, Api, BladApi
from generator_wt.web.serwer import Serwer


@pytest.fixture
def api(tmp_path):
    a = Api(plik_ustawien=tmp_path / "ustawienia_okna.json")
    yield a
    a.czekaj()


def analizuj(api, dxf, **ust):
    api.analizuj(str(dxf), geokodowanie=False, ustawienia=ust)
    api.czekaj()
    koniec = [z for z in api.zdarzenia(0)["zdarzenia"] if z["typ"] == "koniec"][-1]
    assert koniec["ok"], koniec.get("blad")
    return api.dane()


def test_start_bez_projektu(api):
    s = api.start()
    assert s["projekt"] is None and s["dialogi"] is False
    assert s["slowniki"]["operatorzy"]
    assert api.wybierz_plik("") == {"plik": None, "brak_dialogu": True}


def test_analiza_i_dane(api, dxf):
    d = analizuj(api, dxf)
    assert d["epsg"] == 2178 and "+proj=tmerc" in d["proj4"]
    assert len(d["slupy"]) == 151 and len(d["kolejnosc"]) == 151
    assert len(d["arkusze"]) == 18 and len(d["stacje"]) == 7
    assert d["podsumowanie"]["plan"] == 151
    assert all(len(k) == 2 for k in d["krawedzie"])
    sekcje = {s["id"]: s for s in d["kontrola"]}
    assert sekcje["przesla"]["poziom"] == "blad" and len(sekcje["przesla"]["pozycje"]) == 16
    assert len(sekcje["kliki"]["pozycje"]) == 2
    json.dumps(d)  # całość musi dać się wysłać jako JSON
    typy = [z["typ"] for z in api.zdarzenia(0)["zdarzenia"]]
    assert "postep" in typy and "log" in typy and typy[-1] in ("koniec", "log")


def test_brak_pliku(api, tmp_path):
    with pytest.raises(BladApi):
        api.analizuj(str(tmp_path / "nie_ma.dxf"))


def test_jedna_praca_naraz(api, dxf):
    api.analizuj(str(dxf), geokodowanie=False)
    with pytest.raises(BladApi):
        api.analizuj(str(dxf), geokodowanie=False)
    with pytest.raises(BladApi):
        api.dane()
    api.czekaj()


def test_edycja_wykluczenie_i_stan(api, dxf):
    d = analizuj(api, dxf)
    id0 = d["kolejnosc"][0]
    d = api.ustaw_pole(id0, "ulica", "Testowa")
    assert d["slupy"][id0]["ulica"] == "Testowa"
    with pytest.raises(BladApi):
        api.ustaw_pole(id0, "geo_x", "1")  # pola tylko do odczytu
    d = api.przelacz_wykluczenie(d["kolejnosc"][5])
    assert d["podsumowanie"]["plan"] == 150 and d["podsumowanie"]["wykluczone"] == 1
    d = analizuj(Api(plik_ustawien=api.plik_ustawien), dxf)  # nowe okno, ten sam projekt
    assert d["slupy"][id0]["ulica"] == "Testowa" and d["podsumowanie"]["plan"] == 150


def test_przelicz_i_arkusze(api, dxf):
    analizuj(api, dxf)
    d = api.przelicz({"prefiks": "S", "numer_startowy": 10})
    pierwszy = d["slupy"][d["kolejnosc"][0]]
    assert pierwszy["etykieta"] == "S10"
    assert api.ustawienia_projektu_dla(str(dxf))["prefiks"] == "S"
    api.przelicz_arkusze({"zakladka": 25})
    api.czekaj()
    assert len(api.dane()["arkusze"]) == 20


def test_generowanie(api, dxf):
    analizuj(api, dxf)
    o = {"dxf": True, "arkusze": True, "projektowa": True, "pismo": True, "wgs84": True,
         "katalog": str(dxf.parent / "wyniki"), "tolerancja_slupa": 5.0}
    s = api.podsumowanie_generowania(o)
    assert s["arkusze"] == 18 and s["pytaj_o_uklad"] and not s.get("ponowna_analiza")
    assert api.podsumowanie_generowania({**o, "tolerancja_slupa": 3.0}) == {"ponowna_analiza": True}
    api.generuj(o)
    api.czekaj()
    koniec = [z for z in api.zdarzenia(0)["zdarzenia"] if z["typ"] == "koniec"][-1]
    assert koniec["zadanie"] == "generuj" and koniec["ok"]
    assert koniec["wynik"]["bledy"] == []
    assert sorted(koniec["wynik"]["zapisane"]) == ["projekt_numeracja.dxf", "projekt_pismo.docx",
                                                   "projekt_tabela_projektowa.xlsx"]
    with pytest.raises(BladApi):
        api.generuj({})


def test_start_po_przeladowaniu_nie_powtarza_zdarzen(api, dxf):
    analizuj(api, dxf)
    s = api.start()
    assert s["projekt"]["nazwa"] == "projekt.dxf"
    assert s["nr_zdarzenia"] == api.zdarzenia(0)["zdarzenia"][-1]["nr"]
    assert any("Analiza zakończona" in t for t in s["dziennik"])


# ------------------------------------------------------------------ serwer HTTP

@pytest.fixture
def serwer(api):
    s = Serwer(api).start()
    yield s
    s.stop()


def _post(serwer, metoda, args=None, token=None, host=None):
    zad = urllib.request.Request(
        f"http://127.0.0.1:{serwer.port}/api/{metoda}", method="POST",
        data=json.dumps({"args": args or {}}).encode(),
        headers={"Content-Type": "application/json",
                 "X-Token": serwer.token if token is None else token})
    if host:
        zad.add_header("Host", host)
    try:
        with urllib.request.urlopen(zad, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get(serwer, sciezka):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{serwer.port}{sciezka}", timeout=30) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, None, b""


def test_serwer_strona_i_biblioteki(serwer):
    kod, typ, tresc = _get(serwer, "/")
    assert kod == 200 and typ.startswith("text/html") and b"Generator WT" in tresc
    for plik in ("/app.js", "/styl.css", "/vendor/ol.js", "/vendor/proj4.js", "/vendor/ol.css"):
        assert _get(serwer, plik)[0] == 200, plik


def test_serwer_nie_wychodzi_poza_static(serwer):
    for sciezka in ("/../api.py", "/%2e%2e/api.py", "/..%5capi.py", "/vendor/../../serwer.py"):
        assert _get(serwer, sciezka)[0] == 404, sciezka


def test_serwer_wymaga_tokenu(serwer):
    assert _post(serwer, "start", token="zly")[0] == 403
    assert _post(serwer, "start", token="")[0] == 403
    kod, d = _post(serwer, "start")
    assert kod == 200 and d["ok"]


def test_serwer_sprawdza_host(serwer):
    assert _post(serwer, "start", host="zly.example.com")[0] == 403


def test_serwer_tylko_metody_z_listy(serwer):
    assert _post(serwer, "_uruchom")[0] == 404
    assert _post(serwer, "czekaj")[0] == 404
    assert "czekaj" not in METODY and "log" not in METODY


def test_okno_qt_webengine(tmp_path, monkeypatch):
    """Okno programu: strona ładuje się w Qt WebEngine i łączy z API."""
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    import shiboken6
    from PySide6.QtCore import QEventLoop, Qt, QTimer
    from PySide6.QtWidgets import QApplication

    from generator_wt.web import okno as modul
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(modul, "Api", lambda dialogi: Api(plik_ustawien=tmp_path / "u.json",
                                                          dialogi=dialogi))
    o = modul.OknoWeb()
    wynik = {}
    try:
        o.show()
        petla = QEventLoop()
        o.widok.loadFinished.connect(lambda ok: wynik.update(zaladowano=ok))

        def sprawdz():
            o.widok.page().runJavaScript(
                "document.querySelector('#operator').options.length + '|' + typeof ol", 0,
                lambda r: (wynik.update(js=r), petla.quit()))
        o.widok.loadFinished.connect(lambda ok: QTimer.singleShot(2000, sprawdz))
        QTimer.singleShot(45000, petla.quit)
        petla.exec()
        assert wynik.get("zaladowano") is True
        liczba, ol = wynik["js"].split("|")
        assert int(liczba) > 0 and ol == "object"  # listy z API i biblioteka mapy wczytane
    finally:
        o.close()
        shiboken6.delete(o)
        app.processEvents()


def test_serwer_bledy_jako_komunikat(serwer):
    kod, d = _post(serwer, "dane")
    assert kod == 200 and d == {"ok": False, "blad": "Najpierw wczytaj i przeanalizuj projekt DXF."}
    kod, d = _post(serwer, "analizuj", {"nieznany": 1})
    assert kod == 200 and not d["ok"]
