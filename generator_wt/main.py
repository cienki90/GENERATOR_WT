"""Generator WT - etap 1: odczyt DXF, numeracja wierzchołków !tele w strefach !trafo.

Użycie:
    python -m generator_wt.main plik.dxf [--osobno] [--prefiks S] [--start 1] [--tak]
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .config import Config
from . import dxf_writer, numbering, reader


def pytanie(tekst: str, domyslnie_nie: bool = True) -> bool:
    odp = input(f"{tekst} [{'t/N' if domyslnie_nie else 'T/n'}]: ").strip().lower()
    if not odp:
        return not domyslnie_nie
    return odp in ("t", "tak", "y", "yes")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Numeracja wierzchołków warstwy !tele w DXF")
    ap.add_argument("dxf", help="plik wejściowy DXF")
    ap.add_argument("-o", "--wyjscie", help="plik wyjściowy DXF (domyślnie *_numeracja.dxf)")
    ap.add_argument("--osobno", action="store_true",
                    help="numeracja od nowa w każdej strefie trafo (domyślnie ciągła)")
    ap.add_argument("--prefiks", default="", help="prefiks numeru, np. S -> S1, S2...")
    ap.add_argument("--start", type=int, default=1, help="numer początkowy")
    ap.add_argument("--tak", action="store_true", help="nie pytaj o potwierdzenie")
    args = ap.parse_args(argv)

    cfg = Config(prefiks=args.prefiks, numer_startowy=args.start)
    wej = Path(args.dxf)
    wyj = Path(args.wyjscie) if args.wyjscie else wej.with_name(wej.stem + "_numeracja.dxf")

    doc = reader.wczytaj_dxf(str(wej))
    wierzcholki = reader.wczytaj_wierzcholki_tele(doc, cfg)
    if not wierzcholki:
        print(f"Brak obiektów na warstwie '{cfg.warstwa_tele}'.")
        return 1
    stacje = reader.wczytaj_stacje_trafo(doc, cfg)
    grupy = numbering.przypisz_do_grup(wierzcholki, stacje, cfg)
    plan = numbering.zaplanuj_numeracje(wierzcholki, grupy, cfg, ciagla=not args.osobno)

    # --- Podsumowanie przed numeracją ---
    print(f"\nPlik: {wej}")
    print(f"Wierzchołków na warstwie '{cfg.warstwa_tele}': {len(wierzcholki)}")
    print(f"Stref trafo na warstwie '{cfg.warstwa_trafo}': {len(stacje)}")
    print(f"Numeracja: {'osobna w każdej strefie' if args.osobno else 'ciągła'}")
    for g in grupy:
        nry = [w.nr for w in g.wierzcholki]
        print(f"  - {g.nazwa}: {len(nry)} pkt, numery {cfg.prefiks}{min(nry)}"
              f"..{cfg.prefiks}{max(nry)}")
    if args.osobno:
        dupl = [k for k, v in Counter(w.etykieta for w in plan).items() if v > 1]
        if dupl:
            print("  Uwaga: przy numeracji osobnej numery powtarzają się między strefami.")

    stare = dxf_writer.istniejaca_numeracja(doc, cfg)
    if stare:
        print(f"\nNa warstwie '{cfg.warstwa_numeracji}' jest już {stare} numerów.")

    if not args.tak and not pytanie(f"\nCzy wykonać numerację i zapisać do {wyj.name}?"):
        print("Przerwano - nic nie zapisano.")
        return 0

    if stare:
        if args.tak or pytanie("Usunąć istniejącą numerację przed zapisem nowej?", False):
            dxf_writer.usun_numeracje(doc, cfg)

    dxf_writer.zapisz_numeracje(doc, plan, cfg)
    doc.saveas(str(wyj))
    print(f"Zapisano: {wyj} ({len(plan)} numerów na warstwie '{cfg.warstwa_numeracji}')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
