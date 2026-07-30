"""Tests der lesenden Rechnungs-Gesamtübersicht (`services.uebersicht`, S-0055), Java- und Qt-frei.

Geprüft werden die flache Sicht über alle Kunden und Bestellungen samt Kontext, die
Ausgangs-Sortierung (Rechnungsdatum absteigend) und der leere Bestand.
"""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal

from eu_rechnung.services import (
    alle_rechnungen,
    erzeuge_leeren_datenbestand,
    erzeuge_seed,
    lege_rechnung_an,
    vorbelege_rechnung,
)
from eu_rechnung.domain import Position


def _bestand_mit_rechnungen(tmp_path, daten: list[tuple[str, date]]):
    """Seed-Bestand mit je einer Rechnung (Nummer, Datum) an der Seed-Bestellung."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    for nummer, datum in daten:
        rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=datum)
        rechnung.rechnungsnummer = nummer
        rechnung.positionen = [
            Position("art-1", "Beratung", Decimal("1"), Decimal("100.00"), Decimal("100.00"))
        ]
        lege_rechnung_an(bestand, bestellung, rechnung, pfad=tmp_path / "d.scgr")
    return bestand


def test_leerer_bestand_ergibt_leere_uebersicht():
    assert alle_rechnungen(erzeuge_leeren_datenbestand()) == []


def test_uebersicht_liefert_rechnung_mit_kontext(tmp_path):
    """AK1: Je Eintrag Kunde, Bestellung und Rechnung; die Rechnung allein kennt weder
    Kundenname noch Bestellnummer."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    zeilen = alle_rechnungen(bestand)
    assert len(zeilen) == 1
    zeile = zeilen[0]
    assert zeile.kunde is bestand.kunden[0]
    assert zeile.bestellung is bestand.kunden[0].bestellungen[0]
    assert zeile.rechnung.rechnungsnummer == "2026-10001"


def test_uebersicht_ist_nach_rechnungsdatum_absteigend(tmp_path):
    """AK2: Ausgangszustand ist neueste zuerst."""
    bestand = _bestand_mit_rechnungen(
        tmp_path,
        [
            ("2026-10001", date(2026, 5, 1)),
            ("2026-10002", date(2026, 7, 10)),
            ("2026-10003", date(2026, 6, 1)),
        ],
    )
    nummern = [z.rechnung.rechnungsnummer for z in alle_rechnungen(bestand)]
    assert nummern == ["2026-10002", "2026-10003", "2026-10001"]


def test_uebersicht_greift_ueber_kunden_und_bestellungen(tmp_path):
    """AK1: Die Sicht ist übergreifend, nicht auf eine Bestellung beschränkt."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    # Zweiter Kunde mit eigener Bestellung und Rechnung
    zweiter = copy.deepcopy(bestand.kunden[0])
    zweiter.id = "kun-2"
    zweiter.name = "Zweiter Kunde GmbH"
    zweiter.bestellungen[0].id = "best-2"
    zweiter.bestellungen[0].bestellnummer = "B-999"
    zweiter.bestellungen[0].rechnungen[0].rechnungsnummer = "2026-20001"
    bestand.kunden.append(zweiter)

    zeilen = alle_rechnungen(bestand)
    assert len(zeilen) == 2
    assert {z.kunde.name for z in zeilen} == {"Beispiel Kunde GmbH", "Zweiter Kunde GmbH"}
    assert {z.bestellung.bestellnummer for z in zeilen} == {"4500000001", "B-999"}


def test_uebersicht_veraendert_nichts(tmp_path):
    """AK6/S-0055 AK3: Die Sicht liefert Verweise auf die echten Objekte, ohne sie zu
    verändern."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    vorher = copy.deepcopy(bestand)
    zeilen = alle_rechnungen(bestand)
    assert zeilen[0].rechnung is bestand.kunden[0].bestellungen[0].rechnungen[0]
    assert bestand == vorher
