"""Słowniki z Excela: operatorzy i rejony energetyczne.

Plik: dane/slowniki.xlsx
  arkusz "Operatorzy" - pierwszy wiersz to nagłówki, kolumna "Nazwa" wymagana
  arkusz "Rejony"     - j.w.
Pozostałe kolumny (adres, NIP, osoba kontaktowa itd.) są wczytywane jako
słownik i będą wstawiane do dokumentu docx / zestawienia.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook

DOMYSLNY_PLIK = Path(__file__).resolve().parent.parent / "dane" / "slowniki.xlsx"

ARKUSZ_OPERATORZY = "Operatorzy"
ARKUSZ_REJONY = "Rejony"


def wczytaj_liste(arkusz: str, plik: Path = DOMYSLNY_PLIK) -> list[dict[str, str]]:
    wb = load_workbook(plik, read_only=True, data_only=True)
    if arkusz not in wb.sheetnames:
        raise ValueError(f"Brak arkusza '{arkusz}' w pliku {plik}")
    wiersze = list(wb[arkusz].iter_rows(values_only=True))
    if not wiersze:
        return []
    naglowki = [str(n).strip() if n is not None else f"Kol{i}" for i, n in enumerate(wiersze[0])]
    wynik = []
    for w in wiersze[1:]:
        if not any(w):
            continue
        wynik.append({n: ("" if v is None else str(v).strip()) for n, v in zip(naglowki, w)})
    return wynik


def wybierz(lista: list[dict[str, str]], tytul: str) -> dict[str, str] | None:
    """Prosty wybór z listy w konsoli (później zastąpi go okno GUI)."""
    if not lista:
        print(f"Lista '{tytul}' jest pusta.")
        return None
    print(f"\n{tytul}:")
    for i, poz in enumerate(lista, start=1):
        print(f"  {i:>3}. {poz.get('Nazwa', next(iter(poz.values())))}")
    while True:
        odp = input(f"Wybierz numer (1-{len(lista)}, Enter = pomiń): ").strip()
        if not odp:
            return None
        if odp.isdigit() and 1 <= int(odp) <= len(lista):
            return lista[int(odp) - 1]
        print("Nieprawidłowy wybór.")


def utworz_szablon(plik: Path = DOMYSLNY_PLIK) -> None:
    """Tworzy przykładowy plik słowników (do uzupełnienia przez użytkownika)."""
    plik.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = ARKUSZ_OPERATORZY
    ws.append(["Nazwa", "Pełna nazwa", "Adres", "NIP", "Osoba kontaktowa", "E-mail", "Telefon"])
    ws.append(["Operator A", "Operator A Sp. z o.o.", "ul. Przykładowa 1, 00-001 Warszawa",
               "", "", "", ""])
    ws2 = wb.create_sheet(ARKUSZ_REJONY)
    ws2.append(["Nazwa", "Oddział", "Adres", "Osoba kontaktowa", "E-mail", "Telefon"])
    ws2.append(["Rejon Energetyczny X", "Oddział Y", "ul. Przykładowa 2, 00-002 Miasto",
                "", "", ""])
    for arkusz in wb.worksheets:
        for kol in arkusz.columns:
            arkusz.column_dimensions[kol[0].column_letter].width = 28
    wb.save(plik)
