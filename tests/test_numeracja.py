"""Numeracja: ciągłość, grupy stacji trafo, wykluczenia, zgodność ze wzorcem."""
import json

from tests.conftest import WZORZEC, nowy_projekt


def test_numeracja_ciagla(dxf):
    p = nowy_projekt(dxf)
    assert [w.nr for w in p.plan] == list(range(1, len(p.plan) + 1))
    assert len({w.id for w in p.plan}) == len(p.plan) == len(p.slupy)


def test_prefiks_i_numer_startowy(dxf):
    p = nowy_projekt(dxf, prefiks="S", numer_startowy=100)
    assert p.plan[0].etykieta == "S100"
    assert p.plan[-1].etykieta == f"S{100 + len(p.plan) - 1}"


def test_stacja_trafo_ma_kolejne_numery(dxf):
    p = nowy_projekt(dxf)
    for g in p.grupy:
        if g.stacja:
            nry = sorted(w.nr for w in g.wierzcholki)
            assert nry == list(range(nry[0], nry[0] + len(nry))), g.nazwa


def test_jedna_grupa_na_stacje(dxf):
    p = nowy_projekt(dxf)
    stacje = [g.nazwa for g in p.grupy if g.stacja]
    assert len(stacje) == len(set(stacje))


def test_wykluczenie_slupa(dxf):
    p = nowy_projekt(dxf)
    w = p.plan[10]
    p.ustaw_wykluczenie(w, True)
    p.planuj()
    assert w not in p.plan and w.nr is None and w.etykieta == ""
    assert len(p.plan) == len(p.slupy) - 1
    assert [x.nr for x in p.plan] == list(range(1, len(p.plan) + 1))
    # trasa (sąsiedztwo) bez zmian - słup zostaje na mapie i w arkuszach
    assert w.sasiedzi
    p.ustaw_wykluczenie(w, False)
    p.planuj()
    assert len(p.plan) == len(p.slupy)


def test_zgodnosc_ze_wzorcem(dxf):
    wzorzec = json.loads(WZORZEC.read_text(encoding="utf-8"))
    p = nowy_projekt(dxf)
    assert len(p.slupy) == wzorzec["slupy"]
    plan = [[round(w.x, 2), round(w.y, 2), w.etykieta, w.grupa] for w in p.plan]
    assert plan == wzorzec["plan"], "numeracja różni się od wzorca (python -m tests.wzorzec)"


def test_przesla(dxf):
    p = nowy_projekt(dxf)
    dlugie = p.przesla()
    assert len(dlugie) == 16
    assert all(d > p.cfg.przeslo_ostrzezenie for d, _, _ in dlugie)
    assert [d for d, _, _ in dlugie] == sorted((d for d, _, _ in dlugie), reverse=True)
