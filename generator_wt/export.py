"""Zestawienia w Excelu: rozbudowane (.xlsx) i uproszczone (.xls).

Uproszczone = kolumny jak w tabeli 'Wykaz słupów' w piśmie.
Rozbudowane = to samo + numer słupa z rysunku, stacja trafo, dane działki,
              kod pocztowy, odległości między słupami, uwagi.
"""
from __future__ import annotations

import math
from pathlib import Path

import xlwt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .model import Wierzcholek

UPROSZCZONE = [
    ("L.p.", 6, lambda lp, w, d: lp),
    ("Rejon Energetyczny", 36, lambda lp, w, d: w.rejon or ""),
    ("Gmina", 20, lambda lp, w, d: w.gmina or ""),
    ("Miejscowość", 20, lambda lp, w, d: w.miejscowosc or ""),
    ("Ulica", 20, lambda lp, w, d: w.ulica or "-"),
    ("X", 14, lambda lp, w, d: round(w.geo_x, 2)),
    ("Y", 14, lambda lp, w, d: round(w.geo_y, 2)),
]

ROZBUDOWANE = UPROSZCZONE[:1] + [
    ("Nr słupa (rysunek)", 10, lambda lp, w, d: w.etykieta),
    ("Stacja trafo", 20, lambda lp, w, d: w.stacja_trafo or ""),
] + UPROSZCZONE[1:5] + [
    ("Kod pocztowy", 10, lambda lp, w, d: w.kod or ""),
    ("Powiat", 18, lambda lp, w, d: w.powiat or ""),
    ("Województwo", 16, lambda lp, w, d: w.wojewodztwo or ""),
    ("Obręb", 18, lambda lp, w, d: w.obreb or ""),
    ("Nr działki", 10, lambda lp, w, d: w.dzialka or ""),
] + UPROSZCZONE[5:] + [
    ("Odległość od poprz. [m]", 12, lambda lp, w, d: d[0]),
    ("Długość narastająco [m]", 12, lambda lp, w, d: d[1]),
    ("Uwagi", 30, lambda lp, w, d: w.uwagi),
]


def _odleglosci(slupy: list[Wierzcholek]) -> list[tuple[float | str, float]]:
    """Odległość od poprzedniego słupa - tylko gdy są połączone linią."""
    wynik, suma, poprz = [], 0.0, None
    for w in slupy:
        if poprz is not None and poprz.id in w.sasiedzi:
            o = math.hypot(w.x - poprz.x, w.y - poprz.y)
            suma += o
            wynik.append((round(o, 2), round(suma, 2)))
        else:
            wynik.append(("" if poprz is not None else 0.0, round(suma, 2)))
        poprz = w
    return wynik


def zapisz_rozbudowane(slupy: list[Wierzcholek], plik: Path, tytul: str = "") -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Wykaz słupów"
    cienka = Side(style="thin")
    ramka = Border(left=cienka, right=cienka, top=cienka, bottom=cienka)
    wiersz0 = 1
    if tytul:
        ws.cell(1, 1, tytul).font = Font(bold=True, size=12)
        wiersz0 = 3
    for k, (nagl, szer, _) in enumerate(ROZBUDOWANE, start=1):
        c = ws.cell(wiersz0, k, nagl)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDEBF7")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = ramka
        ws.column_dimensions[c.column_letter].width = szer
    odl = _odleglosci(slupy)
    for lp, (w, d) in enumerate(zip(slupy, odl), start=1):
        for k, (_, _, f) in enumerate(ROZBUDOWANE, start=1):
            c = ws.cell(wiersz0 + lp, k, f(lp, w, d))
            c.border = ramka
            if isinstance(c.value, float):
                c.number_format = "0.00"
    ws.freeze_panes = ws.cell(wiersz0 + 1, 1)
    ws.auto_filter.ref = f"A{wiersz0}:{ws.cell(wiersz0, len(ROZBUDOWANE)).column_letter}" \
                         f"{wiersz0 + len(slupy)}"
    wb.save(plik)


def zapisz_uproszczone(slupy: list[Wierzcholek], plik: Path) -> None:
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Wykaz słupów")
    ramka = "borders: left thin, right thin, top thin, bottom thin;"
    st_nagl = xlwt.easyxf("font: bold on; align: wrap on, horiz center, vert center;"
                          "pattern: pattern solid, fore_colour pale_blue;" + ramka)
    st_txt = xlwt.easyxf(ramka)
    st_liczba = xlwt.easyxf(ramka, num_format_str="0.00")
    for k, (nagl, szer, _) in enumerate(UPROSZCZONE):
        ws.write(0, k, nagl, st_nagl)
        ws.col(k).width = 256 * szer
    for lp, w in enumerate(slupy, start=1):
        for k, (_, _, f) in enumerate(UPROSZCZONE):
            v = f(lp, w, None)
            ws.write(lp, k, v, st_liczba if isinstance(v, float) else st_txt)
    ws.set_panes_frozen(True)
    ws.set_horz_split_pos(1)
    wb.save(str(plik))
