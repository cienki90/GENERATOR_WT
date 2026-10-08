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
    return []  # bloki, punkty itp. są pomijane - słupy to wierzchołki linii


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


def wczytaj_stacje_trafo(doc: Drawing, cfg: Config) -> list[StacjaTrafo]:
    """Zamknięte polilinie na warstwie !trafo = zasięgi stacji.

    Nazwa stacji = tekst (TEXT/MTEXT) z warstwy !trafo leżący wewnątrz obrysu.
    Bez tekstu strefa dostaje nazwę 'TRAFO n'.
    """
    msp = doc.modelspace()
    obrysy: list[tuple[int, Polygon]] = []
    opisy: list[tuple[Point, str]] = []

    for nr, e in enumerate(msp):
        if not _ta_sama_warstwa(e, cfg.warstwa_trafo):
            continue
        typ = e.dxftype()
        if typ in ("LWPOLYLINE", "POLYLINE"):
            pts = _punkty_obiektu(e)
            zamkniety = (e.closed if typ == "LWPOLYLINE" else e.is_closed) or (
                len(pts) > 3 and math.dist(pts[0], pts[-1]) <= cfg.tolerancja)
            if zamkniety and len(pts) >= 4:
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                obrysy.append((nr, poly))
        elif typ == "TEXT" and e.dxf.text.strip():
            opisy.append((Point(e.dxf.insert.x, e.dxf.insert.y), e.dxf.text.strip()))
        elif typ == "MTEXT" and e.plain_text().strip():
            opisy.append((Point(e.dxf.insert.x, e.dxf.insert.y), e.plain_text().strip()))

    stacje: list[StacjaTrafo] = []
    uzyte: set[str] = set()
    for i, (nr, poly) in enumerate(obrysy, start=1):
        nazwa = next((t for p, t in opisy if poly.covers(p)), None) or f"TRAFO {i}"
        if nazwa in uzyte:
            nazwa = f"{nazwa} ({i})"
        uzyte.add(nazwa)
        stacje.append(StacjaTrafo(nazwa=nazwa, obrys=poly, kolejnosc_rysunku=nr))
    return stacje
