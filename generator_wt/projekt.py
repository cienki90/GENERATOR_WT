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

from . import dxf_writer, export, geocoder, numbering, pismo, reader, slowniki
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
        self.tolerancja_analizy = self.cfg.tolerancja_slupa

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

    # ------------------------------------------------------------ zapis
    def zapisz_dxf(self, wyjscie: Path) -> None:
        dxf_writer.usun_numeracje(self.doc, self.cfg)
        dxf_writer.zapisz_numeracje(self.doc, self.plan, self.slupy, self.cfg)
        self.doc.saveas(str(wyjscie))

    def zapisz_pismo(self, wyjscie: Path, operator: dict | None, data_od: str | None,
                     data_do: str = "-") -> None:
        pismo.generuj_pismo(self.cfg.szablon_pisma, wyjscie, self.plan, operator,
                            data_od, data_do)

    def zapisz_rozbudowana(self, wyjscie: Path) -> None:
        export.zapisz_rozbudowane(self.plan, wyjscie, self.cfg, self.epsg)

    def zapisz_uproszczona(self, wyjscie: Path) -> None:
        export.zapisz_uproszczone(self.plan, wyjscie, self.cfg, self.epsg)
