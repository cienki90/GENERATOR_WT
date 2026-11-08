"""Odczyt DXF: słupy, scalanie błędnych klików, strefy trafo, opisy, układ współrzędnych."""
import ezdxf
import pytest
from ezdxf.math import Vec2
from ezdxf.render import mleader

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


# ---------------------------------------------------------------- opisy słupów w blokach

def _dodaj_opis(uklad, tekst, grot, wstawienie=(0, 8)):
    """MULTILEADER 'słup nN\\\\P<typ>' z grotem w punkcie `grot`."""
    ml = uklad.add_multileader_mtext("Standard")
    ml.set_content(tekst)
    ml.add_leader_line(mleader.ConnectionSide.left, [Vec2(grot)])
    ml.build(insert=Vec2(wstawienie))


def _plan_slupow(*punkty, tolerancja=5.0):
    doc = _rysunek(list(punkty))
    cfg = Config(tolerancja_slupa=tolerancja)
    slupy, _ = reader.wczytaj_slupy(doc, cfg)
    return doc, cfg, {(s.x, s.y): s for s in slupy}


def test_opis_slupa_w_bloku():
    doc, cfg, slupy = _plan_slupow((0, 0), (40, 0), (80, 0))
    _dodaj_opis(doc.blocks.new("q"), "słup nN\\PP-10/ZN", (0, 0))
    _dodaj_opis(doc.blocks.new("e2"), "słup SN\\P-10,5/10/E", (0, 0))
    msp = doc.modelspace()
    msp.add_blockref("q", (0, 0), dxfattribs={"rotation": 37})
    msp.add_blockref("q", (40, 0))
    msp.add_blockref("e2", (80, 0))
    assert reader.przypisz_opisy_slupow(doc, list(slupy.values()), cfg) == 3
    assert (slupy[(0, 0)].rodzaj_slupa, slupy[(0, 0)].typ_slupa) == ("nN", "P-10/ZN")
    assert (slupy[(40, 0)].rodzaj_slupa, slupy[(40, 0)].typ_slupa) == ("nN", "P-10/ZN")
    assert (slupy[(80, 0)].rodzaj_slupa, slupy[(80, 0)].typ_slupa) == ("SN", "-10,5/10/E")


def test_opis_w_bloku_uwzglednia_obrot_skale_i_punkt_bazowy():
    # grot 10 m od punktu bazowego bloku: po obrocie o 90° i skali 2 trafia 20 m nad wstawienie
    doc, cfg, slupy = _plan_slupow((100, 120), (100, 60), tolerancja=0.5)
    blok = doc.blocks.new("q", base_point=(5, 0))
    _dodaj_opis(blok, "słup nN\\PP-10/ZN", (15, 0))
    doc.modelspace().add_blockref("q", (100, 100), dxfattribs={"rotation": 90, "xscale": 2, "yscale": 2})
    assert reader.przypisz_opisy_slupow(doc, list(slupy.values()), cfg) == 1
    assert slupy[(100, 120)].typ_slupa == "P-10/ZN"
    assert slupy[(100, 60)].typ_slupa is None


def test_opis_w_bloku_jako_mtext():
    doc, cfg, slupy = _plan_slupow((0, 0), (40, 0))
    doc.blocks.new("t").add_mtext("słup nN\\PK-10,5/10/E", dxfattribs={"insert": (0, 0)})
    doc.modelspace().add_blockref("t", (40, 0))
    assert reader.przypisz_opisy_slupow(doc, list(slupy.values()), cfg) == 1
    assert slupy[(40, 0)].typ_slupa == "K-10,5/10/E"


def test_multileader_z_modelu_wygrywa_z_blokiem():
    doc, cfg, slupy = _plan_slupow((0, 0), (40, 0))
    _dodaj_opis(doc.blocks.new("q"), "słup nN\\PP-10/ZN", (0, 0))
    msp = doc.modelspace()
    msp.add_blockref("q", (0, 0))
    _dodaj_opis(msp, "słup nN\\PRPK-10,5/10/E", (0, 0))
    assert reader.przypisz_opisy_slupow(doc, list(slupy.values()), cfg) == 1      # jeden słup, dwa opisy
    assert slupy[(0, 0)].typ_slupa == "RPK-10,5/10/E"
    assert slupy[(40, 0)].typ_slupa is None


def test_inne_bloki_i_blok_daleko_od_slupa_nie_daja_opisu():
    doc, cfg, slupy = _plan_slupow((0, 0), (40, 0))
    doc.blocks.new("znak").add_line((0, 0), (1, 1))
    _dodaj_opis(doc.blocks.new("q"), "słup nN\\PP-10/ZN", (0, 0))
    _dodaj_opis(doc.blocks.new("stacja"), "STACJA TRAFO\\P05-0001", (0, 0))
    msp = doc.modelspace()
    msp.add_blockref("znak", (0, 0))
    msp.add_blockref("stacja", (0, 0))
    msp.add_blockref("q", (500, 500))
    assert reader.przypisz_opisy_slupow(doc, list(slupy.values()), cfg) == 0
    assert all(s.typ_slupa is None and s.rodzaj_slupa is None for s in slupy.values())


# ---------------------------------------------------------------- numer stacji poza obrysem

def _obrys(msp, x0, y0, bok=100):
    msp.add_lwpolyline([(x0, y0), (x0 + bok, y0), (x0 + bok, y0 + bok), (x0, y0 + bok)],
                       close=True, dxfattribs={"layer": "!trafo"})


def _stacja(msp, nazwa, xy):
    msp.add_text(f"STACJA TRAFO {nazwa}", dxfattribs={"layer": "!trafo_opis", "insert": xy})


def test_numer_stacji_tuz_za_obrysem_z_ostrzezeniem():
    doc = ezdxf.new()
    msp = doc.modelspace()
    _obrys(msp, 0, 0)
    _stacja(msp, "05-0001", (130, 50))                   # 30 m za obrysem
    strefy, ostrz = reader.wczytaj_stacje_trafo(doc, Config())
    assert [s.nazwa for s in strefy] == ["05-0001"]
    assert len(ostrz) == 1
    assert "Stacja 05-0001: w obrysie !trafo" in ostrz[0] and "30.0 m poza obrysem" in ostrz[0]
    assert "leży poza obrysami" not in " ".join(ostrz)


def test_numer_stacji_dalej_niz_50_m_nie_jest_brany():
    doc = ezdxf.new()
    msp = doc.modelspace()
    _obrys(msp, 0, 0)
    _stacja(msp, "05-0001", (160, 50))                   # 60 m za obrysem
    strefy, ostrz = reader.wczytaj_stacje_trafo(doc, Config())
    assert [s.nazwa for s in strefy] == [f"TRAFO ? ({msp[0].dxf.handle})"]
    assert any("nie zawiera opisu stacji" in o for o in ostrz)
    assert any("Stacja 05-0001 leży poza obrysami" in o for o in ostrz)
    strefy, _ = reader.wczytaj_stacje_trafo(doc, Config(odl_opisu_stacji=70))
    assert [s.nazwa for s in strefy] == ["05-0001"]


def test_opis_wewnatrz_innego_obrysu_nie_jest_brany_i_najblizszy_wygrywa():
    doc = ezdxf.new()
    msp = doc.modelspace()
    _obrys(msp, 0, 0)                                    # A: bez numeru w środku
    _obrys(msp, 120, 0)                                  # B: ma własny numer w środku (20 m od A)
    _stacja(msp, "05-0002", (150, 50))
    _obrys(msp, 0, 300)                                  # C: bez numeru, dwa opisy za obrysem
    _stacja(msp, "05-0003", (-10, 350))                  # 10 m
    _stacja(msp, "05-0004", (-40, 350))                  # 40 m
    strefy, ostrz = reader.wczytaj_stacje_trafo(doc, Config())
    nazwy = sorted(s.nazwa for s in strefy)
    assert "05-0002" in nazwy and "05-0003" in nazwy and "05-0004" not in nazwy
    assert any(n.startswith("TRAFO ?") for n in nazwy)  # A nie dostaje numeru stacji B
    assert any("Stacja 05-0004 leży poza obrysami" in o for o in ostrz)


def test_obrys_ze_stacja_w_srodku_bez_zmian():
    doc = ezdxf.new()
    msp = doc.modelspace()
    _obrys(msp, 0, 0)
    _stacja(msp, "05-0001", (50, 50))
    _stacja(msp, "05-0009", (120, 50))                   # opis poza obrysem nie zmienia nazwy
    strefy, ostrz = reader.wczytaj_stacje_trafo(doc, Config())
    assert [s.nazwa for s in strefy] == ["05-0001"]
    assert ostrz == ["Stacja 05-0009 leży poza obrysami !trafo."]
