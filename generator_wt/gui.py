"""Okno programu Generator WT (PySide6 / Qt)."""
from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QDate, QObject, QSettings, Qt, QThread, Signal
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QStyle, QTableWidget, QTableWidgetItem, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import slowniki
from .config import Config
from .projekt import Projekt

STYL = """
QMainWindow, QWidget#tlo { background: #f3f5f8; }
QFrame#naglowek { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1d4e89, stop:1 #2f80c1); }
QLabel#tytul { color: white; font-size: 20px; font-weight: 600; }
QLabel#podtytul { color: #dbe8f6; font-size: 12px; }
QGroupBox { background: white; border: 1px solid #d9dee6; border-radius: 8px;
            margin-top: 14px; padding: 12px 10px 10px 10px; font-weight: 600; color: #1d4e89; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
QLabel { color: #2b2f36; font-weight: normal; }
QLineEdit { border: 1px solid #c8cfd9; border-radius: 5px; padding: 4px 6px;
            background: white; min-height: 20px; font-weight: normal; color: #1f2329; }
QLineEdit:focus { border: 1px solid #2f80c1; }
QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit { min-height: 24px; font-weight: normal;
            color: #1f2329; }
QPushButton { border: 1px solid #c8cfd9; border-radius: 5px; padding: 6px 12px;
              background: #ffffff; color: #1f2329; font-weight: normal; }
QPushButton:hover { background: #eaf2fb; border-color: #2f80c1; }
QPushButton:disabled { color: #9aa3ae; background: #f0f2f5; }
QPushButton#glowny { background: #1d4e89; color: white; border: none; font-size: 14px;
                     font-weight: 600; padding: 10px; }
QPushButton#glowny:hover { background: #2563a8; }
QPushButton#glowny:disabled { background: #9db3cc; }
QPushButton#akcent { background: #2f80c1; color: white; border: none; font-weight: 600; }
QPushButton#akcent:hover { background: #3b8fd3; }
QCheckBox { font-weight: normal; color: #1f2329; }
QTabWidget::pane { border: 1px solid #d9dee6; border-radius: 6px; background: white; }
QTabBar::tab { background: #e6eaf0; padding: 7px 16px; border-top-left-radius: 6px;
               border-top-right-radius: 6px; margin-right: 2px; color: #3a4049; }
QTabBar::tab:selected { background: white; color: #1d4e89; font-weight: 600; }
QTableWidget, QTreeWidget, QPlainTextEdit { border: none; background: white;
    alternate-background-color: #f6f8fb; gridline-color: #e3e7ed; }
QHeaderView::section { background: #eef2f7; padding: 5px; border: none;
    border-right: 1px solid #dde2e9; border-bottom: 1px solid #dde2e9; font-weight: 600; }
QStatusBar { background: #e9edf2; }
QLabel#info { color: #4a5360; }
QLabel#ok { color: #1f7a3a; }
QLabel#ostrz { color: #b35c00; }
"""

KOLUMNY = [  # (nagłówek, atrybut, edytowalna)
    ("Nr", "etykieta", False), ("Stacja trafo", "stacja_trafo", False),
    ("Nr w sieci", "nr_w_sieci", True),
    ("Miejscowość", "miejscowosc", True), ("Ulica", "ulica", True), ("Gmina", "gmina", True),
    ("Rejon", "rejon_skrot", False), ("Rodzaj", "rodzaj_slupa", True),
    ("Typ słupa", "typ_slupa", True), ("X (2000)", "geo_x", False),
    ("Y (2000)", "geo_y", False), ("Działka", "dzialka", False), ("Uwagi", "uwagi", True),
]


class Pracownik(QObject):
    """Analiza pliku w tle: odczyt DXF + geokodowanie + plan numeracji."""
    postep = Signal(int, int, str)
    gotowe = Signal(object)
    blad = Signal(str)

    def __init__(self, projekt: Projekt, plik: str, geokodowanie: bool):
        super().__init__()
        self.projekt, self.plik, self.geokodowanie = projekt, plik, geokodowanie

    def run(self):
        try:
            self.postep.emit(0, 0, "Odczyt pliku DXF…")
            self.projekt.wczytaj(self.plik)
            bledy = 0
            if self.geokodowanie:
                bledy = self.projekt.geokoduj(
                    lambda i, n: self.postep.emit(i, n, f"Pobieranie adresów z GUGiK: {i}/{n}"))
            self.projekt.planuj()
            self.postep.emit(0, 0, "Rozmieszczanie arkuszy…")
            self.projekt.planuj_arkusze()
            self.gotowe.emit(bledy)
        except Exception as e:  # noqa: BLE001 - komunikat dla użytkownika
            self.blad.emit(f"{e}\n\n{traceback.format_exc()}")


class PodgladArkuszy(QWidget):
    """Podgląd ułożenia arkuszy: trasa, ramki z numerami, róg tabelki."""

    def __init__(self):
        super().__init__()
        self.linie, self.arkusze, self.zakazane = [], [], None
        self.setMinimumSize(300, 300)

    def ustaw(self, linie, arkusze, zakazane):
        self.linie, self.arkusze, self.zakazane = linie, arkusze, zakazane
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        if not self.arkusze:
            p.drawText(self.rect(), Qt.AlignCenter, "Brak arkuszy – przeanalizuj projekt.")
            return
        xs = [a.x0 for a in self.arkusze] + [a.x0 + a.szer for a in self.arkusze]
        ys = [a.y0 for a in self.arkusze] + [a.y0 + a.wys for a in self.arkusze]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        m = 20
        s = min((self.width() - 2 * m) / (x1 - x0), (self.height() - 2 * m) / (y1 - y0))
        ox = m + ((self.width() - 2 * m) - (x1 - x0) * s) / 2
        oy = m + ((self.height() - 2 * m) - (y1 - y0) * s) / 2

        def pt(x, y):
            return QPointF(ox + (x - x0) * s, oy + (y1 - y) * s)

        kolory = [QColor(c) for c in ("#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
                                      "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22")]
        for i, a in enumerate(self.arkusze):
            k = kolory[i % len(kolory)]
            if self.zakazane:
                zx0, _, _, zy1 = self.zakazane
                c = QColor(k)
                c.setAlpha(40)
                p.fillRect(QRectF(pt(a.x0 + zx0, a.y0 + zy1), pt(a.x0 + a.szer, a.y0)), c)
            p.setPen(QPen(k, 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(pt(a.x0, a.y0 + a.wys), pt(a.x0 + a.szer, a.y0)))
        p.setPen(QPen(QColor("#222"), 1.8))
        for ls in self.linie:
            c = list(ls.coords)
            for (ax, ay), (bx, by) in zip(c, c[1:]):
                p.drawLine(pt(ax, ay), pt(bx, by))
        f = QFont(self.font())
        f.setPointSize(13)
        f.setBold(True)
        p.setFont(f)
        for i, a in enumerate(self.arkusze):
            p.setPen(kolory[i % len(kolory)])
            r = QRectF(pt(a.x0, a.y0 + a.wys), pt(a.x0 + a.szer, a.y0))
            p.drawText(r, Qt.AlignCenter, a.nazwa)


class OknoGlowne(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self.projekt: Projekt | None = None
        self.ustawienia = QSettings("GeneratorWT", "GeneratorWT")
        self._watek: QThread | None = None
        self.operatorzy: list[dict] = []
        self.rejony: list[dict] = []

        self.setWindowTitle("Generator WT – wykaz słupów")
        self.resize(1400, 860)
        self._buduj()
        self.wczytaj_slowniki()
        self._stan_przyciskow()

    # ================================================================ budowa okna
    def _buduj(self):
        tlo = QWidget(objectName="tlo")
        self.setCentralWidget(tlo)
        uk = QVBoxLayout(tlo)
        uk.setContentsMargins(0, 0, 0, 0)
        uk.setSpacing(0)

        nagl = QFrame(objectName="naglowek")
        nl = QVBoxLayout(nagl)
        nl.setContentsMargins(20, 12, 20, 12)
        nl.addWidget(QLabel("Generator WT", objectName="tytul"))
        nl.addWidget(QLabel("Numeracja słupów linii !tele, pismo o dostęp do słupów "
                            "i wykazy w Excelu", objectName="podtytul"))
        uk.addWidget(nagl)

        podzial = QSplitter(Qt.Horizontal)
        podzial.setHandleWidth(6)
        uk.addWidget(podzial, 1)

        # ---------------- lewy panel
        lewy = QWidget()
        ll = QVBoxLayout(lewy)
        ll.setContentsMargins(14, 6, 8, 14)
        ll.setSpacing(4)
        ikona = self.style().standardIcon

        g1 = QGroupBox("1. Plik projektowy")
        f1 = QVBoxLayout(g1)
        self.e_plik = QLineEdit(readOnly=True, placeholderText="Wybierz plik DXF projektu…")
        b_plik = QPushButton(ikona(QStyle.SP_DirOpenIcon), " Wybierz plik DXF…")
        b_plik.clicked.connect(self.wybierz_plik)
        self.cb_geo = QCheckBox("Pobieraj adresy z GUGiK (miejscowość, ulica, gmina)")
        self.cb_geo.setChecked(True)
        self.b_analizuj = QPushButton(ikona(QStyle.SP_BrowserReload), " Analizuj projekt",
                                      objectName="akcent")
        self.b_analizuj.clicked.connect(self.analizuj)
        self.l_info = QLabel("Nie wczytano projektu.", objectName="info", wordWrap=True)
        for w in (self.e_plik, b_plik, self.cb_geo, self.b_analizuj, self.l_info):
            f1.addWidget(w)
        ll.addWidget(g1)

        g2 = QGroupBox("2. Zlecenie")
        f2 = QFormLayout(g2)
        self.c_operator = QComboBox()
        self.c_rejon = QComboBox()
        self.c_rejon.currentIndexChanged.connect(self._rejon_zmieniony)
        self.d_od = QDateEdit(QDate.currentDate(), calendarPopup=True, displayFormat="dd.MM.yyyy")
        self.e_do = QLineEdit("-")
        f2.addRow("Operator:", self.c_operator)
        f2.addRow("Rejon domyślny:", self.c_rejon)
        f2.addRow("Umowa od:", self.d_od)
        f2.addRow("Umowa do:", self.e_do)
        self.e_opracowal = QLineEdit(self.ustawienia.value("opracowal", ""),
                                     placeholderText="imię i nazwisko")
        self.e_data_rys = QLineEdit(QDate.currentDate().toString("MM.yyyy"))
        self.e_data_rys.setToolTip("Data w tabelce rysunku")
        f2.addRow("Opracował:", self.e_opracowal)
        f2.addRow("Data rysunku:", self.e_data_rys)
        rz = QHBoxLayout()
        b_edytuj = QPushButton(ikona(QStyle.SP_FileDialogDetailedView), " Edytuj listy")
        b_edytuj.setToolTip("Otwiera dane/slowniki.xlsx (operatorzy i rejony energetyczne)")
        b_edytuj.clicked.connect(self.edytuj_slowniki)
        b_odsw = QPushButton(ikona(QStyle.SP_BrowserReload), " Odśwież")
        b_odsw.clicked.connect(self.wczytaj_slowniki)
        rz.addWidget(b_edytuj)
        rz.addWidget(b_odsw)
        f2.addRow(rz)
        ll.addWidget(g2)

        g3 = QGroupBox("3. Numeracja")
        f3 = QFormLayout(g3)
        self.e_prefiks = QLineEdit(placeholderText="np. S → S1, S2…")
        self.s_start = QSpinBox(minimum=0, maximum=99999, value=1)
        self.s_tol = QDoubleSpinBox(minimum=0.01, maximum=50, value=self.cfg.tolerancja_slupa,
                                    singleStep=0.5, suffix=" m", decimals=2)
        self.s_tol.setToolTip("Wierzchołki bliżej niż ta odległość są traktowane jako jeden "
                              "słup (błędny klik). Zmiana wymaga ponownej analizy.")
        self.cb_kier = QCheckBox("Odnośnik po stronie z dala od linii")
        self.cb_kier.setChecked(True)
        self.e_prefiks.editingFinished.connect(self.przelicz_numeracje)
        self.s_start.valueChanged.connect(self.przelicz_numeracje)
        f3.addRow("Prefiks:", self.e_prefiks)
        f3.addRow("Numer startowy:", self.s_start)
        f3.addRow("Scalanie wierzchołków do:", self.s_tol)
        f3.addRow(self.cb_kier)
        ll.addWidget(g3)

        g4 = QGroupBox("4. Wyniki")
        f4 = QVBoxLayout(g4)
        self.cb_dxf = QCheckBox("Numeracja w DXF (*_numeracja.dxf)")
        self.cb_arkusze = QCheckBox("    + arkusze 1:1000 (układy 1, 2, 3…)")
        self.cb_dxf.toggled.connect(self.cb_arkusze.setEnabled)
        self.s_zakladka = QSpinBox(minimum=0, maximum=200, value=int(self.cfg.zakladka),
                                   suffix=" m")
        self.s_zakladka.setToolTip("Wspólny odcinek trasy na sąsiednich arkuszach")
        self.s_zakladka.valueChanged.connect(self.przelicz_arkusze)
        self.cb_orient = QCheckBox("Plan orientacyjny (*_orientacja.dxf + jpg)")
        rz_z = QHBoxLayout()
        rz_z.setContentsMargins(22, 0, 0, 0)
        rz_z.addWidget(QLabel("Zakładka arkuszy:"))
        rz_z.addWidget(self.s_zakladka)
        rz_z.addStretch(1)
        self.cb_pismo = QCheckBox("Pismo – zapytanie o dostęp (*_pismo.docx)")
        self.cb_rozb = QCheckBox("Zestawienie rozbudowane (*_rozbudowana.xlsx)")
        self.cb_upr = QCheckBox("Zestawienie uproszczone (*_uproszczona.xls)")
        for c in (self.cb_dxf, self.cb_arkusze, self.cb_pismo, self.cb_rozb, self.cb_upr,
                  self.cb_orient):
            c.setChecked(True)
            f4.addWidget(c)
            if c is self.cb_arkusze:
                f4.addLayout(rz_z)
        fo = QFormLayout()
        fo.setContentsMargins(22, 0, 0, 0)
        self.c_skala = QComboBox()
        self.c_skala.addItem("1:10 000", 10000)
        self.c_skala.addItem("1:25 000", 25000)
        self.c_zrodlo = QComboBox()
        self.c_zrodlo.addItem("OpenStreetMap (zapasowo GUGiK)", "osm")
        self.c_zrodlo.addItem("Mapa topograficzna GUGiK", "gugik")
        self.cb_szarosc = QCheckBox("Podkład w odcieniach szarości")
        self.cb_trasa_or = QCheckBox("Pokaż trasę na planie")
        self.cb_trasa_or.setChecked(True)
        fo.addRow("Skala:", self.c_skala)
        fo.addRow("Podkład:", self.c_zrodlo)
        fo.addRow(self.cb_szarosc)
        fo.addRow(self.cb_trasa_or)
        self.w_orient = QWidget()
        self.w_orient.setLayout(fo)
        self.cb_orient.toggled.connect(self.w_orient.setEnabled)
        f4.addWidget(self.w_orient)
        rk = QHBoxLayout()
        self.e_katalog = QLineEdit(placeholderText="Folder wyników (domyślnie folder projektu)")
        b_kat = QPushButton(ikona(QStyle.SP_DirIcon), "")
        b_kat.setToolTip("Wybierz folder wyników")
        b_kat.clicked.connect(self.wybierz_katalog)
        rk.addWidget(self.e_katalog, 1)
        rk.addWidget(b_kat)
        f4.addLayout(rk)
        ll.addWidget(g4)

        self.b_generuj = QPushButton("Numeruj i generuj dokumenty", objectName="glowny")
        self.b_generuj.clicked.connect(self.generuj)
        ll.addWidget(self.b_generuj)
        self.b_otworz = QPushButton(ikona(QStyle.SP_DirOpenIcon), " Otwórz folder wyników")
        self.b_otworz.clicked.connect(self.otworz_katalog)
        ll.addWidget(self.b_otworz)
        ll.addStretch(1)

        przewijany = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        przewijany.setWidget(lewy)
        przewijany.setMinimumWidth(400)
        podzial.addWidget(przewijany)

        # ---------------- prawy panel
        self.zakladki = QTabWidget()
        prawy = QWidget()
        pl = QVBoxLayout(prawy)
        pl.setContentsMargins(8, 14, 14, 14)
        pl.addWidget(self.zakladki)
        podzial.addWidget(prawy)
        podzial.setStretchFactor(1, 1)
        podzial.setSizes([420, 980])

        self.tabela = QTableWidget(0, len(KOLUMNY))
        self.tabela.setHorizontalHeaderLabels([k[0] for k in KOLUMNY])
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(24)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        self.tabela.itemChanged.connect(self._komorka_zmieniona)
        self.zakladki.addTab(self.tabela, "Wykaz słupów")

        self.drzewo = QTreeWidget()
        self.drzewo.setHeaderLabels(["Kontrola", "Szczegóły"])
        self.drzewo.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.zakladki.addTab(self.drzewo, "Kontrola projektu")

        self.podglad = PodgladArkuszy()
        self.zakladki.addTab(self.podglad, "Arkusze")

        self.dziennik = QPlainTextEdit(readOnly=True)
        self.dziennik.setFont(QFont("Consolas", 9))
        self.zakladki.addTab(self.dziennik, "Dziennik")

        self.pasek = QProgressBar(maximumWidth=280, visible=False, textVisible=True)
        self.l_stan = QLabel("Gotowy")
        self.statusBar().addWidget(self.l_stan, 1)
        self.statusBar().addPermanentWidget(self.pasek)

        ost = self.ustawienia.value("ostatni_plik", "")
        if ost and Path(ost).exists():
            self.e_plik.setText(ost)

    # ================================================================ pomocnicze
    def log(self, tekst: str):
        self.dziennik.appendPlainText(tekst)
        self.l_stan.setText(tekst.splitlines()[0] if tekst else "")

    def _stan_przyciskow(self, praca: bool = False):
        jest = self.projekt is not None and bool(self.projekt.plan)
        self.b_analizuj.setEnabled(not praca and bool(self.e_plik.text()))
        self.b_generuj.setEnabled(not praca and jest)

    def _katalog(self) -> Path:
        if self.e_katalog.text().strip():
            return Path(self.e_katalog.text().strip())
        return Path(self.e_plik.text()).parent

    def _otworz(self, sciezka: Path):
        if sys.platform.startswith("win"):
            os.startfile(str(sciezka))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(sciezka)])
        else:
            subprocess.Popen(["xdg-open", str(sciezka)])

    # ================================================================ słowniki
    def wczytaj_slowniki(self):
        plik = self.cfg.plik_slownikow
        if not plik.exists():
            slowniki.utworz_szablon(plik)
            self.log(f"Utworzono plik list: {plik}")
        try:
            self.operatorzy = slowniki.wczytaj_liste(plik, slowniki.ARKUSZ_OPERATORZY)
            self.rejony = slowniki.wczytaj_liste(plik, slowniki.ARKUSZ_REJONY)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Listy", f"Nie można wczytać {plik}:\n{e}\n\n"
                                "Zamknij plik w Excelu i kliknij Odśwież.")
            return
        for combo, lista, klucz in ((self.c_operator, self.operatorzy, "operator"),
                                    (self.c_rejon, self.rejony, "rejon")):
            combo.blockSignals(True)
            combo.clear()
            for poz in lista:
                combo.addItem(poz.get("Nazwa", ""), poz)
            idx = combo.findText(self.ustawienia.value(klucz, ""))
            combo.setCurrentIndex(max(idx, 0))
            combo.blockSignals(False)
        self._rejon_zmieniony()

    def edytuj_slowniki(self):
        self._otworz(self.cfg.plik_slownikow)

    def _rejon_zmieniony(self):
        if self.projekt and self.projekt.slupy:
            bez = self.projekt.przypisz_rejony(self.rejony, self.c_rejon.currentData())
            self._wypelnij_tabele()
            if bez:
                self.log("Gminy bez rejonu w liście (użyto rejonu domyślnego): "
                         + ", ".join(bez))

    # ================================================================ plik i analiza
    def wybierz_plik(self):
        start = self.e_plik.text() or self.ustawienia.value("ostatni_plik", "")
        plik, _ = QFileDialog.getOpenFileName(self, "Wybierz plik projektu", start,
                                              "Rysunek DXF (*.dxf);;Wszystkie pliki (*)")
        if plik:
            self.e_plik.setText(plik)
            self.ustawienia.setValue("ostatni_plik", plik)
            self._stan_przyciskow()
            self.analizuj()

    def wybierz_katalog(self):
        k = QFileDialog.getExistingDirectory(self, "Folder wyników", str(self._katalog()))
        if k:
            self.e_katalog.setText(k)

    def otworz_katalog(self):
        if self.e_plik.text():
            self._otworz(self._katalog())

    def _konfiguracja(self) -> Config:
        self.cfg.prefiks = self.e_prefiks.text().strip()
        self.cfg.numer_startowy = self.s_start.value()
        self.cfg.tolerancja_slupa = self.s_tol.value()
        self.cfg.inteligentny_kierunek = self.cb_kier.isChecked()
        self.cfg.zakladka = float(self.s_zakladka.value())
        return self.cfg

    def przelicz_arkusze(self):
        if self.projekt and self.projekt.plan:
            self._konfiguracja()
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.projekt.planuj_arkusze()
            finally:
                QApplication.restoreOverrideCursor()
            self._wypelnij_kontrole()

    def analizuj(self):
        plik = self.e_plik.text()
        if not plik:
            return
        self.projekt = Projekt(self._konfiguracja())
        self._stan_przyciskow(praca=True)
        self.pasek.setVisible(True)
        self.pasek.setRange(0, 0)
        self.log(f"Analiza: {plik}")

        self._watek = QThread(self)
        self._prac = Pracownik(self.projekt, plik, self.cb_geo.isChecked())
        self._prac.moveToThread(self._watek)
        self._watek.started.connect(self._prac.run)
        self._prac.postep.connect(self._postep)
        self._prac.gotowe.connect(self._analiza_gotowa)
        self._prac.blad.connect(self._analiza_blad)
        self._prac.gotowe.connect(self._watek.quit)
        self._prac.blad.connect(self._watek.quit)
        self._watek.start()

    def _postep(self, i, n, opis):
        if n:
            self.pasek.setRange(0, n)
            self.pasek.setValue(i)
        self.l_stan.setText(opis)

    def _analiza_blad(self, tekst):
        self.pasek.setVisible(False)
        self.projekt = None
        self._stan_przyciskow()
        self.log("BŁĄD: " + tekst)
        QMessageBox.critical(self, "Błąd analizy", tekst.split("\n\n")[0])

    def _analiza_gotowa(self, bledy_geo: int):
        self.pasek.setVisible(False)
        p = self.projekt
        p.przypisz_rejony(self.rejony, self.c_rejon.currentData())
        info = (f"Słupów: <b>{len(p.slupy)}</b> · stref trafo: <b>{len(p.stacje)}</b> · "
                f"błędnych klików: <b>{len(p.bledne_kliki)}</b>")
        if p.epsg:
            info += f" · układ EPSG:{p.epsg}"
        if bledy_geo:
            info += f"<br><span style='color:#b35c00'>Bez adresu (błąd usługi): {bledy_geo} "
            info += "– uruchom analizę ponownie.</span>"
        self.l_info.setText(info)
        self._wypelnij_tabele()
        self._wypelnij_kontrole()
        self.log(f"Analiza zakończona: {len(p.slupy)} słupów, {len(p.bledne_kliki)} "
                 f"błędnych klików, {len(p.ostrzezenia)} ostrzeżeń.")
        if p.bledne_kliki or p.ostrzezenia or p.przesla():
            self.zakladki.setCurrentWidget(self.drzewo)
        self._stan_przyciskow()

    def przelicz_numeracje(self):
        if self.projekt and self.projekt.slupy:
            self._konfiguracja()
            self.projekt.planuj()
            self.projekt.planuj_arkusze()
            self._wypelnij_tabele()
            self._wypelnij_kontrole()

    # ================================================================ widoki
    def _wypelnij_tabele(self):
        p = self.projekt
        if not p:
            return
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(p.plan))
        szary = QColor("#f0f2f5")
        for r, w in enumerate(p.plan):
            for k, (_, atr, edyt) in enumerate(KOLUMNY):
                v = getattr(w, atr)
                if isinstance(v, float):
                    v = f"{v:.{self.cfg.miejsca_po_przecinku}f}"
                it = QTableWidgetItem("" if v is None else str(v))
                it.setData(Qt.UserRole, w.id)
                if not edyt:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    it.setBackground(szary)
                if atr == "uwagi" and w.uwagi:
                    it.setForeground(QColor("#b35c00"))
                self.tabela.setItem(r, k, it)
        self.tabela.blockSignals(False)
        self.tabela.resizeColumnsToContents()

    def _komorka_zmieniona(self, it: QTableWidgetItem):
        p = self.projekt
        w = p.slupy[it.data(Qt.UserRole)]
        atr = KOLUMNY[it.column()][1]
        tekst = it.text().strip()
        setattr(w, atr, tekst if atr == "uwagi" else (tekst or None))
        if atr == "gmina":
            p.przypisz_rejony(self.rejony, self.c_rejon.currentData())
            self._wypelnij_tabele()
        elif atr == "nr_w_sieci":
            from .reader import ustaw_id_slupow
            ustaw_id_slupow(p.slupy)
        elif atr == "miejscowosc":
            p.planuj()  # grupowanie wg miejscowości mogło się zmienić
            self._wypelnij_tabele()
            self._wypelnij_kontrole()

    def _wypelnij_kontrole(self):
        p = self.projekt
        self._odswiez_podglad()
        self.drzewo.clear()
        ikona = self.style().standardIcon

        plan = QTreeWidgetItem(["Plan numeracji (ciągła)", f"{len(p.plan)} słupów"])
        plan.setIcon(0, ikona(QStyle.SP_FileDialogListView))
        for linia in p.opis_planu():
            nazwa, reszta = linia.split(": ", 1)
            QTreeWidgetItem(plan, [nazwa, reszta])
        if p.plan:
            QTreeWidgetItem(plan, ["Słup początkowy", f"{p.plan[0].etykieta} – "
                                   f"{_adres(p.plan[0])}"])
            QTreeWidgetItem(plan, ["Słup końcowy", f"{p.plan[-1].etykieta} – "
                                   f"{_adres(p.plan[-1])}"])

        bk = QTreeWidgetItem([f"Błędne kliki (wierzchołki < {self.cfg.tolerancja_slupa:g} m)",
                              f"{len(p.bledne_kliki)} – scalone w jeden słup"])
        bk.setIcon(0, ikona(QStyle.SP_MessageBoxWarning if p.bledne_kliki
                            else QStyle.SP_DialogApplyButton))
        mapa = {(round(w.x, 3), round(w.y, 3)): w for w in p.slupy}
        for b in p.bledne_kliki:
            w = mapa.get((round(b.x, 3), round(b.y, 3)))
            QTreeWidgetItem(bk, [f"Słup {w.etykieta if w else '?'}",
                                 f"{b.liczba} wierzchołki, rozrzut {b.max_odleglosc:.2f} m · "
                                 f"X={b.y:.2f} Y={b.x:.2f}"])

        dlugie = p.przesla()
        bledne = sum(1 for d, _, _ in dlugie if d > self.cfg.przeslo_blad)
        pr = QTreeWidgetItem([f"Przęsła > {self.cfg.przeslo_ostrzezenie:g} m",
                              f"{len(dlugie)}, w tym {bledne} > {self.cfg.przeslo_blad:g} m"])
        pr.setIcon(0, ikona(QStyle.SP_MessageBoxCritical if bledne else
                            QStyle.SP_MessageBoxWarning if dlugie else QStyle.SP_DialogApplyButton))
        czerwony, pomaranczowy = QColor("#c62828"), QColor("#b35c00")
        for d, a, b in dlugie:
            it = QTreeWidgetItem(pr, [f"Słupy {a.etykieta} – {b.etykieta}", f"{d:.2f} m"])
            kolor = czerwony if d > self.cfg.przeslo_blad else pomaranczowy
            for k in (0, 1):
                it.setForeground(k, kolor)
                if d > self.cfg.przeslo_blad:
                    f = it.font(k)
                    f.setBold(True)
                    it.setFont(k, f)
        if bledne:
            pr.setForeground(1, czerwony)

        st = QTreeWidgetItem(["Stacje trafo", f"{len(p.stacje)}"])
        st.setIcon(0, ikona(QStyle.SP_DriveNetIcon))
        for s in p.stacje:
            n = sum(1 for w in p.slupy if w.stacja_trafo == s.nazwa)
            QTreeWidgetItem(st, [s.nazwa, f"{n} słupów w zasięgu"])
        poza = sum(1 for w in p.slupy if not w.stacja_trafo)
        if poza:
            QTreeWidgetItem(st, ["(poza strefami)", f"{poza} słupów – grupowane wg miejscowości"])

        ar = QTreeWidgetItem([f"Arkusze 1:{self.cfg.skala_arkuszy}",
                              f"{len(p.arkusze)} (zakładka {self.cfg.zakladka:g} m)"])
        ar.setIcon(0, ikona(QStyle.SP_FileDialogContentsView))
        for a in p.arkusze:
            QTreeWidgetItem(ar, [f"Arkusz {a.nazwa}", ", ".join(a.miejscowosci) or "–"])

        bez_nr = [w for w in p.plan if not w.nr_w_sieci]
        ns = QTreeWidgetItem([f"Numery słupów w sieci ({self.cfg.prefiks_warstwy_numerow}…)",
                              f"przypisano {p.numerow_w_sieci}, bez numeru {len(bez_nr)}"])
        ns.setIcon(0, ikona(QStyle.SP_MessageBoxWarning if bez_nr else QStyle.SP_DialogApplyButton))
        for w in bez_nr:
            QTreeWidgetItem(ns, [f"Słup {w.etykieta}", f"{w.stacja_trafo or 'poza strefą'} · "
                                 f"X={w.geo_x:.2f} Y={w.geo_y:.2f}"])

        bez_opisu = [w for w in p.plan if not w.rodzaj_slupa]
        op = QTreeWidgetItem(["Słupy bez opisu rodzaju/typu",
                              f"{len(bez_opisu)} (opisano {p.opisanych_slupow})"])
        op.setIcon(0, ikona(QStyle.SP_MessageBoxInformation))
        for w in bez_opisu:
            QTreeWidgetItem(op, [f"Słup {w.etykieta}", f"X={w.geo_x:.2f} Y={w.geo_y:.2f}"])

        if p.ostrzezenia:
            o = QTreeWidgetItem(["Ostrzeżenia", str(len(p.ostrzezenia))])
            o.setIcon(0, ikona(QStyle.SP_MessageBoxWarning))
            for t in p.ostrzezenia:
                QTreeWidgetItem(o, ["", t])
        self.drzewo.addTopLevelItems([plan, bk, pr, ar, st, ns, op] + ([o] if p.ostrzezenia else []))
        plan.setExpanded(True)
        bk.setExpanded(True)
        pr.setExpanded(True)

    def _odswiez_podglad(self):
        from . import arkusze as ark
        p = self.projekt
        if not p or not p.arkusze:
            self.podglad.ustaw([], [], None)
            return
        sz = ark.wczytaj_szablon(p.szablon_doc(), self.cfg.uklad_trasy)
        k = self.cfg.skala_arkuszy / 1000
        self.podglad.ustaw(ark.lancuchy_trasy(p.slupy), p.arkusze,
                           tuple(v * k for v in sz.zakazane))

    # ================================================================ generowanie
    def generuj(self):
        p = self.projekt
        if not p or not p.plan:
            return
        if abs(self.s_tol.value() - p.tolerancja_analizy) > 1e-9:
            QMessageBox.information(self, "Zmieniono tolerancję",
                                    "Zmieniono odległość scalania wierzchołków – projekt "
                                    "zostanie przeanalizowany ponownie.")
            self.analizuj()
            return
        self.przelicz_numeracje()
        kat = self._katalog()
        kat.mkdir(parents=True, exist_ok=True)

        tekst = "<b>Plan numeracji:</b><ul>" + "".join(
            f"<li>{x}</li>" for x in p.opis_planu()) + "</ul>"
        stare = p.istniejaca_numeracja()
        if stare:
            tekst += (f"<p>Na warstwie <i>{self.cfg.warstwa_numeracji}</i> jest już {stare} "
                      "numerów – zostaną zastąpione.</p>")
        if p.bledne_kliki:
            tekst += f"<p>Scalono {len(p.bledne_kliki)} błędnych klików.</p>"
        if self.cb_dxf.isChecked() and self.cb_arkusze.isChecked():
            tekst += (f"<p>Arkusze 1:{self.cfg.skala_arkuszy}: {len(p.arkusze)} "
                      "(układy papieru 1–" + str(len(p.arkusze)) + ").</p>")
        tekst += f"<p>Pliki zostaną zapisane w:<br><i>{kat}</i></p>"
        tekst += "<p><b>Czy wykonać numerację?</b></p>"
        if QMessageBox.question(self, "Potwierdzenie numeracji", tekst,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            self.log("Przerwano – nic nie zapisano.")
            return

        operator = self.c_operator.currentData()
        opracowal = self.e_opracowal.text().strip() or None
        data_rys = self.e_data_rys.text().strip() or None
        self.ustawienia.setValue("opracowal", self.e_opracowal.text().strip())
        self.ustawienia.setValue("operator", self.c_operator.currentText())
        self.ustawienia.setValue("rejon", self.c_rejon.currentText())
        zadania = []
        if self.cb_dxf.isChecked():
            zadania.append(("numeracja.dxf", lambda f: p.zapisz_dxf(
                f, self.cb_arkusze.isChecked(), operator, opracowal, data_rys)))
        if self.cb_pismo.isChecked():
            zadania.append(("pismo.docx", lambda f: p.zapisz_pismo(
                f, operator, self.d_od.date().toString("dd.MM.yyyy"),
                self.e_do.text().strip() or "-")))
        if self.cb_rozb.isChecked():
            zadania.append(("rozbudowana.xlsx", p.zapisz_rozbudowana))
        if self.cb_upr.isChecked():
            zadania.append(("uproszczona.xls", p.zapisz_uproszczona))

        if self.cb_orient.isChecked():
            def orient(f):
                self.pasek.setVisible(True)

                def post(i, n):
                    self.pasek.setRange(0, n)
                    self.pasek.setValue(i)
                    self.l_stan.setText(f"Pobieranie podkładu: {i}/{n}")
                    QApplication.processEvents()
                try:
                    o = p.zapisz_orientacje(f, self.c_skala.currentData(),
                                            self.cb_szarosc.isChecked(), operator, opracowal,
                                            data_rys, self.c_zrodlo.currentData(),
                                            self.cb_trasa_or.isChecked(), post, self.log)
                    self.log(f"Plan orientacyjny: arkusze {', '.join(a.nazwa for a in o)}")
                finally:
                    self.pasek.setVisible(False)
            zadania.append(("orientacja.dxf", orient))

        zapisane, bledy = [], []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for przyrostek, f in zadania:
                cel = p.sciezka(kat, przyrostek)
                try:
                    f(cel)
                    zapisane.append(cel)
                    self.log(f"Zapisano: {cel}")
                except PermissionError:
                    bledy.append(f"{cel.name}: plik jest otwarty w innym programie.")
                except Exception as e:  # noqa: BLE001
                    bledy.append(f"{cel.name}: {e}")
                    self.log(traceback.format_exc())
        finally:
            QApplication.restoreOverrideCursor()
        msg = "Zapisano:\n" + "\n".join(f"• {z.name}" for z in zapisane)
        if bledy:
            QMessageBox.warning(self, "Gotowe z błędami", msg + "\n\nBłędy:\n" + "\n".join(bledy))
        else:
            QMessageBox.information(self, "Gotowe", msg)


def _adres(w) -> str:
    from .pismo import adres_slupa
    return adres_slupa(w)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYL)
    app.setFont(QFont("Segoe UI", 9))
    okno = OknoGlowne()
    okno.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
