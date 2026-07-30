"""Tests der Datenbestand-Bausteine (leerer Bestand und Beispiel-Seed), Java-frei."""

from eu_rechnung.domain import ArtikelTyp, ObergrenzeArt
from eu_rechnung.persistence import lade, speichere
from eu_rechnung.services import erzeuge_leeren_datenbestand, erzeuge_seed


def test_seed_ist_vollstaendig_und_ohne_rechnung():
    bestand = erzeuge_seed()
    assert bestand.eigene_firma.name == "Muster Consulting GmbH"
    assert bestand.einstellungen.standardwaehrung == "EUR"  # Default-Währung (S-0062)
    assert bestand.einstellungen.ui_sprache == "de"  # Default DE (S-0058)
    assert len(bestand.artikel) == 2
    assert bestand.artikel[0].vorschlagspreis.waehrung == "EUR"  # Preis mit Pflicht-Währung (S-0005)
    assert bestand.artikel[0].aktiv is True  # Default Ja (S-0005)
    assert bestand.artikel[0].typ is ArtikelTyp.LEISTUNG  # Default Leistung (S-0066)
    assert len(bestand.kunden) == 1
    kunde = bestand.kunden[0]
    assert kunde.reverse_charge is True
    assert kunde.aktiv is True  # Default Ja (S-0011)
    assert kunde.waehrung is None  # erbt Standardwährung (S-0062)
    assert kunde.rechnungssprache is None  # erbt, Rückfall Deutsch (S-0058)
    assert len(kunde.bestellungen) == 1
    bestellung = kunde.bestellungen[0]
    assert bestellung.bestellnummer == "4500000001"
    assert bestellung.waehrung == "EUR"  # Belegwährung (S-0017)
    assert bestellung.aktiv is True  # Default Ja (S-0017)
    assert len(bestellung.gueltige_artikel) == 2
    grenze = bestellung.gueltige_artikel[0].obergrenze
    assert grenze.art is ObergrenzeArt.MENGE  # Mengen-Obergrenze (S-0017)
    assert str(grenze.wert) == "20"
    assert bestellung.rechnungen == []  # der Anwender legt die Rechnung im Durchstich an


def test_leerer_datenbestand_ist_leer():
    """Eine frisch angelegte Firma hat leere Felder, offene Bank und keine Stammdaten."""
    bestand = erzeuge_leeren_datenbestand()
    assert bestand.eigene_firma.name == ""
    assert bestand.eigene_firma.adresse.land == ""
    assert bestand.eigene_firma.bankverbindungen == []
    assert bestand.artikel == []
    assert bestand.kunden == []
    assert bestand.schema_version == 3


def test_leerer_datenbestand_speichern_laden_roundtrip(tmp_path):
    """Eine leere Firma erfüllt das Schema und ist verlustfrei speicher-/ladbar (AK1)."""
    bestand = erzeuge_leeren_datenbestand()
    pfad = tmp_path / "neue-firma.scgr"
    speichere(bestand, pfad)
    assert lade(pfad) == bestand
