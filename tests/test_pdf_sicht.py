"""Tests des PDF/A-Sichtteils (`pdf_sicht.py`), Java-frei.

Inhaltliche Gegenprobe über den extrahierten PDF-Text (analog
`Daten/check_text.py`) und Nachweis des für PDF/A nötigen OutputIntents. Die
PDF/A-Konformität als Ganzes prüft veraPDF (Goldstandard, 4T-0021).

Die Sprach-Tests am Ende decken S-0060 ab: feste Texte, Zahlen- und Datumsformate,
die Dokumentsprache und die Unberührtheit dynamischer Inhalte.
"""

from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from eu_rechnung.domain import Skonto
from eu_rechnung.export.pdf_sicht import erzeuge_sichtteil


def _pdf_text(pdf: bytes) -> str:
    """Extrahiert den PDF-Text und normalisiert Whitespace (pypdf bricht in
    schmalen Tabellenspalten anders um als visuell sichtbar)."""
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(seite.extract_text() for seite in reader.pages)
    return " ".join(text.split())


def test_sichtteil_textinhalt(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    # Umlaute korrekt als Glyph
    assert "München" in text
    assert "Grüßen" in text
    assert "Musterstraße" in text
    # Reverse-Charge-Hinweis
    assert "Steuerschuldnerschaft des Leistungsempfängers" in text
    # aktive individuelle Felder sichtbar, inaktives ausgeblendet
    assert "#PAKET_1" in text
    assert "Cutover & Go-Live" in text
    assert "DARF NICHT ERSCHEINEN" not in text
    # Pflichtangaben und Summe in deutscher Notation
    assert "4500000001" in text
    assert "D10002" in text
    assert "16.900,00" in text


def test_sichtteil_output_intent(beispiel_rechnung):
    """PDF/A verlangt einen OutputIntent (sRGB), den pdf_sicht ergänzt."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    pdf = erzeuge_sichtteil(rechnung, bestellnummer, waehrung)
    root = PdfReader(BytesIO(pdf)).trailer["/Root"]
    assert "/OutputIntents" in root
    assert len(root["/OutputIntents"]) >= 1


def test_sichtteil_normalfall_zeigt_umsatzsteuer(beispiel_rechnung):
    """Normalsteuerfall: der Sichtteil weist die Umsatzsteuer aus, ohne RC-Hinweis (S-0079)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "Umsatzsteuer 19 %" in text
    assert "Steuerschuldnerschaft des Leistungsempfängers" not in text
    # Steuer 3.211,00 und Zahlbetrag 20.111,00 in deutscher Notation
    assert "3.211,00" in text
    assert "20.111,00" in text


def test_sichtteil_zeigt_skonto(beispiel_rechnung):
    """Bei gesetztem Skonto weist der Sichtteil Satz, Frist mit Stichtag, Abzug und den
    verbleibenden Zahlbetrag aus, weil das XML sie nur maschinell kodiert trägt (S-0051 AK5).
    Stichtag = Rechnungsdatum (19.06.2026) + 14 Tage; Abzug = 2 % von 16.900,00."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert (
        "Skonto: 2,00 % bei Zahlung innerhalb von 14 Tagen (bis 03.07.2026): "
        "338,00 EUR Abzug, Zahlbetrag 16.562,00 EUR"
    ) in text
    # Der ausgewiesene Zahlbetrag im Summenblock bleibt ungekürzt (S-0051 AK3)
    assert "16.900,00" in text


def test_sichtteil_skonto_basis_ist_der_bruttobetrag(beispiel_rechnung):
    """Der Abzug rechnet auf den fälligen Betrag (BT-115, brutto), wie ihn BR-DE-18 ohne
    eigenes BASISBETRAG-Segment zugrunde legt: 2 % von 20.111,00 statt von netto."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "402,22 EUR Abzug, Zahlbetrag 19.708,78 EUR" in text


def test_sichtteil_skonto_einzelner_tag_im_singular(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=1, prozent=Decimal("1.5"))
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert (
        "Skonto: 1,50 % bei Zahlung innerhalb von 1 Tag (bis 20.06.2026): "
        "253,50 EUR Abzug, Zahlbetrag 16.646,50 EUR"
    ) in text


def test_sichtteil_ohne_skonto_kein_hinweis(beispiel_rechnung):
    """Ohne Skonto-Angabe erscheint kein Skonto-Hinweis (S-0051 AK5)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    assert rechnung.skonto is None  # Default
    assert "Skonto" not in _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))


def test_sichtteil_zeigt_faelligkeitsdatum(beispiel_rechnung):
    """Bei gesetzter Zahlungsfrist weist der Sichtteil das Fälligkeitsdatum aus, dasselbe
    Datum wie BT-9 im XML (S-0081 AK3). 19.06.2026 + 30 Tage = 19.07.2026."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.zahlungsfrist = 30
    assert "Fällig am: 19.07.2026" in _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))


def test_sichtteil_ohne_zahlungsfrist_kein_faelligkeitsdatum(beispiel_rechnung):
    """Ohne Zahlungsfrist erscheint kein Hinweis (S-0081 AK3)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    assert rechnung.zahlungsfrist == 0  # Default
    assert "Fällig am" not in _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))


# --- Rechnungssprache (S-0060) ----------------------------------------------


def test_sichtteil_ist_ohne_gesetzte_sprache_deutsch(beispiel_rechnung):
    """Der Default „de" hält den bisherigen Stand; kein Bestandsbeleg ändert sich."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    assert rechnung.rechnungssprache == "de"
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "Rechnungsnummer" in text
    assert "Zahlbetrag" in text


@pytest.mark.parametrize(
    "sprache, nummer_label, zahlbetrag_label, land",
    [
        ("en", "Invoice number", "Amount due", "Germany"),
        ("it", "Numero fattura", "Importo da pagare", "Germania"),
        ("fr", "Numéro de facture", "Montant à payer", "Allemagne"),
        ("es", "Número de factura", "Importe a pagar", "Alemania"),
    ],
)
def test_sichtteil_folgt_der_rechnungssprache(
    beispiel_rechnung, sprache, nummer_label, zahlbetrag_label, land
):
    """AK2: Die festen Texte erscheinen in der aufgelösten Rechnungssprache."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = sprache
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert nummer_label in text
    assert zahlbetrag_label in text
    assert land in text  # ausgeschriebenes Land im Adressfeld
    assert "Rechnungsnummer" not in text  # kein deutscher Rest


def test_sichtteil_uebersetzt_den_reverse_charge_hinweis(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "en"
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "Reverse charge. The recipient of the supply is liable for the VAT." in text
    assert "Steuerschuldnerschaft" not in text


def test_sichtteil_formatiert_betraege_nach_sprache(beispiel_rechnung):
    """AK3: Ein englischer Empfänger darf 16.900,00 nicht als 16,9 lesen können."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "de"
    assert "16.900,00" in _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))

    rechnung.rechnungssprache = "en"
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "16,900.00" in text
    assert "16.900,00" not in text


def test_sichtteil_formatiert_datum_nach_sprache(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "de"
    assert "19.06.2026" in _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))

    rechnung.rechnungssprache = "en"
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "19/06/2026" in text
    assert "19.06.2026" not in text


def test_sichtteil_franzoesisch_trennt_tausender_mit_leerzeichen(beispiel_rechnung):
    """Franzoesisch trennt Tausender mit einem Leerzeichen statt mit einem Punkt.

    In der Sprachdatei steht ein geschuetztes Leerzeichen (U+00A0), damit ein Betrag nicht
    umbrochen wird. Im extrahierten Text erscheint es als gewoehnliches Leerzeichen: Die
    Vera-Schrift bildet NBSP und Space auf dasselbe Glyph gleicher Breite ab, und pypdf
    loest es ueber das ToUnicode-Mapping als U+0020 auf. Geprueft wird deshalb die
    dargestellte Form; dass in der Datei ein NBSP steht, sichert test_texte.py.
    """
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "fr"
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "16 900,00" in text
    assert "16.900,00" not in text


def test_sichtteil_uebersetzt_skonto_und_faelligkeit(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "en"
    rechnung.zahlungsfrist = 30
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "Due on: 19/07/2026" in text
    assert "Early payment discount:" in text
    assert "2.00 % if paid within 14 days (by 03/07/2026)" in text


def test_sichtteil_skonto_einzelner_tag_im_singular_je_sprache(beispiel_rechnung):
    """Die Pluralisierung liegt in den Sprachdateien, nicht im Code."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.skonto = Skonto(tage=1, prozent=Decimal("1.5"))
    rechnung.rechnungssprache = "en"
    assert "within 1 day" in _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    rechnung.rechnungssprache = "it"
    assert "entro 1 giorno" in _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))


def test_sichtteil_uebernimmt_dynamische_inhalte_unveraendert(beispiel_rechnung):
    """AK5: Anschreiben, Bezeichnungen und individuelle Felder werden nicht übersetzt."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "en"
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "Mit freundlichen Grüßen" in text  # deutscher Anschreibentext bleibt
    assert "Cutover-Management nach Aufwand" in text  # Artikelbezeichnung bleibt
    assert "Cutover & Go-Live" in text  # individuelles Feld bleibt


def test_sichtteil_setzt_die_dokumentsprache(beispiel_rechnung):
    """AK4: Das PDF trägt die Rechnungssprache als /Lang (Ersatz für das
    normseitig unzulässige XML-Sprachattribut, E-010)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "en"
    reader = PdfReader(BytesIO(erzeuge_sichtteil(rechnung, bestellnummer, waehrung)))
    assert reader.trailer["/Root"]["/Lang"] == "en"


def test_sichtteil_unbekannte_sprache_faellt_auf_deutsch_zurueck(beispiel_rechnung):
    """Ein verfremdeter Wert in der Firma-Datei darf die Erzeugung nicht brechen."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.rechnungssprache = "kl"
    pdf = erzeuge_sichtteil(rechnung, bestellnummer, waehrung)
    assert "Rechnungsnummer" in _pdf_text(pdf)
    assert PdfReader(BytesIO(pdf)).trailer["/Root"]["/Lang"] == "de"


# --- Dynamische Belegwährung (S-0064, 4T-0134) -----------------------------


def test_sichtteil_zeigt_die_belegwaehrung(beispiel_rechnung):
    """Der Summenblock weist die Belegwährung der Bestellung aus, nicht mehr fest EUR
    (S-0064 AK2)."""
    rechnung, bestellnummer, _ = beispiel_rechnung
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, "CHF"))
    assert "16.900,00 CHF" in text  # Reverse-Charge: netto = Zahlbetrag
    assert "16.900,00 EUR" not in text


def test_sichtteil_waehrung_und_sprache_unabhaengig(beispiel_rechnung):
    """AK4: Eine englische Rechnung in CHF trägt englische Texte und CHF-Beträge; Sprache und
    Währung wirken unabhängig voneinander."""
    rechnung, bestellnummer, _ = beispiel_rechnung
    rechnung.rechnungssprache = "en"
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, "CHF"))
    assert "Amount due" in text  # englischer fester Text
    assert "16,900.00 CHF" in text  # englisches Zahlenformat plus CHF-Währung


def test_meta_beschriftungen_passen_in_jeder_sprache_einzeilig():
    """Das Kopf-Layout trägt die längsten Beschriftungen aller fünf Sprachen.

    Das ursprüngliche Layout war auf die deutschen Texte kalibriert; „Periodo di
    riferimento", „Numéro de commande" und „Periodo de prestación" sind breiter und
    brachen um. Der Test hält die Aufteilung gegen künftige Übersetzungen: Wer einen
    längeren Text einträgt, sieht hier sofort, dass er nicht mehr in die Spalte passt,
    statt es erst am erzeugten Beleg zu bemerken (D5-Absicherung).
    """
    from reportlab.pdfbase import pdfmetrics

    from eu_rechnung.export.pdf_sicht import (
        _BREITE_META_LABEL,
        _META_PADDING,
        _SCHRIFT_FETT,
        _registriere_schriften,
    )
    from eu_rechnung.texte import SPRACHEN, text

    _registriere_schriften()
    verfuegbar = _BREITE_META_LABEL - _META_PADDING
    schluessel = [
        "sichtteil.rechnungsnummer",
        "sichtteil.rechnungsdatum",
        "sichtteil.kundennummer",
        "sichtteil.bestellnummer",
        "sichtteil.leistungszeitraum",
        "sichtteil.ust_id_kunde",
    ]
    zu_breit = []
    for sprache in SPRACHEN:
        for s in schluessel:
            beschriftung = text(s, sprache)
            breite = pdfmetrics.stringWidth(beschriftung, _SCHRIFT_FETT, 8)
            if breite > verfuegbar:
                zu_breit.append(
                    f"{sprache}/{s}: {beschriftung!r} braucht {breite:.0f}pt, "
                    f"verfügbar sind {verfuegbar:.0f}pt"
                )
    assert not zu_breit, "Beschriftungen brechen um:\n" + "\n".join(zu_breit)


def test_zeitraum_wert_passt_in_jeder_sprache_einzeilig():
    """Auch der längste Wert (der Leistungszeitraum) bleibt in seiner Spalte."""
    from reportlab.pdfbase import pdfmetrics

    from eu_rechnung.export.pdf_sicht import (
        _BREITE_META_WERT,
        _META_PADDING,
        _SCHRIFT,
        _registriere_schriften,
    )
    from eu_rechnung.texte import SPRACHEN, text

    _registriere_schriften()
    verfuegbar = _BREITE_META_WERT - _META_PADDING
    zu_breit = []
    for sprache in SPRACHEN:
        wert = text("sichtteil.zeitraum", sprache, von="01/05/2026", bis="31/05/2026")
        breite = pdfmetrics.stringWidth(wert, _SCHRIFT, 8)
        if breite > verfuegbar:
            zu_breit.append(f"{sprache}: {wert!r} braucht {breite:.0f}pt von {verfuegbar:.0f}pt")
    assert not zu_breit, "Zeitraum-Werte brechen um:\n" + "\n".join(zu_breit)


# --- Positions-Leistungszeitraum im Sichtteil (S-0070 AK3, 4T-0145) ---------


def test_sichtteil_zeigt_abweichenden_positionszeitraum(beispiel_rechnung):
    """AK3: Ein vom Kopf abweichender Positions-Zeitraum erscheint an der Position.
    beispiel_rechnung: Position 2 trägt 10.–20.05.2026, innerhalb des Kopf-Zeitraums Mai."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "10.05.2026" in text
    assert "20.05.2026" in text


def test_sichtteil_verschweigt_kopfgleichen_positionszeitraum(beispiel_rechnung):
    """Design B (4T-0145): Ein Positions-Zeitraum gleich dem Kopf wird nicht zusätzlich an der
    Position wiederholt; der Kopf-Zeitraum steht allein im Metadaten-Block."""
    from eu_rechnung.domain import Leistungszeitraum

    rechnung, bestellnummer, waehrung = beispiel_rechnung
    kopf = rechnung.leistungszeitraum
    for pos in rechnung.positionen:
        pos.leistungszeitraum = Leistungszeitraum(von=kopf.von, bis=kopf.bis)
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    # Der Kopf-Zeitraum (Mai) erscheint nur einmal (Metadaten-Block), nicht je Position wiederholt.
    assert text.count("01.05.2026") == 1


# --- Encoding-Randfälle: lange und mehrzeilige Texte (4T-0167) --------------


def test_sichtteil_traegt_sehr_lange_positionsbezeichnung(beispiel_rechnung):
    """Eine sehr lange Positionsbezeichnung bricht den Sichtteil nicht.

    Das PDF entsteht, und der Anfang der Bezeichnung ist (umbruch-normalisiert)
    wiederauffindbar. Die PDF/A-Konformität als Ganzes prüft veraPDF im Goldstandard; hier zählt,
    dass die Erzeugung den Zeilenüberlauf trägt statt zu scheitern.
    """
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    lang = ("Sehr umfangreiche Beratungsleistung " * 8).strip()  # ~290 Zeichen
    rechnung.positionen[0].bezeichnung = lang
    text = _pdf_text(erzeuge_sichtteil(rechnung, bestellnummer, waehrung))
    assert "Sehr umfangreiche Beratungsleistung" in text
