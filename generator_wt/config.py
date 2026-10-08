"""Ustawienia programu - nazwy warstw, parametry tekstów, tolerancje, ścieżki."""
from dataclasses import dataclass
from pathlib import Path

KATALOG = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    # Warstwy wejściowe (polilinie; bloki są pomijane)
    warstwa_tele: str = "!tele"
    warstwa_trafo: str = "!trafo"

    # Warstwa, na którą trafiają numery słupów
    warstwa_numeracji: str = "!tele_nr"

    # Parametry tekstu numeru
    wysokosc_tekstu: float = 1.5
    przesuniecie_x: float = 0.8
    przesuniecie_y: float = 0.8
    kolor_numeracji: int = 1  # 1 = czerwony (ACI)

    # Wierzchołki bliżej niż tolerancja [m] traktujemy jako jeden słup
    tolerancja: float = 0.01

    numer_startowy: int = 1
    prefiks: str = ""

    # Grupa dla słupów poza strefami trafo, dla których nie ustalono miejscowości
    grupa_nieznana: str = "NIEUSTALONA MIEJSCOWOŚĆ"

    # Promień szukania najbliższego punktu adresowego [m]
    promien_adresu: int = 300

    # Szablony i słowniki
    szablon_pisma: Path = KATALOG / "szablony" / "pismo_warunki.docx"
    plik_slownikow: Path = KATALOG / "dane" / "slowniki.xlsx"
