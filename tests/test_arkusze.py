"""Arkusze 1:1000: zgodność ze wzorcem, pokrycie trasy, funkcje pomocnicze."""
import json

import numpy as np
import pytest
from shapely.geometry import Point

from generator_wt import arkusze as ark
from tests.conftest import WZORZEC, nowy_projekt


def _porownaj(arkusze, oczekiwane):
    assert len(arkusze) == len(oczekiwane)
    for a, (nazwa, x0, y0) in zip(arkusze, oczekiwane):
        assert a.nazwa == nazwa
        assert a.x0 == pytest.approx(x0, abs=0.011) and a.y0 == pytest.approx(y0, abs=0.011)


def test_arkusze_zgodne_ze_wzorcem(projekt_z_arkuszami):
    wzorzec = json.loads(WZORZEC.read_text(encoding="utf-8"))
    _porownaj(projekt_z_arkuszami.arkusze, wzorzec["arkusze"]["10"])


@pytest.mark.parametrize("zakladka", ["0", "25"])
def test_arkusze_inna_zakladka(dxf, zakladka):
    wzorzec = json.loads(WZORZEC.read_text(encoding="utf-8"))
    p = nowy_projekt(dxf, zakladka=float(zakladka))
    _porownaj(p.planuj_arkusze(), wzorzec["arkusze"][zakladka])


def test_kazdy_slup_na_arkuszu(projekt_z_arkuszami):
    p = projekt_z_arkuszami
    for w in p.slupy:
        assert any(a.prostokat.covers(Point(w.x, w.y)) for a in p.arkusze), w.etykieta


def test_miejscowosci_na_arkuszu(projekt_z_arkuszami):
    p = projekt_z_arkuszami
    # bez geokodowania słupy nie mają miejscowości
    assert all(a.miejscowosci == [] for a in p.arkusze)


@pytest.mark.parametrize("ksztalt", [(1, 5), (40, 7), (300, 129), (64, 8)])
def test_unikalne_wiersze_jak_numpy(ksztalt):
    rng = np.random.default_rng(len(ksztalt) + ksztalt[0])
    M = rng.random(ksztalt) < 0.3
    M = np.vstack([M, M[: len(M) // 2]])  # duplikaty
    _, oczek = np.unique(M, axis=0, return_index=True)
    assert list(ark._unikalne_wiersze(M)) == list(oczek)


def test_unikalne_wiersze_pusta():
    assert len(ark._unikalne_wiersze(np.zeros((0, 4), bool))) == 0


def test_zachlanny_pokrywa_wszystko():
    rng = np.random.default_rng(1)
    M = rng.random((30, 50)) < 0.2
    M[0] |= ~M.any(axis=0)  # każdy punkt da się pokryć
    wybrane = ark._wybierz_zachlannie(M)
    assert M[wybrane].any(axis=0).all()


@pytest.mark.parametrize("m, tekst", [(1000, "1:1000"), (10000, "1:10 000"),
                                      (25000, "1:25 000")])
def test_opis_skali(m, tekst):
    assert ark.opis_skali(m) == tekst


def test_tekst_obiektu():
    s = "Budowa sieci w miejscowości Huta Kuflewska"
    assert ark.tekst_obiektu(s, ["Jakubów"]) == "Budowa sieci w miejscowości Jakubów"
    assert ark.tekst_obiektu(s, ["A", "B"]) == "Budowa sieci w miejscowościach A, B"
    assert ark.tekst_obiektu(s, []) == "Budowa sieci"


def test_zawijanie_tekstu():
    linie = ark.zawin("raz dwa trzy cztery pięć sześć", 2.5, 20)
    assert len(linie) > 1
    assert all(ark.szerokosc_tekstu(l, 2.5) <= 20 for l in linie if " " in l)
    assert " ".join(linie) == "raz dwa trzy cztery pięć sześć"


def test_na_arial_zachowuje_pogrubienie():
    assert ark.na_arial("\\fLato Light|b1|i0|c238|p34;X") == "\\fArial|b1|i0|c238|p34;X"
