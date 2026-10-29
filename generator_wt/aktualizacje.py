"""Wersja programu i sprawdzanie, czy na GitHubie jest nowsza (zakładka Releases).

Paczka .exe budowana na GitHubie (windows.yml) ma plik wersja.json z numerem commita.
Wydanie "najnowsza-wersja" wskazuje commit, z którego je zbudowano - jeśli jest inny
niż nasz, w oknie pojawia się informacja o nowszej wersji. Uruchomienie ze źródeł
(bez wersja.json) niczego nie sprawdza.

    python -m generator_wt.aktualizacje <commit> [gałąź]   # zapis wersja.json przy budowie
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

PLIK_WERSJI = Path(__file__).with_name("wersja.json")
REPOZYTORIUM = "cienki90/GENERATOR_WT"
WYDANIE = "najnowsza-wersja"
ADRES_API = f"https://api.github.com/repos/{REPOZYTORIUM}/releases/tags/{WYDANIE}"
ADRES_WYDAN = f"https://github.com/{REPOZYTORIUM}/releases"


def wersja() -> dict | None:
    """{"commit", "data", "galaz"} spakowanego programu albo None (uruchomienie ze źródeł)."""
    try:
        w = json.loads(PLIK_WERSJI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return w if isinstance(w, dict) and w.get("commit") else None


def opis_wersji() -> str:
    w = wersja()
    if not w:
        return "wersja ze źródeł"
    return f"wersja {w['commit'][:7]} z {w.get('data', '?')}"


def sprawdz(limit: float = 8) -> dict | None:
    """Nowsza wersja na GitHubie: {"adres", "data"}; None, gdy jej nie ma, program
    uruchomiono ze źródeł albo nie udało się sprawdzić (brak internetu)."""
    w = wersja()
    if not w:
        return None
    zad = urllib.request.Request(ADRES_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "GeneratorWT"})
    try:
        with urllib.request.urlopen(zad, timeout=limit) as r:
            wyd = json.loads(r.read())
    except (OSError, ValueError):
        return None
    commit = str(wyd.get("target_commitish") or "")
    if not commit or commit == w["commit"]:
        return None
    adres = str(wyd.get("html_url") or "")
    if not adres.startswith(f"https://github.com/{REPOZYTORIUM}/"):
        adres = ADRES_WYDAN
    return {"adres": adres, "data": str(wyd.get("published_at") or "")[:10]}


def zapisz_wersje(commit: str, galaz: str = "") -> None:
    PLIK_WERSJI.write_text(json.dumps({"commit": commit, "galaz": galaz,
                                       "data": date.today().isoformat()}), encoding="utf-8")


if __name__ == "__main__":
    zapisz_wersje(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
    print(f"Zapisano {PLIK_WERSJI}: {opis_wersji()}")
