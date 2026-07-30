"""Tests der eingebauten, Java-freien Validierung (`validation.pruefe_xsd`).

Die optional zuschaltbaren Java-Prüfer (KoSIT, veraPDF) werden in 4T-0021
getestet.
"""

import re

from eu_rechnung.export.cii_xml import erzeuge_cii
from eu_rechnung.export.validation import pruefe_xsd


def test_pruefe_xsd_valide(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    assert pruefe_xsd(xml).gueltig is True


def test_pruefe_xsd_kaputt(beispiel_rechnung):
    """Ein XML ohne ExchangedDocument verletzt die EN-16931-XSD."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
    kaputt = re.sub(
        rb"<rsm:ExchangedDocument>.*?</rsm:ExchangedDocument>", b"", xml, flags=re.DOTALL
    )
    ergebnis = pruefe_xsd(kaputt)
    assert ergebnis.gueltig is False
    assert ergebnis.befunde
