"""Tests der Kunde-Validierung (services/kunde.py): zweistufige Pflicht, Eindeutigkeit."""

from eu_rechnung.domain import Adresse, Kunde
from eu_rechnung.services import erzeuge_seed, pruefe_kunde


def _kunde(
    nummer: str = "D99999",
    *,
    name: str = "Muster AG",
    land: str = "DE",
    strasse: str = "Weg 1",
    plz: str = "12345",
    ort: str = "Berlin",
    email: str = "a@b.de",
    ustid: str = "DE123456789",
    reverse_charge: bool = False,
    id: str = "",
) -> Kunde:
    return Kunde(
        id=id,
        kundennummer=nummer,
        name=name,
        adresse=Adresse(strasse=strasse, plz=plz, ort=ort, land=land),
        email=email,
        umsatzsteuer_id=ustid,
        reverse_charge=reverse_charge,
    )


def test_pruefe_kunde_gueltig_ist_leer():
    assert pruefe_kunde(_kunde(), erzeuge_seed()) == []


def test_pruefe_kunde_nummer_ist_pflicht():
    befunde = pruefe_kunde(_kunde(nummer="  "), erzeuge_seed())
    assert any(b.feld == "kundennummer" for b in befunde)


def test_pruefe_kunde_nummer_eindeutig_ohne_gross_klein():
    bestand = erzeuge_seed()
    nummer = bestand.kunden[0].kundennummer  # "D10002"
    befunde = pruefe_kunde(_kunde(nummer=nummer.lower()), bestand)
    assert any(b.feld == "kundennummer" for b in befunde)


def test_pruefe_kunde_selbst_ist_von_dublette_ausgenommen():
    bestand = erzeuge_seed()
    vorhanden = bestand.kunden[0]
    befunde = pruefe_kunde(
        _kunde(nummer=vorhanden.kundennummer, id=vorhanden.id),
        bestand,
        ignoriere_id=vorhanden.id,
    )
    assert all(b.feld != "kundennummer" for b in befunde)


def test_pruefe_kunde_name_wird_nicht_auf_eindeutigkeit_geprueft():
    bestand = erzeuge_seed()
    name = bestand.kunden[0].name
    befunde = pruefe_kunde(_kunde(nummer="D88888", name=name), bestand)
    assert all(b.feld != "name" for b in befunde)


def test_pruefe_kunde_ustid_pflicht_bei_reverse_charge():
    befunde = pruefe_kunde(_kunde(reverse_charge=True, ustid=""), erzeuge_seed())
    assert any(b.feld == "umsatzsteuer_id" for b in befunde)


def test_pruefe_kunde_ohne_xrechnung_keine_adress_pflicht():
    bestand = erzeuge_seed()
    bestand.eigene_firma.xrechnung_aktiv = False
    befunde = pruefe_kunde(_kunde(strasse="", plz="", ort="", email=""), bestand)
    assert all(b.feld not in ("strasse", "plz", "ort", "email") for b in befunde)


def test_pruefe_kunde_mit_xrechnung_adresse_und_email_pflicht():
    bestand = erzeuge_seed()  # xrechnung_aktiv = True
    befunde = pruefe_kunde(_kunde(strasse="", plz="", ort="", email=""), bestand)
    felder = {b.feld for b in befunde}
    assert {"strasse", "plz", "ort", "email"} <= felder


def test_pruefe_kunde_email_format():
    befunde = pruefe_kunde(_kunde(email="keine-email"), erzeuge_seed())
    assert any(b.feld == "email" for b in befunde)
