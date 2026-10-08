"""Odczyt pliku DXF: wierzchołki warstwy !tele i zasięgi stacji z warstwy !trafo."""
from __future__ import annotations

import math

import ezdxf
from ezdxf.document import Drawing
from shapely.geometry import Point, Polygon

from .config import Config
from .model import StacjaTrafo, Wierzcholek


def wczytaj_dxf(sciezka: str) -> Drawing:
    return ezdxf.readfile(sciezka)


def _ta_sama_warstwa(e, nazwa: str) -> bool:
    return e.dxf.layer.casefold() == nazwa.casefold()


def _punkty_obiektu(e) -> list[tuple[float, float]]:
    """Zwraca kolejne wierzchołki obiektu liniowego/punktowego."""
    typ = e.dxftype()
    if typ == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    if typ == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in e.get_points("xy")]
        if e.closed and pts:
            pts.append(pts[0])
        return pts
    if typ == "POLYLINE":
        pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
        if e.is_closed and pts:
            pts.append(pts[0])
        return pts
    if typ in ("POINT",):
        return [(e.dxf.location.x, e.dxf.location.y)]
    if typ == "INSERT":
        return [(e.dxf.insert.x, e.dxf.insert.y)]
    return []


class _IndeksWierzcholkow:
    """Scala wierzchołki leżące w tym samym miejscu (w granicy tolerancji)."""

    def __init__(self, tolerancja: float):
        self.tol = tolerancja
        self.siatka: dict[tuple[int, int], list[int]] = {}
        self.lista: list[Wierzcholek] = []

    def _klucz(self, x, y):
        return (math.floor(x / self.tol), math.floor(y / self.tol))

    def dodaj(self, x: float, y: float, kolejnosc: tuple[int, int]) -> int:
        kx, ky = self._klucz(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for idx in self.siatka.get((kx + dx, ky + dy), []):
                    w = self.lista[idx]
                    if math.hypot(w.x - x, w.y - y) <= self.tol:
                        return idx
        idx = len(self.lista)
        self.lista.append(Wierzcholek(id=idx, x=x, y=y, kolejnosc_rysunku=kolejnosc))
        self.siatka.setdefault((kx, ky), []).append(idx)
        return idx


def wczytaj_wierzcholki_tele(doc: Drawing, cfg: Config) -> list[Wierzcholek]:
    """Zbiera unikalne wierzchołki z warstwy !tele wraz z połączeniami między nimi."""
    indeks = _IndeksWierzcholkow(cfg.tolerancja)
    msp = doc.modelspace()
    for nr_obiektu, e in enumerate(msp):
        if not _ta_sama_warstwa(e, cfg.warstwa_tele):
            continue
        poprzedni = None
        for nr_wierzch, (x, y) in enumerate(_punkty_obiektu(e)):
            idx = indeks.dodaj(x, y, (nr_obiektu, nr_wierzch))
            if poprzedni is not None and poprzedni != idx:
                indeks.lista[poprzedni].sasiedzi.add(idx)
                indeks.lista[idx].sasiedzi.add(poprzedni)
            poprzedni = idx
    return indeks.lista


def _tekst_obiektu(e) -> str | None:
    typ = e.dxftype()
    if typ == "TEXT":
        return e.dxf.text.strip()
    if typ == "MTEXT":
        return e.plain_text().strip()
    if typ == "INSERT":
        for a in e.attribs:
            if a.dxf.text.strip():
                return a.dxf.text.strip()
    return None


def wczytaj_stacje_trafo(doc: Drawing, cfg: Config) -> list[StacjaTrafo]:
    """Zamknięte obrysy na warstwie !trafo = zasięgi stacji.

    Nazwa stacji jest brana z tekstu/bloku (z atrybutem) leżącego wewnątrz obrysu.
    Blok lub punkt wewnątrz obrysu jest traktowany jako lokalizacja samej stacji
    (od niej zaczyna się numeracja w danej strefie).
    """
    msp = doc.modelspace()
    obrysy: list[tuple[int, Polygon]] = []
    opisy: list[tuple[Point, str | None, bool]] = []  # (punkt, tekst, czy_to_stacja)

    for nr, e in enumerate(msp):
        if not _ta_sama_warstwa(e, cfg.warstwa_trafo):
            continue
        typ = e.dxftype()
        if typ in ("LWPOLYLINE", "POLYLINE"):
            pts = _punkty_obiektu(e)
            zamkniety = (e.closed if typ == "LWPOLYLINE" else e.is_closed) or (
                len(pts) > 3 and math.dist(pts[0], pts[-1]) <= cfg.tolerancja
            )
            if zamkniety and len(pts) >= 4:
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                obrysy.append((nr, poly))
        elif typ in ("TEXT", "MTEXT"):
            p = e.dxf.insert
            opisy.append((Point(p.x, p.y), _tekst_obiektu(e), False))
        elif typ in ("INSERT", "POINT", "CIRCLE"):
            p = e.dxf.insert if typ == "INSERT" else (
                e.dxf.location if typ == "POINT" else e.dxf.center)
            tekst = _tekst_obiektu(e) if typ == "INSERT" else None
            opisy.append((Point(p.x, p.y), tekst, True))

    stacje: list[StacjaTrafo] = []
    for i, (nr, poly) in enumerate(obrysy, start=1):
        nazwa, punkt = None, None
        for p, tekst, czy_stacja in opisy:
            if poly.covers(p):
                if tekst and nazwa is None:
                    nazwa = tekst
                if czy_stacja and punkt is None:
                    punkt = p
        stacje.append(StacjaTrafo(
            nazwa=nazwa or f"TRAFO {i}", obrys=poly,
            punkt_stacji=punkt, kolejnosc_rysunku=nr))
    return stacje
