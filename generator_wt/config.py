"""Ustawienia programu - nazwy warstw, parametry tekstów, tolerancje."""
from dataclasses import dataclass


@dataclass
class Config:
    # Warstwy wejściowe
    warstwa_tele: str = "!tele"
    warstwa_trafo: str = "!trafo"

    # Warstwa, na którą trafiają numery wierzchołków
    warstwa_numeracji: str = "!tele_nr"

    # Parametry tekstu numeru
    wysokosc_tekstu: float = 1.5
    przesuniecie_x: float = 0.8
    przesuniecie_y: float = 0.8
    kolor_numeracji: int = 1  # 1 = czerwony (ACI)

    # Wierzchołki bliżej niż tolerancja [m] traktujemy jako jeden punkt
    tolerancja: float = 0.01

    # Numer początkowy i prefiks (np. "S" -> S1, S2...)
    numer_startowy: int = 1
    prefiks: str = ""

    # Nazwa grupy dla wierzchołków poza zasięgiem jakiejkolwiek stacji trafo
    # (docelowo zostaną pogrupowane wg miejscowości - etap geokodowania)
    grupa_poza_strefa: str = "POZA STREFĄ TRAFO"
