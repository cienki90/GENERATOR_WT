# Generator WT

Program do numeracji wierzchołków warstwy `!tele` w plikach DXF i do tworzenia zestawień w Excelu (`rozbudowana.xlsx` i `uproszczona.xls`).

## Instalacja

```
pip install -r requirements.txt
```

## Etap 1: numeracja w DXF

```
python -m generator_wt.main projekt.dxf                # numeracja ciągła 1..N
python -m generator_wt.main projekt.dxf --osobno       # od nowa w każdej strefie trafo
python -m generator_wt.main projekt.dxf --prefiks S --start 1
```

- Wierzchołki leżące w tym samym miejscu (np. łączenie polilinii) są liczone jako jeden punkt.
- Strefa trafo to zamknięta polilinia na warstwie `!trafo`.
  - Nazwa strefy jest brana z tekstu albo atrybutu bloku leżącego w obrysie.
  - Punkt albo blok w obrysie oznacza samą stację. Numeracja w strefie zaczyna się od wierzchołka położonego najbliżej stacji.
- Numery idą wzdłuż trasy, a odgałęzienia są numerowane po kolei.
- Przed zapisem program pokazuje podsumowanie i pyta o potwierdzenie.
- Wynik jest zapisywany jako `*_numeracja.dxf` (oryginał zostaje bez zmian), na warstwie `!tele_nr`.
- Ustawienia (warstwy, wysokość tekstu, odsunięcie, tolerancja) są w `generator_wt/config.py`.

## Słowniki

Plik `dane/slowniki.xlsx` ma dwa arkusze: `Operatorzy` i `Rejony` (rejony energetyczne). Kolumna `Nazwa` jest wymagana, a pozostałe kolumny można dowolnie rozszerzać.

## Plan

1. Numeracja w DXF (zrobione).
2. Eksport do Excela: rozbudowana `.xlsx` i uproszczona `.xls`.
3. Automatyczne uzupełnianie miejscowości, ulicy i gminy (GUGiK: ULDK i PRG) oraz grupowanie punktów spoza stref według miejscowości.
4. Dokument docx powiązany z wybranym operatorem i rejonem energetycznym.
5. Identyfikacja słupów powiązana ze stacjami trafo.
6. GUI albo `.exe`.
