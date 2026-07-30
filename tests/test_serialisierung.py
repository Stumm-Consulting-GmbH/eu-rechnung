"""Tests der typgesteuerten (De)serialisierung (`serialisierung.py`).

Geprüft werden der verlustfreie Roundlauf über den vollständigen Datenbestand
sowie die bewusst gewählte JSON-Form der Sondertypen (Decimal als String,
`datetime` als UTC mit Z-Suffix, Enum über den Wert, `None`, dict).
"""

from datetime import date
from decimal import Decimal

from eu_rechnung.domain import (
    Adresse,
    Artikel,
    ArtikelTyp,
    Bankverbindung,
    Bestellung,
    Datenbestand,
    EigeneFirma,
    Einstellungen,
    GueltigerArtikel,
    Kunde,
    Leistungszeitraum,
    Obergrenze,
    ObergrenzeArt,
    Position,
    Preis,
    Rechnung,
    RechnungsStatus,
    Skonto,
)
from eu_rechnung.persistence.serialisierung import von_json, zu_json


def test_roundtrip_vollstaendig(beispiel_datenbestand):
    """`zu_json` gefolgt von `von_json` liefert einen gleichwertigen Datenbestand."""
    daten = zu_json(beispiel_datenbestand)
    zurueck = von_json(Datenbestand, daten)
    assert zurueck == beispiel_datenbestand


def _erste_rechnung(daten: dict) -> dict:
    return daten["kunden"][0]["bestellungen"][0]["rechnungen"][0]


def test_decimal_als_string(beispiel_datenbestand):
    """Decimal wird als String serialisiert, auch im verschachtelten Preis-Wertobjekt."""
    daten = zu_json(beispiel_datenbestand)
    vorschlagspreis = daten["artikel"][0]["vorschlagspreis"]
    assert vorschlagspreis == {"betrag": "1200.00", "waehrung": "EUR"}
    assert isinstance(vorschlagspreis["betrag"], str)


def test_datetime_als_utc_z(beispiel_datenbestand):
    """Erzeugungs-Zeitstempel als UTC, sekundengenau, mit Z-Suffix (Standard H)."""
    daten = zu_json(beispiel_datenbestand)
    assert _erste_rechnung(daten)["zuletzt_erzeugt_am"] == "2026-06-20T12:30:15Z"


def test_date_als_isoformat(beispiel_datenbestand):
    daten = zu_json(beispiel_datenbestand)
    assert _erste_rechnung(daten)["rechnungsdatum"] == "2026-06-19"


def test_enum_als_wert(beispiel_datenbestand):
    daten = zu_json(beispiel_datenbestand)
    assert _erste_rechnung(daten)["status"] == RechnungsStatus.ERZEUGT.value == "Erzeugt"


def test_none_bleibt_none(beispiel_datenbestand):
    """Geerbtes Anschreiben (`None`) bleibt erhalten, statt zu verschwinden."""
    daten = zu_json(beispiel_datenbestand)
    assert daten["kunden"][0]["anschreibentext"] is None


def test_dict_jahr_zu_nummer(beispiel_datenbestand):
    daten = zu_json(beispiel_datenbestand)
    assert daten["einstellungen"]["naechste_rechnungsnummer"] == {"2026": 10002}


def test_firma_v1_felder_roundtrip():
    """Die v1-Firma-Felder bleiben beim Roundlauf erhalten (4T-0087): Schalter
    `xrechnung_aktiv`, Adress-Hausnummer und mehrere Bankverbindungen mit Währung."""
    firma = EigeneFirma(
        name="Test GmbH",
        adresse=Adresse(
            strasse="Hauptstrasse", plz="12345", ort="Musterstadt", land="DE",
            hausnummer="7a",
        ),
        mehrwertsteuer_id="DE123456789",
        email="info@test.de",
        telefon="+49 30 123456",
        kontakt_name="Max Muster",
        bankverbindungen=[
            Bankverbindung(
                kontoinhaber="Test GmbH", bank="Bank A", iban="DE0011112222",
                bic="AAAADEFFXXX", waehrung="EUR",
            ),
            Bankverbindung(
                kontoinhaber="Test GmbH", bank="Bank B", iban="CH0033334444",
                bic="BBBBCHZZ", waehrung="CHF",
            ),
        ],
        xrechnung_aktiv=False,
        standard_steuersatz=Decimal("7.7"),
    )
    zurueck = von_json(EigeneFirma, zu_json(firma))
    assert zurueck == firma
    assert len(zurueck.bankverbindungen) == 2
    assert zurueck.bankverbindungen[1].waehrung == "CHF"
    assert zurueck.adresse.hausnummer == "7a"
    assert zurueck.xrechnung_aktiv is False
    assert zurueck.standard_steuersatz == Decimal("7.7")


def test_artikel_v1_felder_roundtrip():
    """Die v1-Artikel-Felder überstehen den Roundlauf (4T-0089): Vorschlagspreis als
    `Preis`-Wertobjekt, das `aktiv`-Flag und der `typ` (Produkt/Leistung)."""
    artikel = Artikel(
        id="art-99",
        artikelname="Beispielprodukt",
        vorschlagspreis=Preis(betrag=Decimal("99.90"), waehrung="CHF"),
        aktiv=False,
        typ=ArtikelTyp.PRODUKT,
    )
    zurueck = von_json(Artikel, zu_json(artikel))
    assert zurueck == artikel
    assert zurueck.vorschlagspreis == Preis(betrag=Decimal("99.90"), waehrung="CHF")
    assert zurueck.aktiv is False
    assert zurueck.typ is ArtikelTyp.PRODUKT


def test_artikel_ohne_neue_felder_erhaelt_defaults():
    """AK4: Ein Bestandsartikel ohne `aktiv`/`typ` erhält beim Laden die Defaults
    (aktiv=Ja, typ=Leistung) über die dataclass-Defaults, ohne Sonderbehandlung."""
    alt = {
        "id": "art-1",
        "artikelname": "Altbestand",
        "vorschlagspreis": {"betrag": "100.00", "waehrung": "EUR"},
    }
    artikel = von_json(Artikel, alt)
    assert artikel.aktiv is True
    assert artikel.typ is ArtikelTyp.LEISTUNG
    assert artikel.vorschlagspreis == Preis(betrag=Decimal("100.00"), waehrung="EUR")


def test_kunde_v1_felder_roundtrip():
    """Die v1-Kunde-Felder überstehen den Roundlauf (4T-0090): das aktiv-Flag sowie die
    optionalen Vererbungsfelder `waehrung` und `rechnungssprache` (`None` = erbt)."""
    kunde = Kunde(
        id="kun-9",
        kundennummer="D10099",
        name="Muster AG",
        adresse=Adresse(strasse="Weg 1", plz="3000", ort="Bern", land="CH"),
        email="rechnung@muster.ch",
        umsatzsteuer_id="CHE-999.999.999",
        reverse_charge=False,
        aktiv=False,
        waehrung="CHF",
        rechnungssprache="fr",
    )
    zurueck = von_json(Kunde, zu_json(kunde))
    assert zurueck == kunde
    assert zurueck.aktiv is False
    assert zurueck.waehrung == "CHF"
    assert zurueck.rechnungssprache == "fr"


def test_kunde_ohne_neue_felder_erhaelt_defaults():
    """AK4: Ein Bestandskunde ohne `aktiv`/`waehrung`/`rechnungssprache` erhält beim Laden
    die Defaults (aktiv=Ja, Währung/Sprache erben) über die dataclass-Defaults."""
    alt = {
        "id": "kun-1",
        "kundennummer": "D10002",
        "name": "Altbestand GmbH",
        "adresse": {"strasse": "Alt 1", "plz": "10000", "ort": "Berlin", "land": "DE"},
        "email": "alt@bestand.de",
        "umsatzsteuer_id": "DE111111111",
        "reverse_charge": True,
    }
    kunde = von_json(Kunde, alt)
    assert kunde.aktiv is True
    assert kunde.waehrung is None
    assert kunde.rechnungssprache is None


def test_bestellung_v1_felder_roundtrip():
    """Die v1-Bestellung-Felder überstehen den Roundlauf (4T-0091): Belegwährung,
    Gesamt-Höchstbetrag, aktiv, Rechnungssprache und die diskriminierte Artikel-Obergrenze
    (Menge oder Betrag; `None` = keine Grenze)."""
    bestellung = Bestellung(
        id="best-9",
        bestellnummer="B-999",
        beginn_datum=date(2026, 1, 1),
        ende_datum=date(2026, 12, 31),
        zahlungsfrist=14,
        zahlungsbedingung="Zahlbar in 14 Tagen.",
        waehrung="CHF",
        gesamt_hoechstbetrag=Decimal("50000.00"),
        aktiv=False,
        rechnungssprache="fr",
        gueltige_artikel=[
            GueltigerArtikel(
                artikel_id="art-1",
                einzelpreis=Decimal("1000.00"),
                obergrenze=Obergrenze(art=ObergrenzeArt.BETRAG, wert=Decimal("30000.00")),
            ),
            GueltigerArtikel(artikel_id="art-2", einzelpreis=Decimal("500.00")),
        ],
    )
    zurueck = von_json(Bestellung, zu_json(bestellung))
    assert zurueck == bestellung
    assert zurueck.waehrung == "CHF"
    assert zurueck.gesamt_hoechstbetrag == Decimal("50000.00")
    assert zurueck.aktiv is False
    assert zurueck.rechnungssprache == "fr"
    assert zurueck.gueltige_artikel[0].obergrenze == Obergrenze(
        art=ObergrenzeArt.BETRAG, wert=Decimal("30000.00")
    )
    assert zurueck.gueltige_artikel[1].obergrenze is None


def test_bestellung_ohne_neue_felder_erhaelt_defaults():
    """AK5: Eine Bestandsbestellung ohne die neuen Felder erhält beim Laden die Defaults
    (Belegwährung EUR, aktiv=Ja, kein Höchstbetrag, Sprache erbt); ein gültiger Artikel
    ohne Obergrenze erhält `None`."""
    alt = {
        "id": "best-1",
        "bestellnummer": "4500000001",
        "beginn_datum": "2026-05-01",
        "ende_datum": "2026-05-31",
        "zahlungsfrist": 30,
        "zahlungsbedingung": "Zahlbar in 30 Tagen.",
        "gueltige_artikel": [
            {"artikel_id": "art-1", "einzelpreis": "1200.00"},
        ],
    }
    bestellung = von_json(Bestellung, alt)
    assert bestellung.waehrung == "EUR"
    assert bestellung.aktiv is True
    assert bestellung.gesamt_hoechstbetrag is None
    assert bestellung.rechnungssprache is None
    assert bestellung.gueltige_artikel[0].obergrenze is None


def test_einstellungen_v1_felder_roundtrip():
    """Die v1-Einstellungen-Felder überstehen den Roundlauf (4T-0092): pflegbare
    Währungsliste, Standardwährung und UI-Sprache; dazu das Ausgabe-Verzeichnis (S-0057)."""
    einstellungen = Einstellungen(
        standard_anschreibentext="Text",
        waehrungsliste=["EUR", "CHF", "USD"],
        standardwaehrung="CHF",
        ui_sprache="en",
        ausgabe_verzeichnis=r"C:\Rechnungen",
    )
    zurueck = von_json(Einstellungen, zu_json(einstellungen))
    assert zurueck == einstellungen
    assert zurueck.waehrungsliste == ["EUR", "CHF", "USD"]
    assert zurueck.standardwaehrung == "CHF"
    assert zurueck.ui_sprache == "en"
    assert zurueck.ausgabe_verzeichnis == r"C:\Rechnungen"


def test_position_leistungszeitraum_roundtrip():
    """Die Position trägt einen optionalen Leistungszeitraum (BG-26, S-0068); eine
    Position ohne trägt `None`."""
    mit = Position(
        artikel_id="art-1",
        bezeichnung="Beratung",
        menge=Decimal("5"),
        einzelpreis=Decimal("1000.00"),
        gesamtpreis=Decimal("5000.00"),
        leistungszeitraum=Leistungszeitraum(von=date(2026, 3, 1), bis=date(2026, 3, 31)),
    )
    ohne = Position(
        artikel_id="art-2",
        bezeichnung="Produkt",
        menge=Decimal("2"),
        einzelpreis=Decimal("50.00"),
        gesamtpreis=Decimal("100.00"),
    )
    assert von_json(Position, zu_json(mit)) == mit
    assert von_json(Position, zu_json(ohne)) == ohne
    assert von_json(Position, zu_json(ohne)).leistungszeitraum is None


def test_rechnung_rechnungssprache_roundtrip(beispiel_datenbestand):
    """AK2: Die Rechnung trägt die Rechnungssprache als eigenen Wert (Default `de`), der
    den Roundlauf übersteht; ein abweichender Wert bleibt erhalten."""
    rechnung = beispiel_datenbestand.kunden[0].bestellungen[0].rechnungen[0]
    assert rechnung.rechnungssprache == "de"  # Default, Rückfall Deutsch (S-0058)
    rechnung.rechnungssprache = "it"
    zurueck = von_json(Datenbestand, zu_json(beispiel_datenbestand))
    assert zurueck.kunden[0].bestellungen[0].rechnungen[0].rechnungssprache == "it"


def test_v1_rest_ohne_neue_felder_erhaelt_defaults():
    """AK5: Bestandsdaten ohne die neuen Felder erhalten beim Laden die Defaults:
    Einstellungen (Währungsliste [EUR], Standardwährung EUR, UI-Sprache de) und eine
    Position ohne Leistungszeitraum (None)."""
    einstellungen = von_json(Einstellungen, {"standard_anschreibentext": "X"})
    assert einstellungen.waehrungsliste == ["EUR"]
    assert einstellungen.standardwaehrung == "EUR"
    assert einstellungen.ui_sprache == "de"
    assert einstellungen.ausgabe_verzeichnis == ""  # S-0057: leer = beim Erzeugen vorschlagen
    position = von_json(
        Position,
        {
            "artikel_id": "art-1",
            "bezeichnung": "Alt",
            "menge": "1",
            "einzelpreis": "10.00",
            "gesamtpreis": "10.00",
        },
    )
    assert position.leistungszeitraum is None


def test_rechnung_ohne_steuersatz_erhaelt_default(beispiel_datenbestand):
    """S-0079: Eine Bestandsrechnung ohne das neue Feld `steuersatz` erhält beim Laden den
    Default 0 (Reverse-Charge-Fall; die Kategorie ergibt sich aus dem RC-Kennzeichen)."""
    daten = zu_json(beispiel_datenbestand)
    del _erste_rechnung(daten)["steuersatz"]  # Altbestand ohne das Feld
    zurueck = von_json(Datenbestand, daten)
    assert zurueck.kunden[0].bestellungen[0].rechnungen[0].steuersatz == Decimal("0")


def test_rechnung_skonto_roundtrip(beispiel_datenbestand):
    """S-0051: Das optionale Skonto-Wertobjekt übersteht den Roundlauf; die Tage bleiben
    ganzzahlig, der Prozentsatz wird wie jedes Decimal als String geführt."""
    rechnung = beispiel_datenbestand.kunden[0].bestellungen[0].rechnungen[0]
    assert rechnung.skonto is None  # Default: kein Skonto
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2.00"))
    daten = zu_json(beispiel_datenbestand)
    assert _erste_rechnung(daten)["skonto"] == {"tage": 14, "prozent": "2.00"}
    zurueck = von_json(Datenbestand, daten)
    assert zurueck == beispiel_datenbestand
    assert zurueck.kunden[0].bestellungen[0].rechnungen[0].skonto == Skonto(
        tage=14, prozent=Decimal("2.00")
    )


def test_rechnung_ohne_skonto_erhaelt_default(beispiel_datenbestand):
    """S-0051: Eine Bestandsrechnung ohne das neue Feld `skonto` lädt weiter und erhält den
    Default `None` über den dataclass-Default, ohne Schema-Bump oder Migration."""
    daten = zu_json(beispiel_datenbestand)
    del _erste_rechnung(daten)["skonto"]  # Altbestand ohne das Feld
    zurueck = von_json(Datenbestand, daten)
    assert zurueck.kunden[0].bestellungen[0].rechnungen[0].skonto is None


def test_bestellung_skonto_und_zahlungsfrist_roundtrip(beispiel_datenbestand):
    """S-0080: Das vereinbarte Skonto der Bestellung und die Zahlungsfrist der Rechnung
    überstehen den Roundlauf."""
    bestellung = beispiel_datenbestand.kunden[0].bestellungen[0]
    assert bestellung.skonto is None  # Default: keine Vereinbarung
    bestellung.skonto = Skonto(tage=14, prozent=Decimal("2.00"))
    bestellung.rechnungen[0].zahlungsfrist = 30
    daten = zu_json(beispiel_datenbestand)
    assert daten["kunden"][0]["bestellungen"][0]["skonto"] == {"tage": 14, "prozent": "2.00"}
    assert _erste_rechnung(daten)["zahlungsfrist"] == 30
    zurueck = von_json(Datenbestand, daten)
    assert zurueck == beispiel_datenbestand


def test_bestand_ohne_zahlungsmodalitaeten_erhaelt_defaults(beispiel_datenbestand):
    """S-0080: Bestandsdaten ohne die neuen Felder laden weiter und erhalten die Defaults
    (Bestellung ohne Skonto, Rechnung mit Zahlungsfrist 0); kein Schema-Bump."""
    daten = zu_json(beispiel_datenbestand)
    del daten["kunden"][0]["bestellungen"][0]["skonto"]
    del _erste_rechnung(daten)["zahlungsfrist"]
    zurueck = von_json(Datenbestand, daten)
    assert zurueck.kunden[0].bestellungen[0].skonto is None
    assert zurueck.kunden[0].bestellungen[0].rechnungen[0].zahlungsfrist == 0


def test_firma_ohne_standard_steuersatz_erhaelt_default():
    """S-0079: Eine Bestandsfirma ohne `standard_steuersatz` erhält beim Laden den Default 0."""
    firma = von_json(
        EigeneFirma,
        {
            "name": "Alt GmbH",
            "adresse": {"strasse": "Alt 1", "plz": "10000", "ort": "Berlin", "land": "DE"},
            "mehrwertsteuer_id": "DE111111111",
            "email": "a@b.de",
            "telefon": "",
            "kontakt_name": "",
        },
    )
    assert firma.standard_steuersatz == Decimal("0")


def test_rechnung_bankverbindung_roundtrip(beispiel_datenbestand):
    """S-0065: Die gewählte Bankverbindung übersteht den Roundlauf als eingefrorene Kopie."""
    rechnung = beispiel_datenbestand.kunden[0].bestellungen[0].rechnungen[0]
    assert rechnung.bankverbindung is None  # Default: keine Wahl
    rechnung.bankverbindung = Bankverbindung(
        kontoinhaber="Muster", bank="Beispielbank", iban="CH99", bic="BEISCHZZ", waehrung="CHF"
    )
    zurueck = von_json(Datenbestand, zu_json(beispiel_datenbestand))
    assert zurueck == beispiel_datenbestand
    assert zurueck.kunden[0].bestellungen[0].rechnungen[0].bankverbindung.iban == "CH99"


def test_rechnung_ohne_bankverbindung_erhaelt_default(beispiel_datenbestand):
    """S-0065 AK5: Eine Bestandsrechnung ohne das neue Feld `bankverbindung` lädt weiter und
    erhält den Default `None`, ohne Schema-Migration."""
    daten = zu_json(beispiel_datenbestand)
    del _erste_rechnung(daten)["bankverbindung"]  # Altbestand ohne das Feld
    zurueck = von_json(Datenbestand, daten)
    assert zurueck.kunden[0].bestellungen[0].rechnungen[0].bankverbindung is None
