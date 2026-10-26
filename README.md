# Generator WT

Program okienkowy, który numeruje słupy (wierzchołki polilinii warstwy `!tele`) w pliku DXF. Na podstawie numeracji tworzy:
- pismo „Zapytanie o możliwość dostępu do słupów elektroenergetycznych” (docx),
- zestawienie rozbudowane (`.xlsx`), uproszczone (`.xls`) i tabelę projektową (`.xlsx`, współrzędne GPS w WGS 84) według szablonów.

## Instalacja (Windows)

1. Zainstaluj Pythona 3.12 lub nowszego z python.org. Przy instalacji zaznacz „Add Python to PATH”.
2. Uruchom `instaluj.bat`.
3. Program uruchamiasz plikiem `Generator WT.bat` albo dwuklikiem w `uruchom.pyw`.

Wersję `.exe` buduje się ręcznie: GitHub → Actions → „Wersja Windows (.exe)” → Run workflow. Lokalnie `buduj_exe.bat` tworzy samodzielny `dist\Generator WT\Generator WT.exe`. Na komputerze, na którym potem uruchamiasz ten plik, nie trzeba instalować Pythona.

## Okno programu

Okno ma interfejs webowy wyświetlany przez Qt WebEngine. Lewy panel zawiera kroki pracy (projekt, zlecenie, numeracja, wyniki), środek mapę OpenLayers w układzie PL-2000 projektu z wykazem słupów, prawy panel „Do sprawdzenia”. Kliknięcie pozycji w „Do sprawdzenia” przybliża mapę do słupa lub przęsła. Na mapie możesz przełączać podkład (OpenStreetMap, ortofotomapa, mapa topograficzna GUGiK) i nakładki (działki i budynki EGiB, sieci GESUT, strefy trafo, arkusze, numery). Jest jasny i ciemny motyw (przycisk ◐).

- `uruchom.pyw --qt` uruchamia poprzednie okno (Qt Widgets). Program przechodzi na nie sam, gdy Qt WebEngine nie jest dostępne.
- `python -m generator_wt.web --przegladarka` uruchamia sam serwer i wypisuje adres do otwarcia w przeglądarce (do testów; zamiast okien wyboru pliku wpisujesz ścieżki).
- Kod interfejsu: `generator_wt/web/` (`api.py` – operacje i dane, `serwer.py` – lokalny serwer pod 127.0.0.1 z tokenem, `okno.py` – okno Qt, `static/` – HTML/CSS/JS, `static/vendor/` – OpenLayers 10.6.1 i proj4 2.15.0 z licencjami).

## Praca z programem

1. **Plik projektowy:** wybierz plik DXF. Analiza uruchamia się sama. Program wtedy:
   - scala wierzchołki leżące bliżej niż 5 m w jeden słup (błędne kliknięcia),
   - wyznacza strefy trafo z polilinii na warstwie `!trafo` i na warstwach o nazwie zaczynającej się od `_trafo`. Niezamknięte polilinie są domykane. Nazwa strefy to numer stacji z opisu (multileader „STACJA TRAFO 05-0792”). Obrysy bez opisu stacji dołączane są do strefy, z którą się stykają,
   - odczytuje rodzaj i typ słupa z opisów „słup nN / P-10/ZN”,
   - odczytuje numery słupów w sieci (np. 9, 9.1) z tekstów na warstwach zaczynających się od `_numery`; identyfikator słupa ma postać `stacja/numer`, np. `05-0743/9.1`,
   - pobiera z GUGiK miejscowość, ulicę, gminę i działkę,
   - sprawdza ulice: porównuje ulicę z najbliższego adresu z nazwanymi drogami z OpenStreetMap w promieniu 30 m od słupu. Niezgodności pokazuje w „Kontroli projektu” i podświetla w wykazie. Przycisk „Przyjmij ulice z dróg” zamienia je na nazwę drogi.
2. **Zlecenie:** wybierz operatora i rejon domyślny. Nowego operatora dodasz przyciskiem „Dodaj operatora po NIP…”: nazwa, adres i REGON pochodzą z GUS (jeśli podasz klucz API REGON) albo z białej listy podatników VAT (MF), a numer wpisu z rejestru przedsiębiorców telekomunikacyjnych UKE. Dane można poprawić przed zapisem. Dla operatora, który już jest na liście, program aktualizuje tylko dane z rejestrów. Rejon dobierany jest według gminy z listy w `dane/slowniki.xlsx`, a dla gmin spoza listy używany jest rejon domyślny. Listy edytujesz przyciskiem „Edytuj listy”.
3. Sprawdź zakładki „Wykaz słupów”, „Mapa” i „Kontrola projektu”. W wykazie możesz poprawić miejscowość, ulicę, gminę, rodzaj i typ słupa oraz uwagi.
   - **Mapa:** zakładka pokazuje trasę `!tele` ze słupami i ich numeracją. Kółko myszy przybliża/oddala, przeciąganie przesuwa widok, „Dopasuj widok” wraca do całości. Klik zaznacza słup, podwójny klik wyłącza go z numeracji (albo włącza z powrotem). Przycisk **„Mapa zasadnicza (Geoportal)”** włącza podkład z usług WMS GUGiK (działki, budynki, numery, użytki + sieci uzbrojenia terenu GESUT) — wygląda jak mapa zasadnicza. Podkład jest domyślnie wyłączony, wymaga internetu i dociąga się dla aktualnego widoku.
   - **Wyłączanie słupów:** każdy słup można wyłączyć z numeracji — w wykazie odznacz pole w kolumnie „W num.”, na mapie kliknij słup i użyj „Wyłącz zaznaczony z numeracji” albo kliknij go podwójnie. Wyłączony słup zostaje na trasie (arkusze i podkład obejmują go nadal), ale nie dostaje numeru i nie trafia do numeracji DXF, pisma ani zestawień. Pozostałe słupy numerowane są dalej ciągle. Lista wyłączonych jest w „Kontroli projektu”.
4. Kliknij **Numeruj i generuj dokumenty**. Program pokaże plan i zapyta o potwierdzenie, a potem o układ współrzędnych w piśmie i zestawieniach: PL-2000 albo WGS 84.

### Numeracja

- Jest ciągła i biegnie wzdłuż trasy. Słupy jednej stacji trafo mają kolejne numery. Słupy poza strefami są grupowane według miejscowości.
- Wygląd odpowiada plikowi `przyklady/numeracja_leader.dxf`: odnośnik (LEADER) z tekstem (MTEXT) o wysokości 3,0, styl GeodText, warstwa `makro-numeracja-punktow`.
- Odnośnik jest kierowany na stronę z dala od linii.
- Poprzednia numeracja na tej warstwie jest zastępowana. Wynik trafia do `*_numeracja.dxf`, a oryginał zostaje bez zmian.

### Kontrola przęseł

W zakładce „Kontrola projektu” są wymienione przęsła dłuższe niż 55 m. Te powyżej 60 m są oznaczone na czerwono.

### Arkusze 1:1000 (w pliku `*_numeracja.dxf`)

- Układy papieru „1”, „2”, „3”… są tworzone z szablonu `szablony/arkusze_wt.dxf` (układ „a (2)”; tabelka jako zwykłe linie i teksty, pola wyszukiwane po etykietach): format A3, kierunek N-S, bez obrotu, skala 1:1000.
- Arkusze są układane wzdłuż trasy tak, żeby było ich jak najmniej. Sąsiednie arkusze mają zakładkę 10 m trasy (zmienisz ją w oknie: „Zakładka arkuszy”). Trasa nie wchodzi pod tabelkę i legendę w prawym dolnym rogu.
- Każdy arkusz ma rzutnię papieru i ustawienia strony A3. Wszystkie teksty mają styl Arial (`WT_Arial`).
- W tabelce program uzupełnia: inwestora (wybrany operator), opracował, datę, numer rysunku, skalę, miejscowości widoczne na arkuszu.
- Obrysy arkuszy z numerami są w modelu na niedrukowalnej warstwie `WT_arkusze`.
- Opcjonalnie arkusze zapisywane są też jako wielostronicowy PDF (`*_numeracja.pdf`): jeden arkusz 1:1000 na stronie A3, rysunek wektorowy razem z tabelką i legendą.

### Plan orientacyjny (`*_orientacja.dxf` + `*_orientacja.jpg`)

- Oddzielny plik z podkładem OSM. Zapasowo, albo jeśli to wybierzesz, używana jest mapa topograficzna GUGiK. Podkład może być w kolorze lub w odcieniach szarości.
- Plan zawiera obrysy arkuszy z numerami, trasę (opcjonalnie) oraz arkusze A3 „0.A”, „0.B”… w skali 1:10 000 lub 1:25 000. Nazwa rysunku: „Plan orientacyjny - układ arkusza”.
- Kafle są pobierane tylko dla widoku arkuszy orientacji z zapasem 10 mm papieru (`zapas_podkladu_mm` w `config.py`).
- Arkusze orientacji, których widoki się stykają lub nakładają, mają jeden wspólny obraz. Arkusze rozłączne mają osobne obrazy: `*_orientacja_1.jpg`, `*_orientacja_2.jpg`…
- Obrazy JPG są podpięte do DXF ścieżką względną. Przenoś je razem z plikiem DXF. Pliki `.jgw` to georeferencja.
- Opcjonalnie plan zapisywany jest też jako PDF (`*_orientacja.pdf`): jeden arkusz orientacji (0.A, 0.B…) na stronie A3, z podkładem mapowym wklejonym pod rysunek wektorowy.

## Pliki

- `szablony/` zawiera szablony pisma (`pismo_warunki.docx`), zestawień (`rozbudowana.xlsx`, `uproszczona.xls`) i arkuszy (`arkusze_wt.dxf`).
- `dane/slowniki.xlsx` ma dwa arkusze:
  - `Operatorzy`,
  - `Rejony`: `Nazwa` (do pisma), `Nazwa skrócona` (do Excela), `Gminy` (rozdzielone `;`).
- `przyklady/` zawiera przykładowy projekt i wzór numeracji.
- `generator_wt/config.py` przechowuje ustawienia: warstwy, wygląd numeracji, tolerancje.

### Plik stanu projektu (`*.wt.json`)

Obok pliku DXF program zapisuje `<projekt>.wt.json`: ręczne poprawki z wykazu (ulica, miejscowość, gmina, rodzaj, typ, nr w sieci, uwagi), słupy wyłączone z numeracji i ustawienia projektu (prefiks, numer startowy, zakładka, operator, rejon, daty umowy). Przy każdej analizie są nakładane na nowo, więc nie przepadają po ponownym otwarciu. Słupy są rozpoznawane po położeniu (do 0,5 m). Usunięcie pliku przywraca dane z rysunku i usług.

## Testy i wersje bibliotek

Wersje bibliotek są przypięte: `requirements.txt` (biblioteki programu), `requirements-dev.txt` (pytest, PyInstaller) i `constraints.txt` (pełny zestaw z zależnościami pośrednimi, sprawdzony z Pythonem 3.12 i 3.14). Testy uruchamiasz poleceniem:

    python -m pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt
    python -m pytest

Testy nie potrzebują internetu (usługi GUGiK i OSM są zastępowane danymi testowymi). Numeracja i ułożenie arkuszy przykładowego projektu są porównywane ze wzorcem `tests/dane/wzorzec.json`. Gdy zmiana algorytmu ma zmienić wynik, odśwież wzorzec poleceniem `python -m tests.wzorzec` i zatwierdź go razem ze zmianą. Na GitHubie testy uruchamiają się przy każdym wypchnięciu zmian (Actions → „Testy”), a budowa `.exe` przerywa się, gdy nie przejdą.

Wiersz poleceń (do automatyzacji): `python -m generator_wt.main projekt.dxf --tak`. Flaga `--pdf` dodaje PDF arkuszy numeracji (i planu orientacyjnego, gdy użyto `--orientacja`).

## Plan

1. Numeracja w DXF, scalanie błędnych kliknięć (zrobione).
2. Pismo i zestawienia według szablonów, listy operatorów i rejonów (zrobione).
3. Adresy z GUGiK (zrobione).
4. Okno programu (zrobione).
5. Arkusze 1:1000, plan orientacyjny, raport przęseł (zrobione).
6. Identyfikacja słupów powiązana ze stacjami trafo.
