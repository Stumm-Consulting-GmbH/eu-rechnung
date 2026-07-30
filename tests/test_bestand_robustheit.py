"""Robustheit gegen leere und große Datenbestände (4T-0165), offscreen.

Härtet zwei Ränder, die der Normalfall der Suite nicht abdeckt:

- **Fall A — aktive Firma, leere Stammdaten.** Der Leerzustand des Rechnungen-Reiters
  (Hinweis, gesperrtes „Neue Rechnung") und der Rechnungsübersicht ist bereits geprüft
  (`test_ui_rechnungen`, `test_ui_rechnungsuebersicht`); ungeprüft war der Leerzustand der
  drei Stammdaten-Listen selbst, deren Tests bisher stets bestückte Bestände nutzen.
- **Fall B — Mengengerüst.** Kein Test baute bisher einen Bestand mit vielen Kunden,
  Bestellungen und Rechnungen; geprüft wird der verlustfreie Persistenz-Roundlauf und das
  Listen- und Übersichts-Verhalten (Aufbau, Filter) über die Menge.

Der Generator ist deterministisch (keine Zufallswerte), damit die Erwartungen stabil sind.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication

from eu_rechnung.domain import (
    Adresse,
    Artikel,
    Bestellung,
    GueltigerArtikel,
    Kunde,
    Obergrenze,
    ObergrenzeArt,
    Position,
    Preis,
)
from eu_rechnung.persistence import lade, speichere
from eu_rechnung.services import (
    erzeuge_leeren_datenbestand,
    erzeuge_seed,
    vorbelege_rechnung,
)
from eu_rechnung.ui.artikel_reiter import ArtikelReiter
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.bestellung_reiter import BestellungReiter
from eu_rechnung.ui.kunde_reiter import KundeReiter
from eu_rechnung.ui.rechnungsuebersicht_reiter import RechnungsuebersichtReiter


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# Mengengerüst: bewusst klein genug für eine schnelle Suite, groß genug, um das
# Mengen-Verhalten (Laden, Auflisten, Filtern) beobachtbar zu machen.
_KUNDEN = 15
_BESTELLUNGEN_JE_KUNDE = 2
_RECHNUNGEN_JE_BESTELLUNG = 4
_ARTIKEL = 25
_RECHNUNGEN_GESAMT = _KUNDEN * _BESTELLUNGEN_JE_KUNDE * _RECHNUNGEN_JE_BESTELLUNG


def _leerer_bestand_mit_firma():
    """Leerer Bestand mit gesetztem Firmennamen (aktive Firma, aber keine Stammdaten)."""
    bestand = erzeuge_leeren_datenbestand()
    bestand.eigene_firma.name = "Testfirma"
    return bestand


def _grosser_bestand():
    """Deterministisches Mengengerüst auf valider Firma: viele Artikel, Kunden,
    Bestellungen und Rechnungen (jede Rechnung mit eindeutiger Nummer)."""
    bestand = erzeuge_seed()
    bestand.artikel.clear()
    bestand.kunden.clear()
    for i in range(_ARTIKEL):
        bestand.artikel.append(
            Artikel(
                id=f"art-{i:03d}",
                artikelname=f"Artikel {i:03d}",
                vorschlagspreis=Preis(Decimal("100.00"), "EUR"),
            )
        )
    lfd = 0
    for k in range(_KUNDEN):
        kunde = Kunde(
            id=f"kun-{k:03d}",
            kundennummer=f"D{10000 + k}",
            name=f"Kunde {k:03d}",
            adresse=Adresse(strasse="Teststrasse 1", plz="12345", ort="Teststadt", land="DE"),
            email=f"kunde{k}@example.org",
            umsatzsteuer_id="DE123456789",
            reverse_charge=False,
            bestellungen=[],
        )
        for b in range(_BESTELLUNGEN_JE_KUNDE):
            bestellung = Bestellung(
                id=f"best-{k:03d}-{b}",
                bestellnummer=f"B-{k:03d}-{b}",
                beginn_datum=date(2026, 1, 1),
                ende_datum=date(2026, 12, 31),
                zahlungsfrist=30,
                zahlungsbedingung="Zahlbar innerhalb von 30 Tagen ohne Abzug.",
                waehrung="EUR",
                gueltige_artikel=[
                    GueltigerArtikel(
                        artikel_id="art-000",
                        einzelpreis=Decimal("100.00"),
                        obergrenze=Obergrenze(art=ObergrenzeArt.MENGE, wert=Decimal("999")),
                    )
                ],
                rechnungen=[],
            )
            for _ in range(_RECHNUNGEN_JE_BESTELLUNG):
                lfd += 1
                rechnung = vorbelege_rechnung(
                    bestand, kunde, bestellung, heute=date(2026, (lfd % 12) + 1, (lfd % 28) + 1)
                )
                rechnung.rechnungsnummer = f"2026-{10000 + lfd}"
                rechnung.positionen = [
                    Position("art-000", "Artikel 000", Decimal("1"), Decimal("100.00"), Decimal("100.00"))
                ]
                bestellung.rechnungen.append(rechnung)
            kunde.bestellungen.append(bestellung)
        bestand.kunden.append(kunde)
    return bestand


# --- Fall A: aktive Firma, leere Stammdaten ---------------------------------


def test_leere_artikelliste_ist_bedienbar(qapp):
    """AK1: Ohne Artikel zeigt die Liste keine Zeile, und das Anlegen bleibt möglich."""
    reiter = ArtikelReiter(_leerer_bestand_mit_firma())
    assert reiter._liste._tabelle.rowCount() == 0
    reiter._neuer_artikel()  # darf im Leerzustand nicht scheitern
    assert reiter._name.text() == ""


def test_leere_kundenliste_ist_leer(qapp):
    """AK1: Ohne Kunden zeigt die Kundenliste fehlerfrei keine Zeile."""
    reiter = KundeReiter(_leerer_bestand_mit_firma())
    assert reiter._liste._tabelle.rowCount() == 0


def test_leere_bestellungsliste_ist_leer(qapp, tmp_path):
    """AK1: Ohne Kunden und Bestellungen konstruiert der Bestellungs-Reiter fehlerfrei und leer."""
    bestand = _leerer_bestand_mit_firma()
    reiter = BestellungReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    assert reiter._liste._tabelle.rowCount() == 0


# --- Fall B: großes Mengengerüst --------------------------------------------


def test_grosser_bestand_roundtrip(tmp_path):
    """AK2: Ein großer Bestand wird verlustfrei gespeichert und geladen."""
    bestand = _grosser_bestand()
    pfad = tmp_path / "gross.scgr"
    speichere(bestand, pfad)
    assert lade(pfad) == bestand


def test_grosse_uebersicht_zeigt_alle_rechnungen(qapp):
    """AK2/AK3: Die Rechnungsübersicht listet alle Rechnungen des Mengengerüsts."""
    reiter = RechnungsuebersichtReiter(_grosser_bestand())
    assert reiter._liste._tabelle.rowCount() == _RECHNUNGEN_GESAMT


def test_grosse_uebersicht_filter_grenzt_auf_eine_rechnung_ein(qapp):
    """AK2: Der Textfilter findet über die Menge genau eine Rechnung (K2)."""
    reiter = RechnungsuebersichtReiter(_grosser_bestand())
    reiter._liste._filter.setText("2026-10007")
    sichtbar = [
        z
        for z in range(reiter._liste._tabelle.rowCount())
        if not reiter._liste._tabelle.isRowHidden(z)
    ]
    assert len(sichtbar) == 1


def test_grosse_artikelliste_baut_und_filtert(qapp):
    """AK2: Die Artikelliste trägt die volle Menge, und der Filter grenzt sie ein (K2)."""
    reiter = ArtikelReiter(_grosser_bestand())
    assert reiter._liste._tabelle.rowCount() == _ARTIKEL
    reiter._liste._filter.setText("Artikel 007")
    sichtbar = [
        z
        for z in range(reiter._liste._tabelle.rowCount())
        if not reiter._liste._tabelle.isRowHidden(z)
    ]
    assert len(sichtbar) == 1
