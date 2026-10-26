"""Lokalny serwer okna webowego: pliki interfejsu (static/) i wywołania API.

- nasłuchuje tylko na 127.0.0.1 (losowy port),
- API wymaga tokenu (nagłówek X-Token) - inne strony otwarte w przeglądarce nie mogą
  wywołać programu, nawet znając port,
- nagłówek Host musi wskazywać 127.0.0.1/localhost (ochrona przed DNS rebinding),
- dostępne są tylko metody z api.METODY i pliki z katalogu static/.

POST /api/<metoda>  treść: {"args": {...}}  ->  {"ok": true, "wynik": ...}
                                            albo {"ok": false, "blad": "..."}
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .api import METODY, Api, BladApi

STATIC = Path(__file__).resolve().parent / "static"
TYPY = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".md": "text/plain"}


class Serwer:
    def __init__(self, api: Api, port: int = 0):
        self.api = api
        self.token = secrets.token_urlsafe(24)
        serwer = self

        class Obsluga(_Obsluga):
            pass
        Obsluga.serwer = serwer
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Obsluga)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._watek: threading.Thread | None = None

    @property
    def adres(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self) -> "Serwer":
        self._watek = threading.Thread(target=self.httpd.serve_forever, name="wt-serwer",
                                       daemon=True)
        self._watek.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class _Obsluga(BaseHTTPRequestHandler):
    serwer: Serwer
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # bez wpisów do konsoli przy każdym żądaniu
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost")

    def _wyslij(self, kod: int, tresc: bytes, typ: str) -> None:
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(tresc)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(tresc)

    def _json(self, kod: int, dane) -> None:
        self._wyslij(kod, json.dumps(dane, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    def do_GET(self):
        if not self._host_ok():
            return self._wyslij(403, b"", "text/plain")
        sciezka = unquote(urlparse(self.path).path).lstrip("/") or "index.html"
        plik = (STATIC / sciezka).resolve()
        if not plik.is_relative_to(STATIC) or not plik.is_file():
            return self._wyslij(404, b"Nie znaleziono", "text/plain; charset=utf-8")
        typ = TYPY.get(plik.suffix) or mimetypes.guess_type(plik.name)[0] or \
            "application/octet-stream"
        self._wyslij(200, plik.read_bytes(), typ)

    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"ok": False, "blad": "Niedozwolony adres."})
        if not secrets.compare_digest(self.headers.get("X-Token", ""), self.serwer.token):
            return self._json(403, {"ok": False, "blad": "Brak dostępu."})
        sciezka = urlparse(self.path).path
        if not sciezka.startswith("/api/"):
            return self._json(404, {"ok": False, "blad": "Nie znaleziono."})
        metoda = sciezka[len("/api/"):]
        if metoda not in METODY:
            return self._json(404, {"ok": False, "blad": f"Nieznana metoda {metoda}."})
        try:
            dlugosc = int(self.headers.get("Content-Length") or 0)
            tresc = json.loads(self.rfile.read(dlugosc) or b"{}")
            args = tresc.get("args") or {}
            if not isinstance(args, dict):
                raise BladApi("Nieprawidłowe argumenty.")
            wynik = getattr(self.serwer.api, metoda)(**args)
            self._json(200, {"ok": True, "wynik": wynik})
        except BladApi as e:
            self._json(200, {"ok": False, "blad": str(e)})
        except TypeError as e:
            self.serwer.api.log(traceback.format_exc())
            self._json(200, {"ok": False, "blad": f"Nieprawidłowe wywołanie {metoda}: {e}"})
        except Exception as e:  # noqa: BLE001
            self.serwer.api.log(traceback.format_exc())
            self._json(200, {"ok": False, "blad": str(e)})
