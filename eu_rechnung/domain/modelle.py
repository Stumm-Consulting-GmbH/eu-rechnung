"""Domänenmodell der Anwendung.

Die Klassen bilden das in Datenmodell.md beschriebene Datenmodell ab. Sie
tragen nur Daten und einfache Strukturen, keine Berechnungs- oder
Persistenzlogik: Die Summenbildung gehört in services/export, das Laden und
Speichern in persistence. Geldbeträge sind Decimal, Datumswerte date bzw.
datetime (UTC) für den Erzeugungs-Zeitstempel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class RechnungsStatus(str, Enum):
    """Status einer Rechnung, rein informativ für die Übersicht."""

    ENTWURF = "Entwurf"
    ERZEUGT = "Erzeugt"


class ArtikelTyp(str, Enum):
    """Art eines Artikels. Eine Leistung trägt einen Leistungszeitraum, ein Produkt nicht."""

    PRODUKT = "Produkt"
    LEISTUNG = "Leistung"


class ObergrenzeArt(str, Enum):
    """Art einer Artikel-Obergrenze in der Bestellung: Mengen- oder Betragsgrenze."""

    MENGE = "menge"
    BETRAG = "betrag"


# --- Gemeinsame Bausteine ---------------------------------------------------


@dataclass
class Adresse:
    strasse: str
    plz: str
    ort: str
    land: str  # ISO-Ländercode, z.B. "CH", "DE"
    hausnummer: str = ""  # optionales eigenes Adressfeld (S-0001)

    def adresszeile(self) -> str:
        """Straße und Hausnummer als **eine** Zeile, wie die Ausgabe sie braucht.

        EN 16931 kennt keine separate Hausnummer; das Datenmodell führt sie als eigenes
        Feld und schreibt die Zusammenführung beim Mapping vor. Sie steht hier und nicht
        je einmal in Oberfläche, Sichtteil und XML-Mapping: Fünf Kopien derselben Regel
        wären der sichere Weg, dass die sechste Stelle sie wieder vergisst. Genau so ist
        der Fehler entstanden, den 4T-0201 behebt.

        Ist die Hausnummer leer, bleibt die Zeile unverändert die Straße; Bestände, die
        die Hausnummer bisher in der Straße mitführen, sehen deshalb aus wie zuvor.
        """
        if not self.hausnummer.strip():
            return self.strasse
        return f"{self.strasse} {self.hausnummer}".strip()


@dataclass
class Bankverbindung:
    kontoinhaber: str
    bank: str
    iban: str
    bic: str
    waehrung: str  # genau eine Währung je Bankverbindung (S-0001)


@dataclass
class IndividuellesFeld:
    """Frei benennbares Zusatzfeld auf Kunden- oder Bestellungsebene."""

    name: str
    aktiv: bool
    wert: str


@dataclass
class Preis:
    """Geldbetrag netto mit Währung. Wiederverwendbares Wertobjekt (Artikel-Vorschlagspreis)."""

    betrag: Decimal
    waehrung: str


@dataclass
class Obergrenze:
    """Optionale Obergrenze eines gültigen Artikels: Menge oder Betrag (netto, in Belegwährung)."""

    art: ObergrenzeArt
    wert: Decimal


# --- Stammdaten -------------------------------------------------------------


@dataclass
class Artikel:
    """Globaler Artikel, in Bestellungen per id referenziert."""

    id: str
    artikelname: str
    vorschlagspreis: Preis  # Betrag netto plus Pflicht-Währung (S-0005)
    aktiv: bool = True  # false = erscheint nicht in neuen Auswahllisten (S-0005)
    typ: ArtikelTyp = ArtikelTyp.LEISTUNG  # Produkt oder Leistung, Default Leistung (S-0066)


@dataclass
class GueltigerArtikel:
    """Zuordnung eines Artikels zu einer Bestellung (n:m mit eigenen Attributen)."""

    artikel_id: str
    einzelpreis: Decimal  # vorbelegt aus vorschlagspreis, überschreibbar
    obergrenze: Obergrenze | None = None  # None = keine Grenze; Menge oder Betrag (S-0017)


@dataclass
class EigeneFirma:
    """Stammdaten der eigenen Firma. Dient als Vorlage des Rechnungs-Verkäufers."""

    name: str
    adresse: Adresse
    mehrwertsteuer_id: str
    email: str  # BT-34 elektronische Adresse und BT-43 Kontakt-E-Mail
    telefon: str  # BT-42 Kontakt-Telefon (BG-6)
    kontakt_name: str  # BT-41 Kontaktname (BG-6, XRechnung-Pflicht BR-DE-2)
    bankverbindungen: list[Bankverbindung] = field(default_factory=list)  # je eine Währung
    namenszusatz: list[str] = field(default_factory=list)  # bis zu 2 freie Zeilen
    xrechnung_aktiv: bool = True  # Steuerfeld der zweistufigen Pflicht (S-0001)
    standard_steuersatz: Decimal = Decimal("0")  # USt-Standardsatz der Firma in Prozent, belegt die Rechnung vor (S-0079)


@dataclass
class Einstellungen:
    standard_anschreibentext: str
    naechste_rechnungsnummer: dict[str, int] = field(default_factory=dict)  # Jahr -> Nr
    naechste_debitornummer: int = 10001  # durchlaufender Zähler, Präfix D
    waehrungsliste: list[str] = field(default_factory=lambda: ["EUR"])  # ISO-4217, min. ein Eintrag (S-0062)
    standardwaehrung: str = "EUR"  # Default-Währung aus der Liste (S-0062)
    ui_sprache: str = "de"  # Bedienoberfläche, eine aus fünf, Default DE (S-0058)
    ausgabe_verzeichnis: str = ""  # Wurzel der Ausgabe-Ablage; leer = beim Erzeugen vorschlagen (S-0057)


# --- Rechnung (festgeschrieben, hält editierbare Kopien) --------------------


@dataclass
class Leistungszeitraum:
    von: date
    bis: date


@dataclass
class Kaeufer:
    """Rechnungs-Käufer, beim Anlegen aus dem Kunden vorbelegte Kopie."""

    name: str
    adresse: Adresse
    umsatzsteuer_id: str
    kundennummer: str  # normseitige Käuferkennung (BT-46)
    email: str  # BT-49 elektronische Adresse, aus Kunde.email übernommen
    namenszusatz: list[str] = field(default_factory=list)


@dataclass
class Position:
    """Rechnungsposition. Der Preis stammt aus der Bestellung."""

    artikel_id: str
    bezeichnung: str
    menge: Decimal
    einzelpreis: Decimal
    gesamtpreis: Decimal
    leistungszeitraum: Leistungszeitraum | None = None  # nur bei Leistungs-Artikeln (BG-26, S-0068)


@dataclass
class Summen:
    """Gehaltene Rechnungssummen. Maßgeblich werden sie bei der Erzeugung neu
    aus den Positionen berechnet (EN-16931-Mapping)."""

    netto: Decimal
    steuer: Decimal
    brutto: Decimal


@dataclass
class Skonto:
    """Strukturierte Skonto-Angabe der Rechnung: Frist in Tagen und Satz in Prozent.

    Als Wertobjekt hält es die Regel „beide oder keines" strukturell fest. Die Ausgabe
    kodiert daraus die BR-DE-18-Zeile in BT-20 und den Sichtteil-Hinweis (S-0051); auf
    Positionen, Summen und Zahlbetrag wirkt es nicht.
    """

    tage: int
    prozent: Decimal


@dataclass
class Rechnung:
    """Festgeschriebene Rechnung. Werte werden beim Anlegen aus den Stammdaten
    vorbelegt, bleiben danach editierbar (E-006)."""

    id: str
    rechnungsnummer: str
    rechnungsdatum: date
    leistungszeitraum: Leistungszeitraum
    verkaeufer: EigeneFirma
    kaeufer: Kaeufer
    reverse_charge: bool
    zahlungsbedingung: str
    anschreibentext: str  # effektiver Text nach Vererbung
    summen: Summen
    steuersatz: Decimal = Decimal("0")  # Umsatzsteuersatz in Prozent; 0 bei Reverse-Charge (AE), sonst Kategorie S (S-0079)
    skonto: Skonto | None = None  # optionale Skonto-Angabe; None = kein Skonto (S-0051)
    zahlungsfrist: int = 0  # in Tagen, aus der Bestellung vorbelegt und hier änderbar (S-0080)
    rechnungssprache: str = "de"  # aufgelöste Sprache als eigener Wert, Rückfall Deutsch (S-0058)
    bankverbindung: Bankverbindung | None = None  # gewählte Bankverbindung als eingefrorene Kopie; None = Rückfall auf die erste im Export (S-0065)
    status: RechnungsStatus = RechnungsStatus.ENTWURF
    zuletzt_erzeugt_am: datetime | None = None
    positionen: list[Position] = field(default_factory=list)
    individuelle_felder: list[IndividuellesFeld] = field(default_factory=list)


# --- Verschachtelte Hierarchie ----------------------------------------------


@dataclass
class Bestellung:
    id: str
    bestellnummer: str  # Bestellnummer des Kunden (BT-13), darf sich wiederholen
    beginn_datum: date
    ende_datum: date
    zahlungsfrist: int  # in Tagen; vertraglich vereinbart, belegt die Rechnung vor (S-0080)
    zahlungsbedingung: str
    waehrung: str = "EUR"  # Belegwährung (BT-5), Default Standardwährung; alle Beträge in ihr (S-0017)
    skonto: Skonto | None = None  # vertraglich vereinbart, belegt die Rechnung vor; None = keines (S-0080)
    gesamt_hoechstbetrag: Decimal | None = None  # optionale Gesamt-Obergrenze, netto (S-0017)
    aktiv: bool = True  # false = erscheint nicht in neuen Auswahllisten (S-0017)
    rechnungssprache: str | None = None  # None = erbt, Rückfall Deutsch (S-0058)
    gueltige_artikel: list[GueltigerArtikel] = field(default_factory=list)
    individuelle_felder: list[IndividuellesFeld] = field(default_factory=list)
    anschreibentext: str | None = None  # None = erbt vom Kunden
    rechnungen: list[Rechnung] = field(default_factory=list)


@dataclass
class Kunde:
    id: str
    kundennummer: str  # Präfix D, vorbelegt aus Zähler, editierbar
    name: str
    adresse: Adresse
    email: str
    umsatzsteuer_id: str
    reverse_charge: bool
    aktiv: bool = True  # false = erscheint nicht in neuen Auswahllisten (S-0011)
    waehrung: str | None = None  # None = erbt von der Standardwährung (S-0062)
    rechnungssprache: str | None = None  # None = erbt, Rückfall Deutsch (S-0058)
    namenszusatz: list[str] = field(default_factory=list)
    individuelle_felder: list[IndividuellesFeld] = field(default_factory=list)
    anschreibentext: str | None = None  # None = erbt vom Standard
    bestellungen: list[Bestellung] = field(default_factory=list)


@dataclass
class Datenbestand:
    """Wurzel des Datenmodells, entspricht der einen lokalen JSON-Datei."""

    eigene_firma: EigeneFirma
    einstellungen: Einstellungen
    schema_version: int = 3
    artikel: list[Artikel] = field(default_factory=list)
    kunden: list[Kunde] = field(default_factory=list)
