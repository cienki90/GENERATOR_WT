"""Struktury danych używane w całym programie."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Point, Polygon


@dataclass
class StacjaTrafo:
    """Zasięg stacji transformatorowej (obrys na warstwie !trafo)."""
    nazwa: str                      # np. "05-0792"
    obrys: Polygon
    punkt_stacji: Optional[Point] = None
    kolejnosc_rysunku: int = 0


@dataclass
class BlednyKlik:
    """Grupa wierzchołków odległych o mniej niż tolerancja - scalona w jeden słup."""
    x: float
    y: float
    liczba: int
    max_odleglosc: float


@dataclass
class Wierzcholek:
    """Słup = wierzchołek linii !tele (po scaleniu błędnych klików)."""
    id: int
    x: float  # współrzędna wschodnia w DXF (w geodezji: Y)
    y: float  # współrzędna północna w DXF (w geodezji: X)
    kolejnosc_rysunku: tuple[int, int] = (0, 0)
    scalonych: int = 1  # ile wierzchołków rysunku wskazuje ten słup

    nr: Optional[int] = None
    etykieta: str = ""
    grupa: str = ""

    stacja_trafo: Optional[str] = None
    rodzaj_slupa: Optional[str] = None   # nN / SN
    typ_slupa: Optional[str] = None      # np. K-10,5/10/E
    id_slupa: Optional[str] = None       # stacja/numer, np. 05-0743/9.1
    nr_w_sieci: Optional[str] = None     # numer słupa z rysunku (warstwa _numery...)

    miejscowosc: Optional[str] = None
    ulica: Optional[str] = None
    kod: Optional[str] = None
    gmina: Optional[str] = None
    powiat: Optional[str] = None
    wojewodztwo: Optional[str] = None
    obreb: Optional[str] = None
    dzialka: Optional[str] = None
    rejon: Optional[str] = None
    rejon_skrot: Optional[str] = None
    uwagi: str = ""

    sasiedzi: set[int] = field(default_factory=set)

    @property
    def punkt(self) -> Point:
        return Point(self.x, self.y)

    @property
    def geo_x(self) -> float:
        return self.y

    @property
    def geo_y(self) -> float:
        return self.x
