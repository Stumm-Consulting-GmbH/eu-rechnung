"""Tests der ZUGFeRD-Einbettung (`zugferd.py`), Java-frei.

Nachweis des hybriden PDF (eingebettetes XML wieder extrahierbar) und der
deutschen PDF-Metadaten. Die PDF/A-3- und KoSIT-Validierung des Ergebnisses
liegt in 4T-0021 (Goldstandard).
"""

from decimal import Decimal
from io import BytesIO

from facturx import get_facturx_xml_from_pdf
from pypdf import PdfReader

from eu_rechnung.export.zugferd import erzeuge_zugferd


def test_zugferd_einbettung_und_metadaten(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)

    # Hybrid-Nachweis: eingebettetes CII-XML wieder extrahierbar
    filename, xml = get_facturx_xml_from_pdf(
        zugferd, check_xsd=False, check_schematron=False
    )
    assert filename == "factur-x.xml"
    assert xml

    # deutsche PDF-Metadaten aus der Rechnung
    meta = PdfReader(BytesIO(zugferd)).metadata
    assert meta.get("/Title") == "Rechnung 2026-10001"
    assert meta.get("/Author") == "Muster Consulting GmbH"
    assert "vom 19.06.2026" in (meta.get("/Subject") or "")


def test_zugferd_normalfall_einbettung(beispiel_rechnung):
    """Normalsteuerfall: das hybride ZUGFeRD entsteht und trägt das eingebettete XML (S-0079)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    zugferd = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
    filename, xml = get_facturx_xml_from_pdf(
        zugferd, check_xsd=False, check_schematron=False
    )
    assert filename == "factur-x.xml"
    assert xml
