"""Tests der Firma-Validierung (`pruefe_firma`, S-0004), Java-frei.

Prüft die zweistufige Pflicht (EN vs. aktive XRechnung), die Bankverbindungs-Regeln
und die Formatprüfungen (IBAN-Prüfziffer, E-Mail, BIC).
"""

from eu_rechnung.domain import Adresse, Bankverbindung, EigeneFirma
from eu_rechnung.services import pruefe_firma


def _firma(**anpassungen) -> EigeneFirma:
    basis = dict(
        name="Muster Consulting GmbH",
        adresse=Adresse(
            strasse="Musterstrasse", plz="4000", ort="Basel", land="CH", hausnummer="1"
        ),
        mehrwertsteuer_id="CHE-999.999.999 MWST",
        email="kontakt@example.com",
        telefon="+41 44 123 45 67",
        kontakt_name="Max Muster",
        bankverbindungen=[
            Bankverbindung(
                kontoinhaber="Muster Consulting GmbH",
                bank="Beispielbank",
                iban="CH09 0000 0000 0000 0000 1",
                bic="MUSTCHZZ",
                waehrung="EUR",
            )
        ],
        xrechnung_aktiv=True,
    )
    basis.update(anpassungen)
    return EigeneFirma(**basis)


def test_vollstaendige_firma_ist_gueltig():
    assert pruefe_firma(_firma()) == []


def test_xrechnung_verlangt_bankverbindung():
    befunde = pruefe_firma(_firma(bankverbindungen=[]))
    assert any(
        b.feld == "bank" and b.schluessel == "firma.xr_pflicht_bank" for b in befunde
    )


def test_ohne_xrechnung_keine_bankverbindung_noetig():
    # EN-Pflicht erfüllt, keine Bankverbindung erzwungen
    assert pruefe_firma(_firma(xrechnung_aktiv=False, bankverbindungen=[])) == []


def test_en_pflichtfelder_fehlen():
    befunde = pruefe_firma(_firma(xrechnung_aktiv=False, name="", mehrwertsteuer_id=""))
    felder = {b.feld for b in befunde}
    assert "name" in felder
    assert "mwst" in felder


def test_xrechnung_pflichtfelder_fehlen():
    befunde = pruefe_firma(_firma(kontakt_name="", telefon=""))
    felder = {b.feld for b in befunde}
    assert "kontakt" in felder
    assert "telefon" in felder


def test_ungueltige_iban_faellt_auf():
    firma = _firma(
        bankverbindungen=[
            Bankverbindung(
                kontoinhaber="X", bank="Y", iban="CH00 0000 0000 0000 0000 0",
                bic="", waehrung="EUR",
            )
        ]
    )
    assert any(
        b.feld == "bank" and b.schluessel == "firma.bank_iban_ungueltig"
        for b in pruefe_firma(firma)
    )


def test_ungueltige_email_faellt_auf():
    assert any(
        b.feld == "email" and b.schluessel == "allgemein.email_format"
        for b in pruefe_firma(_firma(email="kein-email"))
    )


def test_ungueltiger_bic_faellt_auf():
    firma = _firma(
        bankverbindungen=[
            Bankverbindung(
                kontoinhaber="X", bank="Y", iban="CH09 0000 0000 0000 0000 1",
                bic="ABC", waehrung="EUR",
            )
        ]
    )
    assert any(
        b.feld == "bank" and b.schluessel == "firma.bank_bic_ungueltig"
        for b in pruefe_firma(firma)
    )
