"""ZUGFeRD-Erzeugung über factur-x (PDF/A-3 mit eingebettetem CII-XML).

Verbindet den PDF/A-Sichtteil (`pdf_sicht`) und das CII-XML (`cii_xml`) zum
hybriden ZUGFeRD: factur-x bettet das XML in den Sicht-PDF ein und finalisiert
PDF/A-3 (setzt das `pdfaid`-XMP). Der für PDF/A nötige OutputIntent stammt aus
dem Sichtteil (E-007) und bleibt beim Dokument-Klonen erhalten.

Die PDF-Metadaten werden explizit aus der Rechnung gesetzt; ohne den
`pdf_metadata`-Parameter erzeugt factur-x englische Default-Metadaten aus dem
XML. Sie folgen wie der Sichtteil der Rechnungssprache (S-0060), ebenso die
Dokumentsprache `/Lang`: factur-x setzt sie aus seinem `lang`-Parameter und
überschreibt dabei den Wert des Sichtteils, weshalb sie hier mitgegeben wird.

Die factur-x-Schematron-Prüfung ist standardmäßig abgeschaltet
(`check_schematron=False`): Sie nutzt das generische Factur-X/PEPPOL-EN-16931-
Schematron, das die XRechnung-CIUS-Guideline-ID (BT-24) ablehnt und damit nicht
zum XRechnung-konformen XML passt (E-002, E-008). Die Norm-Sicherung des XML
läuft über KoSIT (Test-Goldstandard E-005, optional in validation.py).
`check_xsd` bleibt aktiv.

Beide Steuerfälle wie `cii_xml.py` und `pdf_sicht.py`: Reverse-Charge (Kategorie
AE) und Normalsteuerfall (Kategorie S mit Steuersatz). Die Steuerlogik liegt in
`erzeuge_cii`/`erzeuge_sichtteil` und wird hier nicht dupliziert.
"""

from __future__ import annotations

from facturx import generate_from_binary

from eu_rechnung.domain import Rechnung
from eu_rechnung.export.cii_xml import erzeuge_cii
from eu_rechnung.export.pdf_sicht import erzeuge_sichtteil
from eu_rechnung.texte import Sprachkontext

# ZUGFeRD-Profil EN 16931 (Comfort), Syntax CII (E-002).
FLAVOR = "factur-x"
LEVEL = "en16931"


def _pdf_metadaten(rechnung: Rechnung, sp: Sprachkontext) -> dict:
    """PDF-Metadaten aus der Rechnung (sonst englische factur-x-Defaults).

    In der Rechnungssprache, wie der Sichtteil: Titel und Betreff eines fremdsprachigen
    Belegs sollen nicht deutsch in der Dateiverwaltung des Empfängers auftauchen.
    """
    titel = sp.t("sichtteil.titel", nummer=rechnung.rechnungsnummer)
    return {
        "author": rechnung.verkaeufer.name,
        "title": titel,
        "subject": sp.t(
            "zugferd.metadaten_betreff",
            titel=titel,
            datum=sp.datum(rechnung.rechnungsdatum),
        ),
        "keywords": sp.t("zugferd.metadaten_schlagworte"),
    }


def erzeuge_zugferd(
    rechnung: Rechnung,
    bestellnummer: str,
    waehrung: str,
    *,
    check_schematron: bool = False,
) -> bytes:
    """Erzeugt das hybride ZUGFeRD (PDF/A-3 mit eingebettetem CII-XML) als `bytes`.

    Orchestriert die Erzeugung des CII-XML und des PDF/A-Sichtteils und bettet
    beide über factur-x ein. `bestellnummer` (BT-13) und `waehrung` (die
    Belegwährung) stammen aus der übergeordneten Bestellung. Metadaten und
    Dokumentsprache folgen `rechnung.rechnungssprache` (S-0060). `check_schematron` ist
    standardmäßig aus, weil das factur-x-Schematron nicht zum XRechnung-CIUS-XML passt
    (siehe Modul-Docstring); `check_xsd` bleibt aktiv.
    """
    sp = Sprachkontext(rechnung.rechnungssprache)
    cii = erzeuge_cii(rechnung, bestellnummer, waehrung)
    sicht = erzeuge_sichtteil(rechnung, bestellnummer, waehrung)
    return generate_from_binary(
        sicht,
        cii,
        flavor=FLAVOR,
        level=LEVEL,
        check_xsd=True,
        check_schematron=check_schematron,
        pdf_metadata=_pdf_metadaten(rechnung, sp),
        # RFC 3066; der reine Sprachcode ist die ehrliche Angabe, weil die
        # Rechnungssprache keine Region kennt (bis 4T-0126 stand hier fest „de-DE").
        lang=sp.sprache,
    )
