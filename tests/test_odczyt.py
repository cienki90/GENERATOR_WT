"""Odczyt DXF: słupy, scalanie błędnych klików, strefy trafo, opisy, układ współrzędnych."""
import ezdxf
import pytest

from generator_wt import reader
from generator_wt.config import Config
from generator_wt.geocoder import wykryj_epsg
from tests.conftest import nowy_projekt


def test_przyklad(dxf):
    p = nowy_projekt(dxf)
    assert len(p.slupy) == 151
    assert len(p.stacje) == 7
    assert len(p.bledne_kliki) == 2
    assert p.opisanych_slupow == 149
    assert p.numerow_w_sieci == 148
    assert p.epsg == 2178
    assert p.ostrzezenia == []
    assert {s.nazwa for s in p.stacje} == {"05-0792", "05-1179", "05-0743", "05-0170",
                                           "05-0811", "05-0741", "05-0770"}


def test_sasiedztwo_symetryczne(dxf):
    p = nowy_projekt(dxf)
    for w in p.slupy:
        assert w.id not in w.sasiedzi
        for n in w.sasiedzi:
            assert w.id in p.slupy[n].sasiedzi


def _rysunek(*polilinie, warstwa="!tele"):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for pts in polilinie:
        msp.add_lwpolyline(pts, dxfattribs={"layer": warstwa})
    return doc


def test_scalanie_bliskich_wierzcholkow():
    # koniec pierwszej linii i początek drugiej "kliknięte" 1 m od siebie -> jeden słup
    doc = _rysunek([(0, 0), (40, 0)], [(41, 0), (80, 0)])
    slupy, bledne = reader.wczytaj_slupy(doc, Config())
    assert len(slupy) == 3
    assert len(bledne) == 1 and bledne[0].liczba == 2
    srodek = next(w for w in slupy if len(w.sasiedzi) == 2)
    assert srodek.scalonych == 2


def test_scalanie_przechodnie():
    # A-B < 5 m i B-C < 5 m (choć A-C > 5 m) => jeden słup
    doc = _rysunek([(0, 0), (100, 0)], [(104, 0), (200, 0)], [(108, 0), (108, 100)])
    slupy, _ = reader.wczytaj_slupy(doc, Config())
    assert len(slupy) == 4


def test_wspolny_wierzcholek_nie_jest_bledem():
    doc = _rysunek([(0, 0), (50, 0)], [(50, 0), (100, 0)])
    slupy, bledne = reader.wczytaj_slupy(doc, Config())
    assert len(slupy) == 3 and bledne == []


def test_warstwa_bez_rozrozniania_wielkosci_liter():
    doc = _rysunek([(0, 0), (50, 0)], warstwa="!TELE")
    slupy, _ = reader.wczytaj_slupy(doc, Config())
    assert len(slupy) == 2


@pytest.mark.parametrize("x, epsg", [(5_500_000, 2176), (6_500_000, 2177), (7_541_000, 2178),
                                     (8_400_000, 2179), (500_000, 2180)])
def test_wykryj_epsg(x, epsg):
    assert wykryj_epsg(x) == epsg


def test_wykryj_epsg_nieznany():
    with pytest.raises(ValueError):
        wykryj_epsg(42)


@pytest.mark.parametrize("tekst, nazwa", [("STACJA TRAFO 05-0792", "05-0792"),
                                          ("stacja trafo\n05-11790", "05-11790"),
                                          ("STACJA TRAFO Kolonia", "Kolonia")])
def test_nazwa_stacji(tekst, nazwa):
    assert reader._nazwa_stacji(tekst) == nazwa


def test_czysty_tekst_mtext():
    assert reader._czysty_tekst("{\\fArial|b1;słup nN}\\PP-10/ZN") == "słup nN\nP-10/ZN"
