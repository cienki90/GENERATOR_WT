"""Numeracja wierzchołków !tele z zachowaniem kolejności w obrębie stref trafo."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import Point

from .config import Config
from .model import StacjaTrafo, Wierzcholek


@dataclass
class Grupa:
    nazwa: str
    stacja: StacjaTrafo | None
    wierzcholki: list[Wierzcholek] = field(default_factory=list)


def przypisz_do_grup(wierzcholki: list[Wierzcholek], stacje: list[StacjaTrafo],
                     cfg: Config) -> list[Grupa]:
    """Każdy wierzchołek trafia do strefy trafo, w której leży.

    Jeśli strefy się nakładają - wygrywa najmniejsza (najbardziej szczegółowa).
    Wierzchołki poza strefami trafiają do grupy 'poza strefą'
    (w kolejnym etapie zostaną rozbite wg miejscowości).
    """
    stacje_wg_pola = sorted(stacje, key=lambda s: s.obrys.area)
    grupy = {s.nazwa: Grupa(s.nazwa, s) for s in
             sorted(stacje, key=lambda s: s.kolejnosc_rysunku)}
    poza = Grupa(cfg.grupa_poza_strefa, None)

    for w in wierzcholki:
        p = Point(w.x, w.y)
        stacja = next((s for s in stacje_wg_pola if s.obrys.covers(p)), None)
        if stacja:
            w.stacja_trafo = stacja.nazwa
            w.grupa = stacja.nazwa
            grupy[stacja.nazwa].wierzcholki.append(w)
        else:
            w.grupa = poza.nazwa
            poza.wierzcholki.append(w)

    wynik = [g for g in grupy.values() if g.wierzcholki]
    if poza.wierzcholki:
        wynik.append(poza)
    return wynik


def _kolejnosc_w_grupie(grupa: Grupa, wszystkie: list[Wierzcholek]) -> list[Wierzcholek]:
    """Ustala kolejność przejścia po trasie w obrębie grupy.

    Idziemy wzdłuż linii (przeszukiwanie w głąb po grafie połączeń), zaczynając
    od wierzchołka najbliższego stacji trafo; gdy jej brak - od końca linii,
    który pojawił się w rysunku najwcześniej. Odgałęzienia numerowane są
    po kolei, w kolejności rysowania.
    """
    w_grupie = {w.id for w in grupa.wierzcholki}
    odwiedzone: set[int] = set()
    kolejnosc: list[Wierzcholek] = []
    start_ref = grupa.stacja.punkt_stacji if grupa.stacja else None

    def klucz_startu(w: Wierzcholek):
        stopien = len(w.sasiedzi & w_grupie)
        if start_ref is not None:
            return (0, math.hypot(w.x - start_ref.x, w.y - start_ref.y))
        # najpierw końce linii (stopień <= 1), potem kolejność rysunku
        return (0 if stopien <= 1 else 1, w.kolejnosc_rysunku)

    while len(odwiedzone) < len(w_grupie):
        pozostale = [w for w in grupa.wierzcholki if w.id not in odwiedzone]
        start = min(pozostale, key=klucz_startu)
        stos = [start.id]
        while stos:
            idx = stos.pop()
            if idx in odwiedzone:
                continue
            odwiedzone.add(idx)
            kolejnosc.append(wszystkie[idx])
            nastepne = sorted(
                (n for n in wszystkie[idx].sasiedzi if n in w_grupie and n not in odwiedzone),
                key=lambda n: wszystkie[n].kolejnosc_rysunku, reverse=True)
            stos.extend(nastepne)
    return kolejnosc


def zaplanuj_numeracje(wierzcholki: list[Wierzcholek], grupy: list[Grupa],
                       cfg: Config, ciagla: bool = True) -> list[Wierzcholek]:
    """Nadaje numery (bez zapisu do DXF). Zwraca wierzchołki w kolejności numerów.

    ciagla=True  -> 1..N przez wszystkie strefy,
    ciagla=False -> numeracja od nowa w każdej strefie.
    """
    wynik: list[Wierzcholek] = []
    nr = cfg.numer_startowy
    for g in grupy:
        if not ciagla:
            nr = cfg.numer_startowy
        for w in _kolejnosc_w_grupie(g, wierzcholki):
            w.nr = nr
            w.etykieta = f"{cfg.prefiks}{nr}"
            wynik.append(w)
            nr += 1
    return wynik
