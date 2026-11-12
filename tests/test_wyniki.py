"""Pliki wyników: DXF z numeracją i arkuszami, PDF, pismo, zestawienia, wiersz poleceń."""
import collections

import docx
import ezdxf
import pytest
import xlrd
from openpyxl import load_workbook

from generator_wt import slowniki
from generator_wt.main import main as cli
from tests.conftest import nowy_projekt


@pytest.fixture
def operator(dxf):
    from generator_wt.config import Config
    return slowniki.wczytaj_liste(Config().plik_slownikow, slowniki.ARKUSZ_OPERATORZY)[0]


def test_dxf_numeracja_i_arkusze(dxf, operator):
    p = nowy_projekt(dxf, arkusze=True)
    cel = dxf.with_name("projekt_numeracja.dxf")
    p.zapisz_dxf(cel, True, operator, "Test", "10.2026")
    doc = ezdxf.readfile(cel)
    msp = doc.modelspace()
    warstwa = p.cfg.warstwa_numeracji
    teksty = msp.query(f'MTEXT[layer=="{warstwa}"]')
    assert len(msp.query(f'LEADER[layer=="{warstwa}"]')) == len(p.plan)
    assert sorted(t.text for t in teksty) == sorted(w.etykieta for w in p.plan)
    uklady = sorted((n for n in doc.layouts.names() if n.isdigit()), key=int)
    assert uklady == [str(i) for i in range(1, len(p.arkusze) + 1)]
    # oryginał bez zmian
    assert len(ezdxf.readfile(dxf).modelspace().query(f'MTEXT[layer=="{warstwa}"]')) == 0


def test_dxf_ponowny_zapis_zastepuje_numeracje(dxf):
    p = nowy_projekt(dxf)
    cel = dxf.with_name("projekt_numeracja.dxf")
    p.zapisz_dxf(cel)
    p.zapisz_dxf(cel)  # drugi zapis na tym samym dokumencie - bez dublowania
    warstwa = p.cfg.warstwa_numeracji
    assert len(ezdxf.readfile(cel).modelspace().query(f'LEADER[layer=="{warstwa}"]')) \
        == len(p.plan)


def test_uwagi_na_warstwie_niedrukowalnej(dxf):
    p = nowy_projekt(dxf, arkusze=True)
    cel = dxf.with_name("projekt_numeracja.dxf")
    p.zapisz_dxf(cel, True)
    p.zapisz_dxf(cel, True)                       # ponowny zapis - bez dublowania okręgów
    doc = ezdxf.readfile(cel)
    w = p.cfg.warstwa_uwag
    lay = doc.layers.get(w)
    assert lay.dxf.plot == 0 and lay.dxf.lineweight == 100          # niedrukowalna, 1.00 mm
    kola = doc.modelspace().query(f'CIRCLE[layer=="{w}"]')
    assert len(kola) == len(doc.modelspace().query(f'MTEXT[layer=="{w}"]')) == p.uwag_na_rysunku
    kolory = collections.Counter(k.dxf.color for k in kola)
    dlugie = p.przesla()
    assert dlugie and all(d > 50 for d, _, _ in dlugie)
    assert kolory[p.KOLOR_SCALENIA] == len(p.bledne_kliki) == 2
    assert kolory[p.KOLOR_PRZESLA_BLAD] == sum(1 for d, _, _ in dlugie if d > 60) > 0
    assert kolory[p.KOLOR_PRZESLA] == sum(1 for d, _, _ in dlugie if d <= 60) > 0
    # w rzutniach arkuszy warstwa jest zamrożona - okręgi nie trafiają do arkuszy ani do PDF
    rzutnie = [vp for n in doc.layouts.names() if n.isdigit()
               for vp in doc.layouts.get(n).viewports() if vp.dxf.id > 1]
    assert rzutnie and all(w in vp.frozen_layers for vp in rzutnie)
    # oryginał bez zmian
    assert w not in ezdxf.readfile(dxf).layers


def test_uwagi_przesla_scalenia_i_stacja_poza_obrysem(tmp_path):
    from generator_wt.config import Config
    from generator_wt.projekt import Projekt
    doc = ezdxf.new()
    msp = doc.modelspace()
    x0, y0 = 7_500_000.0, 5_700_000.0
    tele = {"layer": "!tele"}
    msp.add_lwpolyline([(x0 + x, y0) for x in (0, 45, 100, 165)], dxfattribs=tele)   # 45, 55, 65 m
    msp.add_lwpolyline([(x0 + 165.3, y0), (x0 + 165.3, y0 + 40)], dxfattribs=tele)   # klik 0.3 m obok
    msp.add_lwpolyline([(x0 - 10, y0 - 10), (x0 + 60, y0 - 10), (x0 + 60, y0 + 10), (x0 - 10, y0 + 10)],
                       close=True, dxfattribs={"layer": "!trafo"})
    msp.add_text("STACJA TRAFO 05-0001", dxfattribs={"layer": "!trafo_opis", "insert": (x0 + 80, y0 + 30)})
    plik = tmp_path / "plan.dxf"
    doc.saveas(plik)
    p = Projekt(Config())
    p.wczytaj(plik)
    p.zastosuj_stan()
    p.planuj()
    uwagi = sorted((kolor, opis) for *_, opis, kolor in p.uwagi_rysunku())
    assert [k for k, _ in uwagi] == sorted([p.KOLOR_SCALENIA, p.KOLOR_PRZESLA, p.KOLOR_PRZESLA_BLAD,
                                            p.KOLOR_STACJI])
    opisy = " | ".join(o for _, o in uwagi)
    assert "przęsło 55.0 m" in opisy and "przęsło 65.0 m" in opisy and "przęsło 45" not in opisy
    assert "scalono wierzchołki: 2 (do 0.30 m)" in opisy
    assert "stacja 05-0001: numer 28.3 m poza obrysem !trafo" in opisy


def test_pdf_arkuszy(dxf, operator):
    import pymupdf
    p = nowy_projekt(dxf, arkusze=True)
    p.zapisz_dxf(dxf.with_name("projekt_numeracja.dxf"), True, operator)
    cel = dxf.with_name("projekt_numeracja.pdf")
    assert p.zapisz_numeracje_pdf(cel, log=lambda t: None) == len(p.arkusze)
    with pymupdf.open(cel) as pdf:
        assert pdf.page_count == len(p.arkusze)
        r = pdf[0].rect
        assert (round(r.width * 25.4 / 72), round(r.height * 25.4 / 72)) == (420, 297)  # A3


def test_pdf_w_procesach_identyczny_z_rysowanym_po_kolei(dxf):
    """Strony rysowane w procesach pomocniczych są takie same jak rysowane po kolei - także przy
    pierwszym eksporcie (pogrubiony styl numerów musi istnieć, zanim powstanie kontekst rysowania)."""
    import pymupdf
    from generator_wt import pdf as wtpdf
    assert wtpdf.liczba_procesow(3) == 1 and wtpdf.liczba_procesow(16, 4) == 4 and wtpdf.liczba_procesow(2, 8) == 2
    p = nowy_projekt(dxf, arkusze=True)
    p.zapisz_dxf(dxf.with_name("projekt_numeracja.dxf"), True)
    nazwa_dokumentu = p.doc.filename
    nazwy = ["1", "2", "3", "4"]
    log = []
    for ile in (1, 2):
        wtpdf.eksportuj_uklady(p.doc, dxf.with_name(f"n{ile}.pdf"), nazwy,
                               warstwa_numeracji=p.cfg.warstwa_numeracji, log=log.append, procesy=ile)
    assert not any("nie powiodło" in x for x in log), log
    assert sorted(log) == sorted([f"PDF: strona {n}" for n in nazwy] * 2)
    assert p.doc.filename == nazwa_dokumentu                       # zapis kopii dla pomocników nie zmienia nazwy
    with pymupdf.open(dxf.with_name("n1.pdf")) as a, pymupdf.open(dxf.with_name("n2.pdf")) as b:
        assert len(a) == len(b) == 4
        for sa, sb in zip(a, b):
            assert sa.get_pixmap(dpi=60).samples == sb.get_pixmap(dpi=60).samples


def test_pdf_blad_pomocnika_rysuje_po_kolei(dxf, monkeypatch):
    import pymupdf
    from generator_wt import pdf as wtpdf
    p = nowy_projekt(dxf, arkusze=True)
    p.zapisz_dxf(dxf.with_name("projekt_numeracja.dxf"), True)

    def zepsuty(*a, **k):
        raise RuntimeError("proces pomocniczy: test")

    monkeypatch.setattr(wtpdf, "_strony_w_procesach", zepsuty)
    log = []
    assert wtpdf.eksportuj_uklady(p.doc, dxf.with_name("n.pdf"), ["1", "2"], log=log.append, procesy=2) == 2
    assert any("rysuję po kolei" in x for x in log)
    with pymupdf.open(dxf.with_name("n.pdf")) as pdf:
        assert pdf.page_count == 2


@pytest.mark.parametrize("wgs84", [False, True])
def test_pismo(dxf, operator, wgs84):
    p = nowy_projekt(dxf, wgs84=wgs84)
    cel = dxf.with_name("projekt_pismo.docx")
    p.zapisz_pismo(cel, operator, "01.10.2026", "-")
    d = docx.Document(cel)
    tekst = "\n".join(x.text for x in d.paragraphs)
    assert "OD: 01.10.2026 DO: -" in tekst
    assert f"Łączna ilość Słupów elektroenergetycznych: {len(p.plan)}" in tekst
    tabela = next(t for t in d.tables if t.rows[0].cells[0].text.strip().startswith("L.p"))
    assert len(tabela.rows) == len(p.plan) + 1
    x = float(tabela.rows[1].cells[5].text)
    assert (50 < x < 56) if wgs84 else (x > 5_000_000)


def test_zestawienie_rozbudowane(dxf):
    p = nowy_projekt(dxf)
    cel = dxf.with_name("projekt_rozbudowana.xlsx")
    p.zapisz_rozbudowana(cel)
    ws = load_workbook(cel).worksheets[0]
    assert ws.cell(4, 1).value == 1
    assert ws.cell(3 + len(p.plan), 1).value == len(p.plan)
    assert ws.cell(5 + len(p.plan), 1).value == f"Wykaz dotyczy łącznie {len(p.plan)} słupów."
    assert "str. 7" in ws["F3"].value  # EPSG:2178 = strefa 7


def test_zestawienie_uproszczone(dxf):
    p = nowy_projekt(dxf)
    cel = dxf.with_name("projekt_uproszczona.xls")
    p.zapisz_uproszczona(cel)
    s = xlrd.open_workbook(str(cel)).sheet_by_index(0)
    assert s.cell_value(4, 0).strip() == p.plan[0].etykieta
    assert s.cell_value(3 + len(p.plan), 0).strip() == p.plan[-1].etykieta
    assert s.cell_value(4, 5) == pytest.approx(p.plan[0].geo_x, abs=0.01)


def test_tabela_projektowa_zawsze_wgs84(dxf):
    p = nowy_projekt(dxf)  # wgs84=False, a tabela i tak ma GPS
    cel = dxf.with_name("projekt_tabela_projektowa.xlsx")
    p.zapisz_projektowa(cel)
    ws = load_workbook(cel).worksheets[0]
    lat, lon = ws.cell(2, 7).value, ws.cell(2, 8).value
    assert 49 < lat < 55 and 14 < lon < 25
    assert ws.max_row == len(p.plan) + 1


def test_wiersz_polecen(dxf, capsys):
    kat = dxf.parent / "wyniki"
    assert cli([str(dxf), "--bez-geokodowania", "--tak", "--katalog", str(kat),
                "--prefiks", "S", "--format", "dxf"]) == 0
    pliki = sorted(f.name for f in kat.iterdir())
    assert pliki == ["projekt_numeracja.dxf", "projekt_pismo.docx", "projekt_rozbudowana.xlsx",
                     "projekt_tabela_projektowa.xlsx", "projekt_uproszczona.xls"]
    wyjscie = capsys.readouterr().out
    assert "Słupów: 151" in wyjscie and "początek: S1" in wyjscie
