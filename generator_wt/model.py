"""Struktury danych używane w całym programie."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Point, Polygon


@dataclass
class StacjaTrafo:
    """Zasięg stacji transformatorowej (zamknięta polilinia na warstwie !trafo)."""
    nazwa: str
    obrys: Polygon
    kolejnosc_rysunku: int = 0


@dataclass
class Wierzcholek:
    """Wierzchołek linii !tele = słup."""
    id: int
    x: float  # współrzędna wschodnia w DXF (w geodezji: Y)
    y: float  # współrzędna północna w DXF (w geodezji: X)
    kolejnosc_rysunku: tuple[int, int] = (0, 0)

    # Numeracja
    nr: Optional[int] = None
    etykieta: str = ""
    grupa: str = ""  # nazwa stacji trafo lub miejscowości

    # Identyfikacja słupa
    stacja_trafo: Optional[str] = None
    id_slupa: Optional[str] = None

    # Dane adresowe (geokodowanie)
    miejscowosc: Optional[str] = None
    ulica: Optional[str] = None
    kod: Optional[str] = None
    gmina: Optional[str] = None
    powiat: Optional[str] = None
    wojewodztwo: Optional[str] = None
    obreb: Optional[str] = None
    dzialka: Optional[str] = None
    rejon: Optional[str] = None
    uwagi: str = ""

    sasiedzi: set[int] = field(default_factory=set)

    @property
    def punkt(self) -> Point:
        return Point(self.x, self.y)

    # Współrzędne w konwencji geodezyjnej (jak w piśmie: X = północna, Y = wschodnia)
    @property
    def geo_x(self) -> float:
        return self.y

    @property
    def geo_y(self) -> float:
        return self.x
