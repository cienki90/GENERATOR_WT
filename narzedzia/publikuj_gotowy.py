#!/usr/bin/env python3
"""Publikacja „czystej” kopii programu - bez przykładów i materiałów pomocniczych.

Kopiuje do wskazanego katalogu tylko pliki potrzebne do działania programu (kod, szablony,
skrypty uruchomieniowe), w stanie z OSTATNIEGO COMMITA (HEAD albo gałęzi z ``--z-galezi``) -
niezatwierdzone zmiany robocze nie trafiają do kopii.

Kopia jest lustrem: pliki programu usunięte z repozytorium znikają też z kopii. Inne pliki
w katalogu docelowym (np. wyniki pracy użytkownika) nie są ruszane - skrypt prowadzi listę
plików, które sam umieścił (``.pliki_programu.txt``), i usuwa tylko z niej.

Użycie:
    python narzedzia/publikuj_gotowy.py "D:/…/GOTOWE PROJEKTY/GENERATOR WT"
    python narzedzia/publikuj_gotowy.py "D:/…/GENERATOR WT" --z-galezi inna-galaz
    python narzedzia/publikuj_gotowy.py "D:/…/GENERATOR WT" --zainstaluj-hook [--galaz Generator_WT_PGE-CLAUDE]

``--zainstaluj-hook`` instaluje hooki gita (post-commit, post-merge, post-rewrite), które po
każdym commicie / pull na wskazanej gałęzi automatycznie odświeżają kopię. Każda gałąź może
mieć własną kopię: kolejne wywołania dopisują parę gałąź -> katalog, a nie kasują poprzednich.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# co trafia do gotowego programu (ścieżki z repozytorium; katalog = cała zawartość)
PLIKI_PROGRAMU = [
    "generator_wt/",
    "szablony/",
    "uruchom.pyw",
    "Generator WT.bat",
    "instaluj.bat",
    "requirements.txt",
    "constraints.txt",
    "README.md",
    "INSTRUKCJA.txt",
]
POMIN: set = set()
# dane użytkownika (lista operatorów i rejonów, pamięć geokodowania, kafle): plik startowy trafia do
# kopii tylko wtedy, gdy go tam jeszcze nie ma - aktualizacja NIGDY nie nadpisuje danych użytkownika
PLIKI_STARTOWE = ["dane/slowniki.xlsx"]

MANIFEST = ".pliki_programu.txt"
PLIK_WERSJI = "WERSJA.txt"
INSTRUKCJA = "O TEJ KOPII.txt"
HOOKI = ("post-commit", "post-merge", "post-rewrite")

TRESC_INSTRUKCJI = """GENERATOR WT — gotowy program
=============================
Wersja: {wersja}

Uruchamianie: „Generator WT.bat” (albo uruchom.pyw). Pierwszy raz na komputerze: instaluj.bat.
Opis programu: INSTRUKCJA.txt i README.md.

Ten katalog jest odświeżany automatycznie z repozytorium (gałąź {galaz}, commit {commit}).
Nie zmieniaj tu plików programu — zmiany zostaną nadpisane przy następnej aktualizacji.
Folder „dane” (lista operatorów i rejonów, pamięć adresów, kafle map) jest Twój — aktualizacja
go nie rusza.
"""


def _git(repo, *args, tekst=True):
    wynik = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True)
    return wynik.stdout.decode("utf-8") if tekst else wynik.stdout


def _pliki_z_commita(repo, ref="HEAD") -> list[str]:
    wszystkie = _git(repo, "-c", "core.quotepath=off", "ls-tree", "-r", "--name-only", "-z", ref)
    wszystkie = [p for p in wszystkie.split("\0") if p]
    wybrane = []
    for p in wszystkie:
        if p in POMIN:
            continue
        if any(p == w or (w.endswith("/") and p.startswith(w)) for w in PLIKI_PROGRAMU):
            wybrane.append(p)
    return wybrane


def _zapisz_jesli_inny(sciezka, dane: bytes) -> bool:
    try:
        with open(sciezka, "rb") as f:
            if f.read() == dane:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(sciezka) or ".", exist_ok=True)
    tmp = sciezka + ".tmp_publikacja"
    with open(tmp, "wb") as f:
        f.write(dane)
    os.replace(tmp, sciezka)
    return True


def publikuj(repo: str, cel: str, ref: str = "HEAD") -> tuple[int, int, int]:
    """Odświeża kopię programu w katalogu ``cel`` stanem z ``ref`` (commit / gałąź, domyślnie HEAD).
    Zwraca (zmienione, bez zmian, usunięte)."""
    repo = os.path.abspath(repo)
    cel = os.path.abspath(cel)
    pliki = _pliki_z_commita(repo, ref)
    if not pliki:
        raise RuntimeError(f"W {ref} nie ma plików programu - sprawdź repozytorium.")
    os.makedirs(cel, exist_ok=True)

    zmienione = bez_zmian = 0
    for p in pliki:
        dane = _git(repo, "show", f"{ref}:{p}", tekst=False)
        if _zapisz_jesli_inny(os.path.join(cel, *p.split("/")), dane):
            zmienione += 1
        else:
            bez_zmian += 1

    galaz = _git(repo, "rev-parse", "--abbrev-ref", ref).strip()
    commit = _git(repo, "rev-parse", "--short", ref).strip()
    # numer wersji dla kopii (bez gita): <główna z generator/__init__.py>.<liczba commitów>
    licznik = _git(repo, "rev-list", "--count", ref).strip()
    data = _git(repo, "log", "-1", "--format=%cs", ref).strip()
    wersja = f"{licznik} ({data}, {commit})"
    _zapisz_jesli_inny(os.path.join(cel, *PLIK_WERSJI.split("/")), (wersja + "\n").encode("utf-8"))
    pliki = pliki + [PLIK_WERSJI]
    for p in PLIKI_STARTOWE:                         # dane użytkownika - tylko gdy ich brak
        cel_p = os.path.join(cel, *p.split("/"))
        if not os.path.exists(cel_p):
            _zapisz_jesli_inny(cel_p, _git(repo, "show", f"{ref}:{p}", tekst=False))

    instrukcja = TRESC_INSTRUKCJI.format(galaz=galaz, commit=commit, wersja=wersja).replace("\n", "\r\n")
    _zapisz_jesli_inny(os.path.join(cel, INSTRUKCJA), instrukcja.encode("utf-8"))

    # usuń pliki programu, których już nie ma (tylko te, które sami wcześniej umieściliśmy)
    usuniete = 0
    sciezka_manifestu = os.path.join(cel, MANIFEST)
    try:
        with open(sciezka_manifestu, encoding="utf-8") as f:
            poprzednie = {ln.strip() for ln in f if ln.strip()}
    except OSError:
        poprzednie = set()
    for p in sorted(poprzednie - set(pliki) - {INSTRUKCJA}):
        pelna = os.path.join(cel, *p.split("/"))
        if os.path.isfile(pelna):
            os.remove(pelna)
            usuniete += 1
            katalog = os.path.dirname(pelna)          # sprzątnij puste katalogi po programie
            while katalog != cel and os.path.isdir(katalog) and not os.listdir(katalog):
                os.rmdir(katalog)
                katalog = os.path.dirname(katalog)
    _zapisz_jesli_inny(sciezka_manifestu, ("\n".join(sorted(pliki + [INSTRUKCJA])) + "\n").encode("utf-8"))
    return zmienione, bez_zmian, usuniete


ZNACZNIK_KOPII = "# kopia: "        # „# kopia: <gałąź> => <katalog>” - jedna linia na kopię


def kopie_z_hooka(tresc: str) -> dict:
    """Pary gałąź -> katalog kopii zapisane w hooku (także w starym formacie z jedną kopią)."""
    kopie = {}
    for linia in tresc.splitlines():
        if linia.startswith(ZNACZNIK_KOPII) and " => " in linia:
            galaz, cel = linia[len(ZNACZNIK_KOPII):].split(" => ", 1)
            kopie[galaz.strip()] = cel.strip()
    if not kopie:                                   # stary hook: [ "…HEAD)" = "<gałąź>" ] i CEL='<katalog>'
        g = re.search(r'--abbrev-ref HEAD\)" = "([^"]+)" \]', tresc)
        c = re.search(r"^CEL='([^']+)'", tresc, re.M)
        if g and c:
            kopie[g.group(1)] = c.group(1)
    return kopie


def tresc_hooka(kopie: dict) -> str:
    skrypt = "narzedzia/publikuj_gotowy.py"
    linie = ["#!/bin/sh",
             "# Automatyczna publikacja czystych kopii programu (narzedzia/publikuj_gotowy.py).",
             "# Każda gałąź ma własną kopię:"]
    linie += [f"{ZNACZNIK_KOPII}{g} => {c}" for g, c in kopie.items()]
    linie += ['case "$(git rev-parse --abbrev-ref HEAD)" in']
    linie += [f"  '{g}') CEL='{c}' ;;" for g, c in kopie.items()]
    linie += ["  *) exit 0 ;;",
              "esac",
              'if command -v python >/dev/null 2>&1; then PY=python; else PY="py -3"; fi',
              f'$PY "{skrypt}" "$CEL" --cicho || echo "UWAGA: nie udało się odświeżyć kopii programu w $CEL"',
              "exit 0", ""]
    return "\n".join(linie)


def zainstaluj_hook(repo: str, cel: str, galaz: str) -> list[str]:
    """Hooki gita odświeżające kopię ``cel`` po commicie / pull / amend na gałęzi ``galaz``.
    Kopie innych gałęzi zapisane już w hookach zostają."""
    katalog_hookow = _git(repo, "rev-parse", "--git-path", "hooks").strip()
    if not os.path.isabs(katalog_hookow):
        katalog_hookow = os.path.join(repo, katalog_hookow)
    os.makedirs(katalog_hookow, exist_ok=True)
    try:
        with open(os.path.join(katalog_hookow, HOOKI[0]), encoding="utf-8") as f:
            kopie = kopie_z_hooka(f.read())
    except OSError:
        kopie = {}
    kopie[galaz] = cel
    tresc = tresc_hooka(kopie)
    zapisane = []
    for nazwa in HOOKI:
        sciezka = os.path.join(katalog_hookow, nazwa)
        with open(sciezka, "w", encoding="utf-8", newline="\n") as f:
            f.write(tresc)
        os.chmod(sciezka, 0o755)
        zapisane.append(sciezka)
    return zapisane


def main(argv=None):
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="Publikacja czystej kopii programu (bez przykładów).")
    ap.add_argument("cel", help="katalog gotowego programu")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="repozytorium źródłowe (domyślnie to, w którym leży skrypt)")
    ap.add_argument("--zainstaluj-hook", action="store_true",
                    help="zainstaluj hooki gita - automatyczna publikacja po każdym commicie")
    ap.add_argument("--galaz", default="Generator_WT_PGE-CLAUDE", help="gałąź publikowana przez hooki")
    ap.add_argument("--z-galezi", default="HEAD", metavar="GAŁĄŹ",
                    help="kopia ze stanu tej gałęzi / commita, bez przełączania (domyślnie HEAD)")
    ap.add_argument("--cicho", action="store_true", help="jedna linia podsumowania")
    a = ap.parse_args(argv)

    if a.zainstaluj_hook:
        for h in zainstaluj_hook(a.repo, os.path.abspath(a.cel), a.galaz):
            print("hook:", h)
    zm, bz, us = publikuj(a.repo, a.cel, a.z_galezi)
    if a.cicho:
        print(f"Kopia programu odświeżona ({a.cel}): zmienione {zm}, usunięte {us}.")
    else:
        print(f"Kopia programu: {a.cel}")
        print(f"  zmienione/nowe: {zm}, bez zmian: {bz}, usunięte: {us}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
