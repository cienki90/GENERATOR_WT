"""Generator WT - numeracja słupów (wierzchołków !tele) w DXF, zestawienia i pismo.

Użycie:
    python -m generator_wt.main projekt.dxf
    python -m generator_wt.main projekt.dxf --zestawienie oba --operator InterWan --tak
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dxf_writer, export, geocoder, numbering, pismo, reader, slowniki
from .config import Config


def pytanie(tekst: str, domyslnie_tak: bool = False) -> bool:
    odp = input(f"{tekst} [{'T/n' if domyslnie_tak else 't/N'}]: ").strip().lower()
    if not odp:
        return domyslnie_tak
    return odp in ("t", "tak", "y", "yes")


def _znajdz(lista, nazwa):
    for poz in lista:
        if poz.get("Nazwa", "").casefold() == nazwa.casefold():
            return poz
    raise SystemExit(f"Nie ma pozycji '{nazwa}' w słowniku. Dostępne: "
                     + ", ".join(p.get("Nazwa", "") for p in lista))


def _postep(i, n):
    print(f"\r  geokodowanie: {i}/{n}", end="", file=sys.stderr, flush=True)
    if i == n:
        print(file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Numeracja słupów warstwy !tele i zestawienia")
    ap.add_argument("dxf", help="plik wejściowy DXF")
    ap.add_argument("--zestawienie", choices=["rozbudowana", "uproszczona", "oba", "brak"],
                    help="rodzaj zestawienia Excel (domyślnie: pytanie)")
    ap.add_argument("--operator", help="nazwa operatora ze słownika (domyślnie: wybór z listy)")
    ap.add_argument("--rejon", help="rejon energetyczny dla gmin nieprzypisanych w słowniku")
    ap.add_argument("--od", help="data OD w piśmie (domyślnie dzisiejsza)")
    ap.add_argument("--do", default="-", help="data DO w piśmie (domyślnie '-')")
    ap.add_argument("--prefiks", default="", help="prefiks numeru, np. S -> S1, S2...")
    ap.add_argument("--start", type=int, default=1, help="numer początkowy")
    ap.add_argument("--bez-geokodowania", action="store_true",
                    help="nie pobieraj adresów z GUGiK (praca offline)")
    ap.add_argument("--tak", action="store_true", help="nie pytaj o potwierdzenia")
    args = ap.parse_args(argv)

    cfg = Config(prefiks=args.prefiks, numer_startowy=args.start)
    wej = Path(args.dxf)
    baza = wej.with_name(wej.stem)
    wyj_dxf = Path(f"{baza}_numeracja.dxf")

    # --- 1. Odczyt rysunku ---
    doc = reader.wczytaj_dxf(str(wej))
    slupy = reader.wczytaj_wierzcholki_tele(doc, cfg)
    if not slupy:
        print(f"Brak polilinii na warstwie '{cfg.warstwa_tele}'.")
        return 1
    stacje = reader.wczytaj_stacje_trafo(doc, cfg)
    print(f"Plik: {wej}")
    print(f"Słupów (wierzchołków '{cfg.warstwa_tele}'): {len(slupy)}")
    print(f"Stref trafo ('{cfg.warstwa_trafo}'): {len(stacje)}")

    # --- 2. Dane adresowe (potrzebne też do grupowania wg miejscowości) ---
    if not args.bez_geokodowania:
        epsg = geocoder.wykryj_epsg(slupy[0].x)
        print(f"Pobieranie adresów z GUGiK (EPSG:{epsg})...")
        bledy = geocoder.uzupelnij(slupy, geocoder.Geokoder(epsg, cfg.promien_adresu),
                                   postep=_postep)
        if bledy:
            print(f"  Uwaga: {bledy} słupów bez danych (błąd usługi) - "
                  "uruchom ponownie, aby dociągnąć brakujące.")

    # --- 3. Plan numeracji i potwierdzenie ---
    grupy = numbering.utworz_grupy(slupy, stacje, cfg)
    plan = numbering.zaplanuj_numeracje(slupy, grupy, cfg)
    print("\nPlan numeracji (ciągła):")
    for g in grupy:
        nry = sorted(w.nr for w in g.wierzcholki)
        rodzaj = "strefa trafo" if g.stacja else "miejscowość"
        print(f"  - {g.nazwa} [{rodzaj}]: {len(nry)} słupów, "
              f"{cfg.prefiks}{nry[0]}..{cfg.prefiks}{nry[-1]}")
    print(f"  Słup początkowy: {plan[0].etykieta} ({pismo.adres_slupa(plan[0])})")
    print(f"  Słup końcowy:    {plan[-1].etykieta} ({pismo.adres_slupa(plan[-1])})")

    stare = dxf_writer.istniejaca_numeracja(doc, cfg)
    if stare:
        print(f"\nNa warstwie '{cfg.warstwa_numeracji}' jest już {stare} numerów "
              "- zostaną zastąpione.")
    if not args.tak and not pytanie(f"\nCzy wykonać numerację i zapisać {wyj_dxf.name}?"):
        print("Przerwano - nic nie zapisano.")
        return 0
    dxf_writer.usun_numeracje(doc, cfg)
    dxf_writer.zapisz_numeracje(doc, plan, cfg)
    doc.saveas(str(wyj_dxf))
    print(f"Zapisano: {wyj_dxf}")

    # --- 4. Operator i rejony energetyczne ---
    if not cfg.plik_slownikow.exists():
        slowniki.utworz_szablon(cfg.plik_slownikow)
        print(f"Utworzono przykładowy plik słowników: {cfg.plik_slownikow}")
    operatorzy = slowniki.wczytaj_liste(cfg.plik_slownikow, slowniki.ARKUSZ_OPERATORZY)
    rejony = slowniki.wczytaj_liste(cfg.plik_slownikow, slowniki.ARKUSZ_REJONY)

    if args.operator:
        operator = _znajdz(operatorzy, args.operator)
    elif args.tak:
        operator = operatorzy[0] if operatorzy else None
    else:
        operator = slowniki.wybierz(operatorzy, "Dla którego operatora jest zestawienie?", 1)

    for w in plan:
        w.rejon = slowniki.rejon_dla_gminy(rejony, w.gmina)
    bez_rejonu = sorted({w.gmina or "(brak gminy)" for w in plan if not w.rejon})
    if bez_rejonu:
        print(f"\nGminy bez przypisanego rejonu energetycznego: {', '.join(bez_rejonu)}")
        if args.rejon:
            rejon = _znajdz(rejony, args.rejon)
        elif args.tak:
            rejon = rejony[0] if rejony else None
        else:
            rejon = slowniki.wybierz(rejony, "Wybierz rejon energetyczny dla tych gmin", 1)
        for w in plan:
            if not w.rejon and rejon:
                w.rejon = rejon["Nazwa"]

    # --- 5. Pismo i zestawienia ---
    if cfg.szablon_pisma.exists():
        wyj_docx = Path(f"{baza}_pismo.docx")
        pismo.generuj_pismo(cfg.szablon_pisma, wyj_docx, plan, operator, args.od, args.do)
        print(f"Zapisano: {wyj_docx}")
    else:
        print(f"Brak szablonu pisma: {cfg.szablon_pisma}")

    rodzaj = args.zestawienie
    if rodzaj is None:
        rodzaj = "oba" if args.tak else {"r": "rozbudowana", "u": "uproszczona", "o": "oba",
                                         "": "oba", "n": "brak"}.get(
            input("\nZestawienie: [r]ozbudowana.xlsx / [u]proszczona.xls / [o]ba / [n]ie "
                  "(Enter = oba): ").strip().lower()[:1], "oba")
    tytul = f"Wykaz słupów - {operator['Nazwa']}" if operator else "Wykaz słupów"
    if rodzaj in ("rozbudowana", "oba"):
        p = Path(f"{baza}_rozbudowana.xlsx")
        export.zapisz_rozbudowane(plan, p, tytul)
        print(f"Zapisano: {p}")
    if rodzaj in ("uproszczona", "oba"):
        p = Path(f"{baza}_uproszczona.xls")
        export.zapisz_uproszczone(plan, p)
        print(f"Zapisano: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
