"""Struktury danych używane w całym programie."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Point, Polygon


@dataclass
class StacjaTrafo:
    """Zasięg stacji transformatorowej (zamknięty obrys na warstwie !trafo)."""
    nazwa: str
    obrys: Polygon
    punkt_stacji: Optional[Point] = None  # lokalizacja stacji (blok/punkt), jeśli jest
    kolejnosc_rysunku: int = 0


@dataclass
class Wierzcholek:
    """Wierzchołek warstwy !tele - docelowo punkt zestawienia (np. słup)."""
    id: int
    x: float
    y: float
    # kolejność wystąpienia w rysunku: (nr obiektu, nr wierzchołka)
    kolejnosc_rysunku: tuple[int, int] = (0, 0)

    # Uzupełniane podczas numeracji
    nr: Optional[int] = None
    etykieta: str = ""
    grupa: str = ""  # nazwa stacji trafo lub miejscowości

    # --- Pola przygotowane pod kolejne etapy ---
    stacja_trafo: Optional[str] = None
    id_slupa: Optional[str] = None       # identyfikacja słupa powiązana ze stacją
    miejscowosc: Optional[str] = None
    ulica: Optional[str] = None
    gmina: Optional[str] = None
    powiat: Optional[str] = None
    wojewodztwo: Optional[str] = None
    obreb: Optional[str] = None
    dzialka: Optional[str] = None
    uwagi: str = ""

    sasiedzi: set[int] = field(default_factory=set)

    @property
    def punkt(self) -> Point:
        return Point(self.x, self.y)
