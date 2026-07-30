"""Smoke-Test: belegt, dass die Testsammlung läuft und das zentrale Fixture
`beispiel_rechnung` den erwarteten Reverse-Charge-Realfall liefert."""

from decimal import Decimal


def test_beispiel_rechnung_grunddaten(beispiel_rechnung):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    assert rechnung.reverse_charge is True
    assert len(rechnung.positionen) == 2
    netto = sum((p.gesamtpreis for p in rechnung.positionen), Decimal("0.00"))
    assert netto == Decimal("16900.00")
    assert bestellnummer == "4500000001"
    assert waehrung == "EUR"


def test_beispiel_rechnung_umlaute(beispiel_rechnung):
    """Der Realfall trägt echte Umlaute (Grundlage der Sichtteil-Gegenprobe)."""
    rechnung, _, _ = beispiel_rechnung
    assert rechnung.kaeufer.adresse.ort == "München"
    assert "Grüßen" in rechnung.anschreibentext
