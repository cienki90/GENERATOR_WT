"""Arkusze rysunkowe (układy papieru) na podstawie szablonu 'arkusze do wt.dxf'.

- rozmieszczenie arkuszy wzdłuż trasy (N-S, bez obrotu), z zakładką,
  tak by trasa nie wchodziła pod tabelkę/legendę w prawym dolnym rogu,
- tworzenie układów papieru z szablonu: ramka, tabelka, legenda, rzutnia w skali,
- uzupełnianie tabelki: inwestor (operator), opracował, data, nr rysunku, skala,
  nazwa rysunku, obiekt (miejscowości widoczne na arkuszu).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import ezdxf
import numpy as np
import shapely
from shapely import affinity
from ezdxf import bbox
from ezdxf.addons import Importer
from ezdxf.document import Drawing
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from .model import Wierzcholek

# ====================================================================== szablon

ROLE = ("nr", "skala", "nazwa", "obiekt")


@dataclass
class SzablonUkladu:
    """Układ papieru z szablonu (np. 'a (2)' albo 'ORIENTACJA')."""
    nazwa: str
    atrybuty_ukladu: dict
    vp_srodek: tuple[float, float]
    vp_rozmiar: tuple[float, float]           # [mm papieru]
    vp_atrybuty: dict
    zakazane: tuple[float, float, float, float]  # róg tabelki/legendy wzgl. lewego dolnego rogu rzutni [mm]
    encje: list = field(default_factory=list)  # encje układu poza rzutniami
    role: dict = field(default_factory=dict)   # rola -> (x, y) położenia MTEXT


def _rola_tekstu(tekst: str) -> str | None:
    t = _bez_formatow(tekst)
    if re.fullmatch(r"\d+(\.\w+)?", t):
        return "nr"
    if re.fullmatch(r"1\s*:\s*[\d\s]+", t):
        return "skala"
    if "miejscowo" in t.lower() or t.lower().startswith("projektowane"):
        return "obiekt"
    return "nazwa"


def _bez_formatow(t: str) -> str:
    t = re.sub(r"\\[A-Za-z][^;\\{}]*;", "", t)
    t = t.replace("\\P", "\n").replace("{", "").replace("}", "")
    return t.strip()


def wczytaj_szablon(doc: Drawing, nazwa_ukladu: str) -> SzablonUkladu:
    uk = doc.layouts.get(nazwa_ukladu)
    vps = [e for e in uk if e.dxftype() == "VIEWPORT" and e.dxf.id != 1]
    if not vps:
        raise ValueError(f"Układ '{nazwa_ukladu}' szablonu nie ma rzutni modelu.")
    vp = max(vps, key=lambda v: v.dxf.width * v.dxf.height)
    cx, cy = vp.dxf.center.x, vp.dxf.center.y
    w, h = vp.dxf.width, vp.dxf.height
    x0, y0 = cx - w / 2, cy - h / 2

    encje = [e for e in uk if e.dxftype() != "VIEWPORT"]
    wstawienia = [e for e in encje if e.dxftype() == "INSERT"]
    if wstawienia:
        ext = bbox.extents(wstawienia)
        zak = (ext.extmin.x - x0, ext.extmin.y - y0, ext.extmax.x - x0, ext.extmax.y - y0)
    else:
        zak = (w, 0, w, 0)
    role = {}
    for e in encje:
        if e.dxftype() == "MTEXT":
            r = _rola_tekstu(e.text)
            role.setdefault(r, (e.dxf.insert.x, e.dxf.insert.y))
    pomin = {"handle", "owner", "name", "taborder", "block_record_handle", "viewport_handle",
             "extmin", "extmax", "layout_flags"}
    atr = {k: v for k, v in uk.dxf_layout.dxfattribs().items() if k not in pomin}
    vatr = {k: v for k, v in vp.dxfattribs().items()
            if k in ("flags", "status", "circle_zoom", "render_mode", "ucs_icon")}
    return SzablonUkladu(nazwa_ukladu, atr, (cx, cy), (w, h), vatr, zak, encje, role)


# ====================================================================== rozmieszczanie

def lancuchy_trasy(slupy: list[Wierzcholek]) -> list[LineString]:
    """Trasa jako ciągi słupów między rozgałęzieniami/końcami, w kolejności numeracji."""
    stopien = {w.id: len(w.sasiedzi) for w in slupy}
    uzyte: set[tuple[int, int]] = set()
    wynik: list[tuple[int, LineString]] = []
    for w in sorted(slupy, key=lambda s: s.nr or 0):
        for n in sorted(w.sasiedzi, key=lambda i: slupy[i].nr or 0):
            if (w.id, n) in uzyte:
                continue
            droga = [w.id, n]
            uzyte |= {(w.id, n), (n, w.id)}
            while stopien[droga[-1]] == 2:
                nast = [x for x in slupy[droga[-1]].sasiedzi if (droga[-1], x) not in uzyte]
                if not nast:
                    break
                uzyte |= {(droga[-1], nast[0]), (nast[0], droga[-1])}
                droga.append(nast[0])
            if (slupy[droga[0]].nr or 0) > (slupy[droga[-1]].nr or 0):
                droga.reverse()
            wynik.append((min(slupy[i].nr or 0 for i in droga),
                          LineString([(slupy[i].x, slupy[i].y) for i in droga])))
    return [ls for _, ls in sorted(wynik, key=lambda t: t[0])]


def _obszar_uzytkowy(W, H, zakazane, margines):
    zx0, zy0, zx1, zy1 = zakazane
    pole = box(margines, margines, W - margines, H - margines)
    rog = box(zx0 - margines, -1, W + 1, zy1 + margines)
    return pole.difference(rog)


def rozmiesc(linie: list[LineString], W: float, H: float, zakazane, margines: float,
             zakladka: float, krok: float = 15.0, gestosc: float = 2.0
             ) -> list[tuple[float, float]]:
    """Zwraca lewe dolne narożniki arkuszy (w układzie modelu) pokrywających linie.

    W, H, zakazane, margines, zakladka - w metrach terenu.
    Punkt trasy jest 'pokryty' przez arkusz, gdy leży w obszarze użytkowym (ramka
    pomniejszona o margines, bez rogu z tabelką i legendą) i jest dalej niż
    'zakladka' (wzdłuż trasy) od miejsca, w którym trasa wychodzi z arkusza.
    Dzięki temu sąsiednie arkusze nachodzą na siebie o co najmniej 'zakladka'.

    Metoda: kandydaci na siatce co 'krok' -> zachłanne pokrycie zbioru ->
    usunięcie arkuszy zbędnych -> numeracja wzdłuż trasy.
    """
    uzyt = _obszar_uzytkowy(W, H, zakazane, margines)
    shapely.prepare(uzyt)

    pts, nr_linii, t_linii = [], [], []
    for i, ls in enumerate(linie):
        n = max(2, int(math.ceil(ls.length / gestosc)) + 1)
        for t in np.linspace(0, ls.length, n):
            p = ls.interpolate(t)
            pts.append((p.x, p.y))
            nr_linii.append(i)
            t_linii.append(t)
    if not pts:
        return []
    P = np.array(pts)
    nr_linii = np.array(nr_linii)
    t_linii = np.array(t_linii)
    zakresy = {}
    for i in range(len(linie)):
        idx = np.nonzero(nr_linii == i)[0]
        zakresy[i] = (idx[0], idx[-1] + 1)

    def pokrycie(x0: float, y0: float) -> np.ndarray:
        obszar = affinity.translate(uzyt, x0, y0)
        granica = obszar.boundary
        wyn = np.zeros(len(P), bool)
        ramka = box(x0, y0, x0 + W, y0 + H)
        for i, ls in enumerate(linie):
            if not ls.intersects(ramka):
                continue
            czesc = ls.intersection(obszar)
            if czesc.is_empty:
                continue
            i0, i1 = zakresy[i]
            t = t_linii[i0:i1]
            for k in getattr(czesc, "geoms", [czesc]):
                if k.geom_type != "LineString" or k.length == 0:
                    continue
                a, b = ls.project(Point(k.coords[0])), ls.project(Point(k.coords[-1]))
                if a > b:
                    a, b = b, a
                if a > 0.01 and granica.distance(ls.interpolate(a)) < 0.5:
                    a += zakladka
                if b < ls.length - 0.01 and granica.distance(ls.interpolate(b)) < 0.5:
                    b -= zakladka
                if b >= a:
                    wyn[i0:i1] |= (t >= a - 1e-6) & (t <= b + 1e-6)
        return wyn

    # --- kandydaci na siatce (tylko te, które zawierają jakąś część trasy)
    xmin, ymin = P.min(axis=0)
    xmax, ymax = P.max(axis=0)
    kand_xy, kand_pk = [], []
    for x0 in np.arange(xmin - W + margines, xmax - margines + krok, krok):
        for y0 in np.arange(ymin - H + margines, ymax - margines + krok, krok):
            w_ramce = ((P[:, 0] > x0) & (P[:, 0] < x0 + W) & (P[:, 1] > y0) & (P[:, 1] < y0 + H))
            if not w_ramce.any():
                continue
            pk = pokrycie(x0, y0)
            if pk.any():
                kand_xy.append((x0, y0))
                kand_pk.append(pk)
    if not kand_pk:
        return []
    M = np.array(kand_pk)

    # --- zachłanne pokrycie zbioru
    pokryte = np.zeros(len(P), bool)
    wybrane: list[int] = []
    while not pokryte.all():
        zysk = (M & ~pokryte).sum(axis=1)
        j = int(np.argmax(zysk))
        if zysk[j] == 0:  # punkty niemożliwe do pokrycia z zakładką - bierz arkusz z punktem
            s = int(np.argmax(~pokryte))
            sx, sy = P[s]
            x0, y0 = sx - W / 2, sy - H / 2
            kand_xy.append((x0, y0))
            pk = shapely.contains_xy(affinity.translate(uzyt, x0, y0), P[:, 0], P[:, 1])
            pk[s] = True
            M = np.vstack([M, pk])
            j = len(kand_xy) - 1
        wybrane.append(j)
        pokryte |= M[j]

    # --- usunięcie arkuszy zbędnych (od najmniej wnoszących)
    zmiana = True
    while zmiana and len(wybrane) > 1:
        zmiana = False
        for j in sorted(wybrane, key=lambda j: M[j].sum()):
            inne = [k for k in wybrane if k != j]
            if M[inne].any(axis=0).all():
                wybrane = inne
                zmiana = True
                break

    # --- kolejność wzdłuż trasy (wg pierwszego pokrytego punktu)
    wybrane.sort(key=lambda j: int(np.argmax(M[j])))
    return [kand_xy[j] for j in wybrane]


# ====================================================================== tabelka

def _ustaw_mtext(e, nowy_tekst: str) -> None:
    """Podmienia treść MTEXT, zachowując początkowe kody formatowania."""
    stary = e.text
    m = re.match(r"^((?:\\[A-Za-z][^;\\{}]*;|\{)*)(.*?)(\}*)$", stary, re.S)
    if m and m.group(1):
        poczatek, kon = m.group(1), m.group(3)
        # zachowaj formaty znajdujące się wewnątrz klamry, np. {\fLato...;\C256;tekst}
        wew = re.match(r"^((?:\\[A-Za-z][^;\\{}]*;)*)", m.group(2))
        poczatek += wew.group(1) if wew else ""
        e.text = poczatek + nowy_tekst + kon
    else:
        e.text = nowy_tekst


def tekst_obiektu(szablon: str, miejscowosci: list[str]) -> str:
    """'...w miejscowości Huta Kuflewska' -> lista miejscowości z arkusza."""
    plain = _bez_formatow(szablon)
    if not miejscowosci:
        return re.sub(r"\s+w\s+miejscowo\w+.*$", "", plain)
    lacznik = "w miejscowości" if len(miejscowosci) == 1 else "w miejscowościach"
    lista = ", ".join(miejscowosci)
    if re.search(r"w\s+miejscowo\w+", plain):
        return re.sub(r"w\s+miejscowo\w+.*$", f"{lacznik} {lista}", plain)
    return f"{plain} {lacznik} {lista}"


def uzupelnij_tabelke(doc: Drawing, nazwa_bloku: str, inwestor: str | None,
                      opracowal: str | None, data: str | None) -> None:
    """Pola w bloku tabelki: tekst pod etykietą INWESTOR / Opracował: / Data:."""
    blk = doc.blocks.get(nazwa_bloku)
    if blk is None:
        return
    mt = [e for e in blk if e.dxftype() == "MTEXT"]

    def pod(etykieta: str):
        lab = next((e for e in mt if _bez_formatow(e.text).rstrip(":").strip().lower()
                    == etykieta.lower()), None)
        if lab is None:
            return None
        lx, ly = lab.dxf.insert.x, lab.dxf.insert.y
        # wartość = najbliższy tekst poniżej etykiety, który sam nie jest etykietą
        kand = [e for e in mt if e is not lab and e.dxf.insert.y < ly - 0.5
                and ly - e.dxf.insert.y < 12 and abs(e.dxf.insert.x - lx) < 12
                and not _bez_formatow(e.text).endswith(":")]
        return min(kand, key=lambda e: (ly - e.dxf.insert.y) + abs(e.dxf.insert.x - lx),
                   default=None)

    for etykieta, wartosc in (("INWESTOR", inwestor), ("Opracował", opracowal),
                              ("Data", data)):
        if wartosc:
            e = pod(etykieta)
            if e is not None:
                _ustaw_mtext(e, wartosc.replace("\n", "\\P"))


# ====================================================================== tworzenie układów

@dataclass
class Arkusz:
    nazwa: str           # nazwa układu i numer rysunku, np. "1" albo "0.A"
    x0: float
    y0: float
    szer: float          # [m terenu]
    wys: float
    miejscowosci: list[str] = field(default_factory=list)

    @property
    def prostokat(self):
        return box(self.x0, self.y0, self.x0 + self.szer, self.y0 + self.wys)


def miejscowosci_na_arkuszu(ark: Arkusz, slupy: list[Wierzcholek]) -> list[str]:
    p = ark.prostokat
    wynik = []
    for w in sorted(slupy, key=lambda s: s.nr or 0):
        if w.miejscowosc and w.miejscowosc not in wynik and p.covers(Point(w.x, w.y)):
            wynik.append(w.miejscowosc)
    return wynik


def opis_skali(mianownik: int) -> str:
    return f"1:{mianownik:,}".replace(",", " ") if mianownik >= 10000 else f"1:{mianownik}"


def usun_arkusze(doc: Drawing, nazwy) -> None:
    for n in list(doc.layouts.names()):
        if n in nazwy:
            doc.layouts.delete(n)


def dodaj_uklady(doc: Drawing, szablon_doc: Drawing, szablon: SzablonUkladu,
                 arkusze: list[Arkusz], mianownik: int, nazwa_rysunku: str | None,
                 inwestor: str | None, opracowal: str | None, data: str | None,
                 dodatkowe_teksty: list[str] | None = None,
                 zamrozone: list[str] | None = None) -> None:
    """Tworzy układy papieru (po jednym na arkusz) na wzór układu szablonu."""
    imp = Importer(szablon_doc, doc)
    nowe = []
    for ark in arkusze:
        if ark.nazwa in doc.layouts:
            doc.layouts.delete(ark.nazwa)
        uk = doc.layouts.new(ark.nazwa)
        for k, v in szablon.atrybuty_ukladu.items():
            try:
                uk.dxf_layout.dxf.set(k, v)
            except (ezdxf.DXFAttributeError, ezdxf.DXFValueError):
                pass
        imp.import_entities(szablon.encje, uk)
        nowe.append((uk, ark))
    imp.finalize()

    bloki = {e.dxf.name for uk, _ in nowe for e in uk if e.dxftype() == "INSERT"}
    for b in bloki:
        if any(_bez_formatow(e.text).upper().startswith("INWESTOR")
               for e in doc.blocks.get(b) if e.dxftype() == "MTEXT"):
            uzupelnij_tabelke(doc, b, inwestor, opracowal, data)

    w, h = szablon.vp_rozmiar
    for uk, ark in nowe:
        for e in uk:
            if e.dxftype() != "MTEXT":
                continue
            rola = _rola_tekstu(e.text)
            if rola == "nr":
                _ustaw_mtext(e, ark.nazwa)
            elif rola == "skala":
                _ustaw_mtext(e, opis_skali(mianownik))
            elif rola == "nazwa" and nazwa_rysunku:
                _ustaw_mtext(e, nazwa_rysunku)
            elif rola == "obiekt":
                _ustaw_mtext(e, tekst_obiektu(e.text, ark.miejscowosci))
        vp = uk.add_viewport(center=szablon.vp_srodek, size=(w, h),
                             view_center_point=(ark.x0 + ark.szer / 2, ark.y0 + ark.wys / 2),
                             view_height=ark.wys)
        for k, v in szablon.vp_atrybuty.items():
            vp.dxf.set(k, v)
        if zamrozone:
            vp.frozen_layers = zamrozone
        for i, t in enumerate(dodatkowe_teksty or []):
            x0 = szablon.vp_srodek[0] - w / 2
            y0 = szablon.vp_srodek[1] - h / 2
            uk.add_mtext(t, dxfattribs={"char_height": 1.8, "insert": (x0 + 3, y0 + 3 + i * 3),
                                        "layer": "0"})


def rysuj_obrysy(doc: Drawing, arkusze: list[Arkusz], warstwa: str, drukowalna: bool,
                 wys_tekstu: float, kolor: int = 1) -> None:
    if warstwa not in doc.layers:
        lay = doc.layers.add(warstwa, color=kolor)
    else:
        lay = doc.layers.get(warstwa)
    lay.dxf.plot = 1 if drukowalna else 0
    msp = doc.modelspace()
    for e in list(msp.query(f'*[layer=="{warstwa}"]i')):
        msp.delete_entity(e)
    for a in arkusze:
        msp.add_lwpolyline([(a.x0, a.y0), (a.x0 + a.szer, a.y0), (a.x0 + a.szer, a.y0 + a.wys),
                            (a.x0, a.y0 + a.wys)], close=True, dxfattribs={"layer": warstwa})
        t = msp.add_mtext(a.nazwa, dxfattribs={"layer": warstwa, "char_height": wys_tekstu})
        t.set_location((a.x0 + a.szer / 2, a.y0 + a.wys / 2),
                       attachment_point=ezdxf.enums.MTextEntityAlignment.MIDDLE_CENTER)


def obwiednia(arkusze: list[Arkusz]):
    return unary_union([a.prostokat for a in arkusze]).bounds
