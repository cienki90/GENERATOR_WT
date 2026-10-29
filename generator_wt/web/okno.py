"""Okno programu: strona interfejsu (static/) w Qt WebEngine + lokalny serwer API.

Okna wyboru pliku/folderu są natywne (Qt) - API wywołuje je z wątku serwera, a one
wykonują się w wątku okna (połączenie blokujące), bo Qt pozwala na okna tylko tam.

Rysunek można otworzyć, upuszczając go na okno albo na ikonę programu (ścieżka
w wierszu poleceń: "Generator WT.exe" projekt.dwg).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QWidget

from .api import Api
from .serwer import Serwer

# DWG jako domyślny format; DXF i oba naraz w kolejnych filtrach
FILTR_RYSUNKOW = ("Rysunek DWG (*.dwg);;Rysunek DXF (*.dxf);;Rysunki DWG i DXF (*.dwg *.dxf);;"
                  "Wszystkie pliki (*)")


class Dialogi(QObject):
    """Natywne okna wyboru pliku i folderu, wywoływane z dowolnego wątku."""
    _zadanie = Signal(object)

    def __init__(self, rodzic: QMainWindow):
        super().__init__()
        self.rodzic = rodzic
        self._zadanie.connect(self._wykonaj, Qt.BlockingQueuedConnection)

    @Slot(object)
    def _wykonaj(self, zadanie: dict) -> None:
        zadanie["wynik"] = zadanie["funkcja"]()

    def _w_watku_okna(self, funkcja):
        if QThread.currentThread() is QApplication.instance().thread():
            return funkcja()  # już w wątku okna (połączenie blokujące by się zakleszczyło)
        zadanie = {"funkcja": funkcja, "wynik": None}
        self._zadanie.emit(zadanie)
        return zadanie["wynik"]

    def wybierz_plik(self, start: str) -> str | None:
        def f():
            plik, _ = QFileDialog.getOpenFileName(self.rodzic, "Wybierz plik projektu", start,
                                                  FILTR_RYSUNKOW)
            return plik or None
        return self._w_watku_okna(f)

    def wybierz_program(self, start: str) -> str | None:
        def f():
            plik, _ = QFileDialog.getOpenFileName(self.rodzic, "Wskaż ODAFileConverter.exe", start,
                                                  "ODA File Converter (ODAFileConverter.exe);;"
                                                  "Programy (*.exe)")
            return plik or None
        return self._w_watku_okna(f)

    def wybierz_katalog(self, start: str) -> str | None:
        return self._w_watku_okna(
            lambda: QFileDialog.getExistingDirectory(self.rodzic, "Folder wyników", start) or None)


class _Strona(QWebEnginePage):
    """Linki zewnętrzne (np. atrybucja map) otwierane w przeglądarce systemowej."""

    def acceptNavigationRequest(self, url, typ, glowna):
        if url.host() in ("127.0.0.1", "localhost"):
            return True
        if typ == QWebEnginePage.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
        return False

    def createWindow(self, typ):  # target=_blank -> przeglądarka systemowa
        strona = _Strona(self.profile(), self)
        strona.urlChanged.connect(lambda u: (QDesktopServices.openUrl(u), strona.deleteLater()))
        return strona


def _rysunek(mime) -> str | None:
    """Ścieżka pierwszego przeciąganego pliku DWG/DXF albo None."""
    for url in mime.urls() if mime.hasUrls() else []:
        p = url.toLocalFile()
        if p and Path(p).suffix.lower() in (".dwg", ".dxf"):
            return str(Path(p))  # ukośniki jak w Windows
    return None


class _Upuszczanie(QObject):
    """Przeciąganie rysunku na okno. Filtr na całej aplikacji, bo widok strony
    (Chromium) przejmuje zdarzenia przeciągania, zanim dotrą do okna."""

    def __init__(self, okno: "OknoWeb"):
        super().__init__(okno)
        self.okno = okno

    def eventFilter(self, obj, ev):
        typ = ev.type()
        if typ in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop) and                 isinstance(obj, QWidget) and obj.window() is self.okno:
            plik = _rysunek(ev.mimeData())
            if plik is None:
                return False
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
            if typ == QEvent.Drop:
                self.okno.otworz(plik)
            return True
        return False


class OknoWeb(QMainWindow):
    def __init__(self, plik: str | None = None):
        super().__init__()
        self.setWindowTitle("Generator WT")
        self.resize(1500, 920)
        self.setMinimumSize(1100, 700)
        self.dialogi = Dialogi(self)
        self.api = Api(dialogi=self.dialogi)
        self.api.plik_startowy = plik
        self.serwer = Serwer(self.api).start()
        self.widok = QWebEngineView(self)
        strona = _Strona(self.widok)
        self.widok.setPage(strona)
        ust = strona.settings()
        ust.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        ust.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        self.setCentralWidget(self.widok)
        self.widok.load(QUrl(self.serwer.adres))
        self._upuszczanie = _Upuszczanie(self)
        QApplication.instance().installEventFilter(self._upuszczanie)

    def otworz(self, plik: str) -> None:
        """Rysunek upuszczony na okno - interfejs wpisuje ścieżkę i uruchamia analizę."""
        self.raise_()
        self.activateWindow()
        self.widok.page().runJavaScript(f"window.wtOtworzPlik && window.wtOtworzPlik({json.dumps(plik)})")

    def closeEvent(self, ev):
        if self.api.zajety():
            QMessageBox.information(self, "Trwa praca",
                                    "Program jeszcze pracuje (analiza lub zapis plików). "
                                    "Poczekaj na zakończenie i zamknij okno ponownie.")
            ev.ignore()
            return
        QApplication.instance().removeEventFilter(self._upuszczanie)
        self.serwer.stop()
        super().closeEvent(ev)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # wymagane przez Qt WebEngine
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("Generator WT")
    plik = next((a for a in argv[1:] if Path(a).suffix.lower() in (".dwg", ".dxf")
                 and Path(a).is_file()), None)
    okno = OknoWeb(plik)
    okno.show()
    kod = app.exec()
    # okno usuwane jawnie przed aplikacją (patrz gui.main) - bez losowego "Aborted" przy wyjściu
    import shiboken6
    shiboken6.delete(okno)
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
