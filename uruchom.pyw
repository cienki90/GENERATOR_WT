"""Uruchomienie programu Generator WT (okno). Dwuklik w Windows otwiera program bez konsoli."""
import sys

if "--autotest" in sys.argv:
    from generator_wt.autotest import uruchom

    raise SystemExit(uruchom())

from generator_wt.gui import main

raise SystemExit(main())
