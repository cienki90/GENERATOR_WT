"""Okno programu Generator WT (PySide6 / Qt)."""
from __future__ import annotations

import math
import os
import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QDate, QObject, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QDoubleSpinBox,
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

class SpinBox(QSpinBox):
    """QSpinBox, który ignoruje kółko myszy (żeby przewijanie strony nie zmieniało
    wartości przez przypadek). Strzałki i klawiatura działają normalnie."""
    def wheelEvent(self, ev):
        ev.ignore()


class DoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox ignorujący kółko myszy (jak SpinBox)."""
    def wheelEvent(self, ev):
        ev.ignore()


KOLUMNY = [  # (nagłówek, atrybut, edytowalna)
    ("W num.", "_wlaczony", False),  # kolumna z checkboxem (wyłączanie z numeracji)
    ("Nr", "etykieta", False), ("Stacja trafo", "stacja_trafo", False),
    ("Nr w sieci", "nr_w_sieci", True),
    ("Miejscowość", "miejscowosc", True), ("Ulica", "ulica", True),
    ("Droga przy słupie", "ulica_droga", False), ("Gmina", "gmina", True),
    ("Rejon", "rejon_skrot", False), ("Rodzaj", "rodzaj_slupa", True),
    ("Typ słupa", "typ_slupa", True), ("X (2000)", "geo_x", False),
    ("Y (2000)", "geo_y", False), ("Działka", "dzialka", False), ("Uwagi", "uwagi", True),
]


class Zadanie(QObject):
    """Praca w tle (analiza, arkusze, generowanie). 'praca' dostaje to zadanie i przez
    jego sygnały zgłasza postęp i wpisy do dziennika - okno nie zamarza."""
    postep = Signal(int, int, str)
    log = Signal(str)
    gotowe = Signal(object)
    blad = Signal(str)

    def __init__(self, praca):
        super().__init__()
        self.praca = praca

    def run(self):
        try:
            wynik = ("gotowe", self.praca(self))
        except Exception as e:  # noqa: BLE001 - komunikat dla użytkownika
            wynik = ("blad", f"{e}\n\n{traceback.format_exc()}")
        # przed końcem wątku oddaj obiekt wątkowi okna - inaczej Python usuwa go potem
        # z innego wątku niż jego własny, co bywa przyczyną losowego przerwania programu
        self.moveToThread(QApplication.instance().thread())
        getattr(self, wynik[0]).emit(wynik[1])


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


class WidokMapy(QWidget):
    """Podgląd rysunku DXF: trasa !tele, słupy i ich numeracja.

    - trasa rysowana z sąsiedztwa słupów (niezależnie od numeracji),
    - każdy słup to punkt z etykietą numeru; wykluczone słupy są szare, przekreślone
      i bez numeru,
    - kółko myszy przybliża/oddala, przeciąganie przesuwa widok,
    - klik w słup zaznacza go i zgłasza sygnałem (do wyłączania w numeracji),
      podwójny klik przełącza wykluczenie,
    - opcjonalny podkład mapy zasadniczej (Geoportal) rysowany pod wektorem;
      zmiana widoku zgłasza prośbę o pobranie podkładu dla nowego zakresu.
    """
    slup_klikniety = Signal(int)       # id słupa (zaznaczenie)
    slup_przelacz = Signal(int)        # id słupa (podwójny klik - wyłącz/włącz)
    widok_zmieniony = Signal()         # zoom/pan zakończony - czas odświeżyć podkład

    def __init__(self):
        super().__init__()
        self.slupy: list = []
        # transformacja świat->ekran: ekran = (ox + skala*x, oy - skala*y)
        # (oś Y w geodezji rośnie w górę, na ekranie w dół -> minus przy skala*y)
        self.skala = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self._dopasowano = False
        self.zaznaczony: int | None = None
        self._ostatni_pkt = None
        self._przeciaganie = False
        # podkład mapy zasadniczej (QImage) + jego obwiednia w układzie projektu
        self.podklad_img = None
        self.podklad_bbox = None       # (xmin, ymin, xmax, ymax)
        self.podklad_wlaczony = False
        # odłożone zgłoszenie prośby o podkład (po zakończeniu zoomu/przesuwania)
        self._zwloka_widoku = QTimer(self, singleShot=True, interval=350)
        self._zwloka_widoku.timeout.connect(self._zglos_widok)
        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def _zglos_widok(self):
        if self.podklad_wlaczony and self.slupy:
            self.widok_zmieniony.emit()

    def _po_zmianie_widoku(self):
        """Wywoływane po zoomie/przesunięciu - odłóż prośbę o nowy podkład."""
        if self.podklad_wlaczony:
            self._zwloka_widoku.start()

    def widok_bbox(self):
        """Obwiednia aktualnie widocznego obszaru w układzie projektu (xmin,ymin,xmax,ymax)."""
        x0 = (0 - self.ox) / self.skala
        x1 = (self.width() - self.ox) / self.skala
        y1 = (self.oy - 0) / self.skala          # góra ekranu = większy Y
        y0 = (self.oy - self.height()) / self.skala
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def ustaw_podklad(self, img, bbox):
        self.podklad_img = img
        self.podklad_bbox = bbox
        self.update()

    def ustaw_podklad_wlaczony(self, wl: bool):
        self.podklad_wlaczony = wl
        if not wl:
            self.podklad_img = None
            self.podklad_bbox = None
        self.update()

    def ustaw(self, slupy: list, zaznaczony: int | None = None, dopasuj: bool = False):
        self.slupy = slupy
        if zaznaczony is not None:
            self.zaznaczony = zaznaczony
        if dopasuj or not self._dopasowano:
            self._dopasuj()
        self.update()

    def resizeEvent(self, ev):
        # dopasuj widok, dopóki użytkownik sam nie przybliżył/przesunął
        if self.slupy and not self._dopasowano:
            self._dopasuj()
        super().resizeEvent(ev)

    def _zakres(self):
        xs = [w.x for w in self.slupy]
        ys = [w.y for w in self.slupy]
        return min(xs), max(xs), min(ys), max(ys)

    def _dopasuj(self):
        if not self.slupy or self.width() < 2 or self.height() < 2:
            return
        x0, x1, y0, y1 = self._zakres()
        m = 40
        szer = max(x1 - x0, 1e-6)
        wys = max(y1 - y0, 1e-6)
        self.skala = min((self.width() - 2 * m) / szer, (self.height() - 2 * m) / wys)
        # środek rysunku na środku widżetu
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        self.ox = self.width() / 2 - self.skala * cx
        self.oy = self.height() / 2 + self.skala * cy
        self._dopasowano = True
        self._po_zmianie_widoku()

    def _ekran(self, x, y) -> QPointF:
        return QPointF(self.ox + self.skala * x, self.oy - self.skala * y)

    def _slup_przy(self, px, py, prog=12):
        """id słupa, którego punkt ekranowy leży najbliżej (px, py) w promieniu prog [px]."""
        najbl, najd = None, prog
        for w in self.slupy:
            e = self._ekran(w.x, w.y)
            d = math.hypot(e.x() - px, e.y() - py)
            if d <= najd:
                najd, najbl = d, w.id
        return najbl

    # -------------------------------------------------- interakcja
    def wheelEvent(self, ev):
        if not self.slupy:
            return
        pos = ev.position()
        k = 1.2 if ev.angleDelta().y() > 0 else 1 / 1.2
        # punkt świata pod kursorem ma zostać w tym samym miejscu po zoomie
        gx = (pos.x() - self.ox) / self.skala
        gy = (self.oy - pos.y()) / self.skala
        self.skala *= k
        self.ox = pos.x() - self.skala * gx
        self.oy = pos.y() + self.skala * gy
        self._dopasowano = True  # użytkownik przejął sterowanie widokiem
        self._po_zmianie_widoku()
        self.update()

    def mousePressEvent(self, ev):
        self._ostatni_pkt = ev.position()
        self._przeciaganie = False
        if ev.button() == Qt.LeftButton and self.slupy:
            i = self._slup_przy(ev.position().x(), ev.position().y())
            if i is not None:
                self.zaznaczony = i
                self.slup_klikniety.emit(i)
                self.update()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.slupy:
            i = self._slup_przy(ev.position().x(), ev.position().y())
            if i is not None:
                self.slup_przelacz.emit(i)

    def mouseMoveEvent(self, ev):
        if (ev.buttons() & Qt.LeftButton) and self._ostatni_pkt is not None:
            d = ev.position() - self._ostatni_pkt
            if self._przeciaganie or abs(d.x()) + abs(d.y()) > 3:
                self._przeciaganie = True
                self.ox += d.x()
                self.oy += d.y()
                self._ostatni_pkt = ev.position()
                self._dopasowano = True
                self.update()

    def mouseReleaseEvent(self, ev):
        if self._przeciaganie:
            self._po_zmianie_widoku()
        self._przeciaganie = False
        self._ostatni_pkt = None

    # -------------------------------------------------- rysowanie
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        if not self.slupy:
            p.drawText(self.rect(), Qt.AlignCenter, "Brak projektu – przeanalizuj plik DXF.")
            return

        # podkład mapy zasadniczej (pod wektorem), rozciągnięty wg jego georeferencji
        if self.podklad_img is not None and self.podklad_bbox is not None:
            bx0, by0, bx1, by1 = self.podklad_bbox
            gl = self._ekran(bx0, by1)   # lewy-górny róg bboxu na ekranie
            pr = self._ekran(bx1, by0)   # prawy-dolny
            cel = QRectF(gl, pr)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(cel, self.podklad_img)

        # trasa z sąsiedztwa (każda krawędź raz)
        p.setPen(QPen(QColor("#555"), 1.4))
        narysowane = set()
        for w in self.slupy:
            a = self._ekran(w.x, w.y)
            for n in w.sasiedzi:
                if (w.id, n) in narysowane:
                    continue
                narysowane |= {(w.id, n), (n, w.id)}
                b = self.slupy[n]
                p.drawLine(a, self._ekran(b.x, b.y))

        # słupy i etykiety
        f = QFont(self.font())
        f.setPointSize(9)
        f.setBold(True)
        p.setFont(f)
        for w in self.slupy:
            e = self._ekran(w.x, w.y)
            wybrany = w.id == self.zaznaczony
            if w.wykluczony:
                kol = QColor("#9aa3ae")
            elif wybrany:
                kol = QColor("#d62728")
            else:
                kol = QColor("#1d4e89")
            r = 6 if wybrany else 4
            p.setPen(QPen(kol, 2 if wybrany else 1))
            p.setBrush(QColor("#ffffff") if w.wykluczony else kol)
            p.drawEllipse(e, r, r)
            if w.wykluczony:
                # przekreślenie
                p.setPen(QPen(QColor("#c62828"), 1.5))
                p.drawLine(QPointF(e.x() - r, e.y() - r), QPointF(e.x() + r, e.y() + r))
                p.drawLine(QPointF(e.x() - r, e.y() + r), QPointF(e.x() + r, e.y() - r))
            etyk = w.etykieta if (w.etykieta and not w.wykluczony) else ("—" if w.wykluczony
                                                                         else "")
            if etyk:
                p.setPen(kol)
                p.drawText(QRectF(e.x() + 6, e.y() - 16, 60, 14), Qt.AlignLeft | Qt.AlignVCenter,
                           etyk)


class DialogOperatora(QDialog):
    """Dodawanie / aktualizacja operatora po numerze NIP (GUS lub biała lista MF + RPT UKE)."""

    POLA_REJESTRU = ("Pełna nazwa", "Adres (siedziba)", "Kod pocztowy", "Regon",
                     "Numer wpisu do RPT")

    def __init__(self, parent, operatorzy: list[dict], ustawienia: QSettings):
        super().__init__(parent)
        from . import slowniki
        self.operatorzy = operatorzy
        self.ustawienia = ustawienia
        self.setWindowTitle("Dodaj operatora po NIP")
        self.setMinimumWidth(560)
        uk = QVBoxLayout(self)

        rz = QHBoxLayout()
        self.e_nip = QLineEdit(placeholderText="np. 822-234-93-74")
        self.b_pobierz = QPushButton(self.style().standardIcon(QStyle.SP_ArrowDown),
                                     " Pobierz z rejestrów", objectName="akcent")
        self.b_pobierz.clicked.connect(self.pobierz)
        self.e_nip.returnPressed.connect(self.pobierz)
        rz.addWidget(QLabel("NIP:"))
        rz.addWidget(self.e_nip, 1)
        rz.addWidget(self.b_pobierz)
        uk.addLayout(rz)

        self.l_info = QLabel("Dane adresowe: GUS (gdy podano klucz) albo biała lista MF; "
                             "numer RPT: rejestr UKE.", objectName="info", wordWrap=True)
        uk.addWidget(self.l_info)

        g = QGroupBox("Dane operatora (możesz poprawić przed zapisem)")
        f = QFormLayout(g)
        self.pola: dict[str, QLineEdit] = {}
        for k in slowniki.KOLUMNY_OPERATORA:
            e = QLineEdit()
            if k == "Nazwa":
                e.setPlaceholderText("krótka nazwa na liście wyboru")
            self.pola[k] = e
            f.addRow(k + ":", e)
        uk.addWidget(g)

        g2 = QGroupBox("Klucz GUS (opcjonalnie)")
        f2 = QHBoxLayout(g2)
        self.e_klucz = QLineEdit(ustawienia.value("klucz_gus", ""),
                                 placeholderText="bez klucza dane pochodzą z białej listy MF")
        self.e_klucz.setToolTip("Bezpłatny klucz do API REGON wydaje GUS "
                                "(api.stat.gov.pl → API REGON).")
        f2.addWidget(self.e_klucz)
        uk.addWidget(g2)

        przyc = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        przyc.button(QDialogButtonBox.Save).setText("Zapisz na liście")
        przyc.button(QDialogButtonBox.Cancel).setText("Anuluj")
        przyc.accepted.connect(self.zapisz)
        przyc.rejected.connect(self.reject)
        uk.addWidget(przyc)
        self.wpis: dict | None = None

    def _istniejacy(self, nip: str) -> dict | None:
        import re
        return next((o for o in self.operatorzy
                     if re.sub(r"\D", "", o.get("NIP", "")) == nip), None)

    def pobierz(self):
        from . import rejestry
        klucz = self.e_klucz.text().strip()
        self.ustawienia.setValue("klucz_gus", klucz)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            w = rejestry.operator_po_nip(self.e_nip.text(), klucz or None)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "NIP", str(e))
            return
        QApplication.restoreOverrideCursor()
        info = list(w.pop("_info", []))
        stary = self._istniejacy(w["NIP"])
        if stary:
            # zachowaj pola wpisane ręcznie, podmień tylko dane z rejestrów
            nowy = dict(stary)
            for k in self.POLA_REJESTRU + ("NIP",):
                if w.get(k):
                    nowy[k] = w[k]
            info.insert(0, f"Operator '{stary.get('Nazwa')}' jest już na liście – "
                           "zapis zaktualizuje dane z rejestrów.")
            w = nowy
        for k, e in self.pola.items():
            e.setText(w.get(k, ""))
            e.setStyleSheet("")
        for k in self.POLA_REJESTRU:
            if stary and stary.get(k, "") != w.get(k, ""):
                self.pola[k].setStyleSheet("background:#fff3cd;")
                self.pola[k].setToolTip(f"Było: {stary.get(k, '') or '–'}")
        self.l_info.setText("<br>".join(info))
        self.adjustSize()
        self.wpis = w

    def zapisz(self):
        from . import rejestry
        if not self.pola["Nazwa"].text().strip() or not self.pola["NIP"].text().strip():
            QMessageBox.warning(self, "Operator", "Uzupełnij co najmniej nazwę i NIP.")
            return
        try:
            nip = rejestry.oczysc_nip(self.pola["NIP"].text())
        except rejestry.BladRejestru as e:
            QMessageBox.warning(self, "Operator", str(e))
            return
        self.wpis = {k: e.text().strip() for k, e in self.pola.items()}
        self.wpis["NIP"] = nip
        self.accept()


class OknoGlowne(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self.projekt: Projekt | None = None
        self.ustawienia = QSettings("GeneratorWT", "GeneratorWT")
        # bieżące zadanie w tle (najwyżej jedno naraz) i jego wynik
        self._watek: QThread | None = None
        self._zadanie: Zadanie | None = None
        self._wynik_zadania: tuple | None = None
        self._po_zadaniu = None
        self._plik_ustawien: str | None = None  # DXF, z którego wczytano ustawienia projektu
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
        b_nip = QPushButton(ikona(QStyle.SP_FileDialogNewFolder), " Dodaj operatora po NIP…")
        b_nip.setToolTip("Pobiera nazwę i adres (GUS / biała lista MF) oraz numer RPT (UKE)")
        b_nip.clicked.connect(self.dodaj_operatora)
        f2.addRow(b_nip)
        ll.addWidget(g2)

        g3 = QGroupBox("3. Numeracja")
        f3 = QFormLayout(g3)
        self.e_prefiks = QLineEdit(placeholderText="np. S → S1, S2…")
        self.s_start = SpinBox(minimum=0, maximum=99999, value=1)
        self.s_tol = DoubleSpinBox(minimum=0.01, maximum=50, value=self.cfg.tolerancja_slupa,
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
        self.cb_pdf_num = QCheckBox("    + arkusze jako PDF (*_numeracja.pdf)")
        self.cb_pdf_num.setToolTip("Wielostronicowy PDF: po jednym arkuszu 1:1000 na stronę A3")
        self.cb_dxf.toggled.connect(self.cb_arkusze.setEnabled)
        self.cb_arkusze.toggled.connect(self.cb_pdf_num.setEnabled)
        self.s_zakladka = SpinBox(minimum=0, maximum=200, value=int(self.cfg.zakladka),
                                  suffix=" m")
        self.s_zakladka.setToolTip("Wspólny odcinek trasy na sąsiednich arkuszach")
        # przeliczenie arkuszy dopiero po chwili bez zmian (nie przy każdym kliknięciu strzałki)
        self._zwloka_arkuszy = QTimer(self, singleShot=True, interval=700)
        self._zwloka_arkuszy.timeout.connect(self.przelicz_arkusze)
        self.s_zakladka.valueChanged.connect(self._zwloka_arkuszy.start)
        self.cb_orient = QCheckBox("Plan orientacyjny (*_orientacja.dxf + jpg)")
        rz_z = QHBoxLayout()
        rz_z.setContentsMargins(22, 0, 0, 0)
        rz_z.addWidget(QLabel("Zakładka arkuszy:"))
        rz_z.addWidget(self.s_zakladka)
        rz_z.addStretch(1)
        self.cb_pismo = QCheckBox("Pismo – zapytanie o dostęp (*_pismo.docx)")
        self.cb_rozb = QCheckBox("Zestawienie rozbudowane (*_rozbudowana.xlsx)")
        self.cb_upr = QCheckBox("Zestawienie uproszczone (*_uproszczona.xls)")
        self.cb_proj = QCheckBox("Tabela projektowa (*_tabela_projektowa.xlsx)")
        for c in (self.cb_dxf, self.cb_arkusze, self.cb_pdf_num, self.cb_pismo, self.cb_rozb,
                  self.cb_upr, self.cb_proj, self.cb_orient):
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
        self.cb_pdf_orient = QCheckBox("Zapisz też jako PDF (*_orientacja.pdf)")
        self.cb_pdf_orient.setToolTip("Plan orientacyjny jako PDF z podkładem mapowym")
        self.cb_pdf_orient.setChecked(True)
        fo.addRow("Skala:", self.c_skala)
        fo.addRow("Podkład:", self.c_zrodlo)
        fo.addRow(self.cb_szarosc)
        fo.addRow(self.cb_trasa_or)
        fo.addRow(self.cb_pdf_orient)
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
        self.panel_ustawien = lewy  # blokowany na czas pracy w tle

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
        kontrola = QWidget()
        kl = QVBoxLayout(kontrola)
        kl.setContentsMargins(0, 0, 0, 0)
        rk2 = QHBoxLayout()
        rk2.setContentsMargins(6, 6, 6, 0)
        self.b_ulice = QPushButton(self.style().standardIcon(QStyle.SP_DialogApplyButton),
                                   " Przyjmij ulice z dróg dla niezgodnych słupów")
        self.b_ulice.setToolTip("Zastępuje ulicę z adresu nazwą najbliższej drogi (OSM). "
                                "Pojedyncze słupy poprawisz w wykazie.")
        self.b_ulice.clicked.connect(self.przyjmij_ulice)
        self.b_ulice.setEnabled(False)
        rk2.addWidget(self.b_ulice)
        rk2.addStretch(1)
        kl.addLayout(rk2)
        kl.addWidget(self.drzewo)
        self.zakladka_kontroli = kontrola
        self.zakladki.addTab(kontrola, "Kontrola projektu")

        self.mapa = WidokMapy()
        self.mapa.slup_klikniety.connect(self._slup_z_mapy)
        self.mapa.slup_przelacz.connect(self._przelacz_wykluczenie)
        mapa_panel = QWidget()
        ml = QVBoxLayout(mapa_panel)
        ml.setContentsMargins(0, 0, 0, 0)
        pasek_mapy = QHBoxLayout()
        pasek_mapy.setContentsMargins(6, 6, 6, 0)
        self.l_mapa = QLabel("Klik = zaznacz słup · podwójny klik = wyłącz/włącz · "
                             "kółko = zoom · przeciąganie = przesuń", objectName="info")
        self.b_podklad = QPushButton(self.style().standardIcon(QStyle.SP_DialogYesButton),
                                     " Mapa zasadnicza (Geoportal)")
        self.b_podklad.setCheckable(True)
        self.b_podklad.setChecked(False)  # domyślnie wyłączona
        self.b_podklad.setToolTip("Podkład z Geoportalu: działki, budynki, użytki i sieci "
                                  "uzbrojenia terenu (GESUT). Wymaga internetu.")
        self.b_podklad.toggled.connect(self._przelacz_podklad)
        self.b_wyklucz = QPushButton(self.style().standardIcon(QStyle.SP_DialogCancelButton),
                                     " Wyłącz zaznaczony z numeracji")
        self.b_wyklucz.setToolTip("Słup wyłączony nie dostaje numeru i nie trafia do pisma, "
                                  "zestawień ani numeracji DXF (zostaje na trasie).")
        self.b_wyklucz.clicked.connect(self._wyklucz_zaznaczony)
        self.b_wyklucz.setEnabled(False)
        b_dopasuj = QPushButton(self.style().standardIcon(QStyle.SP_FileDialogListView),
                                " Dopasuj widok")
        b_dopasuj.clicked.connect(lambda: self.mapa.ustaw(self.mapa.slupy, dopasuj=True))
        pasek_mapy.addWidget(self.l_mapa, 1)
        pasek_mapy.addWidget(self.b_podklad)
        pasek_mapy.addWidget(self.b_wyklucz)
        pasek_mapy.addWidget(b_dopasuj)
        ml.addLayout(pasek_mapy)
        ml.addWidget(self.mapa)
        self.mapa.widok_zmieniony.connect(self._pobierz_podklad_mapy)
        self._watek_podkladu: QThread | None = None
        self._podklad_oczekuje = False
        self.zakladki.addTab(mapa_panel, "Mapa")

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

    def _stan_przyciskow(self):
        praca = self.zajety()
        jest = self.projekt is not None and bool(self.projekt.plan)
        self.b_analizuj.setEnabled(not praca and bool(self.e_plik.text()))
        self.b_generuj.setEnabled(not praca and jest)

    # ================================================================ praca w tle
    def zajety(self) -> bool:
        return self._watek is not None

    def _uruchom(self, praca, po_zakonczeniu=None, przy_bledzie=None) -> bool:
        """Uruchamia 'praca(zadanie)' w osobnym wątku. Na ten czas ustawienia, wykaz
        i przyciski są zablokowane, żeby nic nie zmieniało projektu w trakcie pracy.
        Po zakończeniu (w wątku okna) wywołuje po_zakonczeniu(wynik) albo
        przy_bledzie(tekst). Zwraca False, gdy inna praca jeszcze trwa."""
        if self.zajety():
            return False
        self._wynik_zadania = None
        self._po_zadaniu = (po_zakonczeniu, przy_bledzie)
        self._watek = QThread(self)
        self._zadanie = Zadanie(praca)
        self._zadanie.moveToThread(self._watek)
        self._watek.started.connect(self._zadanie.run)
        self._zadanie.postep.connect(self._postep)
        self._zadanie.log.connect(self.log)
        self._zadanie.gotowe.connect(self._zadanie_gotowe)
        self._zadanie.blad.connect(self._zadanie_blad)
        self._zadanie.gotowe.connect(self._watek.quit)
        self._zadanie.blad.connect(self._watek.quit)
        self._watek.finished.connect(self._zadanie_koniec)
        self._ustaw_prace(True)
        self._watek.start()
        return True

    def _zadanie_gotowe(self, wynik):
        self._wynik_zadania = ("ok", wynik)

    def _zadanie_blad(self, tekst):
        self._wynik_zadania = ("blad", tekst)

    def _zadanie_koniec(self):
        """Wątek się zakończył - zwolnij go i dopiero potem obsłuż wynik
        (obsługa może uruchomić kolejną pracę)."""
        self._watek.deleteLater()
        self._watek = self._zadanie = None  # obiekt zadania (bez rodzica) usunie Python
        self._ustaw_prace(False)
        wynik, (ok, zle) = self._wynik_zadania, self._po_zadaniu
        self._wynik_zadania = self._po_zadaniu = None
        if wynik and wynik[0] == "ok" and ok:
            ok(wynik[1])
        elif wynik and wynik[0] == "blad":
            if zle:
                zle(wynik[1])
            else:
                self.log("BŁĄD: " + wynik[1])
                QMessageBox.critical(self, "Błąd", wynik[1].split("\n\n")[0])

    def _ustaw_prace(self, praca: bool):
        self.panel_ustawien.setEnabled(not praca)
        self.tabela.setEnabled(not praca)
        self.b_ulice.setEnabled(not praca and bool(self.projekt and self.projekt.niezgodne_ulice()))
        self.b_wyklucz.setEnabled(not praca and self.mapa.zaznaczony is not None)
        self.pasek.setVisible(praca)
        if praca:
            self.pasek.setRange(0, 0)
        self._stan_przyciskow()

    def closeEvent(self, ev):
        if self.zajety():
            QMessageBox.information(self, "Trwa praca",
                                    "Program jeszcze pracuje (analiza lub zapis plików). "
                                    "Poczekaj na zakończenie i zamknij okno ponownie.")
            ev.ignore()
            return
        super().closeEvent(ev)

    def _sprawdz_zapis_stanu(self):
        if self.projekt and self.projekt.blad_stanu:
            self.log("UWAGA: " + self.projekt.blad_stanu)

    # ---------------------------------------------- ustawienia projektu (<projekt>.wt.json)
    def _ustawienia_projektu(self) -> dict:
        return {"prefiks": self.e_prefiks.text().strip(), "numer_startowy": self.s_start.value(),
                "tolerancja_slupa": self.s_tol.value(), "zakladka": self.s_zakladka.value(),
                "inteligentny_kierunek": self.cb_kier.isChecked(),
                "operator": self.c_operator.currentText(), "rejon": self.c_rejon.currentText(),
                "umowa_od": self.d_od.date().toString("dd.MM.yyyy"),
                "umowa_do": self.e_do.text().strip()}

    def _zapisz_ustawienia_projektu(self):
        if self.projekt and self.projekt.plik and not self.zajety():
            self.projekt.zapisz_ustawienia(self._ustawienia_projektu())
            self._sprawdz_zapis_stanu()

    def _wczytaj_ustawienia_projektu(self, plik: str):
        """Przed analizą nowego pliku: ustawienia zapamiętane dla tego projektu."""
        from . import stan
        u = stan.wczytaj(stan.plik_stanu(plik)).get("ustawienia") or {}
        self._plik_ustawien = plik
        if not u:
            return
        widzety = (self.e_prefiks, self.s_start, self.s_tol, self.s_zakladka, self.cb_kier,
                   self.c_operator, self.c_rejon, self.d_od, self.e_do)
        for w in widzety:
            w.blockSignals(True)
        try:
            if "prefiks" in u:
                self.e_prefiks.setText(str(u["prefiks"]))
            if "numer_startowy" in u:
                self.s_start.setValue(int(u["numer_startowy"]))
            if "tolerancja_slupa" in u:
                self.s_tol.setValue(float(u["tolerancja_slupa"]))
            if "zakladka" in u:
                self.s_zakladka.setValue(int(u["zakladka"]))
            if "inteligentny_kierunek" in u:
                self.cb_kier.setChecked(bool(u["inteligentny_kierunek"]))
            for combo, k in ((self.c_operator, "operator"), (self.c_rejon, "rejon")):
                i = combo.findText(str(u.get(k, "")))
                if i >= 0:
                    combo.setCurrentIndex(i)
            if u.get("umowa_od"):
                d = QDate.fromString(u["umowa_od"], "dd.MM.yyyy")
                if d.isValid():
                    self.d_od.setDate(d)
            if "umowa_do" in u:
                self.e_do.setText(str(u["umowa_do"]))
        except (TypeError, ValueError):
            pass  # uszkodzone ustawienia - zostają bieżące
        finally:
            for w in widzety:
                w.blockSignals(False)
        self.log(f"Wczytano ustawienia projektu z {stan.plik_stanu(plik).name}")

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

    def dodaj_operatora(self):
        from . import slowniki
        dlg = DialogOperatora(self, self.operatorzy, self.ustawienia)
        if dlg.exec() != QDialog.Accepted or not dlg.wpis:
            return
        try:
            stan = slowniki.zapisz_operatora(self.cfg.plik_slownikow, dlg.wpis)
        except PermissionError:
            QMessageBox.warning(self, "Operator", "Plik list jest otwarty w Excelu – zamknij go "
                                "i spróbuj ponownie.")
            return
        self.log(f"Operator {dlg.wpis['Nazwa']}: {stan} w {self.cfg.plik_slownikow.name}")
        self.ustawienia.setValue("operator", dlg.wpis["Nazwa"])
        self.wczytaj_slowniki()

    def edytuj_slowniki(self):
        self._otworz(self.cfg.plik_slownikow)

    def _rejon_zmieniony(self):
        if self.projekt and self.projekt.slupy and not self.zajety():
            bez = self.projekt.przypisz_rejony(self.rejony, self.c_rejon.currentData())
            self._wypelnij_tabele()
            if bez:
                self.log("Gminy bez rejonu w liście (użyto rejonu domyślnego): "
                         + ", ".join(bez))

    # ================================================================ plik i analiza
    def wybierz_plik(self):
        if self.zajety():
            return
        start = self.e_plik.text() or self.ustawienia.value("ostatni_plik", "")
        plik, _ = QFileDialog.getOpenFileName(self, "Wybierz plik projektu", start,
                                              "Rysunek DXF (*.dxf);;Wszystkie pliki (*)")
        if plik and not self.zajety():
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
        if not (self.projekt and self.projekt.plan):
            return
        if self.zajety():  # trwa inna praca - spróbuj ponownie za chwilę
            self._zwloka_arkuszy.start()
            return
        self._konfiguracja()
        p = self.projekt

        def praca(z):
            z.postep.emit(0, 0, "Rozmieszczanie arkuszy…")
            return len(p.planuj_arkusze())

        def gotowe(n):
            self.l_stan.setText(f"Arkuszy: {n}")
            self._wypelnij_kontrole()
            self._zapisz_ustawienia_projektu()
        self._uruchom(praca, gotowe)

    def analizuj(self):
        plik = self.e_plik.text()
        if not plik or self.zajety():
            return
        if plik != self._plik_ustawien:  # nowy plik - ustawienia zapamiętane dla projektu
            self._wczytaj_ustawienia_projektu(plik)
        projekt = Projekt(self._konfiguracja())
        geo = self.cb_geo.isChecked()
        self.log(f"Analiza: {plik}")

        def praca(z):
            z.postep.emit(0, 0, "Odczyt pliku DXF…")
            projekt.wczytaj(plik)
            bledy = 0
            if geo:
                bledy = projekt.geokoduj(
                    lambda i, n: z.postep.emit(i, n, f"Pobieranie adresów z GUGiK: {i}/{n}"))
                z.postep.emit(0, 0, "Sprawdzanie ulic (drogi OpenStreetMap)…")
                try:
                    projekt.sprawdz_ulice(log=lambda t: None)
                except Exception as e:  # noqa: BLE001
                    projekt.ostrzezenia.append(f"Sprawdzanie ulic pominięte: {e}")
            projekt.zastosuj_stan()
            projekt.planuj()
            z.postep.emit(0, 0, "Rozmieszczanie arkuszy…")
            projekt.planuj_arkusze()
            return bledy

        self._uruchom(praca, lambda bledy: self._analiza_gotowa(projekt, bledy),
                      self._analiza_blad)

    def _postep(self, i, n, opis):
        if n:
            self.pasek.setRange(0, n)
            self.pasek.setValue(i)
        else:
            self.pasek.setRange(0, 0)  # etap bez znanej liczby kroków
        self.l_stan.setText(opis)

    def _analiza_blad(self, tekst):
        self.projekt = None
        self._stan_przyciskow()
        self.log("BŁĄD: " + tekst)
        QMessageBox.critical(self, "Błąd analizy", tekst.split("\n\n")[0])

    def _analiza_gotowa(self, projekt: Projekt, bledy_geo: int):
        self.projekt = p = projekt
        p.przypisz_rejony(self.rejony, self.c_rejon.currentData())
        if p.poprawek_zastosowanych:
            self.log(f"Zastosowano zapamiętane poprawki ({p.plik_stanu.name}): "
                     f"{p.poprawek_zastosowanych} słupów")
        info = (f"Słupów: <b>{len(p.slupy)}</b> · stref trafo: <b>{len(p.stacje)}</b> · "
                f"błędnych klików: <b>{len(p.bledne_kliki)}</b>")
        if p.epsg:
            info += f" · układ EPSG:{p.epsg}"
        if bledy_geo:
            info += f"<br><span style='color:#b35c00'>Bez adresu (błąd usługi): {bledy_geo} "
            info += "– uruchom analizę ponownie.</span>"
        self.l_info.setText(info)
        self.mapa._dopasowano = False  # nowy projekt - dopasuj widok mapy
        self.mapa.zaznaczony = None
        self.b_wyklucz.setEnabled(False)
        self._wypelnij_tabele()
        self._wypelnij_kontrole()
        self.log(f"Analiza zakończona: {len(p.slupy)} słupów, {len(p.bledne_kliki)} "
                 f"błędnych klików, {len(p.ostrzezenia)} ostrzeżeń.")
        if p.bledne_kliki or p.ostrzezenia or p.przesla() or p.niezgodne_ulice():
            self.zakladki.setCurrentWidget(self.zakladka_kontroli)
        self._stan_przyciskow()

    def przelicz_numeracje(self):
        if self.projekt and self.projekt.slupy and not self.zajety():
            self._konfiguracja()
            self.projekt.planuj()
            self.projekt.odswiez_miejscowosci_arkuszy()  # ułożenie arkuszy się nie zmienia
            self._wypelnij_tabele()
            self._wypelnij_kontrole()
            self._zapisz_ustawienia_projektu()

    def _przelicz_po_wykluczeniu(self):
        """Po zmianie wykluczenia słupa: numeracja od nowa, wykaz, kontrola i mapa."""
        p = self.projekt
        if not p:
            return
        p.planuj()
        p.odswiez_miejscowosci_arkuszy()
        self._wypelnij_tabele()
        self._wypelnij_kontrole()  # odświeża też mapę przez _odswiez_podglad
        self._sprawdz_zapis_stanu()
        wykl = sum(1 for w in p.slupy if w.wykluczony)
        self.log(f"Numeracja: {len(p.plan)} słupów"
                 + (f" · wyłączonych: {wykl}" if wykl else ""))

    # -------------------------------------------------- wyłączanie słupów (mapa + wykaz)
    def _slup_z_mapy(self, slup_id: int):
        """Klik w słup na mapie: zaznacz go też w wykazie i uaktywnij przycisk."""
        self.b_wyklucz.setEnabled(not self.zajety())
        w = self.projekt.slupy[slup_id] if self.projekt else None
        if w is not None:
            self.b_wyklucz.setText(" Włącz zaznaczony do numeracji" if w.wykluczony
                                   else " Wyłącz zaznaczony z numeracji")
        # zaznacz odpowiedni wiersz w wykazie
        for r in range(self.tabela.rowCount()):
            it = self.tabela.item(r, 0)
            if it and it.data(Qt.UserRole) == slup_id:
                self.tabela.selectRow(r)
                break

    def _przelacz_wykluczenie(self, slup_id: int):
        p = self.projekt
        if not p or self.zajety():
            return
        w = p.slupy[slup_id]
        p.ustaw_wykluczenie(w, not w.wykluczony)
        self.mapa.zaznaczony = slup_id
        self._przelicz_po_wykluczeniu()
        self._slup_z_mapy(slup_id)

    def _wyklucz_zaznaczony(self):
        if self.mapa.zaznaczony is not None:
            self._przelacz_wykluczenie(self.mapa.zaznaczony)

    # -------------------------------------------------- podkład mapy zasadniczej
    def _przelacz_podklad(self, wl: bool):
        p = self.projekt
        if wl and (not p or not p.slupy):
            self.b_podklad.setChecked(False)
            QMessageBox.information(self, "Mapa zasadnicza",
                                    "Najpierw wczytaj i przeanalizuj projekt DXF.")
            return
        if wl and p.epsg is None:
            self.b_podklad.setChecked(False)
            QMessageBox.warning(self, "Mapa zasadnicza",
                                "Nie rozpoznano układu współrzędnych projektu (PL-2000) – "
                                "nie można pobrać podkładu z Geoportalu.")
            return
        self.mapa.ustaw_podklad_wlaczony(wl)
        if wl:
            self._pobierz_podklad_mapy()
        else:
            self.log("Mapa zasadnicza: wyłączona")

    def _pobierz_podklad_mapy(self):
        """Pobiera podkład mapy zasadniczej dla aktualnego widoku (w osobnym wątku)."""
        p = self.projekt
        if not p or p.epsg is None or not self.mapa.podklad_wlaczony:
            return
        if self._watek_podkladu is not None:
            # pobieranie już trwa - po jego zakończeniu pobierz jeszcze raz dla nowego widoku
            self._podklad_oczekuje = True
            return
        self._podklad_oczekuje = False
        bbox = self.mapa.widok_bbox()
        # mały margines, żeby przy drobnym przesunięciu podkład nie znikał z brzegów
        mx = (bbox[2] - bbox[0]) * 0.1
        my = (bbox[3] - bbox[1]) * 0.1
        bbox = (bbox[0] - mx, bbox[1] - my, bbox[2] + mx, bbox[3] + my)
        szer = min(int(self.mapa.width() * 1.2), 2200)
        wys = int(szer * (bbox[3] - bbox[1]) / max(bbox[2] - bbox[0], 1e-6))
        epsg = p.epsg
        self.l_stan.setText("Pobieranie mapy zasadniczej z Geoportalu…")

        class _Pobieracz(QObject):
            gotowe = Signal(object, object)  # (QImage|None, bbox)
            blad = Signal(str)

            def run(self):
                from . import podklad as _pk
                try:
                    img = _pk.pobierz_mape_zasadnicza(bbox, epsg, szer, wys, sieci=True)
                    dane = img.tobytes("raw", "RGB")
                    qimg = QImage(dane, img.width, img.height, img.width * 3,
                                  QImage.Format_RGB888).copy()
                    wynik = (self.gotowe, (qimg, bbox))
                except Exception as e:  # noqa: BLE001
                    wynik = (self.blad, (str(e),))
                self.moveToThread(QApplication.instance().thread())  # jak w Zadanie.run
                wynik[0].emit(*wynik[1])

        self._watek_podkladu = QThread(self)
        self._pob = _Pobieracz()
        self._pob.moveToThread(self._watek_podkladu)
        self._watek_podkladu.started.connect(self._pob.run)
        self._pob.gotowe.connect(self._podklad_gotowy)
        self._pob.blad.connect(self._podklad_blad)
        self._pob.gotowe.connect(self._watek_podkladu.quit)
        self._pob.blad.connect(self._watek_podkladu.quit)
        self._watek_podkladu.finished.connect(self._sprzatnij_watek_podkladu)
        self._watek_podkladu.start()

    def _podklad_gotowy(self, qimg, bbox):
        if self.mapa.podklad_wlaczony:
            self.mapa.ustaw_podklad(qimg, bbox)
            self.l_stan.setText("Mapa zasadnicza: pobrana")

    def _podklad_blad(self, tekst):
        self.log("Mapa zasadnicza – błąd pobierania: " + tekst)
        self.l_stan.setText("Mapa zasadnicza: błąd pobierania (sprawdź internet)")

    def _sprzatnij_watek_podkladu(self):
        self._watek_podkladu.deleteLater()
        self._watek_podkladu = None
        if self._podklad_oczekuje:  # widok zmienił się w trakcie pobierania
            self._pobierz_podklad_mapy()

    # ================================================================ widoki
    def _wypelnij_tabele(self):
        p = self.projekt
        if not p:
            return
        self.tabela.blockSignals(True)
        slupy = p.slupy_trasa()  # wszystkie słupy (też wykluczone), w kolejności trasy
        self.tabela.setRowCount(len(slupy))
        szary = QColor("#f0f2f5")
        wykl_tlo = QColor("#eceef1")
        for r, w in enumerate(slupy):
            for k, (naglowek, atr, edyt) in enumerate(KOLUMNY):
                if atr == "_wlaczony":
                    it = QTableWidgetItem()
                    it.setFlags((it.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                    it.setCheckState(Qt.Unchecked if w.wykluczony else Qt.Checked)
                    it.setToolTip("Odznacz, aby wyłączyć słup z numeracji i dokumentów")
                    it.setTextAlignment(Qt.AlignCenter)
                else:
                    v = getattr(w, atr)
                    if isinstance(v, float):
                        v = f"{v:.{self.cfg.miejsca_po_przecinku}f}"
                    it = QTableWidgetItem("" if v is None else str(v))
                    if not edyt:
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                        it.setBackground(szary)
                    if atr == "uwagi" and w.uwagi:
                        it.setForeground(QColor("#b35c00"))
                    if atr in ("ulica", "ulica_droga") and w.ulica_zgodna is False:
                        it.setBackground(QColor("#ffe2c2"))
                        it.setToolTip("Ulica z adresu różni się od drogi, przy której stoi słup")
                it.setData(Qt.UserRole, w.id)
                if w.wykluczony:
                    it.setForeground(QColor("#9aa3ae"))
                    if atr not in ("ulica", "ulica_droga"):
                        it.setBackground(wykl_tlo)
                self.tabela.setItem(r, k, it)
        self.tabela.blockSignals(False)
        self.tabela.resizeColumnsToContents()

    def _komorka_zmieniona(self, it: QTableWidgetItem):
        p = self.projekt
        if not p or self.zajety():
            return
        w = p.slupy[it.data(Qt.UserRole)]
        atr = KOLUMNY[it.column()][1]
        if atr == "_wlaczony":
            wykluczony = it.checkState() != Qt.Checked
            if wykluczony != w.wykluczony:
                p.ustaw_wykluczenie(w, wykluczony)
                self._przelicz_po_wykluczeniu()
            return
        tekst = it.text().strip()
        # poprawka zapamiętywana w <projekt>.wt.json - nie przepada przy ponownej analizie
        p.ustaw_pole(w, atr, tekst if atr == "uwagi" else (tekst or None))
        self._sprawdz_zapis_stanu()
        if atr == "gmina":
            p.przypisz_rejony(self.rejony, self.c_rejon.currentData())
            self._wypelnij_tabele()
        elif atr == "ulica":
            self._wypelnij_tabele()
            self._wypelnij_kontrole()
        elif atr == "nr_w_sieci":
            self._wypelnij_kontrole()
        elif atr == "miejscowosc":
            p.planuj()  # grupowanie wg miejscowości mogło się zmienić
            p.odswiez_miejscowosci_arkuszy()  # miejscowości w tabelkach arkuszy
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
            ea = a.etykieta or "(wył.)"
            eb = b.etykieta or "(wył.)"
            it = QTreeWidgetItem(pr, [f"Słupy {ea} – {eb}", f"{d:.2f} m"])
            kolor = czerwony if d > self.cfg.przeslo_blad else pomaranczowy
            for k in (0, 1):
                it.setForeground(k, kolor)
                if d > self.cfg.przeslo_blad:
                    f = it.font(k)
                    f.setBold(True)
                    it.setFont(k, f)
        if bledne:
            pr.setForeground(1, czerwony)

        nz = p.niezgodne_ulice()
        self.b_ulice.setEnabled(bool(nz))
        if p.ulice_sprawdzone:
            spr = sum(1 for w in p.plan if w.ulica_zgodna is not None)
            ul = QTreeWidgetItem([f"Sprawdzenie ulic (drogi OSM do {self.cfg.odl_ulicy:g} m)",
                                  f"niezgodnych {len(nz)} · sprawdzono {spr} z {len(p.plan)}"])
        else:
            ul = QTreeWidgetItem(["Sprawdzenie ulic", "nie wykonano (włącz pobieranie adresów)"])
        ul.setIcon(0, ikona(QStyle.SP_MessageBoxWarning if nz else QStyle.SP_DialogApplyButton))
        for w in nz:
            it = QTreeWidgetItem(ul, [f"Słup {w.etykieta}", f"adres: {w.ulica or '–'}  →  "
                                      f"droga przy słupie: {w.ulica_droga}"])
            it.setForeground(1, QColor("#b35c00"))

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

        wykluczone = [w for w in p.slupy if w.wykluczony]
        wy = QTreeWidgetItem(["Słupy wyłączone z numeracji",
                              f"{len(wykluczone)} (nie trafią do pisma ani zestawień)"])
        wy.setIcon(0, ikona(QStyle.SP_DialogCancelButton if wykluczone
                            else QStyle.SP_DialogApplyButton))
        for w in sorted(wykluczone, key=lambda s: (s.stacja_trafo or "", s.nr_w_sieci or "")):
            opis = w.nr_w_sieci and f"nr w sieci {w.nr_w_sieci}" or f"X={w.geo_x:.2f} Y={w.geo_y:.2f}"
            QTreeWidgetItem(wy, [w.stacja_trafo or "poza strefą", opis])

        poprawki = [k for k, v in p.stan["slupy"].items() if any(a != "wykluczony" for a in v)]
        rp = QTreeWidgetItem(["Ręczne poprawki słupów", f"{len(poprawki)} · zapamiętane w "
                              f"{p.plik_stanu.name}"])
        rp.setIcon(0, ikona(QStyle.SP_DialogSaveButton))
        rp.setToolTip(1, "Poprawki z wykazu (ulica, miejscowość, gmina, rodzaj, typ, nr w sieci, "
                         "uwagi) i wyłączenia słupów są nakładane przy każdej analizie.")
        if p.poprawek_niedopasowanych:
            QTreeWidgetItem(rp, ["Nie pasują do rysunku",
                                 f"{len(p.poprawek_niedopasowanych)} (słup usunięty lub "
                                 "przesunięty o więcej niż 0,5 m)"])

        if p.ostrzezenia:
            o = QTreeWidgetItem(["Ostrzeżenia", str(len(p.ostrzezenia))])
            o.setIcon(0, ikona(QStyle.SP_MessageBoxWarning))
            for t in p.ostrzezenia:
                QTreeWidgetItem(o, ["", t])
        self.drzewo.addTopLevelItems([plan, bk, pr, ul, ar, st, ns, op, wy, rp]
                                     + ([o] if p.ostrzezenia else []))
        plan.setExpanded(True)
        bk.setExpanded(True)
        pr.setExpanded(True)
        ul.setExpanded(True)

    def przyjmij_ulice(self):
        p = self.projekt
        nz = p.niezgodne_ulice() if p else []
        if not nz:
            return
        lista = "".join(f"<li>Słup {w.etykieta}: {w.ulica or '–'} → <b>{w.ulica_droga}</b></li>"
                        for w in nz[:25]) + ("<li>…</li>" if len(nz) > 25 else "")
        if QMessageBox.question(self, "Poprawa ulic", f"Zmienić ulicę dla {len(nz)} słupów?"
                                f"<ul>{lista}</ul>", QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        n = p.przyjmij_ulice_z_drog()
        self.log(f"Poprawiono ulice: {n} słupów")
        self._sprawdz_zapis_stanu()
        self._wypelnij_tabele()
        self._wypelnij_kontrole()

    def _odswiez_podglad(self):
        from . import arkusze as ark
        p = self.projekt
        # mapa z numeracją (działa też bez arkuszy)
        self.mapa.ustaw(p.slupy if p else [], dopasuj=False)
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
        if not p or not p.plan or self.zajety():
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

        if self.cb_pismo.isChecked() or self.cb_rozb.isChecked() or self.cb_upr.isChecked():
            pyt = QMessageBox(QMessageBox.Question, "Układ współrzędnych",
                              "Czy przeliczyć współrzędne słupów w piśmie i zestawieniach "
                              "na układ WGS 84 (szerokość, długość)?\n\n"
                              "Nie = układ PL-2000 projektu."
                              + ("\n\nTabela projektowa zawsze ma współrzędne GPS (WGS 84)."
                                 if self.cb_proj.isChecked() else ""), parent=self)
            b_tak = pyt.addButton("Tak, WGS 84", QMessageBox.YesRole)
            pyt.addButton("Nie, PL-2000", QMessageBox.NoRole)
            b_anuluj = pyt.addButton("Anuluj", QMessageBox.RejectRole)
            pyt.exec()
            if pyt.clickedButton() is b_anuluj:
                self.log("Przerwano – nic nie zapisano.")
                return
            p.cfg.wgs84 = pyt.clickedButton() is b_tak
            self.log("Współrzędne w zestawieniach: " + ("WGS 84" if p.cfg.wgs84 else "PL-2000"))

        operator = self.c_operator.currentData()
        opracowal = self.e_opracowal.text().strip() or None
        data_rys = self.e_data_rys.text().strip() or None
        self.ustawienia.setValue("opracowal", self.e_opracowal.text().strip())
        self.ustawienia.setValue("operator", self.c_operator.currentText())
        self.ustawienia.setValue("rejon", self.c_rejon.currentText())
        self._zapisz_ustawienia_projektu()

        # wszystkie wartości z okna odczytane teraz - zapis idzie w tle (okno nie zamarza)
        arkusze = self.cb_arkusze.isChecked()
        data_od = self.d_od.date().toString("dd.MM.yyyy")
        data_do = self.e_do.text().strip() or "-"
        zadania = []  # (przyrostek pliku, funkcja(cel, zadanie))
        if self.cb_dxf.isChecked():
            zadania.append(("numeracja.dxf", lambda f, z: p.zapisz_dxf(
                f, arkusze, operator, opracowal, data_rys)))
            if arkusze and self.cb_pdf_num.isChecked():
                zadania.append(("numeracja.pdf",
                                lambda f, z: p.zapisz_numeracje_pdf(f, z.log.emit)))
        if self.cb_pismo.isChecked():
            zadania.append(("pismo.docx", lambda f, z: p.zapisz_pismo(f, operator, data_od,
                                                                      data_do)))
        if self.cb_rozb.isChecked():
            zadania.append(("rozbudowana.xlsx", lambda f, z: p.zapisz_rozbudowana(f)))
        if self.cb_upr.isChecked():
            zadania.append(("uproszczona.xls", lambda f, z: p.zapisz_uproszczona(f)))
        if self.cb_proj.isChecked():
            zadania.append(("tabela_projektowa.xlsx", lambda f, z: p.zapisz_projektowa(f)))

        if self.cb_orient.isChecked():
            skala, szarosc = self.c_skala.currentData(), self.cb_szarosc.isChecked()
            zrodlo, trasa = self.c_zrodlo.currentData(), self.cb_trasa_or.isChecked()
            pdf_orient = p.sciezka(kat, "orientacja.pdf") if self.cb_pdf_orient.isChecked() \
                else None

            def orient(f, z):
                o = p.zapisz_orientacje(
                    f, skala, szarosc, operator, opracowal, data_rys, zrodlo, trasa,
                    lambda i, n: z.postep.emit(i, n, f"Pobieranie podkładu: {i}/{n}"),
                    z.log.emit)
                z.log.emit(f"Plan orientacyjny: arkusze {', '.join(a.nazwa for a in o)}")
                if pdf_orient:
                    z.postep.emit(0, 0, "Plan orientacyjny: PDF…")
                    p.zapisz_orientacje_pdf(pdf_orient, z.log.emit)
                    z.log.emit(f"Zapisano: {pdf_orient}")
            zadania.append(("orientacja.dxf", orient))

        def praca(z):
            zapisane, bledy = [], []
            for nr, (przyrostek, f) in enumerate(zadania, start=1):
                cel = p.sciezka(kat, przyrostek)
                z.postep.emit(nr - 1, len(zadania), f"Zapis {cel.name} ({nr}/{len(zadania)})…")
                try:
                    f(cel, z)
                    zapisane.append(cel)
                    z.log.emit(f"Zapisano: {cel}")
                except PermissionError:
                    bledy.append(f"{cel.name}: plik jest otwarty w innym programie.")
                except Exception as e:  # noqa: BLE001
                    bledy.append(f"{cel.name}: {e}")
                    z.log.emit(traceback.format_exc())
            return zapisane, bledy

        def gotowe(wynik):
            zapisane, bledy = wynik
            self.l_stan.setText(f"Zapisano plików: {len(zapisane)}"
                                + (f", błędów: {len(bledy)}" if bledy else ""))
            msg = "Zapisano:\n" + "\n".join(f"• {z.name}" for z in zapisane)
            if bledy:
                QMessageBox.warning(self, "Gotowe z błędami",
                                    msg + "\n\nBłędy:\n" + "\n".join(bledy))
            else:
                QMessageBox.information(self, "Gotowe", msg)
        self._uruchom(praca, gotowe)


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
    kod = app.exec()
    # okno usuwane jawnie przed aplikacją - przypadkowa kolejność sprzątania obiektów Qt
    # przy wyjściu z Pythona potrafi przerwać program (Aborted)
    import shiboken6
    shiboken6.delete(okno)
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
