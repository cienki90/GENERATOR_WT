"""Logika okna webowego: stan projektu jako JSON i operacje wywoływane z interfejsu.

Bez Qt i bez HTTP - serwer (serwer.py) tylko przekazuje wywołania metod z listy
METODY. Długie prace (analiza, arkusze, generowanie) idą w osobnym wątku; postęp,
wpisy dziennika i zakończenie trafiają do kolejki zdarzeń, którą interfejs odpytuje
metodą zdarzenia(od).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import traceback
from datetime import date
from pathlib import Path

from .. import slowniki, stan
from ..config import KATALOG, Config
from ..pismo import adres_slupa
from ..projekt import Projekt

# metody dostępne z interfejsu (wszystko inne jest niedostępne przez serwer)
METODY = {
    "start", "zdarzenia", "dane", "ustawienia_projektu_dla", "analizuj", "przelicz",
    "przelicz_arkusze", "ustaw_pole", "przelacz_wykluczenie", "przyjmij_ulice",
    "podsumowanie_generowania", "generuj", "wybierz_plik", "wybierz_katalog",
    "otworz_folder", "edytuj_listy", "odswiez_slowniki", "operator_po_nip",
    "zapisz_operatora", "zapisz_ustawienia_okna",
}

POLA_EDYTOWALNE = set(stan.POLA_RECZNE)
MAKS_ZDARZEN = 2000


class BladApi(Exception):
    """Błąd zgłaszany użytkownikowi (bez śladu wywołań)."""


class Api:
    def __init__(self, cfg: Config | None = None, plik_ustawien: Path | None = None,
                 dialogi=None):
        self.cfg = cfg or Config()
        self.plik_ustawien = plik_ustawien or KATALOG / "dane" / "ustawienia_okna.json"
        self.dialogi = dialogi  # okno.py: natywne okna wyboru plików; None = przeglądarka
        self.projekt: Projekt | None = None
        self.operatorzy: list[dict] = []
        self.rejony: list[dict] = []
        self._zdarzenia: list[dict] = []
        self._nr_zdarzenia = 0
        self._blokada_zdarzen = threading.Lock()
        self._blokada_pracy = threading.Lock()
        self._praca: str | None = None
        self._ostatnia_analiza: str | None = None
        self._rejon_domyslny: str | None = None
        self.odswiez_slowniki()

    # ================================================================ zdarzenia i praca w tle
    def _zdarzenie(self, typ: str, **dane) -> None:
        with self._blokada_zdarzen:
            self._nr_zdarzenia += 1
            self._zdarzenia.append({"nr": self._nr_zdarzenia, "typ": typ, **dane})
            del self._zdarzenia[:-MAKS_ZDARZEN]

    def log(self, tekst: str) -> None:
        self._zdarzenie("log", tekst=str(tekst))

    def zdarzenia(self, od: int = 0) -> dict:
        with self._blokada_zdarzen:
            nowe = [z for z in self._zdarzenia if z["nr"] > od]
        return {"zdarzenia": nowe, "praca": self._praca}

    def zajety(self) -> bool:
        return self._praca is not None

    def _wolny(self) -> None:
        if self.zajety():
            raise BladApi("Program jeszcze pracuje – poczekaj na zakończenie.")

    def _uruchom(self, nazwa: str, praca) -> dict:
        """praca(postep) w osobnym wątku; postep(i, n, opis). Na końcu zdarzenie 'koniec'."""
        with self._blokada_pracy:
            self._wolny()
            self._praca = nazwa

        def postep(i, n, opis):
            self._zdarzenie("postep", i=i, n=n, opis=opis)

        def watek():
            try:
                wynik = praca(postep)
                self._praca = None
                self._zdarzenie("koniec", zadanie=nazwa, ok=True, wynik=wynik)
            except Exception as e:  # noqa: BLE001 - komunikat dla użytkownika
                self.log(traceback.format_exc())
                self._praca = None
                self._zdarzenie("koniec", zadanie=nazwa, ok=False, blad=str(e))

        threading.Thread(target=watek, name=f"wt-{nazwa}", daemon=True).start()
        return {"praca": nazwa}

    def czekaj(self, limit: float = 600) -> None:
        """Dla testów i wiersza poleceń: czeka na koniec bieżącej pracy."""
        import time
        t0 = time.time()
        while self.zajety():
            if time.time() - t0 > limit:
                raise TimeoutError("praca w tle nie zakończyła się")
            time.sleep(0.05)

    # ================================================================ ustawienia okna
    def _ustawienia_okna(self) -> dict:
        try:
            return json.loads(self.plik_ustawien.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def zapisz_ustawienia_okna(self, ustawienia: dict) -> dict:
        u = {**self._ustawienia_okna(), **(ustawienia or {})}
        try:
            stan.zapisz(self.plik_ustawien, u)
        except OSError as e:
            self.log(f"Nie można zapisać ustawień okna: {e}")
        return u

    # ================================================================ słowniki
    def odswiez_slowniki(self) -> dict:
        plik = self.cfg.plik_slownikow
        if not plik.exists():
            slowniki.utworz_szablon(plik)
            self.log(f"Utworzono plik list: {plik}")
        try:
            self.operatorzy = slowniki.wczytaj_liste(plik, slowniki.ARKUSZ_OPERATORZY)
            self.rejony = slowniki.wczytaj_liste(plik, slowniki.ARKUSZ_REJONY)
        except Exception as e:  # noqa: BLE001
            raise BladApi(f"Nie można wczytać {plik.name}: {e}. Zamknij plik w Excelu "
                          "i kliknij Odśwież.") from e
        return self._slowniki()

    def _slowniki(self) -> dict:
        return {"operatorzy": [o.get("Nazwa", "") for o in self.operatorzy],
                "rejony": [r.get("Nazwa", "") for r in self.rejony]}

    def _operator(self, nazwa: str | None) -> dict | None:
        return next((o for o in self.operatorzy if o.get("Nazwa") == nazwa),
                    self.operatorzy[0] if self.operatorzy else None)

    def _rejon(self, nazwa: str | None) -> dict | None:
        """Rejon o tej nazwie (pierwszy z listy, gdy brak). Zapamiętywany jako domyślny
        dla gmin spoza listy, np. przy ręcznej zmianie gminy w wykazie."""
        if nazwa:
            self._rejon_domyslny = nazwa
        nazwa = nazwa or self._rejon_domyslny
        return next((r for r in self.rejony if r.get("Nazwa") == nazwa),
                    self.rejony[0] if self.rejony else None)

    def edytuj_listy(self) -> None:
        _otworz(self.cfg.plik_slownikow)

    def operator_po_nip(self, nip: str, klucz_gus: str = "") -> dict:
        from .. import rejestry
        self.zapisz_ustawienia_okna({"klucz_gus": klucz_gus or ""})
        try:
            w = rejestry.operator_po_nip(nip, klucz_gus or None)
        except rejestry.BladRejestru as e:
            raise BladApi(str(e)) from e
        info = list(w.pop("_info", []))
        stary = next((o for o in self.operatorzy if _cyfry(o.get("NIP")) == w["NIP"]), None)
        rozne = {}
        if stary:
            nowy = dict(stary)
            for k in ("Pełna nazwa", "Adres (siedziba)", "Kod pocztowy", "Regon",
                      "Numer wpisu do RPT", "NIP"):
                if w.get(k):
                    if stary.get(k, "") != w[k]:
                        rozne[k] = stary.get(k, "")
                    nowy[k] = w[k]
            info.insert(0, f"Operator '{stary.get('Nazwa')}' jest już na liście – zapis "
                           "zaktualizuje dane z rejestrów.")
            w = nowy
        return {"wpis": {k: w.get(k, "") for k in slowniki.KOLUMNY_OPERATORA},
                "info": info, "bylo": rozne}

    def zapisz_operatora(self, wpis: dict) -> dict:
        from .. import rejestry
        wpis = {k: str(v or "").strip() for k, v in (wpis or {}).items()}
        if not wpis.get("Nazwa") or not wpis.get("NIP"):
            raise BladApi("Uzupełnij co najmniej nazwę i NIP.")
        try:
            wpis["NIP"] = rejestry.oczysc_nip(wpis["NIP"])
        except rejestry.BladRejestru as e:
            raise BladApi(str(e)) from e
        try:
            wynik = slowniki.zapisz_operatora(self.cfg.plik_slownikow, wpis)
        except PermissionError as e:
            raise BladApi("Plik list jest otwarty w Excelu – zamknij go i spróbuj "
                          "ponownie.") from e
        self.log(f"Operator {wpis['Nazwa']}: {wynik} w {self.cfg.plik_slownikow.name}")
        self.zapisz_ustawienia_okna({"operator": wpis["Nazwa"]})
        return {**self.odswiez_slowniki(), "operator": wpis["Nazwa"]}

    # ================================================================ start i pliki
    def start(self) -> dict:
        u = self._ustawienia_okna()
        with self._blokada_zdarzen:
            nr = self._nr_zdarzenia
            dziennik = [z["tekst"] for z in self._zdarzenia if z["typ"] == "log"][-300:]
        ostatni = u.get("ostatni_plik", "")
        return {"slowniki": self._slowniki(), "ustawienia": u,
                "ostatni_plik": ostatni if ostatni and Path(ostatni).exists() else "",
                "dialogi": self.dialogi is not None, "dzis": date.today().strftime("%d.%m.%Y"),
                "nr_zdarzenia": nr, "dziennik": dziennik,
                "miesiac": date.today().strftime("%m.%Y"), "praca": self._praca,
                "projekt": self.dane() if self.projekt and not self.zajety() else None,
                "domyslne": {"tolerancja_slupa": self.cfg.tolerancja_slupa,
                             "zakladka": self.cfg.zakladka}}

    def wybierz_plik(self, start: str = "") -> dict:
        if self.dialogi is None:
            return {"plik": None, "brak_dialogu": True}
        return {"plik": self.dialogi.wybierz_plik(start or "")}

    def wybierz_katalog(self, start: str = "") -> dict:
        if self.dialogi is None:
            return {"katalog": None, "brak_dialogu": True}
        return {"katalog": self.dialogi.wybierz_katalog(start or "")}

    def otworz_folder(self, katalog: str = "") -> None:
        k = Path(katalog) if katalog else (self.projekt.plik.parent if self.projekt else None)
        if k is None or not k.exists():
            raise BladApi("Folder nie istnieje.")
        _otworz(k)

    def ustawienia_projektu_dla(self, plik: str) -> dict:
        """Ustawienia zapamiętane w <projekt>.wt.json (przed analizą nowego pliku)."""
        return stan.wczytaj(stan.plik_stanu(plik)).get("ustawienia") or {}

    # ================================================================ analiza i numeracja
    def _konfiguracja(self, u: dict | None) -> None:
        u = u or {}
        c = self.cfg
        c.prefiks = str(u.get("prefiks", c.prefiks) or "").strip()
        c.numer_startowy = int(u.get("numer_startowy", c.numer_startowy))
        c.tolerancja_slupa = float(u.get("tolerancja_slupa", c.tolerancja_slupa))
        c.zakladka = float(u.get("zakladka", c.zakladka))
        c.inteligentny_kierunek = bool(u.get("inteligentny_kierunek", c.inteligentny_kierunek))

    def analizuj(self, plik: str, geokodowanie: bool = True, ustawienia: dict | None = None
                 ) -> dict:
        plik = str(plik or "").strip().strip('"')
        if not plik:
            raise BladApi("Wybierz plik DXF projektu.")
        if not Path(plik).is_file():
            raise BladApi(f"Nie ma pliku: {plik}")
        self._konfiguracja(ustawienia)
        rejon = (ustawienia or {}).get("rejon")
        projekt = Projekt(self.cfg)
        self.zapisz_ustawienia_okna({"ostatni_plik": plik})
        self.log(f"Analiza: {plik}")

        def praca(postep):
            postep(0, 0, "Odczyt pliku DXF…")
            projekt.wczytaj(plik)
            bledy = 0
            if geokodowanie:
                bledy = projekt.geokoduj(
                    lambda i, n: postep(i, n, f"Pobieranie adresów z GUGiK: {i}/{n}"))
                postep(0, 0, "Sprawdzanie ulic (drogi OpenStreetMap)…")
                try:
                    projekt.sprawdz_ulice(log=lambda t: None)
                except Exception as e:  # noqa: BLE001
                    projekt.ostrzezenia.append(f"Sprawdzanie ulic pominięte: {e}")
            projekt.zastosuj_stan()
            projekt.planuj()
            postep(0, 0, "Rozmieszczanie arkuszy…")
            projekt.planuj_arkusze()
            bez = projekt.przypisz_rejony(self.rejony, self._rejon(rejon))
            self.projekt = projekt
            self._ostatnia_analiza = plik
            if bez:
                self.log("Gminy bez rejonu w liście (użyto rejonu domyślnego): " + ", ".join(bez))
            if projekt.poprawek_zastosowanych:
                self.log(f"Zastosowano zapamiętane poprawki ({projekt.plik_stanu.name}): "
                         f"{projekt.poprawek_zastosowanych} słupów")
            self.log(f"Analiza zakończona: {len(projekt.slupy)} słupów, "
                     f"{len(projekt.bledne_kliki)} błędnych klików, "
                     f"{len(projekt.ostrzezenia)} ostrzeżeń.")
            return {"bledy_geokodowania": bledy}

        return self._uruchom("analiza", praca)

    def _p(self) -> Projekt:
        if self.projekt is None:
            raise BladApi("Najpierw wczytaj i przeanalizuj projekt DXF.")
        return self.projekt

    def _zapisz_stan(self, ustawienia: dict | None = None) -> None:
        p = self._p()
        if ustawienia is not None:
            p.zapisz_ustawienia(ustawienia)
        if p.blad_stanu:
            self.log("UWAGA: " + p.blad_stanu)

    def przelicz(self, ustawienia: dict) -> dict:
        """Prefiks, numer startowy, kierunek odnośnika, rejon - bez ponownej analizy."""
        self._wolny()
        p = self._p()
        self._konfiguracja({k: v for k, v in (ustawienia or {}).items()
                            if k != "tolerancja_slupa"})
        p.planuj()
        p.odswiez_miejscowosci_arkuszy()
        p.przypisz_rejony(self.rejony, self._rejon((ustawienia or {}).get("rejon")))
        self._zapisz_stan(ustawienia)
        return self.dane()

    def przelicz_arkusze(self, ustawienia: dict) -> dict:
        p = self._p()
        self._konfiguracja({k: v for k, v in (ustawienia or {}).items()
                            if k != "tolerancja_slupa"})

        def praca(postep):
            postep(0, 0, "Rozmieszczanie arkuszy…")
            n = len(p.planuj_arkusze())
            self._zapisz_stan(ustawienia)
            self.log(f"Arkuszy 1:{self.cfg.skala_arkuszy}: {n} (zakładka {self.cfg.zakladka:g} m)")
            return {"arkuszy": n}
        return self._uruchom("arkusze", praca)

    def ustaw_pole(self, id: int, atr: str, wartosc) -> dict:
        self._wolny()
        p = self._p()
        if atr not in POLA_EDYTOWALNE:
            raise BladApi(f"Pola '{atr}' nie można zmieniać.")
        w = self._slup(id)
        tekst = str(wartosc or "").strip()
        p.ustaw_pole(w, atr, tekst if atr == "uwagi" else (tekst or None))
        if atr == "gmina":
            p.przypisz_rejony(self.rejony, self._rejon(self._rejon_domyslny))
        if atr == "miejscowosc":
            p.planuj()  # grupowanie wg miejscowości mogło się zmienić
            p.odswiez_miejscowosci_arkuszy()
        self._zapisz_stan()
        return self.dane()

    def przelacz_wykluczenie(self, id: int) -> dict:
        self._wolny()
        p = self._p()
        w = self._slup(id)
        p.ustaw_wykluczenie(w, not w.wykluczony)
        p.planuj()
        p.odswiez_miejscowosci_arkuszy()
        self._zapisz_stan()
        wykl = sum(1 for s in p.slupy if s.wykluczony)
        self.log(f"Słup {'wyłączony z' if w.wykluczony else 'włączony do'} numeracji. "
                 f"Numeracja: {len(p.plan)} słupów" + (f" · wyłączonych: {wykl}" if wykl else ""))
        return self.dane()

    def przyjmij_ulice(self) -> dict:
        self._wolny()
        p = self._p()
        n = p.przyjmij_ulice_z_drog()
        self.log(f"Poprawiono ulice: {n} słupów")
        self._zapisz_stan()
        return self.dane()

    def _slup(self, id):
        p = self._p()
        try:
            return p.slupy[int(id)]
        except (IndexError, ValueError, TypeError) as e:
            raise BladApi(f"Nie ma słupa {id}.") from e

    # ================================================================ dane dla interfejsu
    def dane(self) -> dict:
        self._wolny()
        p = self._p()
        from pyproj import CRS, Transformer
        crs = CRS.from_epsg(p.epsg) if p.epsg else None
        zakres = None
        if crs is not None and crs.area_of_use:
            a = crs.area_of_use
            t = Transformer.from_crs(4326, p.epsg, always_xy=True)
            zakres = list(t.transform_bounds(a.west, a.south, a.east, a.north))
        kolej = [w.id for w in p.slupy_trasa()]
        slupy = [_slup_json(w) for w in p.slupy]
        krawedzie = sorted({(min(w.id, n), max(w.id, n)) for w in p.slupy for n in w.sasiedzi})
        from .. import arkusze as ark
        sz = ark.wczytaj_szablon(p.szablon_doc(), self.cfg.uklad_trasy)
        k = self.cfg.skala_arkuszy / 1000
        proj4 = None
        if crs is not None:
            import warnings
            with warnings.catch_warnings():  # PL-2000/1992: zapis PROJ nie gubi niczego istotnego
                warnings.simplefilter("ignore", UserWarning)
                proj4 = crs.to_proj4()
        return {
            "plik": str(p.plik), "nazwa": p.plik.name, "epsg": p.epsg,
            "proj4": proj4, "zakres_ukladu": zakres,
            "slupy": slupy, "kolejnosc": kolej, "krawedzie": [list(e) for e in krawedzie],
            "arkusze": [{"nazwa": a.nazwa, "x0": a.x0, "y0": a.y0, "szer": a.szer,
                         "wys": a.wys, "miejscowosci": a.miejscowosci} for a in p.arkusze],
            "zakazane": [v * k for v in sz.zakazane],
            "stacje": [{"nazwa": s.nazwa, "obrysy": _obrysy(s.obrys)} for s in p.stacje],
            "podsumowanie": {
                "slupy": len(p.slupy), "plan": len(p.plan), "stacje": len(p.stacje),
                "bledne_kliki": len(p.bledne_kliki), "arkusze": len(p.arkusze),
                "wykluczone": sum(1 for w in p.slupy if w.wykluczony),
                "skala": self.cfg.skala_arkuszy, "zakladka": self.cfg.zakladka,
                "tolerancja_analizy": p.tolerancja_analizy},
            "kontrola": kontrola(p, self.cfg),
            "plik_stanu": p.plik_stanu.name,
        }

    # ================================================================ generowanie
    def _katalog(self, katalog: str | None) -> Path:
        return Path(katalog) if katalog else self._p().plik.parent

    def podsumowanie_generowania(self, opcje: dict) -> dict:
        self._wolny()
        p = self._p()
        o = opcje or {}
        if abs(float(o.get("tolerancja_slupa", p.tolerancja_analizy)) - p.tolerancja_analizy) > 1e-9:
            return {"ponowna_analiza": True}
        p.planuj()
        kat = self._katalog(o.get("katalog"))
        wsp = bool(o.get("pismo") or o.get("rozbudowana") or o.get("uproszczona"))
        return {"plan": p.opis_planu(), "istniejaca": p.istniejaca_numeracja(),
                "warstwa": self.cfg.warstwa_numeracji, "bledne_kliki": len(p.bledne_kliki),
                "arkusze": len(p.arkusze) if o.get("dxf") and o.get("arkusze") else 0,
                "katalog": str(kat), "pytaj_o_uklad": wsp, "projektowa": bool(o.get("projektowa"))}

    def generuj(self, opcje: dict) -> dict:
        p = self._p()
        o = dict(opcje or {})
        kat = self._katalog(o.get("katalog"))
        operator = self._operator(o.get("operator"))
        opracowal = (o.get("opracowal") or "").strip() or None
        data_rys = (o.get("data_rysunku") or "").strip() or None
        p.cfg.wgs84 = bool(o.get("wgs84"))
        p.przypisz_rejony(self.rejony, self._rejon(o.get("rejon")))
        self.zapisz_ustawienia_okna({k: o.get(k) for k in (
            "opracowal", "operator", "rejon", "wyniki") if k in o})
        if o.get("ustawienia"):
            p.zapisz_ustawienia(o["ustawienia"])

        zadania = []
        if o.get("dxf"):
            arkusze = bool(o.get("arkusze"))
            zadania.append(("numeracja.dxf", lambda f, log, post: p.zapisz_dxf(
                f, arkusze, operator, opracowal, data_rys)))
            if arkusze and o.get("pdf_numeracji"):
                zadania.append(("numeracja.pdf",
                                lambda f, log, post: p.zapisz_numeracje_pdf(f, log)))
        if o.get("pismo"):
            od, do = o.get("umowa_od") or None, (o.get("umowa_do") or "-").strip() or "-"
            zadania.append(("pismo.docx", lambda f, log, post: p.zapisz_pismo(
                f, operator, od, do)))
        if o.get("rozbudowana"):
            zadania.append(("rozbudowana.xlsx", lambda f, log, post: p.zapisz_rozbudowana(f)))
        if o.get("uproszczona"):
            zadania.append(("uproszczona.xls", lambda f, log, post: p.zapisz_uproszczona(f)))
        if o.get("projektowa"):
            zadania.append(("tabela_projektowa.xlsx",
                            lambda f, log, post: p.zapisz_projektowa(f)))
        if o.get("orientacja"):
            orient = o.get("orientacja_opcje") or {}

            def zapisz_orient(f, log, post):
                ark = p.zapisz_orientacje(
                    f, int(orient.get("skala", 10000)), bool(orient.get("szarosc")), operator,
                    opracowal, data_rys, orient.get("zrodlo", "osm"),
                    bool(orient.get("trasa", True)),
                    lambda i, n: post(i, n, f"Pobieranie podkładu: {i}/{n}"), log)
                log(f"Plan orientacyjny: arkusze {', '.join(a.nazwa for a in ark)}")
                if orient.get("pdf"):
                    cel = p.sciezka(kat, "orientacja.pdf")
                    post(0, 0, "Plan orientacyjny: PDF…")
                    p.zapisz_orientacje_pdf(cel, log)
                    log(f"Zapisano: {cel}")
            zadania.append(("orientacja.dxf", zapisz_orient))
        if not zadania:
            raise BladApi("Zaznacz co najmniej jeden plik do zapisania.")

        def praca(postep):
            kat.mkdir(parents=True, exist_ok=True)
            p.planuj()
            zapisane, bledy = [], []
            for nr, (przyr, f) in enumerate(zadania, start=1):
                cel = p.sciezka(kat, przyr)
                postep(nr - 1, len(zadania), f"Zapis {cel.name} ({nr}/{len(zadania)})…")
                try:
                    f(cel, self.log, postep)
                    zapisane.append(cel.name)
                    self.log(f"Zapisano: {cel}")
                except PermissionError:
                    bledy.append(f"{cel.name}: plik jest otwarty w innym programie.")
                except Exception as e:  # noqa: BLE001
                    bledy.append(f"{cel.name}: {e}")
                    self.log(traceback.format_exc())
            return {"zapisane": zapisane, "bledy": bledy, "katalog": str(kat)}

        self.log("Współrzędne w zestawieniach: " + ("WGS 84" if p.cfg.wgs84 else "PL-2000"))
        return self._uruchom("generuj", praca)


# ==================================================================== pomocnicze

def _cyfry(t) -> str:
    return "".join(c for c in str(t or "") if c.isdigit())


def _otworz(sciezka: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(sciezka))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(sciezka)])
    else:
        subprocess.Popen(["xdg-open", str(sciezka)])


def _slup_json(w) -> dict:
    return {"id": w.id, "x": w.x, "y": w.y, "nr": w.nr, "etykieta": w.etykieta,
            "wykluczony": w.wykluczony, "stacja": w.stacja_trafo, "id_slupa": w.id_slupa,
            "nr_w_sieci": w.nr_w_sieci, "miejscowosc": w.miejscowosc, "ulica": w.ulica,
            "ulica_droga": w.ulica_droga, "ulica_zgodna": w.ulica_zgodna, "gmina": w.gmina,
            "rejon": w.rejon_skrot, "rodzaj_slupa": w.rodzaj_slupa, "typ_slupa": w.typ_slupa,
            "dzialka": w.dzialka, "uwagi": w.uwagi, "geo_x": round(w.geo_x, 2),
            "geo_y": round(w.geo_y, 2), "adres": adres_slupa(w)}


def _obrysy(geom) -> list:
    """Zewnętrzne pierścienie wielokąta / wielokątów jako listy [x, y]."""
    czesci = getattr(geom, "geoms", [geom])
    return [[list(map(float, xy)) for xy in g.exterior.coords] for g in czesci
            if hasattr(g, "exterior")]


def _poz(tytul, szczegoly="", slupy=(), poziom="info", odcinek=None) -> dict:
    d = {"tytul": tytul, "szczegoly": szczegoly, "slupy": list(slupy), "poziom": poziom}
    if odcinek:
        d["odcinek"] = odcinek
    return d


def kontrola(p: Projekt, cfg: Config) -> list[dict]:
    """Sekcje 'Do sprawdzenia' (jak zakładka Kontrola projektu w starym oknie).
    poziom: ok / info / ostrz / blad; pozycje ze 'slupy' przybliżają mapę do słupów."""
    sekcje = []
    nr = {w.id: (w.etykieta or "(wył.)") for w in p.slupy}

    dlugie = p.przesla()
    bledne = [x for x in dlugie if x[0] > cfg.przeslo_blad]
    sekcje.append({
        "id": "przesla", "tytul": f"Przęsła > {cfg.przeslo_ostrzezenie:g} m",
        "opis": f"{len(dlugie)}, w tym {len(bledne)} > {cfg.przeslo_blad:g} m",
        "poziom": "blad" if bledne else "ostrz" if dlugie else "ok",
        "pozycje": [_poz(f"Słupy {nr[a.id]} – {nr[b.id]}", f"{d:.2f} m", [a.id, b.id],
                         "blad" if d > cfg.przeslo_blad else "ostrz", [a.id, b.id])
                    for d, a, b in dlugie]})

    nz = p.niezgodne_ulice()
    if p.ulice_sprawdzone:
        spr = sum(1 for w in p.plan if w.ulica_zgodna is not None)
        opis = f"niezgodnych {len(nz)} · sprawdzono {spr} z {len(p.plan)}"
    else:
        opis = "nie wykonano (włącz pobieranie adresów)"
    sekcje.append({"id": "ulice", "tytul": f"Ulice a drogi OSM (do {cfg.odl_ulicy:g} m)",
                   "opis": opis, "poziom": "ostrz" if nz else "ok" if p.ulice_sprawdzone
                   else "info",
                   "pozycje": [_poz(f"Słup {w.etykieta}", f"adres: {w.ulica or '–'} → droga: "
                                    f"{w.ulica_droga}", [w.id], "ostrz") for w in nz]})

    pozycje = {(round(w.x, 3), round(w.y, 3)): w for w in p.slupy}
    bk = []
    for b in p.bledne_kliki:
        w = pozycje.get((round(b.x, 3), round(b.y, 3)))
        bk.append(_poz(f"Słup {w.etykieta if w else '?'}",
                       f"{b.liczba} wierzchołki, rozrzut {b.max_odleglosc:.2f} m",
                       [w.id] if w else [], "ostrz"))
    sekcje.append({"id": "kliki", "tytul": f"Błędne kliki (< {cfg.tolerancja_slupa:g} m)",
                   "opis": f"{len(p.bledne_kliki)} – scalone w jeden słup",
                   "poziom": "ostrz" if bk else "ok", "pozycje": bk})

    bez_nr = [w for w in p.plan if not w.nr_w_sieci]
    sekcje.append({"id": "numery", "tytul": "Numery słupów w sieci",
                   "opis": f"przypisano {p.numerow_w_sieci}, bez numeru {len(bez_nr)}",
                   "poziom": "ostrz" if bez_nr else "ok",
                   "pozycje": [_poz(f"Słup {w.etykieta}", w.stacja_trafo or "poza strefą",
                                    [w.id], "ostrz") for w in bez_nr]})

    bez_opisu = [w for w in p.plan if not w.rodzaj_slupa]
    sekcje.append({"id": "opisy", "tytul": "Słupy bez opisu rodzaju/typu",
                   "opis": f"{len(bez_opisu)} (opisano {p.opisanych_slupow})",
                   "poziom": "info" if bez_opisu else "ok",
                   "pozycje": [_poz(f"Słup {w.etykieta}", f"X={w.geo_x:.2f} Y={w.geo_y:.2f}",
                                    [w.id]) for w in bez_opisu]})

    wykl = [w for w in p.slupy if w.wykluczony]
    sekcje.append({"id": "wykluczone", "tytul": "Wyłączone z numeracji",
                   "opis": f"{len(wykl)} (nie trafią do pisma ani zestawień)",
                   "poziom": "info" if wykl else "ok",
                   "pozycje": [_poz(w.stacja_trafo or "poza strefą",
                                    f"nr w sieci {w.nr_w_sieci}" if w.nr_w_sieci
                                    else f"X={w.geo_x:.2f} Y={w.geo_y:.2f}", [w.id])
                               for w in wykl]})

    poprawki = [k for k, v in p.stan["slupy"].items() if any(a != "wykluczony" for a in v)]
    sekcje.append({"id": "poprawki", "tytul": "Ręczne poprawki",
                   "opis": f"{len(poprawki)} słupów · {p.plik_stanu.name}", "poziom": "info"
                   if p.poprawek_niedopasowanych else "ok",
                   "pozycje": [_poz("Nie pasują do rysunku",
                                    f"{len(p.poprawek_niedopasowanych)} (słup usunięty lub "
                                    "przesunięty > 0,5 m)", [], "ostrz")]
                   if p.poprawek_niedopasowanych else []})

    if p.ostrzezenia:
        sekcje.append({"id": "ostrzezenia", "tytul": "Ostrzeżenia",
                       "opis": str(len(p.ostrzezenia)), "poziom": "ostrz",
                       "pozycje": [_poz(t, "", [], "ostrz") for t in p.ostrzezenia]})

    plan = []
    for g in p.grupy:
        if not g.wierzcholki:
            continue
        pierwszy = min(g.wierzcholki, key=lambda w: w.nr)
        ostatni = max(g.wierzcholki, key=lambda w: w.nr)
        plan.append(_poz(g.nazwa, f"{'strefa trafo' if g.stacja else 'miejscowość'} · "
                                  f"{len(g.wierzcholki)} słupów · "
                                  f"{pierwszy.etykieta}–{ostatni.etykieta}",
                         [w.id for w in g.wierzcholki]))
    sekcje.append({"id": "plan", "tytul": "Plan numeracji", "opis": f"{len(p.plan)} słupów",
                   "poziom": "ok", "pozycje": plan})
    return sekcje
