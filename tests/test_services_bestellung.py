"""Tests der Bestellungs-Validierung und Verbrauchsrechnung (`services.bestellung`), Java-frei.

Prüft die feld-nahen Befunde (Pflicht-Kopffelder, Datums- und Betragsplausibilität) und die
Verbrauchsrechnung zu den Obergrenzen: ohne Rechnungen null, mit Rechnungen die Summe der
Positionen (Menge bzw. Betrag je Artikel, netto gesamt).
"""

from datetime import date
from decimal import Decimal

from eu_rechnung.domain import (
    Adresse,
    Bestellung,
    EigeneFirma,
    GueltigerArtikel,
    Kaeufer,
    Leistungszeitraum,
    ObergrenzeArt,
    Position,
    Rechnung,
    Skonto,
    Summen,
)
from eu_rechnung.services import pruefe_bestellung, verbrauch_artikel, verbrauch_gesamt


def _bestellung(**anpassungen) -> Bestellung:
    basis = dict(
        id="b-1",
        bestellnummer="4500000001",
        beginn_datum=date(2026, 5, 1),
        ende_datum=date(2026, 5, 31),
        zahlungsfrist=30,
        zahlungsbedingung="Zahlbar innerhalb von 30 Tagen.",
        waehrung="EUR",
        gueltige_artikel=[GueltigerArtikel(artikel_id="art-1", einzelpreis=Decimal("1200"))],
    )
    basis.update(anpassungen)
    return Bestellung(**basis)


def test_vollstaendige_bestellung_ist_gueltig():
    assert pruefe_bestellung(_bestellung()) == []


def test_bestellnummer_pflicht():
    befunde = pruefe_bestellung(_bestellung(bestellnummer="  "))
    assert any(b.feld == "bestellnummer" for b in befunde)


def test_waehrung_pflicht():
    befunde = pruefe_bestellung(_bestellung(waehrung=""))
    assert any(b.feld == "waehrung" for b in befunde)


def test_ende_vor_beginn_faellt_auf():
    befunde = pruefe_bestellung(
        _bestellung(beginn_datum=date(2026, 5, 31), ende_datum=date(2026, 5, 1))
    )
    assert any(b.feld == "ende" for b in befunde)


def test_negative_zahlungsfrist_faellt_auf():
    befunde = pruefe_bestellung(_bestellung(zahlungsfrist=-1))
    assert any(b.feld == "zahlungsfrist" for b in befunde)


def test_negativer_gesamthoechstbetrag_faellt_auf():
    befunde = pruefe_bestellung(_bestellung(gesamt_hoechstbetrag=Decimal("-1")))
    assert any(b.feld == "gesamt_hoechstbetrag" for b in befunde)


def test_zahlungsbedingung_pflicht():
    befunde = pruefe_bestellung(_bestellung(zahlungsbedingung="  "))
    assert any(b.feld == "zahlungsbedingung" for b in befunde)


def test_mindestens_ein_gueltiger_artikel():
    befunde = pruefe_bestellung(_bestellung(gueltige_artikel=[]))
    assert any(b.feld == "gueltige_artikel" for b in befunde)


# --- Vereinbartes Skonto (S-0080) -------------------------------------------


def test_bestellung_ohne_skonto_ist_gueltig():
    """Das Skonto ist optional; ohne Vereinbarung trägt die Bestellung `None`."""
    bestellung = _bestellung()
    assert bestellung.skonto is None
    assert pruefe_bestellung(bestellung) == []


def test_gueltiges_skonto_an_der_bestellung():
    assert pruefe_bestellung(_bestellung(skonto=Skonto(tage=14, prozent=Decimal("2")))) == []


def test_skonto_wertebereich_an_der_bestellung():
    """Wortgleich zur Rechnungsprüfung: Tage größer 0, Prozentsatz größer 0 und höchstens
    100. Sonst ließe die Bestellung durch, was die Rechnung später ablehnt."""
    befunde = pruefe_bestellung(_bestellung(skonto=Skonto(tage=0, prozent=Decimal("0"))))
    felder = [b.feld for b in befunde]
    assert "skonto_tage" in felder
    assert "skonto_prozent" in felder


def test_skonto_prozent_obergrenze_an_der_bestellung():
    """Die Grenze selbst ist zulässig, alles darüber nicht (4T-0116)."""
    assert pruefe_bestellung(_bestellung(skonto=Skonto(tage=14, prozent=Decimal("100")))) == []
    befunde = pruefe_bestellung(_bestellung(skonto=Skonto(tage=14, prozent=Decimal("100.01"))))
    assert any(b.feld == "skonto_prozent" for b in befunde)


def test_verbrauch_ohne_rechnungen_ist_null():
    bestellung = _bestellung()
    assert verbrauch_gesamt(bestellung) == Decimal("0")
    assert verbrauch_artikel(bestellung, "art-1", ObergrenzeArt.MENGE) == Decimal("0")


def _rechnung_mit_positionen(positionen: list[Position]) -> Rechnung:
    """Minimale Rechnung; für die Verbrauchsrechnung zählen allein die Positionen."""
    leer_adresse = Adresse(strasse="", plz="", ort="", land="CH")
    firma = EigeneFirma(
        name="V",
        adresse=leer_adresse,
        mehrwertsteuer_id="",
        email="",
        telefon="",
        kontakt_name="",
    )
    kaeufer = Kaeufer(
        name="K",
        adresse=Adresse(strasse="", plz="", ort="", land="DE"),
        umsatzsteuer_id="",
        kundennummer="D1",
        email="",
    )
    return Rechnung(
        id="r-1",
        rechnungsnummer="R-1",
        rechnungsdatum=date(2026, 6, 1),
        leistungszeitraum=Leistungszeitraum(von=date(2026, 5, 1), bis=date(2026, 5, 31)),
        verkaeufer=firma,
        kaeufer=kaeufer,
        reverse_charge=False,
        zahlungsbedingung="",
        anschreibentext="",
        summen=Summen(netto=Decimal("0"), steuer=Decimal("0"), brutto=Decimal("0")),
        positionen=positionen,
    )


def test_verbrauch_summiert_positionen_der_rechnungen():
    positionen = [
        Position(
            artikel_id="art-1",
            bezeichnung="A1",
            menge=Decimal("5"),
            einzelpreis=Decimal("1200"),
            gesamtpreis=Decimal("6000"),
        ),
        Position(
            artikel_id="art-2",
            bezeichnung="A2",
            menge=Decimal("3"),
            einzelpreis=Decimal("1400"),
            gesamtpreis=Decimal("4200"),
        ),
    ]
    bestellung = _bestellung(rechnungen=[_rechnung_mit_positionen(positionen)])
    assert verbrauch_gesamt(bestellung) == Decimal("10200")
    assert verbrauch_artikel(bestellung, "art-1", ObergrenzeArt.MENGE) == Decimal("5")
    assert verbrauch_artikel(bestellung, "art-1", ObergrenzeArt.BETRAG) == Decimal("6000")
    assert verbrauch_artikel(bestellung, "art-2", ObergrenzeArt.MENGE) == Decimal("3")
