"""Wspólne dane testów: przykładowy projekt (przyklady/baza robocza.dxf).

Testy nie korzystają z internetu - usługi GUGiK/OSM są zastępowane danymi testowymi.
Uruchomienie:  python -m pytest
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

# okno Qt bez wyświetlania (testy GUI na serwerze CI)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

KATALOG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KATALOG))

PRZYKLAD = KATALOG / "przyklady" / "baza robocza.dxf"
WZORZEC = Path(__file__).resolve().parent / "dane" / "wzorzec.json"


@pytest.fixture
def dxf(tmp_path) -> Path:
    """Kopia przykładowego DXF w folderze tymczasowym - pliki wyników i stanu
    (.wt.json) nie trafiają do katalogu przyklady/."""
    cel = tmp_path / "projekt.dxf"
    shutil.copy(PRZYKLAD, cel)
    return cel


def nowy_projekt(plik: Path, arkusze: bool = False, **cfg):
    from generator_wt.config import Config
    from generator_wt.projekt import Projekt
    p = Projekt(Config(**cfg))
    p.wczytaj(plik)
    p.zastosuj_stan()
    p.planuj()
    if arkusze:
        p.planuj_arkusze()
    return p


@pytest.fixture(scope="session")
def projekt_z_arkuszami(tmp_path_factory):
    """Przeanalizowany projekt z arkuszami (raz na sesję - arkusze liczą się ~2 s).
    Testy NIE mogą go zmieniać."""
    kat = tmp_path_factory.mktemp("wspolny")
    cel = kat / "projekt.dxf"
    shutil.copy(PRZYKLAD, cel)
    return nowy_projekt(cel, arkusze=True)
