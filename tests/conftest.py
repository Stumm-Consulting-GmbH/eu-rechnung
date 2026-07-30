"""Projektweite pytest-Fixtures der Testsuite.

Stellt den zentralen Reverse-Charge-Realfall (`beispiel_rechnung`) bereit, eine
versionierte Portierung des manuellen Verifikationsfalls aus
`Daten/verify_pdf_sicht.py`, sowie die optionale Anbindung der
Java-Goldstandard-Werkzeuge KoSIT und veraPDF (E-005). Fehlt Java oder ein
Werkzeug unter `werkzeuge/`, ruft die jeweilige Fixture `pytest.skip`, statt die
Suite zu brechen. So läuft die Standard-Suite ohne harte Java-Abhängigkeit.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

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
    Kaeufer,
    Kunde,
    Leistungszeitraum,
    Obergrenze,
    ObergrenzeArt,
    Position,
    Preis,
    Rechnung,
    RechnungsStatus,
    Summen,
)
from eu_rechnung.export.validation import KositKonfig, VeraPdfKonfig

# Repo-Wurzel relativ zu dieser Datei (tests/), damit die Werkzeug-Pfade
# unabhängig vom aktuellen Arbeitsverzeichnis aufgelöst werden.
_PROJEKT_WURZEL = Path(__file__).resolve().parent.parent
_WERKZEUGE = _PROJEKT_WURZEL / "werkzeuge"


# --- Zentraler Reverse-Charge-Realfall --------------------------------------


@pytest.fixture
def beispiel_rechnung() -> tuple[Rechnung, str, str]:
    """Realistischer Reverse-Charge-Fall (CH-Verkäufer an DE-Kunde).

    Inhaltsgleich zu `Daten/verify_pdf_sicht.py`: zwei Positionen, Umlaute,
    aktive und inaktive individuelle Felder, mehrzeiliges Anschreiben.
    Function-scoped, damit jeder Test eine frische, mutierbare Instanz erhält.
    Rückgabe ist `(Rechnung, bestellnummer, waehrung)`; BT-13 und BT-5 (Belegwährung)
    stammen aus der Bestellung.
    """
    verkaeufer = EigeneFirma(
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
                iban="CH09 0000 0000 0000 0000 1",
                bic="MUSTCHZZ",
                waehrung="EUR",
            )
        ],
        namenszusatz=["IT-Beratung", ""],
    )
    kaeufer = Kaeufer(
        name="Beispiel Kunde GmbH",
        adresse=Adresse(strasse="Musterstraße", hausnummer="5", plz="80331", ort="München", land="DE"),
        umsatzsteuer_id="DE123456789",
        kundennummer="D10002",
        email="rechnungseingang@example.org",
        namenszusatz=["- Rechnungswesen -", ""],
    )
    positionen = [
        Position(
            artikel_id="art-1",
            bezeichnung="IT-Beratung Senior Projektleitung (S/4HANA-Transformation)",
            menge=Decimal("10"),
            einzelpreis=Decimal("1200.00"),
            gesamtpreis=Decimal("12000.00"),
        ),
        Position(
            artikel_id="art-2",
            bezeichnung="Cutover-Management nach Aufwand",
            menge=Decimal("3.5"),
            einzelpreis=Decimal("1400.00"),
            gesamtpreis=Decimal("4900.00"),
            leistungszeitraum=Leistungszeitraum(von=date(2026, 5, 10), bis=date(2026, 5, 20)),
        ),
    ]
    rechnung = Rechnung(
        id="rech-1",
        rechnungsnummer="2026-10001",
        rechnungsdatum=date(2026, 6, 19),
        leistungszeitraum=Leistungszeitraum(von=date(2026, 5, 1), bis=date(2026, 5, 31)),
        verkaeufer=verkaeufer,
        kaeufer=kaeufer,
        reverse_charge=True,
        bankverbindung=verkaeufer.bankverbindungen[0],  # gewählte Bankverbindung (EUR-Konto)
        zahlungsbedingung="Zahlbar innerhalb von 30 Tagen ohne Abzug.",
        anschreibentext=(
            "Sehr geehrte Damen und Herren,\n\n"
            "für die im Mai 2026 erbrachten Beratungsleistungen erlaube ich mir, "
            "Ihnen den folgenden Betrag in Rechnung zu stellen.\n\n"
            "Mit freundlichen Grüßen\nMax Muster"
        ),
        summen=Summen(
            netto=Decimal("16900.00"), steuer=Decimal("0.00"), brutto=Decimal("16900.00")
        ),
        positionen=positionen,
        individuelle_felder=[
            IndividuellesFeld(name="Leistungspaket", aktiv=True, wert="#PAKET_1"),
            IndividuellesFeld(name="Projektphase", aktiv=True, wert="Cutover & Go-Live"),
            IndividuellesFeld(name="Interne Notiz", aktiv=False, wert="DARF NICHT ERSCHEINEN"),
        ],
    )
    bestellnummer = "4500000001"  # BT-13, aus der Bestellung
    waehrung = "EUR"  # BT-5, Belegwährung der Bestellung
    return rechnung, bestellnummer, waehrung


@pytest.fixture
def beispiel_datenbestand() -> Datenbestand:
    """Vollständiger Datenbestand für die Serialisierungs- und Persistenztests.

    Bewusst so bestückt, dass alle Sondertypen der (De)serialisierung vorkommen:
    Decimal, `date`, ein aware-UTC-`datetime` (`zuletzt_erzeugt_am`), Enum
    (`RechnungsStatus.ERZEUGT`), `None`-Felder (geerbtes Anschreiben), Listen und
    das dict `naechste_rechnungsnummer`. Deckt die verschachtelte Hierarchie
    Kunde → Bestellung → Rechnung ab.
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
                iban="CH09 0000 0000 0000 0000 1",
                bic="MUSTCHZZ",
                waehrung="EUR",
            )
        ],
        namenszusatz=["IT-Beratung", ""],
    )
    einstellungen = Einstellungen(
        standard_anschreibentext="Sehr geehrte Damen und Herren,",
        naechste_rechnungsnummer={"2026": 10002},
        naechste_debitornummer=10003,
    )
    artikel = [
        Artikel(
            id="art-1",
            artikelname="IT-Beratung Senior",
            vorschlagspreis=Preis(betrag=Decimal("1200.00"), waehrung="EUR"),
        ),
        Artikel(
            id="art-2",
            artikelname="Cutover-Management",
            vorschlagspreis=Preis(betrag=Decimal("1400.00"), waehrung="EUR"),
        ),
    ]
    rechnung = Rechnung(
        id="rech-1",
        rechnungsnummer="2026-10001",
        rechnungsdatum=date(2026, 6, 19),
        leistungszeitraum=Leistungszeitraum(von=date(2026, 5, 1), bis=date(2026, 5, 31)),
        verkaeufer=firma,
        kaeufer=Kaeufer(
            name="Beispiel Kunde GmbH",
            adresse=Adresse(strasse="Musterstraße", hausnummer="5", plz="80331", ort="München", land="DE"),
            umsatzsteuer_id="DE123456789",
            kundennummer="D10002",
            email="rechnungseingang@example.org",
            namenszusatz=["- Rechnungswesen -", ""],
        ),
        reverse_charge=True,
        zahlungsbedingung="Zahlbar innerhalb von 30 Tagen ohne Abzug.",
        anschreibentext="Sehr geehrte Damen und Herren,\n\nMit freundlichen Grüßen",
        summen=Summen(
            netto=Decimal("16900.00"), steuer=Decimal("0.00"), brutto=Decimal("16900.00")
        ),
        status=RechnungsStatus.ERZEUGT,
        zuletzt_erzeugt_am=datetime(2026, 6, 20, 12, 30, 15, tzinfo=timezone.utc),
        positionen=[
            Position(
                artikel_id="art-1",
                bezeichnung="IT-Beratung Senior Projektleitung",
                menge=Decimal("10"),
                einzelpreis=Decimal("1200.00"),
                gesamtpreis=Decimal("12000.00"),
            ),
            Position(
                artikel_id="art-2",
                bezeichnung="Cutover-Management nach Aufwand",
                menge=Decimal("3.5"),
                einzelpreis=Decimal("1400.00"),
                gesamtpreis=Decimal("4900.00"),
            ),
        ],
        individuelle_felder=[
            IndividuellesFeld(name="Leistungspaket", aktiv=True, wert="#PAKET_1"),
        ],
    )
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
        anschreibentext=None,  # erbt vom Kunden
        rechnungen=[rechnung],
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


# --- Optionale Java-Goldstandard-Werkzeuge (E-005) --------------------------


def _java_vorhanden() -> bool:
    """True, wenn ein aufrufbares `java` im PATH liegt."""
    if shutil.which("java") is None:
        return False
    try:
        subprocess.run(
            ["java", "-version"], capture_output=True, check=False, timeout=30
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.fixture
def kosit_konfig() -> KositKonfig:
    """KoSIT-Konfiguration aus `werkzeuge/kosit/`; skippt ohne Werkzeug oder Java."""
    validator_jar = _WERKZEUGE / "kosit" / "validator-1.6.2-standalone.jar"
    szenarien = _WERKZEUGE / "kosit" / "config" / "scenarios.xml"
    repository = _WERKZEUGE / "kosit" / "config"
    if not (validator_jar.exists() and szenarien.exists() and repository.exists()):
        pytest.skip("KoSIT-Validator nicht unter werkzeuge/kosit/ vorhanden")
    if not _java_vorhanden():
        pytest.skip("Kein aufrufbares Java für KoSIT vorhanden")
    return KositKonfig(
        validator_jar=validator_jar, szenarien=szenarien, repository=repository
    )


@pytest.fixture
def verapdf_konfig() -> VeraPdfKonfig:
    """veraPDF-Konfiguration aus `werkzeuge/verapdf/`; skippt ohne Werkzeug oder Java."""
    verapdf = _WERKZEUGE / "verapdf" / "verapdf.bat"
    if not verapdf.exists():
        pytest.skip("veraPDF nicht unter werkzeuge/verapdf/ vorhanden")
    if not _java_vorhanden():
        pytest.skip("Kein aufrufbares Java für veraPDF vorhanden")
    return VeraPdfKonfig(verapdf=verapdf)
