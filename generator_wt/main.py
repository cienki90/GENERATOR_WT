"""Generator WT - uruchomienie z wiersza poleceń (dla automatyzacji).

Zwykle program uruchamia się oknem:  python uruchom.pyw
Wiersz poleceń:
    python -m generator_wt.main projekt.dxf --operator InterWan --rejon "Rejon ..." --tak
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import slowniki
from .config import Config
from .pismo import adres_slupa
from .projekt import Projekt


def _znajdz(lista, nazwa):
    for poz in lista:
        if poz.get("Nazwa", "").casefold() == nazwa.casefold():
            return poz
    raise SystemExit(f"Nie ma pozycji '{nazwa}'. Dostępne: "
                     + ", ".join(p.get("Nazwa", "") for p in lista))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Numeracja słupów warstwy !tele i zestawienia")
    ap.add_argument("dxf")
    ap.add_argument("--katalog", help="folder wyników (domyślnie folder projektu)")
    ap.add_argument("--zestawienie", choices=["rozbudowana", "uproszczona", "oba", "brak"],
                    default="oba")
    ap.add_argument("--operator")
    ap.add_argument("--rejon", help="rejon domyślny dla gmin spoza listy")
    ap.add_argument("--od")
    ap.add_argument("--do", default="-")
    ap.add_argument("--prefiks", default="")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--tolerancja", type=float, default=5.0,
                    help="odległość scalania wierzchołków w jeden słup [m]")
    ap.add_argument("--bez-geokodowania", action="store_true")
    ap.add_argument("--tak", action="store_true", help="nie pytaj o potwierdzenie")
    a = ap.parse_args(argv)

    cfg = Config(prefiks=a.prefiks, numer_startowy=a.start, tolerancja_slupa=a.tolerancja)
    p = Projekt(cfg)
    p.wczytaj(a.dxf)
    print(f"Słupów: {len(p.slupy)}, stref trafo: {len(p.stacje)}, "
          f"błędnych klików: {len(p.bledne_kliki)}")
    for b in p.bledne_kliki:
        print(f"  scalono {b.liczba} wierzchołki (rozrzut {b.max_odleglosc} m) "
              f"X={b.y:.2f} Y={b.x:.2f}")
    for o in p.ostrzezenia:
        print("  UWAGA:", o)
    if not a.bez_geokodowania:
        bl = p.geokoduj(lambda i, n: print(f"\r  adresy: {i}/{n}", end="", file=sys.stderr))
        print(file=sys.stderr)
        if bl:
            print(f"  {bl} słupów bez adresu (błąd usługi)")
    p.planuj()

    if not cfg.plik_slownikow.exists():
        slowniki.utworz_szablon(cfg.plik_slownikow)
    operatorzy = slowniki.wczytaj_liste(cfg.plik_slownikow, slowniki.ARKUSZ_OPERATORZY)
    rejony = slowniki.wczytaj_liste(cfg.plik_slownikow, slowniki.ARKUSZ_REJONY)
    operator = _znajdz(operatorzy, a.operator) if a.operator else (operatorzy or [None])[0]
    rejon = _znajdz(rejony, a.rejon) if a.rejon else (rejony or [None])[0]
    bez = p.przypisz_rejony(rejony, rejon)
    if bez:
        print(f"Gminy spoza listy (rejon domyślny {rejon and rejon['Nazwa']}): {', '.join(bez)}")

    dlugie = p.przesla()
    if dlugie:
        print(f"\nPrzęsła dłuższe niż {cfg.przeslo_ostrzezenie:g} m: {len(dlugie)}")
        for d, a, b in dlugie:
            znak = "!!" if d > cfg.przeslo_blad else "  "
            print(f"  {znak} {a.etykieta}–{b.etykieta}: {d:.2f} m")

    print("\nPlan numeracji:")
    for x in p.opis_planu():
        print("  -", x)
    print(f"  początek: {p.plan[0].etykieta} ({adres_slupa(p.plan[0])}), "
          f"koniec: {p.plan[-1].etykieta} ({adres_slupa(p.plan[-1])})")
    if not a.tak and input("\nCzy wykonać numerację? [t/N]: ").strip().lower() not in ("t", "tak"):
        print("Przerwano - nic nie zapisano.")
        return 0

    kat = Path(a.katalog) if a.katalog else p.plik.parent
    kat.mkdir(parents=True, exist_ok=True)
    zad = [("numeracja.dxf", p.zapisz_dxf),
           ("pismo.docx", lambda f: p.zapisz_pismo(f, operator, a.od, a.do))]
    if a.zestawienie in ("rozbudowana", "oba"):
        zad.append(("rozbudowana.xlsx", p.zapisz_rozbudowana))
    if a.zestawienie in ("uproszczona", "oba"):
        zad.append(("uproszczona.xls", p.zapisz_uproszczona))
    for przyr, f in zad:
        cel = p.sciezka(kat, przyr)
        f(cel)
        print("Zapisano:", cel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
