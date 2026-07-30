"""Tests der Währungs-Auflösung entlang der Vererbungskaskade (S-0063)."""

from eu_rechnung.domain import Adresse, Einstellungen, Kunde
from eu_rechnung.services import effektive_waehrung


def _einstellungen(standardwaehrung="EUR"):
    return Einstellungen(
        standard_anschreibentext="STANDARD", standardwaehrung=standardwaehrung
    )


def _kunde(waehrung):
    return Kunde(
        id="k1",
        kundennummer="D1",
        name="Kunde",
        adresse=Adresse(strasse="", plz="", ort="", land="DE"),
        email="",
        umsatzsteuer_id="",
        reverse_charge=False,
        waehrung=waehrung,
    )


def test_rueckfall_auf_standardwaehrung_ohne_kundenwert():
    e = _einstellungen("EUR")
    assert effektive_waehrung(e) == "EUR"
    assert effektive_waehrung(e, kunde=_kunde(None)) == "EUR"


def test_kunde_ueberschreibt_standardwaehrung():
    assert effektive_waehrung(_einstellungen("EUR"), kunde=_kunde("CHF")) == "CHF"


def test_vorschau_kunde_erbt_die_standardwaehrung():
    # Die eigene Ebene weggelassen: der für einen Kunden geerbte Wert ist nur die Standardwährung.
    assert effektive_waehrung(_einstellungen("CHF")) == "CHF"


def test_aufloesung_veraendert_keine_werte():
    e = _einstellungen("EUR")
    k = _kunde("CHF")
    effektive_waehrung(e, kunde=k)
    assert k.waehrung == "CHF"
    assert e.standardwaehrung == "EUR"
