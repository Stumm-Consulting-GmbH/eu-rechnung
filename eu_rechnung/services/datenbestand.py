"""Datenbestand-Bausteine der Anwendungslogik: leerer Bestand und Beispiel-Seed.

Stellt der Oberfläche zwei Ausgangs-Datenbestände bereit: `erzeuge_leeren_datenbestand`
für eine neu angelegte Firma (leere Firma, Default-Einstellungen, keine Stammdaten)
und `erzeuge_seed` als voll bestückten Beispiel-Datenbestand. Der frühere
Produktiv-Auto-Seed (Laden mit Anlage bei fehlender Datei) ist mit der
dokument-basierten Persistenz entfallen (4T-0079): eine neue Firma wird über den
Datei-Dialog angelegt und gespeichert, nicht mehr automatisch bei fehlender
Standarddatei. `erzeuge_seed` bleibt der Reverse-Charge-Realfall (CH-Verkäufer an
DE-Kunde) und dient als Test-Fixture.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from eu_rechnung.domain import (
    Adresse,
    Artikel,
    Bankverbindung,
    Bestellung,
    Datenbestand,
    EigeneFirma,
    Einstellungen,
    GueltigerArtikel,
    IndividuellesFeld,
    Kunde,
    Obergrenze,
    ObergrenzeArt,
    Preis,
)


def erzeuge_leeren_datenbestand() -> Datenbestand:
    """Baut einen leeren Datenbestand für eine frisch angelegte Firma.

    Alle Firmenfelder sind leer, die Bankverbindungen offen und die Stammdaten-
    Listen (Artikel, Kunden) leer; die Einstellungen tragen ihre Defaults. Der
    Anwender füllt die Firma anschließend über die Erfassungsmaske (S-0071 AK1).
    """
    firma = EigeneFirma(
        name="",
        adresse=Adresse(strasse="", plz="", ort="", land=""),
        mehrwertsteuer_id="",
        email="",
        telefon="",
        kontakt_name="",
    )
    return Datenbestand(
        eigene_firma=firma,
        einstellungen=Einstellungen(standard_anschreibentext=""),
    )


def erzeuge_seed() -> Datenbestand:
    """Baut den Beispiel-Datenbestand des Durchstichs (Reverse-Charge-Realfall).

    Eine Firma (Aussteller), ein Kunde mit Reverse-Charge und eine Bestellung mit
    zwei gültigen Artikeln; noch ohne Rechnung.
    """
    firma = EigeneFirma(
        name="Muster Consulting GmbH",
        adresse=Adresse(strasse="Musterstrasse", hausnummer="1", plz="4000", ort="Basel", land="CH"),
        mehrwertsteuer_id="CHE-999.999.999 MWST",
        email="kontakt@example.com",
        telefon="+41 44 123 45 67",
        kontakt_name="Max Muster",
        bankverbindungen=[
            Bankverbindung(
                kontoinhaber="Muster Consulting GmbH",
                bank="Beispielbank",
                # Formal gültige Beispiel-IBAN: Die Modulo-97-Prüfziffer stimmt, sonst
                # wiese die Firma-Prüfung den Seed zurück (`services/firma.py`).
                iban="CH09 0000 0000 0000 0000 1",
                bic="MUSTCHZZ",
                waehrung="EUR",
            )
        ],
        namenszusatz=["IT-Beratung", ""],
    )
    einstellungen = Einstellungen(
        standard_anschreibentext=(
            "Sehr geehrte Damen und Herren,\n\n"
            "für die erbrachten Leistungen erlaube ich mir, Ihnen den folgenden "
            "Betrag in Rechnung zu stellen.\n\n"
            "Mit freundlichen Grüßen\nMax Muster"
        ),
        naechste_rechnungsnummer={"2026": 10001},
        naechste_debitornummer=10003,
    )
    artikel = [
        Artikel(
            id="art-1",
            artikelname="IT-Beratung Senior Projektleitung",
            vorschlagspreis=Preis(betrag=Decimal("1200.00"), waehrung="EUR"),
        ),
        Artikel(
            id="art-2",
            artikelname="Cutover-Management nach Aufwand",
            vorschlagspreis=Preis(betrag=Decimal("1400.00"), waehrung="EUR"),
        ),
    ]
    bestellung = Bestellung(
        id="best-1",
        bestellnummer="4500000001",
        beginn_datum=date(2026, 5, 1),
        ende_datum=date(2026, 5, 31),
        zahlungsfrist=30,
        zahlungsbedingung="Zahlbar innerhalb von 30 Tagen ohne Abzug.",
        waehrung="EUR",
        gueltige_artikel=[
            GueltigerArtikel(
                artikel_id="art-1",
                einzelpreis=Decimal("1200.00"),
                obergrenze=Obergrenze(art=ObergrenzeArt.MENGE, wert=Decimal("20")),
            ),
            GueltigerArtikel(
                artikel_id="art-2",
                einzelpreis=Decimal("1400.00"),
                obergrenze=Obergrenze(art=ObergrenzeArt.MENGE, wert=Decimal("10")),
            ),
        ],
        individuelle_felder=[],
        anschreibentext=None,  # erbt vom Kunden
        rechnungen=[],
    )
    kunde = Kunde(
        id="kun-1",
        kundennummer="D10002",
        name="Beispiel Kunde GmbH",
        adresse=Adresse(strasse="Musterstraße", hausnummer="5", plz="80331", ort="München", land="DE"),
        email="rechnungseingang@example.org",
        umsatzsteuer_id="DE123456789",
        reverse_charge=True,
        namenszusatz=["- Rechnungswesen -", ""],
        individuelle_felder=[
            IndividuellesFeld(name="Leistungspaket", aktiv=True, wert="#PAKET_1"),
            IndividuellesFeld(name="Projektphase", aktiv=True, wert="Cutover & Go-Live"),
        ],
        anschreibentext=None,  # erbt vom Standard
        bestellungen=[bestellung],
    )
    return Datenbestand(
        eigene_firma=firma,
        einstellungen=einstellungen,
        artikel=artikel,
        kunden=[kunde],
    )
