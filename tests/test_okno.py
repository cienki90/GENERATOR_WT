"""Okno programu (Qt, bez wyświetlania): analiza i generowanie w tle, blokady,
wyłączanie słupów, ustawienia projektu. Bez internetu (geokodowanie wyłączone)."""
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def komunikaty(monkeypatch):
    """Okna dialogowe nie blokują testu: pytania = Tak, komunikaty są zapisywane."""
    lista = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    for rodzaj in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, rodzaj, staticmethod(
            lambda s, t, m, *a, r=rodzaj: lista.append((r, t, m))))
    return lista


@pytest.fixture
def okno(app, komunikaty):
    import shiboken6

    from generator_wt.gui import OknoGlowne
    o = OknoGlowne()
    yield o
    czekaj(app, o)
    o.close()
    shiboken6.delete(o)


def czekaj(app, o, limit=180):
    t0 = time.time()
    while o.zajety():
        assert time.time() - t0 < limit, "praca w tle nie zakończyła się"
        app.processEvents(QEventLoop.AllEvents, 50)
    app.processEvents()


def analizuj(app, o, dxf):
    o.e_plik.setText(str(dxf))
    o.cb_geo.setChecked(False)
    o.analizuj()
    czekaj(app, o)
    assert o.projekt is not None


def test_analiza_w_tle(app, okno, dxf):
    okno.e_plik.setText(str(dxf))
    okno.cb_geo.setChecked(False)
    okno.analizuj()
    assert okno.zajety()
    assert not okno.panel_ustawien.isEnabled() and not okno.tabela.isEnabled()
    watek = okno._watek
    okno.analizuj()  # druga analiza w trakcie jest ignorowana
    assert okno._watek is watek
    czekaj(app, okno)
    assert okno.panel_ustawien.isEnabled() and okno.tabela.isEnabled()
    assert len(okno.projekt.plan) == 151 and okno.tabela.rowCount() == 151
    assert len(okno.projekt.arkusze) == 18


def test_zamkniecie_w_trakcie_pracy(app, okno, dxf, komunikaty):
    okno.e_plik.setText(str(dxf))
    okno.cb_geo.setChecked(False)
    okno.show()
    okno.analizuj()
    assert okno.close() is False
    assert komunikaty and komunikaty[-1][1] == "Trwa praca"


def test_wylaczenie_slupu_i_stan(app, okno, dxf):
    analizuj(app, okno, dxf)
    p = okno.projekt
    sid = p.plan[3].id
    okno._przelacz_wykluczenie(sid)
    assert len(p.plan) == 150 and p.plik_stanu.exists()
    analizuj(app, okno, dxf)  # ponowna analiza - słup nadal wyłączony
    assert len(okno.projekt.plan) == 150


def test_poprawka_w_wykazie(app, okno, dxf):
    analizuj(app, okno, dxf)
    from generator_wt.gui import KOLUMNY
    k = [a for _, a, _ in KOLUMNY].index("ulica")
    it = okno.tabela.item(0, k)
    it.setText("Poprawiona")
    analizuj(app, okno, dxf)
    assert okno.tabela.item(0, k).text() == "Poprawiona"


def test_arkusze_w_tle_i_ustawienia(app, okno, dxf):
    analizuj(app, okno, dxf)
    okno.s_zakladka.setValue(25)
    okno.przelicz_arkusze()
    assert okno.zajety()
    czekaj(app, okno)
    assert len(okno.projekt.arkusze) == 20
    # nowe okno wczytuje zakładkę zapamiętaną dla projektu
    from generator_wt.gui import OknoGlowne
    import shiboken6
    o2 = OknoGlowne()
    try:
        o2._wczytaj_ustawienia_projektu(str(dxf))
        assert o2.s_zakladka.value() == 25
    finally:
        o2.close()
        shiboken6.delete(o2)


def test_generowanie_w_tle(app, okno, dxf, komunikaty):
    analizuj(app, okno, dxf)
    for c in (okno.cb_pismo, okno.cb_rozb, okno.cb_upr, okno.cb_orient, okno.cb_pdf_num):
        c.setChecked(False)  # bez pytania o układ współrzędnych i bez internetu
    okno.generuj()
    assert okno.zajety()
    czekaj(app, okno)
    assert komunikaty[-1][:2] == ("information", "Gotowe")
    assert (dxf.parent / "projekt_numeracja.dxf").exists()
    assert (dxf.parent / "projekt_tabela_projektowa.xlsx").exists()
