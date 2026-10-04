"""Startskript fuer PyInstaller (absolute Importe, damit das Paket sauber eingebunden wird)."""

from wissens_manager.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
