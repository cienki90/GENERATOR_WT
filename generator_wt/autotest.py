"""Test działania spakowanego programu (uruchamiany przy budowie wersji .exe).

    "Generator WT.exe" --autotest  ->  kod wyjścia 0 = OK, raport w autotest.log
Sprawdza bez internetu: odczyt DXF, numerację, arkusze (scipy), WGS 84 (pyproj),
zapis DXF/docx/xlsx/xls oraz utworzenie okna programu (Qt).
"""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

from .config import KATALOG


def uruchom() -> int:
    raport = KATALOG / "autotest.log"
    linie = []
    try:
        from . import slowniki
        from .projekt import Projekt

        p = Projekt()
        p.wczytaj(KATALOG / "przyklady" / "baza robocza.dxf")
        p.planuj()
        linie.append(f"słupów: {len(p.slupy)}, stref: {len(p.stacje)}")
        p.planuj_arkusze()
        linie.append(f"arkuszy: {len(p.arkusze)}")
        op = slowniki.wczytaj_liste(p.cfg.plik_slownikow, slowniki.ARKUSZ_OPERATORZY)[0]
        p.przypisz_rejony(slowniki.wczytaj_liste(p.cfg.plik_slownikow, slowniki.ARKUSZ_REJONY),
                          None)
        with tempfile.TemporaryDirectory() as tmp:
            k = Path(tmp)
            p.zapisz_dxf(k / "t_numeracja.dxf", True, op, "Test", "01.2026")
            p.cfg.wgs84 = True
            p.zapisz_pismo(k / "t_pismo.docx", op, None)
            p.zapisz_rozbudowana(k / "t_rozbudowana.xlsx")
            p.zapisz_uproszczona(k / "t_uproszczona.xls")
            p.zapisz_projektowa(k / "t_projektowa.xlsx")
            linie.append("pliki: " + ", ".join(sorted(f.name for f in k.iterdir())))
        linie.append(f"WGS 84 słupa 1: {p.plan[0].lat:.6f}, {p.plan[0].lon:.6f}")

        from PySide6.QtWidgets import QApplication

        from .gui import OknoGlowne
        app = QApplication.instance() or QApplication(sys.argv)
        okno = OknoGlowne()
        okno.close()
        del app
        linie.append("okno: OK")
        linie.append("WYNIK: OK")
        kod = 0
    except Exception:  # noqa: BLE001
        linie.append(traceback.format_exc())
        linie.append("WYNIK: BŁĄD")
        kod = 1
    raport.write_text("\n".join(linie), encoding="utf-8")
    return kod
