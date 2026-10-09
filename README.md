# Generator WT

Program okienkowy, który numeruje słupy (wierzchołki polilinii warstwy `!tele`) w pliku DXF. Na podstawie numeracji tworzy:
- pismo „Zapytanie o możliwość dostępu do słupów elektroenergetycznych” (docx),
- zestawienie rozbudowane (`.xlsx`), uproszczone (`.xls`) i tabelę projektową (`.xlsx`, współrzędne GPS w WGS 84) według szablonów.

## Instalacja (Windows)

1. Zainstaluj Pythona 3.11 lub nowszego z python.org. Przy instalacji zaznacz „Add Python to PATH”.
2. Uruchom `instaluj.bat`.
3. Program uruchamiasz plikiem `Generator WT.bat` albo dwuklikiem w `uruchom.pyw`.

Opcjonalnie `buduj_exe.bat` tworzy samodzielny `dist\Generator WT\Generator WT.exe`. Na komputerze, na którym potem uruchamiasz ten plik, nie trzeba instalować Pythona.

## Praca z programem

1. **Plik projektowy:** wybierz plik DXF. Analiza uruchamia się sama. Program wtedy:
   - scala wierzchołki leżące bliżej niż 5 m w jeden słup (błędne kliknięcia),
   - wyznacza strefy trafo z polilinii na warstwie `!trafo` i na warstwach o nazwie zaczynającej się od `_trafo`. Niezamknięte polilinie są domykane. Nazwa strefy to numer stacji z opisu (multileader „STACJA TRAFO 05-0792”). Obrysy bez opisu stacji dołączane są do strefy, z którą się stykają,
   - odczytuje rodzaj i typ słupa z opisów „słup nN / P-10/ZN”,
   - odczytuje numery słupów w sieci (np. 9, 9.1) z tekstów na warstwach zaczynających się od `_numery`; identyfikator słupa ma postać `stacja/numer`, np. `05-0743/9.1`,
   - pobiera z GUGiK miejscowość, ulicę, gminę i działkę,
   - sprawdza ulice: porównuje ulicę z najbliższego adresu z nazwanymi drogami z OpenStreetMap w promieniu 30 m od słupu. Niezgodności pokazuje w „Kontroli projektu” i podświetla w wykazie. Przycisk „Przyjmij ulice z dróg” zamienia je na nazwę drogi.
2. **Zlecenie:** wybierz operatora i rejon domyślny. Rejon dobierany jest według gminy z listy w `dane/slowniki.xlsx`, a dla gmin spoza listy używany jest rejon domyślny. Listy edytujesz przyciskiem „Edytuj listy”.
3. Sprawdź zakładki „Wykaz słupów” i „Kontrola projektu”. W wykazie możesz poprawić miejscowość, ulicę, gminę, rodzaj i typ słupa oraz uwagi.
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

### Plan orientacyjny (`*_orientacja.dxf` + `*_orientacja.jpg`)

- Oddzielny plik z podkładem OSM. Zapasowo, albo jeśli to wybierzesz, używana jest mapa topograficzna GUGiK. Podkład może być w kolorze lub w odcieniach szarości.
- Plan zawiera obrysy arkuszy z numerami, trasę (opcjonalnie) oraz arkusze A3 „0.A”, „0.B”… w skali 1:10 000 lub 1:25 000. Nazwa rysunku: „Plan orientacyjny - układ arkusza”.
- Kafle są pobierane tylko dla widoku arkuszy orientacji z zapasem 10 mm papieru (`zapas_podkladu_mm` w `config.py`).
- Arkusze orientacji, których widoki się stykają lub nakładają, mają jeden wspólny obraz. Arkusze rozłączne mają osobne obrazy: `*_orientacja_1.jpg`, `*_orientacja_2.jpg`…
- Obrazy JPG są podpięte do DXF ścieżką względną. Przenoś je razem z plikiem DXF. Pliki `.jgw` to georeferencja.

## Pliki

- `szablony/` zawiera szablony pisma (`pismo_warunki.docx`), zestawień (`rozbudowana.xlsx`, `uproszczona.xls`) i arkuszy (`arkusze_wt.dxf`).
- `dane/slowniki.xlsx` ma dwa arkusze:
  - `Operatorzy`,
  - `Rejony`: `Nazwa` (do pisma), `Nazwa skrócona` (do Excela), `Gminy` (rozdzielone `;`).
- `przyklady/` zawiera przykładowy projekt i wzór numeracji.
- `generator_wt/config.py` przechowuje ustawienia: warstwy, wygląd numeracji, tolerancje.

Wiersz poleceń (do automatyzacji): `python -m generator_wt.main projekt.dxf --tak`.

## Plan

1. Numeracja w DXF, scalanie błędnych kliknięć (zrobione).
2. Pismo i zestawienia według szablonów, listy operatorów i rejonów (zrobione).
3. Adresy z GUGiK (zrobione).
4. Okno programu (zrobione).
5. Arkusze 1:1000, plan orientacyjny, raport przęseł (zrobione).
6. Identyfikacja słupów powiązana ze stacjami trafo.
