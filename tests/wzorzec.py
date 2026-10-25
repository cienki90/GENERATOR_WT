"""Wzorzec wyników dla przykładowego projektu (tests/dane/wzorzec.json).

Testy regresji porównują numerację i ułożenie arkuszy z tym wzorcem - każda zmiana
algorytmu, która zmienia wynik, zostanie zauważona. Gdy zmiana jest zamierzona,
odśwież wzorzec i zatwierdź go razem ze zmianą:

    python -m tests.wzorzec
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.conftest import PRZYKLAD, WZORZEC, nowy_projekt  # noqa: E402

ZAKLADKI = (0.0, 10.0, 25.0)


def wyniki(plik: Path) -> dict:
    p = nowy_projekt(plik)
    wynik = {
        "slupy": len(p.slupy),
        "plan": [[round(w.x, 2), round(w.y, 2), w.etykieta, w.grupa] for w in p.plan],
        "arkusze": {},
    }
    for z in ZAKLADKI:
        p.cfg.zakladka = z
        wynik["arkusze"][f"{z:g}"] = [[a.nazwa, round(a.x0, 2), round(a.y0, 2)]
                                      for a in p.planuj_arkusze()]
    return wynik


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        cel = Path(tmp) / "projekt.dxf"
        shutil.copy(PRZYKLAD, cel)
        dane = wyniki(cel)
    WZORZEC.parent.mkdir(parents=True, exist_ok=True)
    WZORZEC.write_text(json.dumps(dane, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Zapisano {WZORZEC} ({len(dane['plan'])} słupów w planie, arkuszy: "
          + ", ".join(f"zakładka {k} m: {len(v)}" for k, v in dane["arkusze"].items()) + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
