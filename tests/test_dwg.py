"""DWG przez ODA File Converter. Konwerter jest zastępowany atrapą (na maszynach testowych
go nie ma): 'odczyt DWG' wczytuje DXF o tej samej treści, 'zapis DWG' zapisuje rysunek
pod nazwą .dwg. Sprawdzamy całą ścieżkę programu poza samą konwersją ODA."""
import shutil

import ezdxf
import pytest
from ezdxf.addons import odafc

from generator_wt import dwg
from generator_wt.main import main as cli
from generator_wt.web.api import Api, BladApi
from tests.conftest import PRZYKLAD, nowy_projekt


@pytest.fixture(autouse=True)
def _przywroc_opcje_ezdxf():
    """dwg.ustaw_oda zapisuje ścieżkę konwertera w globalnych opcjach ezdxf - po teście
    przywracamy poprzednią, żeby atrapa nie przeciekała do innych testów."""
    poprzednia = ezdxf.options.get("odafc-addon", "win_exec_path")
    yield
    ezdxf.options.set("odafc-addon", "win_exec_path", poprzednia)


@pytest.fixture
def bez_oda(monkeypatch):
    monkeypatch.setattr(dwg, "znajdz_oda", lambda wskazana=None, odswiez=False: None)


@pytest.fixture
def atrapa_oda(monkeypatch, tmp_path):
    exe = tmp_path / "ODA" / "ODAFileConverter.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    wywolania = {"odczyt": [], "zapis": []}

    def odczyt(plik, version=None, audit=False):
        wywolania["odczyt"].append(plik)
        return ezdxf.readfile(PRZYKLAD)

    def zapis(doc, plik, version=None, audit=False, replace=False):
        wywolania["zapis"].append(plik)
        doc.saveas(plik)

    monkeypatch.setattr(dwg, "znajdz_oda", lambda wskazana=None, odswiez=False: str(exe))
    monkeypatch.setattr(odafc, "readfile", odczyt)
    monkeypatch.setattr(odafc, "export_dwg", zapis)
    return wywolania


@pytest.fixture
def plik_dwg(tmp_path):
    cel = tmp_path / "projekt.dwg"
    shutil.copy(PRZYKLAD, cel)  # treść nieistotna - atrapa i tak czyta przykład
    return cel


def test_jest_dwg():
    assert dwg.jest_dwg("a.DWG") and dwg.jest_dwg("c:/x/b.dwg")
    assert not dwg.jest_dwg("a.dxf")


def test_znajdz_oda_najnowsza_wersja(monkeypatch, tmp_path):
    for wersja in ("25.12.0", "26.4.0", "26.10.0"):
        exe = tmp_path / f"ODAFileConverter {wersja}" / "ODAFileConverter.exe"
        exe.parent.mkdir()
        exe.write_bytes(b"")
    monkeypatch.setattr(dwg, "_WZORCE", [str(tmp_path / "ODAFileConverter*" / "ODAFileConverter.exe")])
    monkeypatch.setattr(odafc, "get_win_exec_path", lambda: "")
    assert dwg.znajdz_oda().endswith("ODAFileConverter 26.10.0\\ODAFileConverter.exe") or \
        dwg.znajdz_oda().endswith("ODAFileConverter 26.10.0/ODAFileConverter.exe")
    wskazany = tmp_path / "ODAFileConverter 25.12.0" / "ODAFileConverter.exe"
    assert dwg.znajdz_oda(str(wskazany)) == str(wskazany)


def test_odczyt_dwg_bez_oda(bez_oda, plik_dwg):
    with pytest.raises(dwg.BladDWG, match="ODA File Converter"):
        dwg.wczytaj(plik_dwg)


def test_dxf_dziala_bez_oda(bez_oda, dxf):
    assert len(nowy_projekt(dxf).slupy) == 151


def test_projekt_dwg(atrapa_oda, plik_dwg):
    p = nowy_projekt(plik_dwg)
    assert len(p.slupy) == 151 and atrapa_oda["odczyt"] == [str(plik_dwg)]
    assert p.plik_stanu.name == "projekt.wt.json"
    cel = plik_dwg.with_name("projekt_numeracja.dwg")
    p.zapisz_dxf(cel)
    assert atrapa_oda["zapis"] == [str(cel)] and cel.exists()
    p.zapisz_dxf(plik_dwg.with_name("projekt_numeracja.dxf"))  # DXF bez konwertera
    assert len(atrapa_oda["zapis"]) == 1


def test_format_rysunkow(dxf):
    assert nowy_projekt(dxf).format_rysunkow == "dwg"  # domyślnie DWG
    assert nowy_projekt(dxf, format_rysunkow="DXF").format_rysunkow == "dxf"


# ------------------------------------------------------------------ wiersz poleceń

def test_cli_domyslnie_dwg_wymaga_oda(bez_oda, dxf):
    with pytest.raises(SystemExit, match="ODA File Converter"):
        cli([str(dxf), "--bez-geokodowania", "--tak"])


def test_cli_dwg(atrapa_oda, plik_dwg):
    kat = plik_dwg.parent / "wyniki"
    assert cli([str(plik_dwg), "--bez-geokodowania", "--tak", "--katalog", str(kat),
                "--zestawienie", "brak"]) == 0
    assert sorted(f.name for f in kat.iterdir()) == ["projekt_numeracja.dwg", "projekt_pismo.docx"]


# ------------------------------------------------------------------ okno webowe

@pytest.fixture
def api(tmp_path):
    a = Api(plik_ustawien=tmp_path / "ustawienia_okna.json")
    yield a
    a.czekaj()


def test_api_dwg_bez_oda(bez_oda, api, plik_dwg, dxf):
    assert api.start()["oda"]["dostepny"] is False
    with pytest.raises(BladApi, match="ODA File Converter"):
        api.analizuj(str(plik_dwg), geokodowanie=False)
    api.analizuj(str(dxf), geokodowanie=False)
    api.czekaj()
    o = {"dxf": True, "katalog": str(dxf.parent / "w")}
    assert api.podsumowanie_generowania(o)["brak_oda"] is True
    assert api.podsumowanie_generowania({**o, "format": "dxf"})["brak_oda"] is False
    with pytest.raises(BladApi, match="ODA File Converter"):
        api.generuj(o)


def test_api_dwg(atrapa_oda, api, plik_dwg):
    assert api.start()["oda"]["dostepny"] is True
    api.analizuj(str(plik_dwg), geokodowanie=False)
    api.czekaj()
    assert len(api.dane()["slupy"]) == 151
    api.generuj({"dxf": True, "projektowa": True, "katalog": str(plik_dwg.parent / "w")})
    api.czekaj()
    koniec = [z for z in api.zdarzenia(0)["zdarzenia"] if z["typ"] == "koniec"][-1]
    assert koniec["ok"] and sorted(koniec["wynik"]["zapisane"]) == [
        "projekt_numeracja.dwg", "projekt_tabela_projektowa.xlsx"]


def test_api_nieobslugiwany_format(api, tmp_path):
    plik = tmp_path / "rysunek.pdf"
    plik.write_bytes(b"")
    with pytest.raises(BladApi, match="DWG i DXF"):
        api.analizuj(str(plik))


def test_api_wskaz_oda(api, tmp_path):
    assert api.wskaz_oda()["brak_dialogu"] is True  # przeglądarka: bez okna wyboru pliku
    with pytest.raises(BladApi):
        api.wskaz_oda(str(tmp_path / "nie_ma.exe"))
    exe = tmp_path / "ODAFileConverter.exe"
    exe.write_bytes(b"")
    r = api.wskaz_oda(str(exe))
    assert r["dostepny"] and r["sciezka"] == str(exe)
    assert Api(plik_ustawien=api.plik_ustawien).cfg.oda_sciezka == str(exe)  # zapamiętane
