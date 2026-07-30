"""Tests des CII-XML-Exports (`cii_xml.py`), Java-frei.

Geprüft werden die tragenden EN-16931-/XRechnung-Merkmale des erzeugten XML
(über gezielte Substrings) sowie die eingebaute XSD-Gültigkeit. Die
KoSIT-Schematron-Prüfung ist der Goldstandard und liegt in 4T-0021.
"""

from decimal import Decimal

from eu_rechnung.domain import Skonto
from eu_rechnung.export.cii_xml import (
    BUSINESS_PROCESS,
    GUIDELINE_XRECHNUNG,
    erzeuge_cii,
)
from eu_rechnung.export.validation import pruefe_xsd


def test_cii_schluesselmerkmale(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    # XRechnung-CIUS-Kennung (BT-24) und Geschäftsprozess (BT-23)
    assert GUIDELINE_XRECHNUNG in xml
    assert BUSINESS_PROCESS in xml
    # Bestellreferenz BT-13 und Lieferdatum BT-72
    assert "4500000001" in xml
    # Adresszeile BT-35 (Verkäufer) und BT-50 (Käufer) mit Hausnummer: Die Norm kennt
    # kein eigenes Feld dafür, das Mapping führt sie mit der Straße zusammen (4T-0201).
    assert "Musterstrasse 1" in xml
    assert "Musterstraße 5" in xml
    assert "ActualDeliverySupplyChainEvent" in xml
    # Reverse-Charge (Kategorie AE)
    assert "VATEX-EU-AE" in xml
    assert "Reverse charge" in xml
    # Nettosumme (= Brutto bei Reverse-Charge)
    assert "16900.00" in xml


def test_cii_xsd_valide(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    assert pruefe_xsd(xml).gueltig is True


def test_cii_normalfall_kategorie_s(beispiel_rechnung):
    """Normalsteuerfall: Kategorie S mit Steuersatz und berechneter Steuer, kein VATEX-EU-AE."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert "VATEX-EU-AE" not in xml  # kein Reverse-Charge-Befreiungsgrund
    assert "Reverse charge" not in xml
    # netto 16900.00, Steuer 19 % = 3211.00, brutto 20111.00
    assert "3211.00" in xml
    assert "20111.00" in xml


def test_cii_normalfall_xsd_valide(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    assert pruefe_xsd(xml).gueltig is True


def test_cii_skonto_zeile_nach_br_de_18(beispiel_rechnung):
    """Bei gesetztem Skonto trägt BT-20 die Skonto-Zeile auf einer eigenen Zeile hinter dem
    freien Text, abgeschlossen mit dem von BR-DE-18 zwingend verlangten Zeilenumbruch (S-0051)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert (
        "Zahlbar innerhalb von 30 Tagen ohne Abzug.\n"
        "#SKONTO#TAGE=14#PROZENT=2.00#\n</ram:Description>"
    ) in xml


def test_cii_skonto_prozent_immer_zweistellig(beispiel_rechnung):
    """BR-DE-18 verlangt genau zwei Nachkommastellen mit Punkt als Trenner."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=7, prozent=Decimal("2.5"))
    assert "#SKONTO#TAGE=7#PROZENT=2.50#" in erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")


def test_cii_ohne_skonto_keine_zeile(beispiel_rechnung):
    """Ohne Skonto-Angabe bleibt BT-20 der unveränderte freie Text."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    assert rechnung.skonto is None  # Default
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert "#SKONTO#" not in xml
    assert "<ram:Description>Zahlbar innerhalb von 30 Tagen ohne Abzug.</ram:Description>" in xml


def test_cii_skonto_xsd_valide(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    assert pruefe_xsd(erzeuge_cii(rechnung, bestellnummer, waehrung)).gueltig is True


def test_cii_faelligkeitsdatum_aus_zahlungsfrist(beispiel_rechnung):
    """Bei gesetzter Zahlungsfrist trägt BT-9 das Rechnungsdatum plus Frist (S-0081 AK1).
    Rechnungsdatum 19.06.2026 + 30 Tage = 19.07.2026, im CII-Format 102 (JJJJMMTT)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.zahlungsfrist = 30
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert "<ram:DueDateDateTime>" in xml
    assert '<udt:DateTimeString format="102">20260719</udt:DateTimeString>' in xml


def test_cii_ohne_zahlungsfrist_kein_faelligkeitsdatum(beispiel_rechnung):
    """Ohne Zahlungsfrist entsteht kein BT-9 (S-0081 AK2)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    assert rechnung.zahlungsfrist == 0  # Default
    assert "DueDateDateTime" not in erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")


def test_cii_faelligkeitsdatum_laesst_bt20_unveraendert(beispiel_rechnung):
    """BT-9 tritt neben BT-20 und ersetzt es nicht; die Skonto-Zeile bleibt erhalten
    (S-0081 AK4)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.zahlungsfrist = 30
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert (
        "Zahlbar innerhalb von 30 Tagen ohne Abzug.\n"
        "#SKONTO#TAGE=14#PROZENT=2.00#\n</ram:Description>"
    ) in xml
    assert "<ram:DueDateDateTime>" in xml


def test_cii_faelligkeitsdatum_xsd_valide(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.zahlungsfrist = 30
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    assert pruefe_xsd(erzeuge_cii(rechnung, bestellnummer, waehrung)).gueltig is True


# --- Dynamische Belegwährung (S-0064, 4T-0134) -----------------------------


def test_cii_belegwaehrung_dynamisch(beispiel_rechnung):
    """BT-5 (InvoiceCurrencyCode) und die Steuersumme (BT-110) tragen die Belegwährung der
    Bestellung, nicht mehr fest EUR (S-0064 AK1/AK2)."""
    rechnung, bestellnummer, _ = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, "CHF").decode("utf-8")
    assert "<ram:InvoiceCurrencyCode>CHF</ram:InvoiceCurrencyCode>" in xml
    assert 'currencyID="CHF"' in xml
    assert 'currencyID="EUR"' not in xml  # keine feste Belegwährung mehr


def test_cii_chf_xsd_valide(beispiel_rechnung):
    """Der CHF-Fall bleibt XSD-valide (Java-frei; die KoSIT-Prüfung liegt im Goldstandard)."""
    rechnung, bestellnummer, _ = beispiel_rechnung
    assert pruefe_xsd(erzeuge_cii(rechnung, bestellnummer, "CHF")).gueltig is True


# --- Bankverbindung nach Rechnungswährung (S-0065, 4T-0135) ----------------


def test_cii_nutzt_gewaehlte_bankverbindung(beispiel_rechnung):
    """S-0065 AK3: BG-16/17 trägt die an der Rechnung gewählte Bankverbindung, nicht die erste."""
    from eu_rechnung.domain import Bankverbindung

    rechnung, bestellnummer, waehrung = beispiel_rechnung
    chf = Bankverbindung(
        kontoinhaber="Muster Consulting GmbH",
        bank="Beispielbank",
        iban="CH1100000000000000000",
        bic="BEISCHZZ",
        waehrung="CHF",
    )
    rechnung.verkaeufer.bankverbindungen.append(chf)
    rechnung.bankverbindung = chf
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert "CH1100000000000000000" in xml  # gewähltes CHF-Konto
    assert "BEISCHZZ" in xml
    assert rechnung.verkaeufer.bankverbindungen[0].bic not in xml  # nicht das erste (EUR-)Konto


def test_cii_faellt_ohne_wahl_auf_erste_bankverbindung_zurueck(beispiel_rechnung):
    """S-0065 AK5: Ohne gewählte Bankverbindung nutzt der Export die erste (heutiges Verhalten)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.bankverbindung = None
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert rechnung.verkaeufer.bankverbindungen[0].bic in xml


# --- Positions-Leistungszeitraum als BG-26 (S-0070, 4T-0145) ---------------


def test_cii_position_mit_zeitraum_traegt_bg26(beispiel_rechnung):
    """AK1: Eine Position mit Leistungszeitraum erhält BG-26 (BT-134/BT-135) auf Zeilenebene.
    beispiel_rechnung trägt bei Position 2 einen vom Kopf abweichenden Zeitraum (10.–20.05.),
    der innerhalb des Kopf-Zeitraums (Mai, BG-14) liegt (KoSIT-Regel BR-CO)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert '<udt:DateTimeString format="102">20260510</udt:DateTimeString>' in xml  # BT-134
    assert '<udt:DateTimeString format="102">20260520</udt:DateTimeString>' in xml  # BT-135
    # Zwei BillingSpecifiedPeriod: der Kopf-BG-14 plus die eine Positions-BG-26.
    assert xml.count("<ram:BillingSpecifiedPeriod>") == 2


def test_cii_position_ohne_zeitraum_kein_bg26(beispiel_rechnung):
    """AK1: Ohne Positions-Zeitraum bleibt nur der Kopf-BG-14, keine Zeilen-BG-26."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    for pos in rechnung.positionen:
        pos.leistungszeitraum = None
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert xml.count("<ram:BillingSpecifiedPeriod>") == 1  # nur der Kopf


def test_cii_kopfzeitraum_bg14_bleibt_unveraendert(beispiel_rechnung):
    """AK2: Der Kopf-Zeitraum BG-14 (und das Lieferdatum BT-72 = Ende) bleiben unverändert."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung).decode("utf-8")
    assert "20260501" in xml  # BG-14 von
    assert "20260531" in xml  # BG-14 bis und BT-72 Lieferdatum


def test_cii_position_zeitraum_xsd_valide(beispiel_rechnung):
    """AK4 (Java-frei): Der BG-26-Fall bleibt XSD-valide; die KoSIT-Prüfung liegt im Goldstandard."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    assert pruefe_xsd(erzeuge_cii(rechnung, bestellnummer, waehrung)).gueltig is True


# --- Encoding-Randfälle: XML-kritische Sonderzeichen (4T-0167) --------------


def test_cii_escaped_xml_sonderzeichen(beispiel_rechnung):
    """XML-kritische Sonderzeichen in einem Feld werden maskiert, das XML bleibt XSD-valide.

    Ein roh eingesetztes ``<`` oder ``&`` würde das Dokument zerstören; der Serializer muss sie
    escapen. Geprüft an der Positionsbezeichnung, die als Klartext ins XML geht.
    """
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.positionen[0].bezeichnung = 'Beratung <A> & "B" \'C\''
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    assert pruefe_xsd(xml).gueltig is True  # wohlgeformt trotz Sonderzeichen
    assert b"&lt;A&gt;" in xml  # < und > maskiert
    assert b"&amp;" in xml  # & maskiert
    assert b"<A>" not in xml  # nirgends roh als Pseudo-Element


# --- Fremdwährung kombiniert mit Normalsteuerfall (4T-0168) -----------------


def test_cii_fremdwaehrung_normalfall_xsd_valide(beispiel_rechnung):
    """Belegwährung CHF und Normalsteuerfall zugleich bleiben XSD-valide.

    Bisher wurde CHF nur mit Reverse-Charge und der Normalfall nur mit EUR geprüft; die
    Kombination trägt die Steuer normal berechnet in fremder Belegwährung.
    """
    rechnung, bestellnummer, _ = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    xml = erzeuge_cii(rechnung, bestellnummer, "CHF")
    assert pruefe_xsd(xml).gueltig is True
    assert b"CHF" in xml  # Belegwährung BT-5
    text = xml.decode("utf-8")
    assert "VATEX-EU-AE" not in text  # kein Reverse-Charge-Befreiungsgrund
    assert "3211.00" in text  # Steuer 19 % auf 16900.00 netto
