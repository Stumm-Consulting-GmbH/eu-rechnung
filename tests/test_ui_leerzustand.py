"""Tests des Leerzustands beim Programmstart ohne aktive Firma (4T-0080, S-0003).

Prüft, dass das Hauptfenster ohne übergebenen Datenbestand leer startet (keine aktive
Firma, keine fachlichen Reiter, nur Menü und Leerfläche mit „Neue Firma" / „Firma
öffnen") und dass das Anlegen oder Öffnen einer Firma die Reiterleiste freischaltet.
Die Datei-Dialoge (`firma_dialoge`) werden gemockt statt angezeigt; offscreen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

import eu_rechnung.ui.firma_dialoge as firma_dialoge
from eu_rechnung.services import erzeuge_leeren_datenbestand, erzeuge_seed
from eu_rechnung.ui.firma_reiter import FirmaReiter
from eu_rechnung.ui.hauptfenster import HauptFenster, LeerHinweis, Reiter


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_start_ohne_firma_ist_leer(qapp):
    """AK1: Ohne Datenbestand startet das Fenster ohne aktive Firma und leer."""
    fenster = HauptFenster()
    assert fenster._datenbestand is None
    assert isinstance(fenster._leer_hinweis, LeerHinweis)
    assert fenster._stapel.currentWidget() is fenster._leer_hinweis
    assert "keine Firma" in fenster.windowTitle()


def test_leerzustand_baut_keine_fachlichen_reiter(qapp):
    """AK2: Solange keine Firma aktiv ist, gibt es keine fachlichen Reiter."""
    fenster = HauptFenster()
    assert fenster._tabs.count() == 0
    assert fenster._reiter_widgets == {}
    assert fenster._stapel.currentWidget() is not fenster._tabs


def test_leerzustand_bietet_nur_firma_aktionen(qapp):
    """AK3: Die Leerfläche bietet nur „Neue Firma" und „Firma öffnen" an."""
    fenster = HauptFenster()
    texte = {knopf.text() for knopf in fenster._leer_hinweis.findChildren(QPushButton)}
    assert texte == {"Neue Firma…", "Firma öffnen…"}


def test_neue_firma_aus_leerzustand_schaltet_frei(qapp, tmp_path, monkeypatch):
    """AK4: Eine neu angelegte Firma aktiviert die Reiter und springt zur Firma-Maske."""
    fenster = HauptFenster()
    bestand = erzeuge_leeren_datenbestand()
    neu_pfad = tmp_path / "neu.scgr"
    monkeypatch.setattr(
        firma_dialoge, "lege_neue_firma_an", lambda parent=None: (bestand, neu_pfad)
    )
    fenster._neue_firma()
    assert fenster._datenbestand is bestand
    assert fenster._tabs.count() == 7
    assert fenster._stapel.currentWidget() is fenster._tabs
    assert fenster._tabs.currentWidget() is fenster._reiter_widgets[Reiter.FIRMA]


def test_firma_oeffnen_aus_leerzustand_schaltet_frei(qapp, tmp_path, monkeypatch):
    """AK4: Eine geladene Firma aktiviert die Reiter und zeigt ihre Daten an."""
    fenster = HauptFenster()
    bestand = erzeuge_seed()
    bestand.eigene_firma.name = "Firma B"
    b_pfad = tmp_path / "b.scgr"
    monkeypatch.setattr(
        firma_dialoge, "oeffne_firma", lambda parent=None: (bestand, b_pfad)
    )
    fenster._firma_oeffnen()
    assert fenster._datenbestand is bestand
    assert fenster._tabs.count() == 7
    assert fenster._stapel.currentWidget() is fenster._tabs
    reiter = fenster._reiter_widgets[Reiter.FIRMA]
    assert isinstance(reiter, FirmaReiter)
    assert reiter._edits["name"].text() == "Firma B"


def test_titel_verliert_leer_hinweis_mit_aktiver_firma(qapp, tmp_path, monkeypatch):
    """Der Leerzustand-Zusatz im Fenstertitel verschwindet, sobald eine Firma aktiv ist."""
    fenster = HauptFenster()
    assert "keine Firma" in fenster.windowTitle()
    bestand = erzeuge_seed()
    b_pfad = tmp_path / "b.scgr"
    monkeypatch.setattr(
        firma_dialoge, "oeffne_firma", lambda parent=None: (bestand, b_pfad)
    )
    fenster._firma_oeffnen()
    assert "keine Firma" not in fenster.windowTitle()
