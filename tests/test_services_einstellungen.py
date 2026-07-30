"""Tests der Einstellungen-Prüfung (S-0035, S-0044, S-0062)."""

import pytest

from eu_rechnung.domain import Einstellungen
from eu_rechnung.services import erzeuge_seed, pruefe_einstellungen, waehrung_referenziert


def test_leerer_standardtext_wird_abgelehnt():
    befunde = pruefe_einstellungen(Einstellungen(standard_anschreibentext="   "))
    assert any(b.feld == "standard_anschreibentext" for b in befunde)


def test_nicht_leerer_standardtext_ist_valide():
    assert pruefe_einstellungen(Einstellungen(standard_anschreibentext="Sehr geehrte")) == []


def test_nicht_positive_debitornummer_wird_abgelehnt():
    befunde = pruefe_einstellungen(
        Einstellungen(standard_anschreibentext="Text", naechste_debitornummer=0)
    )
    assert any(b.feld == "debitornummer" for b in befunde)


def test_ungueltiges_jahr_wird_abgelehnt():
    befunde = pruefe_einstellungen(
        Einstellungen(standard_anschreibentext="Text", naechste_rechnungsnummer={"26": 10001})
    )
    assert any(b.feld == "rechnungsnummer" for b in befunde)


def test_nicht_positiver_jahres_zaehler_wird_abgelehnt():
    befunde = pruefe_einstellungen(
        Einstellungen(standard_anschreibentext="Text", naechste_rechnungsnummer={"2026": 0})
    )
    assert any(b.feld == "rechnungsnummer" for b in befunde)


def test_gueltige_nummernkreise_sind_valide():
    befunde = pruefe_einstellungen(
        Einstellungen(
            standard_anschreibentext="Text",
            naechste_debitornummer=10005,
            naechste_rechnungsnummer={"2026": 10010, "2027": 10001},
        )
    )
    assert befunde == []


# --- Währungsliste und Standardwährung (S-0062 AK1/AK2) ----------------------


def _einstellungen(**anpassungen) -> Einstellungen:
    basis = dict(standard_anschreibentext="Text")
    basis.update(anpassungen)
    return Einstellungen(**basis)


def test_leere_waehrungsliste_wird_abgelehnt():
    """AK1: Ohne Währung ließe sich keine Bestellung mehr anlegen."""
    befunde = pruefe_einstellungen(_einstellungen(waehrungsliste=[]))
    assert any(
        b.feld == "waehrungsliste" and b.schluessel == "einstellungen.fehlt_waehrungsliste"
        for b in befunde
    )


@pytest.mark.parametrize("code", ["eur", "EU", "EURO", "E1R", "", " EUR"])
def test_ungueltiger_waehrungscode_wird_abgelehnt(code):
    """AK1: ISO 4217 sind genau drei Großbuchstaben; alles andere ist ein Tippfehler."""
    befunde = pruefe_einstellungen(
        _einstellungen(waehrungsliste=[code], standardwaehrung=code)
    )
    assert any(
        b.feld == "waehrungsliste" and b.schluessel == "einstellungen.waehrung_format"
        for b in befunde
    )


def test_doppelte_waehrung_wird_abgelehnt():
    befunde = pruefe_einstellungen(_einstellungen(waehrungsliste=["EUR", "CHF", "EUR"]))
    assert any(b.schluessel == "einstellungen.waehrung_doppelt" for b in befunde)


def test_standardwaehrung_muss_in_der_liste_stehen():
    """AK2: Sonst erbte der Kunde einen Wert, den die Auswahl nicht anbietet."""
    befunde = pruefe_einstellungen(
        _einstellungen(waehrungsliste=["EUR"], standardwaehrung="USD")
    )
    assert any(
        b.feld == "standardwaehrung"
        and b.schluessel == "einstellungen.standardwaehrung_nicht_in_liste"
        for b in befunde
    )


def test_leere_liste_meldet_nicht_zusaetzlich_die_standardwaehrung():
    """Eine Ursache, ein Befund: Bei leerer Liste ist die Liste das Problem."""
    befunde = pruefe_einstellungen(_einstellungen(waehrungsliste=[]))
    assert not any(b.feld == "standardwaehrung" for b in befunde)


def test_gueltige_waehrungen_sind_valide():
    assert (
        pruefe_einstellungen(
            _einstellungen(waehrungsliste=["EUR", "CHF"], standardwaehrung="CHF")
        )
        == []
    )


# --- Löschschutz (S-0062) ----------------------------------------------------


def test_standardwaehrung_ist_referenziert():
    bestand = erzeuge_seed()
    befund = waehrung_referenziert(bestand, bestand.einstellungen.standardwaehrung)
    assert befund is not None
    assert befund.schluessel == "einstellungen.fundstelle_standardwaehrung"


def test_unbenutzte_waehrung_ist_loeschbar():
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "JPY"]
    assert waehrung_referenziert(bestand, "JPY") is None


def test_waehrung_eines_kunden_ist_referenziert():
    bestand = erzeuge_seed()
    bestand.kunden[0].waehrung = "JPY"
    befund = waehrung_referenziert(bestand, "JPY")
    assert befund is not None
    assert befund.schluessel == "einstellungen.fundstelle_kunde"
    assert befund.werte == {"name": bestand.kunden[0].name}


def test_belegwaehrung_einer_bestellung_ist_referenziert():
    bestand = erzeuge_seed()
    bestellung = bestand.kunden[0].bestellungen[0]
    bestellung.waehrung = "JPY"
    befund = waehrung_referenziert(bestand, "JPY")
    assert befund is not None
    assert befund.schluessel == "einstellungen.fundstelle_bestellung"
    assert befund.werte == {"nummer": bestellung.bestellnummer}


def test_preiswaehrung_eines_artikels_ist_referenziert():
    bestand = erzeuge_seed()
    bestand.artikel[0].vorschlagspreis.waehrung = "JPY"
    befund = waehrung_referenziert(bestand, "JPY")
    assert befund is not None
    assert befund.schluessel == "einstellungen.fundstelle_artikel"


def test_waehrung_einer_bankverbindung_ist_referenziert():
    bestand = erzeuge_seed()
    bestand.eigene_firma.bankverbindungen[0].waehrung = "JPY"
    befund = waehrung_referenziert(bestand, "JPY")
    assert befund is not None
    assert befund.schluessel == "einstellungen.fundstelle_bankverbindung"
