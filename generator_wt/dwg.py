"""Odczyt i zapis rysunków DWG przez ODA File Converter (Open Design Alliance).

ezdxf czyta i zapisuje tylko DXF, dlatego DWG jest przeliczany zewnętrznym programem
ODA File Converter (darmowy, instaluje go użytkownik - nie wolno go dołączać do paczki
programu bez licencji ODA). Pliki DXF obsługujemy jak dotąd, bez konwertera.

    doc = wczytaj("projekt.dwg")          # albo .dxf
    zapisz(doc, "projekt_numeracja.dwg")  # albo .dxf
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import ezdxf
from ezdxf.addons import odafc
from ezdxf.document import Drawing

ADRES_ODA = "https://www.opendesign.com/guestfiles/oda_file_converter"
KOMUNIKAT_BRAK_ODA = (
    "Do odczytu i zapisu plików DWG potrzebny jest darmowy program ODA File Converter. "
    f"Pobierz go ze strony {ADRES_ODA}, zainstaluj i uruchom analizę ponownie. "
    "Bez niego możesz pracować na plikach DXF.")

# typowe miejsca instalacji (folder ma w nazwie numer wersji, np. "ODAFileConverter 26.4.0")
_WZORCE = [r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
           r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe"]


class BladDWG(Exception):
    """Błąd obsługi DWG z komunikatem dla użytkownika."""


def jest_dwg(plik: str | os.PathLike) -> bool:
    return Path(plik).suffix.lower() == ".dwg"


def znajdz_oda(wskazana: str | None = None) -> str | None:
    """Ścieżka do ODAFileConverter.exe: wskazana przez użytkownika, ustawiona w ezdxf
    albo znaleziona w typowym miejscu instalacji (najnowsza wersja)."""
    for p in (wskazana, odafc.get_win_exec_path()):
        if p and Path(p).is_file():
            return str(p)
    znalezione = sorted((p for w in _WZORCE for p in glob.glob(w)), key=_wersja_z_nazwy)
    return znalezione[-1] if znalezione else None


def _wersja_z_nazwy(sciezka: str) -> tuple:
    nazwa = Path(sciezka).parent.name
    return tuple(int(c) for c in "".join(z if z.isdigit() else " " for z in nazwa).split())


def ustaw_oda(wskazana: str | None = None) -> str | None:
    """Ustawia ścieżkę konwertera dla ezdxf; zwraca ją albo None, gdy go nie ma."""
    p = znajdz_oda(wskazana)
    if p:
        ezdxf.options.set("odafc-addon", "win_exec_path", f'"{p}"')
    return p


def dostepny(wskazana: str | None = None) -> bool:
    return ustaw_oda(wskazana) is not None


def wczytaj(plik: str | os.PathLike, oda: str | None = None) -> Drawing:
    if not jest_dwg(plik):
        return ezdxf.readfile(str(plik))
    if not dostepny(oda):
        raise BladDWG(KOMUNIKAT_BRAK_ODA)
    try:
        return odafc.readfile(str(plik))
    except odafc.ODAFCError as e:
        raise BladDWG(f"Nie udało się odczytać pliku DWG {Path(plik).name}: {e}") from e


def zapisz(doc: Drawing, plik: str | os.PathLike, oda: str | None = None) -> None:
    """Zapis do DWG (wersja jak rysunek źródłowy) albo DXF - wg rozszerzenia pliku."""
    if not jest_dwg(plik):
        doc.saveas(str(plik))
        return
    if not dostepny(oda):
        raise BladDWG(KOMUNIKAT_BRAK_ODA)
    try:
        odafc.export_dwg(doc, str(plik), replace=True)
    except odafc.ODAFCError as e:
        raise BladDWG(f"Nie udało się zapisać pliku DWG {Path(plik).name}: {e}") from e
