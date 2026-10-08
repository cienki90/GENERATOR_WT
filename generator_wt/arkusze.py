"""Arkusze rysunkowe (układy papieru) na podstawie szablonu szablony/arkusze_wt.dxf.

- rozmieszczenie arkuszy wzdłuż trasy (N-S, bez obrotu), z zakładką,
  tak by trasa nie wchodziła pod tabelkę/legendę w prawym dolnym rogu,
- tworzenie układów papieru z szablonu: ramka, tabelka, legenda, rzutnia w skali,
- uzupełnianie pól tabelki wg etykiet ("Nr rysunku:", "Skala:", "Nazwa rysunku:",
  "Obiekt:", "INWESTOR", "Opracował:", "Data:") - wartość to tekst pod etykietą,
- wszystkie teksty ustawiane na czcionkę Arial.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import ezdxf
import numpy as np
import shapely
from ezdxf import bbox
from ezdxf.addons import Importer
from ezdxf.document import Drawing
from shapely import affinity
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from .model import Wierzcholek

STYL_ARIAL = "WT_Arial"

# ====================================================================== czcionki


def styl_arial(doc: Drawing, nazwa: str = STYL_ARIAL) -> str:
    """Styl tekstu z czcionką Arial (tworzony, jeśli go nie ma)."""
    if nazwa not in doc.styles:
        doc.styles.add(nazwa, font="arial.ttf")
    else:
        doc.styles.get(nazwa).dxf.font = "arial.ttf"
    return nazwa


def na_arial(tekst: str) -> str:
    """Zamienia kody czcionek MTEXT (\\fLato Light|b1|...;) na Arial, zachowując pogrubienie."""
    def zamien(m):
        b = re.search(r"\|b(\d)", m.group(0))
        return f"\\fArial|b{b.group(1) if b else 0}|i0|c238|p34;"
    return re.sub(r"\\[fF][^;]*;", zamien, tekst)


def ujednolic_teksty(doc: Drawing, encje) -> None:
    styl = styl_arial(doc)
    for e in encje:
        t = e.dxftype()
        if t == "MTEXT":
            e.dxf.style = styl
            e.text = na_arial(e.text)
        elif t in ("TEXT", "ATTRIB", "ATTDEF"):
            e.dxf.style = styl


# ====================================================================== szablon

@dataclass
class SzablonUkladu:
    """Układ papieru z szablonu (np. 'a (2)' albo 'ORIENTACJA')."""
    nazwa: str
    atrybuty_ukladu: dict
    vp_srodek: tuple[float, float]
    vp_rozmiar: tuple[float, float]              # [mm papieru]
    vp_atrybuty: dict
    zakazane: tuple[float, float, float, float]  # tabelka+legenda wzgl. lewego dolnego rogu rzutni
    encje: list = field(default_factory=list)    # encje układu poza rzutniami


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

    # wypełnienia (białe tło tabelki) na spód, żeby nie zasłaniały tekstów
    encje = sorted((e for e in uk if e.dxftype() != "VIEWPORT"),
                   key=lambda e: 0 if e.dxftype() in ("HATCH", "WIPEOUT", "SOLID") else 1)

    # ramka = największa polilinia; tabelka i legenda = wszystko pozostałe
    def pole(e):
        if e.dxftype() != "LWPOLYLINE":
            return 0
        ext = bbox.extents([e])
        return ext.size.x * ext.size.y if ext.has_data else 0
    ramka = max(encje, key=pole, default=None)
    reszta = [e for e in encje if e is not ramka]
    ext = bbox.extents(reszta) if reszta else None
    if ext is not None and ext.has_data:
        zak = (ext.extmin.x - x0, ext.extmin.y - y0, ext.extmax.x - x0, ext.extmax.y - y0)
    else:
        zak = (w, 0, w, 0)
    pomin = {"handle", "owner", "name", "taborder", "block_record_handle", "viewport_handle",
             "extmin", "extmax", "layout_flags"}
    atr = {k: v for k, v in uk.dxf_layout.dxfattribs().items() if k not in pomin}
    vatr = {k: v for k, v in vp.dxfattribs().items()
            if k in ("flags", "status", "circle_zoom", "render_mode", "ucs_icon")}
    return SzablonUkladu(nazwa_ukladu, atr, (cx, cy), (w, h), vatr, zak, encje)


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


def _probkuj(linie, gestosc):
    P, ch, T = [], [], []
    for i, ls in enumerate(linie):
        n = max(2, int(math.ceil(ls.length / gestosc)) + 1)
        for t in np.linspace(0, ls.length, n):
            q = ls.interpolate(t)
            P.append((q.x, q.y))
            ch.append(i)
            T.append(t)
    return np.array(P), np.array(ch), np.array(T)


def _wybierz_ilp(M: np.ndarray, log=None) -> list[int] | None:
    """Minimalna liczba arkuszy (pokrycie zbioru), a wśród takich rozwiązań -
    najmniejsze dublowanie (suma pokrytych punktów). Wymaga scipy (HiGHS)."""
    try:
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import csr_matrix
    except ImportError:
        return None
    A = np.unique(M.T.astype(np.int8), axis=0)
    n = M.shape[0]
    pokrycie = LinearConstraint(csr_matrix(A), lb=1, ub=np.inf)
    opcje = {"time_limit": 60}
    r1 = milp(c=np.ones(n), constraints=[pokrycie], integrality=np.ones(n),
              bounds=Bounds(0, 1), options=opcje)
    if r1.x is None:
        return None
    k = int(round(r1.x.sum()))
    # etap 2: tyle samo arkuszy, jak najmniej wspólnych fragmentów trasy
    liczba = LinearConstraint(np.ones((1, n)), lb=k, ub=k)
    koszt = M.sum(axis=1).astype(float)
    r2 = milp(c=koszt, constraints=[pokrycie, liczba], integrality=np.ones(n),
              bounds=Bounds(0, 1), options=opcje)
    x = r2.x if r2.x is not None else r1.x
    return [int(j) for j in np.nonzero(x > 0.5)[0]]


def _wybierz_zachlannie(M: np.ndarray) -> list[int]:
    pokryte = np.zeros(M.shape[1], bool)
    wybrane: list[int] = []
    while not pokryte.all():
        zysk = (M & ~pokryte).sum(axis=1)
        j = int(np.argmax(zysk))
        if zysk[j] == 0:
            break
        wybrane.append(j)
        pokryte |= M[j]
    zmiana = True
    while zmiana and len(wybrane) > 1:
        zmiana = False
        for j in sorted(wybrane, key=lambda j: M[j].sum()):
            inne = [k for k in wybrane if k != j]
            if M[inne].any(axis=0).all():
                wybrane, zmiana = inne, True
                break
    return wybrane


def rozmiesc(linie: list[LineString], W: float, H: float, zakazane, margines: float,
             zakladka: float, krok: float = 15.0, gestosc: float = 5.0
             ) -> list[tuple[float, float]]:
    """Zwraca lewe dolne narożniki arkuszy (w układzie modelu) pokrywających linie.

    W, H, zakazane, margines, zakladka - w metrach terenu.

    Punkt trasy jest 'pokryty' przez arkusz, gdy leży w obszarze użytkowym (ramka
    pomniejszona o margines, bez rogu z tabelką i legendą) i jest dalej niż
    'zakladka' (wzdłuż trasy) od miejsca, w którym trasa wychodzi z arkusza -
    dzięki temu sąsiednie arkusze mają wspólny odcinek trasy ok. 'zakladka'.

    1. kandydaci na siatce co 'krok',
    2. minimalna liczba arkuszy (programowanie całkowitoliczbowe; bez scipy - zachłannie),
       a spośród takich rozwiązań - najmniejsze dublowanie trasy,
    3. centrowanie: każdy arkusz przesuwany tak, by jego odcinek trasy był
       możliwie na środku obszaru użytkowego,
    4. numeracja arkuszy wzdłuż trasy.
    """
    uzyt = _obszar_uzytkowy(W, H, zakazane, margines)
    shapely.prepare(uzyt)
    sx, sy = uzyt.centroid.x, uzyt.centroid.y
    P, ch, T = _probkuj(linie, gestosc)
    if not len(P):
        return []

    def pokrycie(x0: float, y0: float) -> np.ndarray:
        wew = shapely.contains_xy(uzyt, P[:, 0] - x0, P[:, 1] - y0)
        if not wew.any() or zakladka <= 0:
            return wew
        wyn = wew.copy()
        # wyjścia trasy z arkusza: sąsiednie punkty łańcucha po różnych stronach granicy
        for k in np.nonzero((wew[:-1] != wew[1:]) & (ch[:-1] == ch[1:]))[0]:
            tg = (T[k] + T[k + 1]) / 2
            wyn &= ~((ch == ch[k]) & (np.abs(T - tg) < zakladka))
        return wyn

    # --- 1. kandydaci
    xmin, ymin = P.min(axis=0)
    xmax, ymax = P.max(axis=0)
    XY, kol = [], []
    for x0 in np.arange(xmin - W + margines, xmax - margines + krok, krok):
        for y0 in np.arange(ymin - H + margines, ymax - margines + krok, krok):
            r = pokrycie(x0, y0)
            if r.any():
                XY.append((float(x0), float(y0)))
                kol.append(r)
    M = np.array(kol)
    # punkty, których nie da się pokryć z zakładką (krótkie odcinki przy granicy):
    # dodaj arkusz wyśrodkowany na takim punkcie i nie wymagaj zakładki
    brak = ~M.any(axis=0)
    while brak.any():
        i = int(np.argmax(brak))
        x0, y0 = P[i, 0] - sx, P[i, 1] - sy
        r = shapely.contains_xy(uzyt, P[:, 0] - x0, P[:, 1] - y0)
        r[i] = True
        XY.append((x0, y0))
        M = np.vstack([M, r])
        brak &= ~r

    # --- 2. wybór arkuszy
    wybrane = _wybierz_ilp(M) or _wybierz_zachlannie(M)
    ark = [XY[j] for j in wybrane]
    pk = [M[j] for j in wybrane]

    # --- 3. centrowanie (2 przebiegi)
    for _ in range(2):
        # punkt należy do arkusza, w którym leży najgłębiej (najdalej od krawędzi)
        glebokosc = np.full((len(ark), len(P)), -np.inf)
        for a, ((x0, y0), m) in enumerate(zip(ark, pk)):
            idx = np.nonzero(m)[0]
            if len(idx):
                pts = shapely.points(P[idx, 0] - x0, P[idx, 1] - y0)
                glebokosc[a, idx] = shapely.distance(uzyt.boundary, pts)
        wlasciciel = np.argmax(glebokosc, axis=0)
        for a in range(len(ark)):
            moje = np.nonzero(wlasciciel == a)[0]
            if not len(moje):
                continue
            # środek odcinka trasy tego arkusza -> środek obszaru użytkowego
            cx = (P[moje, 0].min() + P[moje, 0].max()) / 2
            cy = (P[moje, 1].min() + P[moje, 1].max()) / 2
            cel = (cx - sx, cy - sy)
            x0, y0 = ark[a]
            prop = []
            for dx in np.arange(-W / 2, W / 2 + 1e-9, 5.0):
                for dy in np.arange(-H / 2, H / 2 + 1e-9, 5.0):
                    nx, ny = x0 + dx, y0 + dy
                    if shapely.contains_xy(uzyt, P[moje, 0] - nx, P[moje, 1] - ny).all():
                        prop.append((math.hypot(nx - cel[0], ny - cel[1]), nx, ny))
            prop.sort()
            for _, nx, ny in prop[:60]:
                r = pokrycie(nx, ny)
                if r[moje].all():
                    ark[a], pk[a] = (nx, ny), r
                    break

    # --- 4. kolejność wzdłuż trasy
    kolej = sorted(range(len(ark)), key=lambda a: int(np.argmax(pk[a])) if pk[a].any() else 0)
    return [ark[a] for a in kolej]


# ====================================================================== tabelka

def _ustaw_mtext(e, nowy_tekst: str) -> None:
    """Podmienia treść MTEXT, zachowując początkowe kody formatowania."""
    m = re.match(r"^((?:\\[A-Za-z][^;\\{}]*;|\{)*)(.*?)(\}*)$", e.text, re.S)
    nowy = nowy_tekst.replace("\n", "\\P")
    if m and m.group(1):
        poczatek, kon = m.group(1), m.group(3)
        wew = re.match(r"^((?:\\[A-Za-z][^;\\{}]*;)*)", m.group(2))
        poczatek += wew.group(1) if wew else ""
        e.text = poczatek + nowy + kon
    else:
        e.text = nowy


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


def _etykieta(tekst: str) -> str:
    return _bez_formatow(tekst).rstrip(":").strip().lower()


def pole_tabelki(mtexty: list, etykieta: str):
    """MTEXT z wartością pola: najbliższy tekst poniżej etykiety, w tej samej
    kolumnie lub na prawo od niej, który sam nie jest etykietą."""
    lab = next((e for e in mtexty if _etykieta(e.text) == etykieta.lower()), None)
    if lab is None:
        return None
    lx, ly = lab.dxf.insert.x, lab.dxf.insert.y
    kand = [e for e in mtexty if e is not lab and ly - 12 < e.dxf.insert.y < ly - 0.5
            and lx - 1.5 <= e.dxf.insert.x < lx + 14
            and not _bez_formatow(e.text).endswith(":")
            and _etykieta(e.text) not in ("inwestor",)]
    return min(kand, key=lambda e: (ly - e.dxf.insert.y) + 0.5 * abs(e.dxf.insert.x - lx),
               default=None)


def wypelnij_tabelke(encje, wartosci: dict[str, str | None]) -> None:
    """wartosci: etykieta -> nowy tekst (None = bez zmian). Dla 'Obiekt' podaj listę
    miejscowości jako tekst rozdzielony przecinkami, poprzedzony znakiem '§'."""
    mt = [e for e in encje if e.dxftype() == "MTEXT"]
    for etykieta, wartosc in wartosci.items():
        if wartosc is None:
            continue
        e = pole_tabelki(mt, etykieta)
        if e is None:
            continue
        if etykieta.lower() == "obiekt" and wartosc.startswith("§"):
            lista = [x for x in wartosc[1:].split("|") if x]
            _ustaw_mtext(e, tekst_obiektu(e.text, lista))
        else:
            _ustaw_mtext(e, wartosc)


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


def _nowy_uklad(doc: Drawing, nazwa: str, szablon: SzablonUkladu):
    """Układ papieru z ustawieniami strony szablonu i główną rzutnią papieru (id 1)."""
    if nazwa in doc.layouts:
        doc.layouts.delete(nazwa)
    uk = doc.layouts.new(nazwa)
    a = szablon.atrybuty_ukladu
    uk.page_setup(size=(a.get("paper_width", 420.0), a.get("paper_height", 297.0)),
                  margins=(a.get("top_margin", 0), a.get("right_margin", 0),
                           a.get("bottom_margin", 0), a.get("left_margin", 0)),
                  units="mm", rotation=a.get("plot_rotation", 0), scale=(1, 1),
                  name="ISO_full_bleed_A3_(420.00_x_297.00_MM)",
                  device=a.get("plot_configuration_file", "DWG To PDF.pc3"))
    uk.dxf_layout.dxf.paper_size = "ISO_full_bleed_A3_(420.00_x_297.00_MM)"
    for k in ("plot_layout_flags", "plot_type", "standard_scale_type", "current_style_sheet",
              "plot_origin_x_offset", "plot_origin_y_offset", "limmin", "limmax"):
        if k in a:
            try:
                uk.dxf_layout.dxf.set(k, a[k])
            except (ezdxf.DXFAttributeError, ezdxf.DXFValueError):
                pass
    return uk


def dodaj_uklady(doc: Drawing, szablon_doc: Drawing, szablon: SzablonUkladu,
                 arkusze: list[Arkusz], mianownik: int, nazwa_rysunku: str | None,
                 inwestor: str | None, opracowal: str | None, data: str | None,
                 dodatkowe_teksty: list[str] | None = None,
                 zamrozone: list[str] | None = None) -> None:
    """Tworzy układy papieru (po jednym na arkusz) na wzór układu szablonu."""
    imp = Importer(szablon_doc, doc)
    nowe = []
    for ark in arkusze:
        uk = _nowy_uklad(doc, ark.nazwa, szablon)
        imp.import_entities(szablon.encje, uk)
        nowe.append((uk, ark))
    imp.finalize()

    w, h = szablon.vp_rozmiar
    x0p, y0p = szablon.vp_srodek[0] - w / 2, szablon.vp_srodek[1] - h / 2
    styl = styl_arial(doc)
    bloki = set()
    for uk, ark in nowe:
        encje = [e for e in uk if e.dxftype() != "VIEWPORT"]
        wypelnij_tabelke(encje, {
            "Nr rysunku": ark.nazwa,
            "Skala": opis_skali(mianownik),
            "Nazwa rysunku": nazwa_rysunku,
            "Obiekt": "§" + "|".join(ark.miejscowosci),
            "INWESTOR": inwestor,
            "Opracował": opracowal,
            "Data": data,
        })
        ujednolic_teksty(doc, encje)
        bloki |= {e.dxf.name for e in encje if e.dxftype() == "INSERT"}
        vp = uk.add_viewport(center=szablon.vp_srodek, size=(w, h),
                             view_center_point=(ark.x0 + ark.szer / 2, ark.y0 + ark.wys / 2),
                             view_height=ark.wys)
        for k, v in szablon.vp_atrybuty.items():
            vp.dxf.set(k, v)
        if zamrozone:
            vp.frozen_layers = zamrozone
        for i, t in enumerate(dodatkowe_teksty or []):
            uk.add_mtext(t, dxfattribs={"char_height": 1.8, "style": styl, "layer": "0",
                                        "insert": (x0p + 3, y0p + 3 + i * 3)})
    for b in bloki:  # legenda itp.
        blk = doc.blocks.get(b)
        if blk is not None:
            ujednolic_teksty(doc, blk)


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
    styl = styl_arial(doc)
    for a in arkusze:
        msp.add_lwpolyline([(a.x0, a.y0), (a.x0 + a.szer, a.y0), (a.x0 + a.szer, a.y0 + a.wys),
                            (a.x0, a.y0 + a.wys)], close=True, dxfattribs={"layer": warstwa})
        t = msp.add_mtext(a.nazwa, dxfattribs={"layer": warstwa, "char_height": wys_tekstu,
                                                "style": styl})
        t.set_location((a.x0 + a.szer / 2, a.y0 + a.wys / 2),
                       attachment_point=ezdxf.enums.MTextEntityAlignment.MIDDLE_CENTER)


def obwiednia(arkusze: list[Arkusz]):
    return unary_union([a.prostokat for a in arkusze]).bounds
