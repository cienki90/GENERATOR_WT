"""Okno programu: strona interfejsu (static/) w Qt WebEngine + lokalny serwer API.

Okna wyboru pliku/folderu są natywne (Qt) - API wywołuje je z wątku serwera, a one
wykonują się w wątku okna (połączenie blokujące), bo Qt pozwala na okna tylko tam.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QThread, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

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


class OknoWeb(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Generator WT")
        self.resize(1500, 920)
        self.setMinimumSize(1100, 700)
        self.dialogi = Dialogi(self)
        self.api = Api(dialogi=self.dialogi)
        self.serwer = Serwer(self.api).start()
        self.widok = QWebEngineView(self)
        strona = _Strona(self.widok)
        self.widok.setPage(strona)
        ust = strona.settings()
        ust.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        ust.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        self.setCentralWidget(self.widok)
        self.widok.load(QUrl(self.serwer.adres))

    def closeEvent(self, ev):
        if self.api.zajety():
            QMessageBox.information(self, "Trwa praca",
                                    "Program jeszcze pracuje (analiza lub zapis plików). "
                                    "Poczekaj na zakończenie i zamknij okno ponownie.")
            ev.ignore()
            return
        self.serwer.stop()
        super().closeEvent(ev)


def main() -> int:
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # wymagane przez Qt WebEngine
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Generator WT")
    okno = OknoWeb()
    okno.show()
    kod = app.exec()
    # okno usuwane jawnie przed aplikacją (patrz gui.main) - bez losowego "Aborted" przy wyjściu
    import shiboken6
    shiboken6.delete(okno)
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
