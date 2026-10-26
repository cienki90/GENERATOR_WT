"""python -m generator_wt.web               - okno programu (Qt WebEngine)
python -m generator_wt.web --przegladarka  - sam serwer; adres do otwarcia w przeglądarce
                                             (bez natywnych okien wyboru plików)
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m generator_wt.web")
    ap.add_argument("--przegladarka", action="store_true",
                    help="uruchom tylko serwer i wypisz adres strony")
    ap.add_argument("--port", type=int, default=0)
    a = ap.parse_args(argv)
    if not a.przegladarka:
        from .okno import main as okno
        return okno()

    from .api import Api
    from .serwer import Serwer
    s = Serwer(Api(), a.port).start()
    print(s.adres, flush=True)
    try:
        s._watek.join()
    except KeyboardInterrupt:
        s.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
