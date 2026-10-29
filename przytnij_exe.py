"""Usuwa z paczki PyInstallera części Qt, których program nie używa (ok. 790 -> ~450 MB).

    python przytnij_exe.py "dist/Generator WT"

PySide6 dołącza całe Qt: QML, 3D, wykresy, multimedia, tłumaczenia na 50 języków
i wersje debug zasobów WebEngine. Biblioteki Qt6*.dll zostają tylko te, które są
potrzebne (zależności importów PE od modułów .pyd, wtyczek i QtWebEngineProcess.exe).
Po przycięciu warto uruchomić "Generator WT.exe --autotest" (otwiera okno z mapą).
"""
from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

JEZYKI = ("pl", "en-US", "en")  # tłumaczenia Qt i WebEngine, które zostają
# moduły PySide6 importowane przez program (okno webowe i poprzednie okno Qt)
MODULY = {"QtCore", "QtGui", "QtNetwork", "QtPrintSupport", "QtWebChannel", "QtWebEngineCore",
          "QtWebEngineWidgets", "QtWidgets"}
# wtyczki Qt niepotrzebne w oknie programu (QML, pozycjonowanie, klawiatura ekranowa, PDF)
WTYCZKI = ("qmltooling", "position", "platforminputcontexts", "imageformats/qpdf.dll")


def importy_pe(plik: Path) -> set[str]:
    """Nazwy bibliotek DLL importowanych przez plik PE (zwykłe i opóźnione importy)."""
    d = plik.read_bytes()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        return set()
    sekcji, opt_rozm = struct.unpack_from("<H", d, pe + 6)[0], struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    katalogi = opt + (112 if struct.unpack_from("<H", d, opt)[0] == 0x20B else 96)
    sekcje = [struct.unpack_from("<IIII", d, opt + opt_rozm + 40 * i + 8) for i in range(sekcji)]

    def ofs(rva):
        for vrozm, va, rrozm, wsk in sekcje:
            if va <= rva < va + max(vrozm, rrozm):
                return rva - va + wsk
        return None

    def nazwa(rva):
        o = ofs(rva)
        return d[o:d.index(b"\0", o)].decode("ascii", "replace").lower() if o else None

    wynik = set()
    for indeks, rozm, pole in ((1, 20, 12), (13, 32, 4)):  # import / delay import
        rva = struct.unpack_from("<I", d, katalogi + 8 * indeks)[0]
        o = ofs(rva) if rva else None
        while o is not None and o + rozm <= len(d) and any(d[o:o + rozm]):
            n = nazwa(struct.unpack_from("<I", d, o + pole)[0])
            if n:
                wynik.add(n)
            o += rozm
    return wynik


def _rozmiar(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size


def przytnij(paczka: Path) -> int:
    qt = next(paczka.rglob("PySide6/Qt6Core.dll")).parent
    usuniete: list[Path] = []

    usuniete += [x for x in [qt / "qml", *(qt / "plugins" / w for w in WTYCZKI)] if x.exists()]
    usuniete += [f for f in qt.glob("*.pyd") if f.stem not in MODULY]
    usuniete += list(qt.glob("pyside6qml*.dll"))
    zasoby = qt / "resources"
    usuniete += [f for f in zasoby.glob("*") if ".debug." in f.name or "devtools" in f.name]
    tl = qt / "translations"
    usuniete += [f for f in tl.glob("*.qm") if f.stem.split("_", 1)[-1] not in JEZYKI]
    usuniete += [f for f in (tl / "qtwebengine_locales").glob("*.pak") if f.stem not in JEZYKI]

    # biblioteki Qt: domknięcie zależności od tego, co program faktycznie ładuje
    korzenie = [*(f for f in qt.glob("*.pyd") if f.stem in MODULY), qt / "QtWebEngineProcess.exe",
                *(f for f in (qt / "plugins").rglob("*.dll") if f not in usuniete
                  and not any(x in usuniete for x in f.parents))]
    dlle = {f.name.lower(): f for f in qt.glob("*.dll")}
    potrzebne, kolejka = set(), [f for f in korzenie if f.is_file()]
    while kolejka:
        for n in importy_pe(kolejka.pop()):
            if n in dlle and n not in potrzebne:
                potrzebne.add(n)
                kolejka.append(dlle[n])
    usuniete += [f for n, f in dlle.items() if n.startswith("qt6") and n not in potrzebne]

    zysk = 0
    for p in usuniete:
        zysk += _rozmiar(p)
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    return zysk


if __name__ == "__main__":
    katalog = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/Generator WT")
    przed = _rozmiar(katalog)
    zysk = przytnij(katalog)
    print(f"Przycięto paczkę: {przed / 2**20:.0f} MB -> {(przed - zysk) / 2**20:.0f} MB")
