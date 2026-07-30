"""Tests der Betrags-Formatierung und -Eingabe in der UI-Sprache (S-0059, 4T-0129).

Der Rundlauf ist der Kern: Was `format_betrag` anzeigt, muss `parse_betrag` in derselben
Sprache verlustfrei zurücklesen. Vor 4T-0129 las der Baustein fest deutsch; in einer
englischen Oberfläche wurde aus der Eingabe `1,200.00` der Wert 1,2 statt 1.200. Auf einer
Rechnung ist das ein Betragsfehler, kein Darstellungsdetail.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from decimal import Decimal

import pytest

from eu_rechnung.texte import SPRACHEN
from eu_rechnung.ui.betrag import format_betrag, parse_betrag
from eu_rechnung.ui.sprache import setze_ui_sprache


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    yield
    setze_ui_sprache("de")


_WERTE = [Decimal("0.05"), Decimal("1200"), Decimal("16900.50"), Decimal("1234567.89")]


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize("wert", _WERTE)
def test_rundlauf_je_sprache(sprache, wert):
    """Die eigene Anzeige muss in jeder Sprache verlustfrei rücklesbar sein."""
    assert parse_betrag(format_betrag(wert, sprache), sprache) == wert


def test_anzeige_je_sprache():
    assert format_betrag(Decimal("1234567.89"), "de") == "1.234.567,89"
    assert format_betrag(Decimal("1234567.89"), "en") == "1,234,567.89"
    assert format_betrag(Decimal("1234567.89"), "fr") == "1 234 567,89"


def test_englische_eingabe_wird_richtig_gelesen():
    """Der Fehler, der 4T-0129 ausgelöst hat: 1,200.00 ergab 1,2."""
    assert parse_betrag("1,200.00", "en") == Decimal("1200.00")
    assert parse_betrag("16,900.50", "en") == Decimal("16900.50")


def test_deutsches_verhalten_bleibt_unveraendert():
    """Bestandsverhalten: volles Format und einfache Eingabe, wie vor der Umstellung."""
    assert parse_betrag("1.200,00", "de") == Decimal("1200.00")
    assert parse_betrag("1200.00", "de") == Decimal("1200.00")  # Punkt als Dezimaltrenner
    assert parse_betrag("1200", "de") == Decimal("1200")


def test_franzoesische_eingabe_mit_gewoehnlichem_leerzeichen():
    """Der Trenner ist ein geschütztes Leerzeichen; getippt wird ein gewöhnliches."""
    assert parse_betrag("1 200,00", "fr") == Decimal("1200.00")
    assert parse_betrag("1 200,00", "fr") == Decimal("1200.00")


@pytest.mark.parametrize("eingabe", ["", "   ", "abc", "1.2.3,4,5"])
def test_ungueltige_eingabe_ergibt_none(eingabe):
    assert parse_betrag(eingabe, "de") is None


def test_ohne_sprachangabe_gilt_die_aktive_ui_sprache():
    setze_ui_sprache("en")
    assert format_betrag(Decimal("1200")) == "1,200.00"
    assert parse_betrag("1,200.00") == Decimal("1200.00")
    setze_ui_sprache("de")
    assert format_betrag(Decimal("1200")) == "1.200,00"
    assert parse_betrag("1.200,00") == Decimal("1200.00")
