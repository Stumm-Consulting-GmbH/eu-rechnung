"""Tests der Anschreiben-Auflösung entlang der Vererbungskaskade (S-0034)."""

from datetime import date

from eu_rechnung.domain import Adresse, Bestellung, Einstellungen, Kunde
from eu_rechnung.services import effektiver_anschreibentext


def _einstellungen(standard="STANDARD"):
    return Einstellungen(standard_anschreibentext=standard)


def _kunde(text):
    return Kunde(
        id="k1",
        kundennummer="D1",
        name="Kunde",
        adresse=Adresse(strasse="", plz="", ort="", land="DE"),
        email="",
        umsatzsteuer_id="",
        reverse_charge=False,
        anschreibentext=text,
    )


def _bestellung(text):
    return Bestellung(
        id="b1",
        bestellnummer="B1",
        beginn_datum=date(2026, 1, 1),
        ende_datum=date(2026, 1, 31),
        zahlungsfrist=30,
        zahlungsbedingung="",
        anschreibentext=text,
    )


def test_rueckfall_auf_standard_ohne_ebene():
    e = _einstellungen("STD")
    assert effektiver_anschreibentext(e) == "STD"
    assert effektiver_anschreibentext(e, kunde=_kunde(None), bestellung=_bestellung(None)) == "STD"


def test_kunde_ueberschreibt_standard():
    assert effektiver_anschreibentext(_einstellungen("STD"), kunde=_kunde("KUNDE")) == "KUNDE"


def test_bestellung_ist_speziellste_ebene():
    ergebnis = effektiver_anschreibentext(
        _einstellungen("STD"), kunde=_kunde("KUNDE"), bestellung=_bestellung("BEST")
    )
    assert ergebnis == "BEST"


def test_vorschau_bestellung_erbt_von_kunde_oder_standard():
    e = _einstellungen("STD")
    assert effektiver_anschreibentext(e, kunde=_kunde("KUNDE")) == "KUNDE"
    assert effektiver_anschreibentext(e, kunde=_kunde(None)) == "STD"


def test_aufloesung_veraendert_keine_werte():
    e = _einstellungen("STD")
    k = _kunde("KUNDE")
    b = _bestellung(None)
    effektiver_anschreibentext(e, kunde=k, bestellung=b)
    assert k.anschreibentext == "KUNDE"
    assert b.anschreibentext is None
    assert e.standard_anschreibentext == "STD"
