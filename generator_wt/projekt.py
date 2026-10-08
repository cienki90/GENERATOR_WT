"""Wspólna logika programu (używana przez GUI i wiersz poleceń).

Kolejność pracy:
    p = Projekt(cfg)
    p.wczytaj("projekt.dxf")        # słupy, błędne kliki, strefy trafo, opisy słupów
    p.geokoduj(postep)              # miejscowość/ulica/gmina z GUGiK
    p.planuj()                      # grupy i numery (bez zapisu)
    p.przypisz_rejony(rejony, domyslny)
    p.zapisz_dxf(...), p.zapisz_pismo(...), p.zapisz_rozbudowana(...), p.zapisz_uproszczona(...)
"""
from __future__ import annotations

import math
from pathlib import Path

from ezdxf.document import Drawing

import string

import ezdxf
from shapely.geometry import LineString

from . import arkusze as ark
from . import dxf_writer, export, geocoder, numbering, pismo, podklad, reader, slowniki
from .config import Config
from .model import BlednyKlik, StacjaTrafo, Wierzcholek


class Projekt:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.plik: Path | None = None
        self.doc: Drawing | None = None
        self.slupy: list[Wierzcholek] = []
        self.bledne_kliki: list[BlednyKlik] = []
        self.stacje: list[StacjaTrafo] = []
        self.ostrzezenia: list[str] = []
        self.grupy: list[numbering.Grupa] = []
        self.plan: list[Wierzcholek] = []
        self.epsg: int | None = None
        self.opisanych_slupow = 0
        self.numerow_w_sieci = 0
        self.tolerancja_analizy = self.cfg.tolerancja_slupa
        self.arkusze: list[ark.Arkusz] = []
        self._szablon_doc = None

    # ------------------------------------------------------------ analiza
    def wczytaj(self, plik: str | Path) -> None:
        self.plik = Path(plik)
        self.tolerancja_analizy = self.cfg.tolerancja_slupa
        self.doc = reader.wczytaj_dxf(str(self.plik))
        self.slupy, self.bledne_kliki = reader.wczytaj_slupy(self.doc, self.cfg)
        if not self.slupy:
            raise ValueError(f"Brak polilinii na warstwie '{self.cfg.warstwa_tele}'.")
        self.stacje, self.ostrzezenia = reader.wczytaj_stacje_trafo(self.doc, self.cfg)
        self.opisanych_slupow = reader.przypisz_opisy_slupow(self.doc, self.slupy, self.cfg)
        self.numerow_w_sieci, o = reader.przypisz_numery_slupow(self.doc, self.slupy, self.cfg)
        self.ostrzezenia += o
        try:
            self.epsg = geocoder.wykryj_epsg(self.slupy[0].x)
        except ValueError as e:
            self.epsg = None
            self.ostrzezenia.append(str(e))

    def geokoduj(self, postep=None) -> int:
        if self.epsg is None:
            return len(self.slupy)
        g = geocoder.Geokoder(self.epsg, self.cfg.promien_adresu,
                              plik_cache=self.cfg.plik_slownikow.parent / "cache_geokodowania.json")
        return geocoder.uzupelnij(self.slupy, g, postep=postep)

    def planuj(self) -> None:
        self.grupy = numbering.utworz_grupy(self.slupy, self.stacje, self.cfg)
        reader.ustaw_id_slupow(self.slupy)
        self.plan = numbering.zaplanuj_numeracje(self.slupy, self.grupy, self.cfg)

    def przypisz_rejony(self, rejony: list[dict], domyslny: dict | None) -> list[str]:
        """Rejon wg gminy ze słownika; gminy nieprzypisane -> rejon domyślny.
        Zwraca listę gmin, które dostały rejon domyślny."""
        bez = set()
        for w in self.slupy:
            r = slowniki.rejon_dla_gminy(rejony, w.gmina)
            if r is None:
                bez.add(w.gmina or "(brak gminy)")
                r = domyslny
            w.rejon = r.get("Nazwa") if r else None
            w.rejon_skrot = slowniki.nazwa_skrocona(r)
        return sorted(bez)

    # ------------------------------------------------------------ podsumowania
    def opis_planu(self) -> list[str]:
        p = self.cfg.prefiks
        wynik = []
        for g in self.grupy:
            nry = sorted(w.nr for w in g.wierzcholki)
            rodzaj = "strefa trafo" if g.stacja else "miejscowość"
            wynik.append(f"{g.nazwa} [{rodzaj}]: {len(nry)} słupów, {p}{nry[0]}–{p}{nry[-1]}")
        return wynik

    def przesla(self, prog: float | None = None) -> list[tuple[float, Wierzcholek, Wierzcholek]]:
        """Odległości między połączonymi linią słupami, dłuższe niż próg (malejąco)."""
        prog = self.cfg.przeslo_ostrzezenie if prog is None else prog
        wynik = []
        for a in self.slupy:
            for i in a.sasiedzi:
                b = self.slupy[i]
                if a.id < b.id:
                    d = math.hypot(a.x - b.x, a.y - b.y)
                    if d > prog:
                        para = sorted((a, b), key=lambda w: w.nr or 0)
                        wynik.append((d, para[0], para[1]))
        return sorted(wynik, key=lambda t: -t[0])

    def istniejaca_numeracja(self) -> int:
        return dxf_writer.istniejaca_numeracja(self.doc, self.cfg) if self.doc else 0

    def sciezka(self, katalog: Path, przyrostek: str) -> Path:
        return Path(katalog) / f"{self.plik.stem}_{przyrostek}"

    # ------------------------------------------------------------ arkusze
    def szablon_doc(self):
        if self._szablon_doc is None:
            self._szablon_doc = ezdxf.readfile(str(self.cfg.szablon_arkuszy))
        return self._szablon_doc

    def planuj_arkusze(self) -> list[ark.Arkusz]:
        """Rozmieszcza arkusze trasy (skala cfg.skala_arkuszy) wzdłuż linii."""
        sz = ark.wczytaj_szablon(self.szablon_doc(), self.cfg.uklad_trasy)
        k = self.cfg.skala_arkuszy / 1000  # m terenu na mm papieru
        W, H = sz.vp_rozmiar[0] * k, sz.vp_rozmiar[1] * k
        zak = tuple(v * k for v in sz.zakazane)
        linie = ark.lancuchy_trasy(self.slupy)
        polozenia = ark.rozmiesc(linie, W, H, zak, self.cfg.margines_mm * k, self.cfg.zakladka)
        self.arkusze = []
        for i, (x0, y0) in enumerate(polozenia, start=1):
            a = ark.Arkusz(str(i), x0, y0, W, H)
            a.miejscowosci = ark.miejscowosci_na_arkuszu(a, self.slupy)
            self.arkusze.append(a)
        return self.arkusze

    @staticmethod
    def tekst_inwestora(operator: dict | None) -> str | None:
        if not operator:
            return None
        adres = ", ".join(x for x in (operator.get("Adres (siedziba)"),
                                      operator.get("Kod pocztowy")) if x)
        return "\n".join(x for x in (operator.get("Pełna nazwa") or operator.get("Nazwa"),
                                     adres) if x)

    # ------------------------------------------------------------ zapis
    def zapisz_dxf(self, wyjscie: Path, arkusze: bool = False, operator: dict | None = None,
                   opracowal: str | None = None, data: str | None = None) -> None:
        dxf_writer.usun_numeracje(self.doc, self.cfg)
        dxf_writer.zapisz_numeracje(self.doc, self.plan, self.slupy, self.cfg)
        if arkusze:
            if not self.arkusze:
                self.planuj_arkusze()
            ark.usun_arkusze(self.doc, [n for n in self.doc.layouts.names() if n.isdigit()])
            sz = ark.wczytaj_szablon(self.szablon_doc(), self.cfg.uklad_trasy)
            ark.dodaj_uklady(self.doc, self.szablon_doc(), sz, self.arkusze,
                             self.cfg.skala_arkuszy, None, self.tekst_inwestora(operator),
                             opracowal, data, zamrozone=[self.cfg.warstwa_obrysow],
                             wysokosc_branzy=self.cfg.wysokosc_branzy)
            ark.rysuj_obrysy(self.doc, self.arkusze, self.cfg.warstwa_obrysow,
                             drukowalna=False, wys_tekstu=20.0)
        self.doc.saveas(str(wyjscie))

    def zapisz_orientacje(self, wyjscie: Path, mianownik: int, szarosc: bool,
                          operator: dict | None, opracowal: str | None, data: str | None,
                          zrodlo: str = "osm", trasa: bool = True, postep=None,
                          log=print) -> list[ark.Arkusz]:
        """Oddzielny plik DXF z planem orientacyjnym: podkład, obrysy arkuszy z numerami,
        (opcjonalnie) trasa i układy papieru 0.A, 0.B, ... w skali 1:mianownik (A3)."""
        if not self.arkusze:
            self.planuj_arkusze()
        szd = self.szablon_doc()
        sz = ark.wczytaj_szablon(szd, self.cfg.uklad_orientacji)
        k = mianownik / 1000
        W, H = sz.vp_rozmiar[0] * k, sz.vp_rozmiar[1] * k
        zak = tuple(v * k for v in sz.zakazane)
        # krawędzie obrysów jako osobne odcinki (zamknięty pierścień ma t_początku == t_końca)
        linie = [LineString([c[i], c[i + 1]]) for a in self.arkusze
                 for c in [list(a.prostokat.exterior.coords)] for i in range(4)]
        linie += ark.lancuchy_trasy(self.slupy)
        polozenia = ark.rozmiesc(linie, W, H, zak, self.cfg.margines_orientacji_mm * k,
                                 zakladka=0.0, krok=max(20.0, W / 80), gestosc=max(5.0, k))
        litery = string.ascii_uppercase
        orient = []
        for i, (x0, y0) in enumerate(polozenia):
            nazwa = "0." + (litery[i] if i < 26 else litery[i // 26 - 1] + litery[i % 26])
            a = ark.Arkusz(nazwa, x0, y0, W, H)
            a.miejscowosci = ark.miejscowosci_na_arkuszu(a, self.slupy)
            orient.append(a)

        doc = ezdxf.new(szd.dxfversion, setup=True)
        doc.header["$INSUNITS"] = 6
        msp = doc.modelspace()

        xmin, ymin, xmax, ymax = ark.obwiednia(orient)
        plik_jpg = Path(wyjscie).with_suffix(".jpg")
        pk = podklad.pobierz((xmin, ymin, xmax, ymax), self.epsg, mianownik, plik_jpg,
                             szarosc, zrodlo, self.cfg.katalog_kafli, postep, log)
        doc.layers.add(self.cfg.warstwa_podkladu, color=7)
        idef = doc.add_image_def(filename=plik_jpg.name, size_in_pixel=pk.piks)
        msp.add_image(idef, insert=(pk.x0, pk.y0), size_in_units=(pk.szer_m, pk.wys_m),
                      dxfattribs={"layer": self.cfg.warstwa_podkladu})
        doc.set_raster_variables(frame=0, quality=1, units="m")

        if trasa:
            doc.layers.add(self.cfg.warstwa_trasy_orientacji, color=1)
            for ls in ark.lancuchy_trasy(self.slupy):
                msp.add_lwpolyline(list(ls.coords), dxfattribs={
                    "layer": self.cfg.warstwa_trasy_orientacji, "lineweight": 50})
        ark.rysuj_obrysy(doc, self.arkusze, self.cfg.warstwa_obrysow, drukowalna=True,
                         wys_tekstu=4.0 * k, kolor=5)
        for e in msp.query(f'LWPOLYLINE[layer=="{self.cfg.warstwa_obrysow}"]'):
            e.dxf.lineweight = 35

        domyslne = [n for n in doc.layouts.names() if n != "Model"]
        ark.dodaj_uklady(doc, szd, sz, orient, mianownik, self.cfg.nazwa_orientacji,
                         self.tekst_inwestora(operator), opracowal, data,
                         dodatkowe_teksty=[podklad.ATRYBUCJA[pk.zrodlo]],
                         wysokosc_branzy=self.cfg.wysokosc_branzy)
        for n in domyslne:  # pusty układ 'Layout1' tworzony przez ezdxf
            doc.layouts.delete(n)
        doc.saveas(str(wyjscie))
        return orient

    def zapisz_pismo(self, wyjscie: Path, operator: dict | None, data_od: str | None,
                     data_do: str = "-") -> None:
        pismo.generuj_pismo(self.cfg.szablon_pisma, wyjscie, self.plan, operator,
                            data_od, data_do)

    def zapisz_rozbudowana(self, wyjscie: Path) -> None:
        export.zapisz_rozbudowane(self.plan, wyjscie, self.cfg, self.epsg)

    def zapisz_uproszczona(self, wyjscie: Path) -> None:
        export.zapisz_uproszczone(self.plan, wyjscie, self.cfg, self.epsg)
