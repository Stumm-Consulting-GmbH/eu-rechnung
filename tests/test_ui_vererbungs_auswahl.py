"""Tests des Vererbungs-Auswahlfelds (4T-0132, 4T-0137), offscreen.

Der Baustein trägt vier Felder: die Währung am Kunden und die Rechnungssprache an Kunde,
Bestellung und Rechnung. Geprüft wird er hier einmal für sich, damit die Masken-Tests nur
noch ihre Verdrahtung prüfen müssen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from eu_rechnung.texte import RUECKFALL
from eu_rechnung.ui.sprache import setze_ui_sprache
from eu_rechnung.ui.vererbungs_auswahl import VererbungsAuswahl


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    yield
    setze_ui_sprache(RUECKFALL)


def _auswahl(**kwargs) -> VererbungsAuswahl:
    feld = VererbungsAuswahl(**kwargs)
    feld.setze_optionen([("de", "Deutsch"), ("it", "Italiano")])
    return feld


def _eintraege(feld: VererbungsAuswahl) -> list[tuple[str, object]]:
    box = feld._auswahl
    return [(box.itemText(i), box.itemData(i)) for i in range(box.count())]


def test_erbt_eintrag_steht_vorn_und_nennt_den_wert(qapp):
    feld = _auswahl()
    feld.setze_wert(None, geerbt_anzeige="Deutsch")
    assert _eintraege(feld) == [
        ("erbt (Deutsch)", None),
        ("Deutsch", "de"),
        ("Italiano", "it"),
    ]
    assert feld.wert() is None


def test_eigener_wert_wird_gewaehlt(qapp):
    feld = _auswahl()
    feld.setze_wert("it", geerbt_anzeige="Deutsch")
    assert feld.wert() == "it"


def test_herkunft_erscheint_nur_beim_erben(qapp):
    feld = _auswahl()
    feld.setze_wert(None, geerbt_anzeige="Deutsch", herkunft="allgemein.herkunft_kunde")
    assert feld._hinweis.text() == "Erbt von: Kunde"
    assert feld._hinweis.isVisible() is False  # unsichtbares Elternteil, Text steht

    feld.setze_wert("it", geerbt_anzeige="Deutsch", herkunft="allgemein.herkunft_kunde")
    assert feld._hinweis.isVisible() is False


def test_ohne_herkunft_bleibt_die_zeile_weg(qapp):
    """Die Währung erbt allein von der Standardwährung; eine Herkunft wäre Rauschen."""
    feld = _auswahl()
    feld.setze_wert(None, geerbt_anzeige="EUR")
    assert feld._hinweis.isVisible() is False
    assert feld._hinweis.text() == ""


def test_ohne_erbt_moeglich_fehlt_der_erb_eintrag(qapp):
    """Die Rechnung trägt ihre Sprache als eigenen Wert und erbt nicht (S-0082 AK4)."""
    feld = _auswahl(erbt_moeglich=False)
    feld.setze_wert("de")
    assert _eintraege(feld) == [("Deutsch", "de"), ("Italiano", "it")]
    assert feld.wert() == "de"


def test_unbekannter_bestandswert_bleibt_sichtbar(qapp):
    """Ein gespeicherter Wert darf nicht still auf „erbt" fallen und verloren gehen."""
    feld = _auswahl()
    feld.setze_wert("xx", geerbt_anzeige="Deutsch")
    assert ("xx", "xx") in _eintraege(feld)
    assert feld.wert() == "xx"


def test_aktualisiere_vererbung_haelt_die_wahl(qapp):
    """Wechselt die höhere Ebene, ändert sich die Vorschau, nicht die Entscheidung."""
    feld = _auswahl()
    feld.setze_wert("it", geerbt_anzeige="Deutsch", herkunft="allgemein.herkunft_rueckfall")
    feld.aktualisiere_vererbung(
        geerbt_anzeige="Italiano", herkunft="allgemein.herkunft_kunde"
    )
    assert feld.wert() == "it"  # eigener Wert unberührt
    assert feld._auswahl.itemText(0) == "erbt (Italiano)"


def test_laden_meldet_keine_aenderung(qapp):
    """Sonst stünde der Bestätigen-Knopf nach jedem Maskenwechsel auf „geändert"."""
    feld = _auswahl()
    gesehen = []
    feld.geaendert.connect(lambda: gesehen.append(1))
    feld.setze_wert(None, geerbt_anzeige="Deutsch")
    feld.aktualisiere_vererbung(geerbt_anzeige="Italiano")
    assert gesehen == []


def test_anwenderwechsel_meldet_eine_aenderung(qapp):
    feld = _auswahl()
    feld.setze_wert(None, geerbt_anzeige="Deutsch")
    gesehen = []
    feld.geaendert.connect(lambda: gesehen.append(1))
    feld._auswahl.setCurrentIndex(feld._auswahl.findData("it"))
    assert gesehen == [1]


def test_eintraege_folgen_der_ui_sprache(qapp):
    """Der „erbt"-Text wird beim Setzen gebaut, nicht beim Import (Import-Fallstrick)."""
    setze_ui_sprache("es")
    feld = _auswahl()
    feld.setze_wert(None, geerbt_anzeige="Deutsch", herkunft="allgemein.herkunft_kunde")
    assert feld._auswahl.itemText(0) == "hereda (Deutsch)"
    assert feld._hinweis.text() == "Heredado de: Cliente"
