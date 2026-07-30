# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Konfiguration für die ausführbare Windows-Datei (4T-0182, S-0052).

Diese Datei ist die **eine** Quelle des Builds; sie liegt bewusst im Repository, damit
die Auslieferung wiederholbar ist und nicht an einer Befehlszeile im Gedächtnis hängt.
Anleitung, Voraussetzungen und Fallstricke stehen in der Architektur, Abschnitt „Bau der
ausführbaren Datei".

Aufruf (im Projekt-Wurzelverzeichnis, virtuelle Umgebung aktiv oder über den Pfad):

    .\\.venv\\Scripts\\pyinstaller.exe eu-rechnung.spec

Ergebnis: `dist/<Produktname>/` mit der .exe und ihren Begleitdateien. Das Ergebnis ist
Build-Zwischenstand und Eingangsgröße des Setup-Programms, **keine** portable
Auslieferung (S-0054).

Die Sammlung der Datendateien und die Versionsinfo liegen in `skripte/build_gemeinsam.py`,
weil das Prüf-Binary des Bundle-Selbsttests (`bundle-selbsttest.spec`) dieselbe
Konfiguration braucht; nur dann belegt der Selbsttest etwas über diese Auslieferung.
"""

import sys
from pathlib import Path

_WURZEL = Path(SPECPATH)  # noqa: F821 — von PyInstaller gesetzt
sys.path.insert(0, str(_WURZEL / "skripte"))

from build_gemeinsam import sammle_datas, schreibe_versionsinfo  # noqa: E402

# Dateiname ohne Leerzeichen: Der Anzeigename mit Leerzeichen steht in der Versionsinfo
# und später in der Startmenü-Verknüpfung; ein Dateiname ohne Leerzeichen erspart
# Anführungszeichen in Befehlszeilen und Registry-Einträgen.
_DATEINAME = "SCG-EU-E-Rechnung-Generator"
_ICON = _WURZEL / "eu_rechnung" / "ressourcen" / "icon.ico"
_VERSIONS_DATEI = schreibe_versionsinfo(_WURZEL, _DATEINAME)

a = Analysis(  # noqa: F821
    [str(_WURZEL / "eu_rechnung" / "app.py")],
    pathex=[str(_WURZEL)],
    binaries=[],
    datas=sammle_datas(),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # tkinter wird nirgends genutzt und würde nur Umfang kosten. Weitere Ausschlüsse
    # bewusst nicht: Ein zu enger Ausschluss fällt erst auf dem Zielsystem auf, und der
    # Umfang ist keine Anforderung.
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
    # Fensterlos: Die Anwendung ist eine reine Oberfläche, ein Konsolenfenster daneben
    # wäre ein Fehlerbild.
    console=False,
    icon=str(_ICON),
    version=str(_VERSIONS_DATEI),
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=_DATEINAME,
)
