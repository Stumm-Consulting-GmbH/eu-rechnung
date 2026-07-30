"""Tests des Programm-Icons (4T-0181, S-0086).

Prüft die gebündelte Ressource und ihren Ladeweg: Die `.ico` trägt alle von Windows
genutzten Auflösungen, `lade_programm_icon` liefert sie vollständig als `QIcon`, Motiv
und Farben entsprechen der Vorgabe (Eurozeichen `#003399` auf Champagner `#F7E7CE`,
abgerundete Ecken), und ein Fenster im Leerzustand trägt das Symbol.

Nicht automatisiert prüfbar ist, ob das Zeichen bei 16 px **erkennbar** ist; das ist
eine Sichtprüfung an der Musterreihe unter `Daten/icon-muster/`. Der Test hier sichert,
dass die 16-px-Auflösung überhaupt eigenständig vorliegt und nicht erst durch Skalieren
entsteht: Genau das war die Absicht des eigenen Frames je Größe. Offscreen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from eu_rechnung.app import lade_programm_icon
from eu_rechnung.ui.hauptfenster import HauptFenster

# Die Größen, die das Erzeugungsskript schreibt (skripte/icon_erzeugen.py).
GROESSEN = (16, 24, 32, 48, 64, 128, 256)
GRUND = (247, 231, 206)  # #F7E7CE
ZEICHEN = (0, 51, 153)  # #003399


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_icon_traegt_alle_groessen(qapp):
    """AK1: Die Ressource liefert alle sieben Auflösungen von 16 bis 256 px."""
    icon = lade_programm_icon()
    assert not icon.isNull()
    gefunden = sorted({s.width() for s in icon.availableSizes()})
    assert gefunden == sorted(GROESSEN), f"Erwartet {sorted(GROESSEN)}, gefunden {gefunden}"
    # Die kleinste Auflösung liegt eigenständig vor und entsteht nicht durch Skalieren.
    klein = icon.pixmap(16, 16).toImage()
    assert (klein.width(), klein.height()) == (16, 16)


def test_farben_entsprechen_der_vorgabe(qapp):
    """AK2: Grund in Champagner, Zeichen in EU-Blau, exakt in den festgelegten Werten.

    Geprüft wird an der größten Auflösung, weil dort keine Kantenglättung die reinen
    Farbwerte verwischt: Der Grund ist flächig, das Zeichen ebenso.
    """
    bild = lade_programm_icon().pixmap(256, 256).toImage()
    farben = set()
    for x in range(0, 256, 2):
        for y in range(0, 256, 2):
            farbe = bild.pixelColor(x, y)
            farben.add((farbe.red(), farbe.green(), farbe.blue()))
    assert GRUND in farben, "Champagner-Grund fehlt"
    assert ZEICHEN in farben, "EU-blaues Zeichen fehlt"


def test_ecken_sind_abgerundet(qapp):
    """AK2: Die Ecken sind rund, also außerhalb der Fläche durchsichtig.

    Objektiver Beleg für die Rundung: Die äußerste Ecke trägt keine Farbe, die Mitte
    der Kante dagegen den Grund. Ein rechteckiges Symbol fiele hier durch.
    """
    bild = lade_programm_icon().pixmap(256, 256).toImage()
    for x, y in ((1, 1), (254, 1), (1, 254), (254, 254)):
        assert bild.pixelColor(x, y).alpha() == 0, f"Ecke ({x}, {y}) ist nicht durchsichtig"
    for x, y in ((128, 1), (1, 128), (128, 254), (254, 128)):
        farbe = bild.pixelColor(x, y)
        assert (farbe.red(), farbe.green(), farbe.blue()) == GRUND, (
            f"Kantenmitte ({x}, {y}) trägt nicht den Grund"
        )


def test_fenster_traegt_das_programm_icon(qapp):
    """AK4: Ein Fenster im Leerzustand zeigt das Symbol.

    Gesetzt wird es anwendungsweit (`QApplication.setWindowIcon`), wie beim
    Anwendungsstart; ein Fenster ohne eigenes Symbol übernimmt das der Anwendung.
    """
    qapp.setWindowIcon(lade_programm_icon())
    fenster = HauptFenster()
    assert fenster._datenbestand is None, "Vorbedingung: Leerzustand"
    assert not fenster.windowIcon().isNull()
    assert 16 in {s.width() for s in fenster.windowIcon().availableSizes()}
