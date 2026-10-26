"""Uruchomienie programu Generator WT (okno). Dwuklik w Windows otwiera program bez konsoli.

    uruchom.pyw            - okno z mapą (interfejs webowy w Qt WebEngine)
    uruchom.pyw --qt       - poprzednie okno (Qt Widgets)
    uruchom.pyw --autotest - test spakowanego programu
"""
import sys

if "--autotest" in sys.argv:
    from generator_wt.autotest import uruchom

    raise SystemExit(uruchom())

if "--qt" not in sys.argv:
    try:
        from generator_wt.web.okno import main as okno_web
    except ImportError:  # brak Qt WebEngine - poprzednie okno
        okno_web = None
    if okno_web is not None:
        raise SystemExit(okno_web())

from generator_wt.gui import main

raise SystemExit(main())
