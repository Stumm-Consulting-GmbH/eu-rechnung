"""Goldstandard-Tests gegen KoSIT (XRechnung/EN 16931) und veraPDF (PDF/A-3).

Diese Tests bilden die zweistufige Validierung aus E-005 ab: KoSIT und veraPDF
sind die maßgeblichen Java-Validatoren. Sie laufen optional, die Fixtures
`kosit_konfig`/`verapdf_konfig` (conftest.py) skippen automatisch, wenn Java
oder die projektlokalen Werkzeuge unter `werkzeuge/` fehlen.
"""

import re
from decimal import Decimal

import pytest
from facturx import get_facturx_xml_from_pdf

from eu_rechnung.domain import Skonto
from eu_rechnung.export.cii_xml import erzeuge_cii
from eu_rechnung.export.validation import pruefe_kosit, pruefe_verapdf
from eu_rechnung.export.zugferd import erzeuge_zugferd


@pytest.mark.kosit
def test_kosit_cii_valide(beispiel_rechnung, kosit_konfig):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_zugferd_xml_valide(beispiel_rechnung, kosit_konfig):
    """Das aus dem ZUGFeRD extrahierte XML bleibt KoSIT-valide (factur-x bettet
    es unverändert ein, E-008)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    _, xml = get_facturx_xml_from_pdf(zugferd, check_xsd=False, check_schematron=False)
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_ohne_bt10_ungueltig(beispiel_rechnung, kosit_konfig):
    """Fehlende Käuferreferenz (BT-10) verletzt die XRechnung-Regel BR-DE-15."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    kaputt = re.sub(
        rb"<ram:BuyerReference>.*?</ram:BuyerReference>", b"", xml, flags=re.DOTALL
    )
    ergebnis = pruefe_kosit(kaputt, kosit_konfig)
    assert ergebnis.gueltig is False
    assert ergebnis.befunde


@pytest.mark.verapdf
def test_verapdf_zugferd_konform(beispiel_rechnung, verapdf_konfig):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_verapdf(zugferd, verapdf_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_normalfall_valide(beispiel_rechnung, kosit_konfig):
    """Normalsteuerfall (Kategorie S mit Steuersatz) ist KoSIT-valide (S-0079)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.verapdf
def test_verapdf_normalfall_konform(beispiel_rechnung, verapdf_konfig):
    """Das ZUGFeRD-PDF des Normalfalls bleibt PDF/A-3-konform (veraPDF, S-0079)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_verapdf(zugferd, verapdf_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_mit_skonto_valide(beispiel_rechnung, kosit_konfig):
    """Die Skonto-Zeile in BT-20 erfüllt die Regel BR-DE-18 (S-0051 AK4)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_skonto_ohne_abschliessenden_umbruch_ungueltig(beispiel_rechnung, kosit_konfig):
    """BR-DE-18 verlangt einen Zeilenumbruch am Ende der Skonto-Angabe und wertet dessen
    Fehlen als fatal. Der Gegentest belegt, dass die erzeugte Zeile diese Regel scharf
    trifft und nicht nur zufällig durchläuft."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    kaputt = xml.replace(
        b"#PROZENT=2.00#\n</ram:Description>", b"#PROZENT=2.00#</ram:Description>"
    )
    assert kaputt != xml  # der Umbruch stand tatsächlich im XML
    ergebnis = pruefe_kosit(kaputt, kosit_konfig)
    assert ergebnis.gueltig is False
    assert any("BR-DE-18" in befund for befund in ergebnis.befunde), ergebnis.befunde


@pytest.mark.verapdf
def test_verapdf_mit_skonto_konform(beispiel_rechnung, verapdf_konfig):
    """Das ZUGFeRD-PDF mit Skonto (Sichtteil-Hinweis plus kodierte Zeile) bleibt
    PDF/A-3-konform (S-0051 AK4)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_verapdf(zugferd, verapdf_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_mit_faelligkeitsdatum_valide(beispiel_rechnung, kosit_konfig):
    """Das Fälligkeitsdatum (BT-9) neben BT-20 samt Skonto-Zeile ist KoSIT-valide
    (S-0081 AK5)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.zahlungsfrist = 30
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.verapdf
def test_verapdf_mit_faelligkeitsdatum_konform(beispiel_rechnung, verapdf_konfig):
    """Das ZUGFeRD-PDF mit Fälligkeitsdatum bleibt PDF/A-3-konform (S-0081 AK5)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.zahlungsfrist = 30
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_verapdf(zugferd, verapdf_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_fremdsprachige_rechnung_valide(beispiel_rechnung, kosit_konfig):
    """Eine englischsprachige Rechnung bleibt KoSIT-valide (S-0060 AK4).

    Die Rechnungssprache wirkt ausschließlich auf den Sichtteil und die PDF-Dokumentsprache;
    das XML ist von ihr unberührt und damit unverändert normkonform.
    """
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "en"
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_lehnt_ein_sprachattribut_ab(beispiel_rechnung, kosit_konfig):
    """Gegentest zu E-010: Die Norm lässt im CII keine Sprachangabe zu.

    Belegt scharf, warum S-0060 kein XML-Sprachattribut fordert: Wird `ram:LanguageID`
    ergänzt, schlägt CII-SR-019 an („LanguageID should not be present") und der
    EN-16931-Schematron-Schritt fällt durch. Der Test hält die Entscheidung gegen ein
    späteres, gut gemeintes Nachrüsten fest.
    """
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "en"
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    assert b"LanguageID" not in xml  # der Erzeuger setzt es nicht
    mit_sprache = xml.replace(
        b"</ram:IssueDateTime>",
        b"</ram:IssueDateTime><ram:LanguageID>EN</ram:LanguageID>",
        1,
    )
    assert mit_sprache != xml
    ergebnis = pruefe_kosit(mit_sprache, kosit_konfig)
    assert ergebnis.gueltig is False


@pytest.mark.verapdf
def test_verapdf_fremdsprachige_rechnung_konform(beispiel_rechnung, verapdf_konfig):
    """Das ZUGFeRD-PDF einer fremdsprachigen Rechnung bleibt PDF/A-3-konform (S-0060 AK4).

    Sichert zugleich, dass die ergänzte Dokumentsprache `/Lang` PDF/A nicht verletzt.
    """
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "fr"
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_verapdf(zugferd, verapdf_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.verapdf
def test_zugferd_behaelt_die_dokumentsprache(beispiel_rechnung, verapdf_konfig):
    """factur-x klont das Dokument beim Einbetten; `/Lang` überlebt den Schritt.

    Ohne diesen Nachweis wäre offen, ob die Sprache im ausgelieferten Beleg ankommt oder
    nur in der Vorstufe stand (dieselbe Frage wie beim OutputIntent, E-007).
    """
    from io import BytesIO

    from pypdf import PdfReader

    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "it"
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    assert PdfReader(BytesIO(zugferd)).trailer["/Root"]["/Lang"] == "it"


# --- Dynamische Belegwährung (S-0064, 4T-0134) -----------------------------


@pytest.mark.kosit
def test_kosit_chf_valide(beispiel_rechnung, kosit_konfig):
    """Ein CHF-Beleg ist KoSIT-valide: die dynamisch gesetzte Belegwährung BT-5 bleibt
    normkonform (S-0064 AK3)."""
    rechnung, bestellnummer, _ = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, "CHF")
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.verapdf
def test_verapdf_chf_konform(beispiel_rechnung, verapdf_konfig):
    """Das ZUGFeRD-PDF eines CHF-Belegs bleibt PDF/A-3-konform (veraPDF, S-0064)."""
    rechnung, bestellnummer, _ = beispiel_rechnung
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, "CHF")
    ergebnis = pruefe_verapdf(zugferd, verapdf_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


# --- Kombinierte Vollbelege: mehrere Merkmale zugleich (S-0079/S-0051/S-0081/S-0060, 4T-0169) --


def _kombinierter_vollbeleg(rechnung, *, sprache: str):
    """Konfiguriert den Beispielbeleg auf mehrere Nicht-Standard-Merkmale zugleich.

    Normalsteuerfall mit Steuersatz, Skonto (BT-20), Fälligkeitsdatum aus der Zahlungsfrist
    (BT-9) und eine fremde Rechnungssprache. Die bisherigen Goldstandard-Fälle prüfen jedes
    Merkmal einzeln; hier greifen ihre Schematron-Regeln in einem Beleg zusammen, wie er in der
    Praxis entsteht.
    """
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    rechnung.zahlungsfrist = 30
    rechnung.rechnungssprache = sprache
    return rechnung


@pytest.mark.kosit
def test_kosit_kombinierter_vollbeleg_eur_valide(beispiel_rechnung, kosit_konfig):
    """Normalsteuer, Skonto, Fälligkeit und französische Rechnungssprache in einem EUR-Beleg."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    _kombinierter_vollbeleg(rechnung, sprache="fr")
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.verapdf
def test_verapdf_kombinierter_vollbeleg_eur_konform(beispiel_rechnung, verapdf_konfig):
    """Das ZUGFeRD-PDF desselben kombinierten EUR-Belegs bleibt PDF/A-3-konform."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    _kombinierter_vollbeleg(rechnung, sprache="fr")
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    ergebnis = pruefe_verapdf(zugferd, verapdf_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.kosit
def test_kosit_kombinierter_vollbeleg_chf_valide(beispiel_rechnung, kosit_konfig):
    """Derselbe Merkmals-Mix in Fremdwährung CHF und spanischer Rechnungssprache."""
    rechnung, bestellnummer, _ = beispiel_rechnung
    _kombinierter_vollbeleg(rechnung, sprache="es")
    xml = erzeuge_cii(rechnung, bestellnummer, "CHF")
    ergebnis = pruefe_kosit(xml, kosit_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde


@pytest.mark.verapdf
def test_verapdf_kombinierter_vollbeleg_chf_konform(beispiel_rechnung, verapdf_konfig):
    """Das ZUGFeRD-PDF des kombinierten CHF-Belegs bleibt PDF/A-3-konform."""
    rechnung, bestellnummer, _ = beispiel_rechnung
    _kombinierter_vollbeleg(rechnung, sprache="es")
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, "CHF")
    ergebnis = pruefe_verapdf(zugferd, verapdf_konfig)
    assert ergebnis.gueltig is True, ergebnis.befunde
