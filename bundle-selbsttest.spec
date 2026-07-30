# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Konfiguration des Bundle-Selbsttests (4T-0183, S-0053).

Baut `skripte/bundle_selbsttest.py` zu einem Konsolen-Programm, **mit derselben
Datensammlung wie die Auslieferung** (`skripte/build_gemeinsam.py`). Nur deshalb sagt
sein Ergebnis etwas über die ausgelieferte Anwendung aus: Es läuft unter denselben
Bedingungen, also ohne Python-Umgebung und mit Ressourcen ausschließlich aus dem Bundle.

Dieses Artefakt ist ein **Prüfmittel und wird nicht ausgeliefert**; das Setup-Programm
packt allein das Ergebnis von `eu-rechnung.spec` ein.

Aufruf:

    .\\.venv\\Scripts\\pyinstaller.exe bundle-selbsttest.spec
    .\\dist\\bundle-selbsttest\\bundle-selbsttest.exe Daten\\bundle-selbsttest

Konsole bewusst **an**: Das Programm berichtet auf der Standardausgabe und liefert einen
Rückgabewert; ein Fenster braucht es nicht.
"""

import sys
from pathlib import Path

_WURZEL = Path(SPECPATH)  # noqa: F821 — von PyInstaller gesetzt
sys.path.insert(0, str(_WURZEL / "skripte"))

from build_gemeinsam import sammle_datas  # noqa: E402

_DATEINAME = "bundle-selbsttest"

a = Analysis(  # noqa: F821
    [str(_WURZEL / "skripte" / "bundle_selbsttest.py")],
    pathex=[str(_WURZEL)],
    binaries=[],
    datas=sammle_datas(),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=_DATEINAME,
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=_DATEINAME,
)
