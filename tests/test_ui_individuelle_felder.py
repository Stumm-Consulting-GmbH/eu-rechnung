"""Tests des Fünf-Plätze-Bausteins für individuelle Felder (S-0038, S-0040), offscreen."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from eu_rechnung.domain import IndividuellesFeld
from eu_rechnung.ui.individuelle_felder_feld import IndividuelleFelderFeld


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _feld(name, aktiv, wert):
    return IndividuellesFeld(name=name, aktiv=aktiv, wert=wert)


def test_fuenf_plaetze_vorhanden(qapp):
    feld = IndividuelleFelderFeld()
    assert len(feld._plaetze) == 5


def test_setze_und_auslesen(qapp):
    feld = IndividuelleFelderFeld()
    feld.setze_felder([_feld("Projekt", True, "P-1"), _feld("Ref", False, "R-2")])
    ergebnis = [(f.name, f.aktiv, f.wert) for f in feld.felder()]
    assert ergebnis == [("Projekt", True, "P-1"), ("Ref", False, "R-2")]


def test_leere_plaetze_werden_uebersprungen(qapp):
    feld = IndividuelleFelderFeld()
    feld.setze_felder([_feld("Nur eins", True, "x")])
    assert len(feld.felder()) == 1  # die vier leeren Plätze zählen nicht


def test_aktivierung_nur_mit_namen(qapp):
    feld = IndividuelleFelderFeld()
    name, aktiv, _wert = feld._plaetze[0]
    assert aktiv.isEnabled() is False  # ohne Namen gesperrt
    name.setText("Projekt")
    assert aktiv.isEnabled() is True
    aktiv.setChecked(True)
    name.setText("")  # Namen leeren
    assert aktiv.isChecked() is False  # Schalter geht aus
    assert aktiv.isEnabled() is False  # und wird wieder gesperrt


def test_deaktivieren_erhaelt_name_und_wert(qapp):
    feld = IndividuelleFelderFeld()
    feld.setze_felder([_feld("Projekt", True, "P-1")])
    _name, aktiv, _wert = feld._plaetze[0]
    aktiv.setChecked(False)
    ergebnis = feld.felder()
    assert len(ergebnis) == 1
    assert (ergebnis[0].name, ergebnis[0].wert, ergebnis[0].aktiv) == ("Projekt", "P-1", False)


def test_obergrenze_fuenf(qapp):
    feld = IndividuelleFelderFeld()
    feld.setze_felder([_feld(f"F{i}", True, str(i)) for i in range(6)])
    assert len(feld.felder()) == 5  # nur fünf Plätze werden belegt


def test_geaendert_signal(qapp):
    feld = IndividuelleFelderFeld()
    ausgeloest = []
    feld.geaendert.connect(lambda: ausgeloest.append(True))
    feld._plaetze[0][0].setText("Neu")  # Name-Feld ändern
    assert ausgeloest
