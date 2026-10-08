# Generator WT

Program numeruje słupy (wierzchołki polilinii na warstwie `!tele`) w pliku DXF. Na tej podstawie tworzy:
- pismo „Zapytanie o możliwość dostępu do słupów elektroenergetycznych” (docx),
- zestawienie `rozbudowana.xlsx` albo `uproszczona.xls`.

## Instalacja

```
pip install -r requirements.txt
```

## Użycie

```
python -m generator_wt.main projekt.dxf
```

Program po kolei:
1. Czyta polilinie `!tele` (każdy wierzchołek to słup; bloki są pomijane) i zamknięte polilinie `!trafo` (zasięgi stacji). Nazwa stacji to tekst z warstwy `!trafo` leżący w obrysie.
2. Pobiera z GUGiK miejscowość, ulicę, kod pocztowy, gminę, powiat, obręb i działkę dla każdego słupa. Układ PL-2000 albo PL-1992 rozpoznaje sam. Wyniki zapisuje w pliku cache.
3. Pokazuje plan numeracji i **pyta o potwierdzenie**. Numeracja jest ciągła i biegnie wzdłuż trasy:
   - słupy w zasięgu jednej stacji trafo mają kolejne numery,
   - poza strefami trafo numery są grupowane według miejscowości.
4. Zapisuje numery na warstwie `!tele_nr` w pliku `projekt_numeracja.dxf`. Oryginał zostaje bez zmian.
5. Daje wybór operatora z listy. Rejon energetyczny dobiera według gminy, a jeśli gmina nie jest przypisana, pyta o wybór.
6. Tworzy `projekt_pismo.docx` oraz `projekt_rozbudowana.xlsx` i/lub `projekt_uproszczona.xls`.

Opcje: `--zestawienie rozbudowana|uproszczona|oba|brak`, `--operator NAZWA`, `--rejon NAZWA`, `--od 01.06.2026`, `--do -`, `--prefiks S`, `--start 1`, `--bez-geokodowania`, `--tak` (bez pytań).

## Pliki

- `szablony/pismo_warunki.docx` to szablon pisma. Program podmienia w nim dane operatora, daty, słup początkowy i końcowy, liczbę słupów oraz tabelę wykazu słupów.
- `dane/slowniki.xlsx` zawiera dwa arkusze:
  - `Operatorzy`: kolumny jak pola w piśmie,
  - `Rejony`: `Nazwa` i `Gminy` (gminy rozdzielone `;`).
- `generator_wt/config.py` przechowuje ustawienia: nazwy warstw, wysokość i odsunięcie tekstu numeru, tolerancję, promień szukania adresu.

## Plan

1. Numeracja w DXF (zrobione).
2. Zestawienia Excel oraz pismo docx z operatorem i rejonem (zrobione, wersja wstępna).
3. Automatyczne uzupełnianie miejscowości, ulicy i gminy z GUGiK (zrobione).
4. Identyfikacja słupów powiązana ze stacjami trafo.
5. GUI albo `.exe`.
