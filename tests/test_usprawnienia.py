"""Ułatwienia w oknie: ostatnie projekty, plik startowy, zmiany rysunku na dysku,
cofanie zmian, wyszukiwanie ODA, sprawdzanie nowej wersji i przycinanie paczki .exe."""
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from generator_wt import aktualizacje, dwg
from generator_wt.web.api import Api, BladApi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import przytnij_exe  # noqa: E402


@pytest.fixture
def api(tmp_path):
    a = Api(plik_ustawien=tmp_path / "ustawienia_okna.json")
    yield a
    a.czekaj()


def analizuj(api, plik):
    api.analizuj(str(plik), geokodowanie=False)
    api.czekaj()
    koniec = [z for z in api.zdarzenia(0)["zdarzenia"] if z["typ"] == "koniec"][-1]
    assert koniec["ok"], koniec.get("blad")
    return api.dane()


# ---------------------------------------------------------------- ostatnie projekty, plik startowy
def test_ostatnie_projekty(api, dxf, tmp_path):
    drugi = tmp_path / "drugi.dxf"
    shutil.copy(dxf, drugi)
    analizuj(api, dxf)
    analizuj(api, drugi)
    analizuj(api, dxf)
    assert api.start()["ostatnie"] == [str(dxf), str(drugi)]  # bez powtórzeń, najnowszy pierwszy
    drugi.unlink()
    assert api.start()["ostatnie"] == [str(dxf)]  # usunięte pliki znikają z listy


def test_plik_startowy_tylko_raz(api, dxf):
    api.plik_startowy = str(dxf)
    assert api.start()["plik_startowy"] == str(dxf)
    assert api.start()["plik_startowy"] is None  # przeładowanie strony nie analizuje ponownie


# ---------------------------------------------------------------- zmiany rysunku na dysku
def test_zmiana_rysunku_na_dysku(api, dxf):
    assert api.zdarzenia(0)["plik_zmieniony"] is False
    analizuj(api, dxf)
    assert api.zdarzenia(0)["plik_zmieniony"] is False
    t = time.time() - 10
    os.utime(dxf, (t, t))  # zapis w programie CAD
    assert api.zdarzenia(0)["plik_zmieniony"] is True
    api.pomin_zmiane_pliku()
    assert api.zdarzenia(0)["plik_zmieniony"] is False
    t = time.time()
    os.utime(dxf, (t, t))  # zapis dopiero trwa - jeszcze nie pytamy
    assert api.zdarzenia(0)["plik_zmieniony"] is False


# ---------------------------------------------------------------- cofanie zmian
def test_cofnij_i_ponow(api, dxf):
    d = analizuj(api, dxf)
    assert d["cofnij"] is None and d["ponow"] is None
    a, b = d["kolejnosc"][0], d["kolejnosc"][3]
    ulica = d["slupy"][a]["ulica"]
    d = api.ustaw_pole(a, "ulica", "Testowa")
    d = api.przelacz_wykluczenie(b)
    assert d["slupy"][b]["wykluczony"] and d["podsumowanie"]["plan"] == 150
    assert d["cofnij"].startswith("wyłączenie słupa")

    d = api.cofnij()
    assert not d["slupy"][b]["wykluczony"] and d["podsumowanie"]["plan"] == 151
    assert d["ponow"].startswith("wyłączenie słupa")
    d = api.cofnij()
    assert d["slupy"][a]["ulica"] == ulica and d["cofnij"] is None
    with pytest.raises(BladApi, match="cofnięcia"):
        api.cofnij()
    # plik stanu też wrócił - ponowna analiza nie przywraca cofniętych zmian
    assert api.projekt.stan["slupy"] == {}

    d = api.ponow()
    assert d["slupy"][a]["ulica"] == "Testowa"
    d = api.ponow()
    assert d["slupy"][b]["wykluczony"]
    d = api.cofnij()
    api.ustaw_pole(a, "uwagi", "x")  # nowa zmiana kasuje możliwość ponowienia
    assert api.dane()["ponow"] is None
    d = analizuj(api, dxf)  # nowa analiza zaczyna historię od nowa
    assert d["cofnij"] is None and d["slupy"][a]["ulica"] == "Testowa"


# ---------------------------------------------------------------- wyszukiwanie ODA
def test_przeszukanie_dyskow(tmp_path):
    dysk = tmp_path / "D"
    for k in ("programy/oda", "ODA/ODAFileConverter 26.4.0", "Windows/oda", "inne/x"):
        (dysk / k).mkdir(parents=True)
        (dysk / k / dwg.EXE).write_bytes(b"")
    # najnowsza wersja; folder Windows pomijany
    assert dwg._przeszukaj_dyski([str(dysk)]) == str(dysk / "ODA" / "ODAFileConverter 26.4.0" / dwg.EXE)
    shutil.rmtree(dysk / "ODA")
    assert dwg._przeszukaj_dyski([str(dysk)]) == str(dysk / "programy" / "oda" / dwg.EXE)
    shutil.rmtree(dysk / "programy")
    assert dwg._przeszukaj_dyski([str(dysk)]) is None


def test_znajdz_oda_zapamietuje_przeszukanie(monkeypatch, tmp_path):
    from ezdxf.addons import odafc
    exe = tmp_path / dwg.EXE
    exe.write_bytes(b"")
    wywolania = []
    monkeypatch.setattr(odafc, "get_win_exec_path", lambda: "")
    monkeypatch.setattr(dwg, "_WZORCE", [])
    monkeypatch.setattr(dwg.shutil, "which", lambda n: None)
    monkeypatch.setattr(dwg, "_znaleziony", [])
    monkeypatch.setattr(dwg, "_przeszukaj_dyski", lambda: wywolania.append(1) or str(exe))
    assert dwg.znajdz_oda() == str(exe) and dwg.znajdz_oda() == str(exe)
    assert len(wywolania) == 1  # dyski przeszukane raz
    dwg.znajdz_oda(odswiez=True)
    assert len(wywolania) == 2
    monkeypatch.setattr(dwg.shutil, "which", lambda n: "C:/bin/ODAFileConverter.exe")
    assert dwg.znajdz_oda() == "C:/bin/ODAFileConverter.exe"  # PATH przed dyskami


# ---------------------------------------------------------------- nowa wersja na GitHubie
class _Odp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_aktualizacje(monkeypatch, tmp_path):
    monkeypatch.setattr(aktualizacje, "PLIK_WERSJI", tmp_path / "wersja.json")
    assert aktualizacje.wersja() is None and aktualizacje.sprawdz() is None  # ze źródeł
    assert aktualizacje.opis_wersji() == "wersja ze źródeł"
    aktualizacje.zapisz_wersje("abc1234def", "main")
    assert aktualizacje.opis_wersji().startswith("wersja abc1234 z ")

    wydanie = {"target_commitish": "abc1234def", "published_at": "2026-11-02T10:00:00Z",
               "html_url": "https://github.com/cienki90/GENERATOR_WT/releases/tag/najnowsza-wersja"}
    monkeypatch.setattr(aktualizacje.urllib.request, "urlopen",
                        lambda zad, timeout: _Odp(json.dumps(wydanie).encode()))
    assert aktualizacje.sprawdz() is None  # ta sama wersja
    wydanie["target_commitish"] = "fff0000"
    assert aktualizacje.sprawdz() == {"adres": wydanie["html_url"], "data": "2026-11-02"}
    wydanie["html_url"] = "https://zly-adres.example/x"
    assert aktualizacje.sprawdz()["adres"] == aktualizacje.ADRES_WYDAN

    def bez_sieci(zad, timeout):
        raise OSError("brak internetu")
    monkeypatch.setattr(aktualizacje.urllib.request, "urlopen", bez_sieci)
    assert aktualizacje.sprawdz() is None


def test_aktualizacja_jako_zdarzenie(monkeypatch, api):
    monkeypatch.setattr(aktualizacje, "wersja", lambda: {"commit": "a"})
    monkeypatch.setattr(aktualizacje, "sprawdz", lambda: {"adres": "https://github.com/x", "data": "2026-11-02"})
    api.start()
    for _ in range(100):
        if any(z["typ"] == "aktualizacja" for z in api.zdarzenia(0)["zdarzenia"]):
            break
        time.sleep(0.02)
    assert api.start()["aktualizacja"]["data"] == "2026-11-02"


# ---------------------------------------------------------------- przycinanie paczki .exe
def test_importy_pe():
    assert any(n.startswith("python3") for n in przytnij_exe.importy_pe(Path(sys.executable)))


def test_przytnij_paczke(tmp_path):
    import PySide6
    zrodlo = Path(PySide6.__file__).parent
    qt = tmp_path / "paczka" / "_internal" / "PySide6"
    qt.mkdir(parents=True)
    for f in ("QtCore.pyd", "Qt6Core.dll"):  # prawdziwe pliki: QtCore.pyd importuje Qt6Core.dll
        shutil.copy(zrodlo / f, qt / f)
    for f in ("Qt63DCore.dll", "QtQml.pyd", "resources/qtwebengine_resources.pak",
              "resources/qtwebengine_resources.debug.pak", "translations/qt_pl.qm",
              "translations/qt_de.qm", "translations/qtwebengine_locales/pl.pak",
              "translations/qtwebengine_locales/de.pak", "qml/QtQuick/x.qml",
              "plugins/position/p.dll"):
        (qt / f).parent.mkdir(parents=True, exist_ok=True)
        (qt / f).write_bytes(b"x" * 100)
    assert przytnij_exe.przytnij(tmp_path / "paczka") > 0
    zostalo = {str(p.relative_to(qt)).replace("\\", "/") for p in qt.rglob("*") if p.is_file()}
    assert zostalo == {"QtCore.pyd", "Qt6Core.dll", "resources/qtwebengine_resources.pak",
                       "translations/qt_pl.qm", "translations/qtwebengine_locales/pl.pak"}
