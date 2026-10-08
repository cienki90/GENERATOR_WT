"""Zapis numeracji wierzchołków do pliku DXF."""
from __future__ import annotations

from ezdxf.document import Drawing

from .config import Config
from .model import Wierzcholek


def istniejaca_numeracja(doc: Drawing, cfg: Config) -> int:
    return len(doc.modelspace().query(f'TEXT MTEXT[layer=="{cfg.warstwa_numeracji}"]'))


def usun_numeracje(doc: Drawing, cfg: Config) -> int:
    msp = doc.modelspace()
    stare = list(msp.query(f'TEXT MTEXT[layer=="{cfg.warstwa_numeracji}"]'))
    for e in stare:
        msp.delete_entity(e)
    return len(stare)


def zapisz_numeracje(doc: Drawing, wierzcholki: list[Wierzcholek], cfg: Config) -> None:
    if cfg.warstwa_numeracji not in doc.layers:
        doc.layers.add(cfg.warstwa_numeracji, color=cfg.kolor_numeracji)
    msp = doc.modelspace()
    for w in wierzcholki:
        txt = msp.add_text(
            w.etykieta,
            height=cfg.wysokosc_tekstu,
            dxfattribs={"layer": cfg.warstwa_numeracji},
        )
        txt.set_placement((w.x + cfg.przesuniecie_x, w.y + cfg.przesuniecie_y))
