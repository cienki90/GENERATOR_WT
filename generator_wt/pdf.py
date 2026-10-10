"""Eksport rysunków DXF do PDF (wektorowo), przez dodatek rysujący ezdxf + PyMuPDF.

Każdy układ papieru DXF (A3) staje się osobną stroną wielostronicowego PDF-u,
odwzorowaną 1:1 (bez skalowania do strony). Treść modelu pod rzutnią (słupy,
numeracja, obrysy arkuszy, tabelki, legenda) rysowana jest wektorowo.

Podkład rastrowy planu orientacyjnego (obraz IMAGE w modelu) nie jest wiernie
renderowany przez dodatek rysujący, dlatego dla orientacji wklejamy pliki JPG
podkładu wprost na strony PDF-u, pod rysunek wektorowy. Pozycja obrazu na papierze
wynika z ustawień rzutni (środek i wysokość widoku) oraz georeferencji obrazu.
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout
from ezdxf.addons.drawing import pymupdf as ezpdf
from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration
from ezdxf.document import Drawing


def _nazwy_ukladow(doc: Drawing, nazwy=None) -> list[str]:
    if nazwy is not None:
        return [n for n in nazwy if n in doc.layouts.names()]
    return [n for n in doc.layouts.names() if n != "Model"]


def _strona_ukladu(psp):
    """Strona PDF i ustawienia wiernego odwzorowania papieru układu (bez skalowania)."""
    page = layout.Page.from_dxf_layout(psp)
    ustaw = layout.Settings(fit_page=False, scale=psp.get_plot_unit_scale_factor())
    return page, ustaw


def eksportuj_uklady(doc: Drawing, wyjscie: Path, nazwy=None, tlo_biale: bool = True,
                     obrazy_tla=None, log=None) -> int:
    """Zapisuje układy papieru 'doc' do jednego wielostronicowego PDF-u.

    nazwy       - lista nazw układów (kolejność stron); None = wszystkie poza 'Model'.
    obrazy_tla  - opcjonalny słownik {nazwa_układu: [RysunekTla, ...]} z obrazami do
                  wklejenia pod rysunek wektorowy (podkład planu orientacyjnego).
    Zwraca liczbę zapisanych stron.
    """
    import pymupdf

    nazwy = _nazwy_ukladow(doc, nazwy)
    if not nazwy:
        raise ValueError("Dokument nie ma układów papieru do zapisania w PDF.")
    ctx = RenderContext(doc)
    cfg = Configuration(
        background_policy=BackgroundPolicy.WHITE if not obrazy_tla else BackgroundPolicy.OFF)
    pdf = pymupdf.open()
    try:
        for nazwa in nazwy:
            psp = doc.paperspace(nazwa)
            page, ustaw = _strona_ukladu(psp)
            tla = (obrazy_tla or {}).get(nazwa) or []
            backend = ezpdf.PyMuPdfBackend()
            Frontend(ctx, backend, config=cfg).draw_layout(psp)
            strona_bajty = backend.get_pdf_bytes(page, settings=ustaw)
            zrodlo = pymupdf.open("pdf", strona_bajty)
            if tla:
                _wklej_tla(zrodlo[0], tla, page)
            pdf.insert_pdf(zrodlo)
            zrodlo.close()
            if log:
                log(f"PDF: strona {nazwa}")
        Path(wyjscie).parent.mkdir(parents=True, exist_ok=True)
        pdf.save(str(wyjscie))
        return pdf.page_count
    finally:
        pdf.close()


class RysunekTla:
    """Obraz podkładu do wklejenia na stronę PDF, z pozycją w mm papieru.

    x, y - lewy górny róg obrazu [mm od lewego górnego rogu strony],
    szer, wys - rozmiar obrazu na papierze [mm].
    """

    __slots__ = ("plik", "x", "y", "szer", "wys")

    def __init__(self, plik: Path, x: float, y: float, szer: float, wys: float):
        self.plik = Path(plik)
        self.x, self.y, self.szer, self.wys = x, y, szer, wys


def _wklej_tla(strona, tla: list[RysunekTla], page) -> None:
    """Wkleja obrazy tła na stronę PDF (PyMuPDF). Współrzędne mm -> punkty (1 mm = 72/25.4 pt).
    Układ mm: od lewego górnego rogu strony (tak jak w PDF)."""
    import pymupdf

    na_pt = 72.0 / 25.4
    # strona PDF może być nieco mniejsza niż nominał (zaokrąglenia) - przeskaluj mm->pt
    # tak, by pokryć się z rzeczywistym rozmiarem strony
    sx = strona.rect.width / (page.width * na_pt)
    sy = strona.rect.height / (page.height * na_pt)
    for t in tla:
        if not t.plik.exists():
            continue
        x0 = t.x * na_pt * sx
        y0 = t.y * na_pt * sy
        x1 = (t.x + t.szer) * na_pt * sx
        y1 = (t.y + t.wys) * na_pt * sy
        strona.insert_image(pymupdf.Rect(x0, y0, x1, y1), filename=str(t.plik),
                            overlay=False, keep_proportion=False)


# --------------------------------------------------------- geometria rzutni orientacji

def tla_z_rzutni(psp, obrazy, margines_strony_mm: float = 0.0) -> list[RysunekTla]:
    """Dla układu orientacji: przelicza obrazy IMAGE (model) na pozycje w mm papieru.

    psp     - przestrzeń papieru układu (zawiera rzutnię z widokiem modelu),
    obrazy  - lista krotek (plik_jpg, x0_m, y0_m, szer_m, wys_m) = lewy dolny róg
              obrazu w terenie i jego rozmiar w metrach (z obiektu Podklad).
    Zwraca listę RysunekTla (mm papieru, od lewego górnego rogu strony).
    """
    vp = _rzutnia(psp)
    if vp is None:
        return []
    # środek rzutni na papierze [mm od lewego dolnego rogu arkusza]
    cx_mm, cy_mm = vp.dxf.center.x, vp.dxf.center.y
    w_mm, h_mm = vp.dxf.width, vp.dxf.height
    # widok w terenie
    vcx, vcy = vp.dxf.view_center_point.x, vp.dxf.view_center_point.y
    view_h = vp.dxf.view_height
    view_w = view_h * (w_mm / h_mm) if h_mm else view_h
    if view_w == 0 or view_h == 0:
        return []
    skala_x = w_mm / view_w   # mm papieru na metr terenu
    skala_y = h_mm / view_h
    # wysokość strony (do zamiany osi Y: DXF rośnie w górę, PDF w dół)
    strona_h_mm = _wysokosc_strony_mm(psp)

    def na_papier(mx, my):
        # metr terenu -> mm od lewego dolnego rogu arkusza
        px = cx_mm + (mx - vcx) * skala_x
        py = cy_mm + (my - vcy) * skala_y
        return px, py

    wynik = []
    for plik, x0_m, y0_m, szer_m, wys_m in obrazy:
        # lewy górny róg obrazu w terenie
        lx_mm, gy_mm = na_papier(x0_m, y0_m + wys_m)
        pszer = szer_m * skala_x
        pwys = wys_m * skala_y
        # zamiana na układ "od lewego górnego rogu strony"
        y_od_gory = strona_h_mm - gy_mm
        wynik.append(RysunekTla(plik, lx_mm, y_od_gory, pszer, pwys))
    return wynik


def _rzutnia(psp):
    vps = [e for e in psp if e.dxftype() == "VIEWPORT" and e.dxf.id != 1]
    return max(vps, key=lambda v: v.dxf.width * v.dxf.height) if vps else None


def _wysokosc_strony_mm(psp) -> float:
    a = psp.dxf_layout.dxfattribs()
    h = a.get("paper_height")
    if h:
        return float(h)
    page = layout.Page.from_dxf_layout(psp)
    return page.height
