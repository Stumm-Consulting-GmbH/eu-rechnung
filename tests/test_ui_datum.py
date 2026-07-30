"""Tests des programmweiten Datumsfelds (4T-0076), offscreen.

Prüft den `DatumsFeld`-Baustein (Kalender-Popup aktiv, deutsches Anzeigeformat,
`date`-Round-Trip über `setze_datum`/`datum`) und dass die Rechnungsmaske ihre drei
Datumsfelder über diesen Baustein führt (AK3). Das Klick-Verhalten des Popups
(Tag wählen, übernehmen, schließen) ist Qt-Standard des `QDateEdit`-Kalenders und
wird nicht nachgestellt.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from eu_rechnung.services import erzeuge_seed, vorbelege_rechnung
from eu_rechnung.ui.datums_feld import DatumsFeld
from eu_rechnung.ui.rechnungsmaske import RechnungsMaske


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_datumsfeld_hat_kalender_popup(qapp):
    feld = DatumsFeld()
    assert feld.calendarPopup() is True
    assert feld.calendarWidget() is not None


def test_datumsfeld_round_trip(qapp):
    feld = DatumsFeld()
    feld.setze_datum(date(2026, 7, 10))
    assert feld.datum() == date(2026, 7, 10)


def test_datumsfeld_deutsches_anzeigeformat(qapp):
    feld = DatumsFeld()
    feld.setze_datum(date(2026, 7, 10))
    assert feld.date().toString(feld.displayFormat()) == "10.07.2026"


def _maske(bestand=None):
    bestand = bestand or erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = RechnungsMaske(bestand.artikel)
    maske.zeige(rechnung, bestellung, ist_neu=True)
    return maske, rechnung


def test_rechnungsmaske_datumsfelder_sind_datumsfeld(qapp):
    maske, _ = _maske()
    assert isinstance(maske._datum, DatumsFeld)
    assert isinstance(maske._lz_von, DatumsFeld)
    assert isinstance(maske._lz_bis, DatumsFeld)


def test_rechnungsmaske_datum_round_trip(qapp):
    maske, rechnung = _maske()
    # Vorbelegtes Rechnungsdatum wird angezeigt und zurückgeschrieben (AK3)
    assert maske._datum.datum() == rechnung.rechnungsdatum
    maske._datum.setze_datum(date(2026, 12, 31))
    maske._uebernehme_in_rechnung()
    assert maske.rechnung.rechnungsdatum == date(2026, 12, 31)  # Kopie trägt die Eingabe
