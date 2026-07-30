"""Tests des Anschreiben-Bausteins mit den Zuständen erbt/überschrieben (S-0036), offscreen."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from eu_rechnung.ui.anschreiben_feld import AnschreibenFeld


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_erbt_zeigt_vorschau_und_herkunft(qapp):
    feld = AnschreibenFeld()
    feld.setze_wert(None, geerbt_text="STANDARD", herkunft="allgemein.herkunft_standard")
    assert feld._schalter.isChecked() is False
    assert feld._text.toPlainText() == "STANDARD"  # geerbte Vorschau
    assert feld._text.isReadOnly() is True
    assert "globaler Standard" in feld._hinweis.text()  # Schlüssel aufgelöst angezeigt
    assert feld.wert() is None  # erbt


def test_ueberschrieben_traegt_eigenen_text(qapp):
    feld = AnschreibenFeld()
    feld.setze_wert("EIGEN", geerbt_text="STANDARD", herkunft="allgemein.herkunft_standard")
    assert feld._schalter.isChecked() is True
    assert feld._text.toPlainText() == "EIGEN"
    assert feld._text.isReadOnly() is False
    assert feld._hinweis.isHidden() is True
    assert feld.wert() == "EIGEN"


def test_ueberschreiben_aktivieren_uebernimmt_geerbten_text(qapp):
    feld = AnschreibenFeld()
    feld.setze_wert(None, geerbt_text="STANDARD", herkunft="allgemein.herkunft_standard")
    feld._schalter.setChecked(True)  # Überschreiben aktivieren
    assert feld._text.isReadOnly() is False
    assert feld._text.toPlainText() == "STANDARD"  # geerbter Text als Startpunkt
    assert feld.wert() == "STANDARD"


def test_zuruecksetzen_verwirft_und_zeigt_vorschau(qapp):
    feld = AnschreibenFeld()
    feld.setze_wert("EIGEN", geerbt_text="STANDARD", herkunft="allgemein.herkunft_standard")
    feld._schalter.setChecked(False)  # Zurücksetzen auf erbt
    assert feld.wert() is None
    assert feld._text.toPlainText() == "STANDARD"  # wieder die geerbte Vorschau
    assert feld._text.isReadOnly() is True


def test_leerer_ueberschriebener_text_zaehlt_als_erbt(qapp):
    feld = AnschreibenFeld()
    feld.setze_wert("EIGEN", geerbt_text="STANDARD", herkunft="allgemein.herkunft_standard")
    feld._text.setPlainText("   ")
    assert feld.wert() is None  # leer = erbt


def test_aktualisiere_vererbung_frischt_vorschau_nur_im_erbt_zustand(qapp):
    feld = AnschreibenFeld()
    feld.setze_wert(None, geerbt_text="ALT", herkunft="allgemein.herkunft_standard")
    feld.aktualisiere_vererbung(geerbt_text="NEU", herkunft="allgemein.herkunft_kunde")
    assert feld._text.toPlainText() == "NEU"  # neue Vorschau
    assert "Kunde" in feld._hinweis.text()
    # Im überschrieben-Zustand bleibt der eigene Text unangetastet.
    feld.setze_wert("EIGEN", geerbt_text="ALT", herkunft="allgemein.herkunft_kunde")
    feld.aktualisiere_vererbung(geerbt_text="NEU", herkunft="allgemein.herkunft_kunde")
    assert feld._text.toPlainText() == "EIGEN"


def test_geaendert_signal_bei_eingabe(qapp):
    feld = AnschreibenFeld()
    feld.setze_wert("EIGEN", geerbt_text="STANDARD", herkunft="allgemein.herkunft_standard")
    ausgeloest = []
    feld.geaendert.connect(lambda: ausgeloest.append(True))
    feld._text.setPlainText("Neuer Text")
    assert ausgeloest  # geaendert wurde emittiert (setze_wert selbst emittiert nicht)
