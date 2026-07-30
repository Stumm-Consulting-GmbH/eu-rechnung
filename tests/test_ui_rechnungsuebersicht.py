"""Tests des Rechnungsübersicht-Reiters (S-0055, S-0056), offscreen.

Prüft die flache Tabelle über alle Kunden und Bestellungen, die Ausgangs-Sortierung, den
Textfilter des geteilten Listen-Bausteins und die farbliche Status-Unterscheidung.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from eu_rechnung.domain import Position, RechnungsStatus
from eu_rechnung.services import erzeuge_leeren_datenbestand, erzeuge_seed, lege_rechnung_an, vorbelege_rechnung
from eu_rechnung.ui.hauptfenster import HauptFenster, Reiter
from eu_rechnung.ui.rechnungsuebersicht_reiter import (
    _FARBE_ENTWURF,
    _FARBE_ERZEUGT,
    RechnungsuebersichtReiter,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _bestand_mit_rechnungen(tmp_path, daten: list[tuple[str, date]]):
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


def _spaltentexte(reiter: RechnungsuebersichtReiter, zeile: int) -> list[str]:
    tabelle = reiter._liste._tabelle
    return [tabelle.item(zeile, s).text() for s in range(tabelle.columnCount())]


def test_uebersicht_zeigt_die_sechs_spalten(qapp, tmp_path):
    """AK3: Kunde, Bestellnummer, Rechnungsnummer, Rechnungsdatum, Status, zuletzt erzeugt."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    reiter = RechnungsuebersichtReiter(bestand)
    kopf = reiter._liste._tabelle.horizontalHeader()
    titel = [
        reiter._liste._tabelle.horizontalHeaderItem(i).text() for i in range(kopf.count())
    ]
    assert titel == [
        "Kunde",
        "Bestellnummer",
        "Rechnungsnummer",
        "Rechnungsdatum",
        "Status",
        "Zuletzt erzeugt am",
    ]
    assert _spaltentexte(reiter, 0)[:5] == [
        "Beispiel Kunde GmbH",
        "4500000001",
        "2026-10001",
        "10.07.2026",
        "Entwurf",
    ]


def test_uebersicht_ist_nach_rechnungsdatum_absteigend(qapp, tmp_path):
    """AK2: Ausgangszustand neueste zuerst, auch in der angezeigten Tabelle."""
    bestand = _bestand_mit_rechnungen(
        tmp_path,
        [
            ("2026-10001", date(2026, 5, 1)),
            ("2026-10002", date(2026, 7, 10)),
            ("2026-10003", date(2026, 6, 1)),
        ],
    )
    reiter = RechnungsuebersichtReiter(bestand)
    nummern = [_spaltentexte(reiter, z)[2] for z in range(3)]
    assert nummern == ["2026-10002", "2026-10003", "2026-10001"]


def test_filter_grenzt_die_uebersicht_ein(qapp, tmp_path):
    """AK4: Der Textfilter des geteilten Bausteins wirkt über alle Spalten (K2)."""
    bestand = _bestand_mit_rechnungen(
        tmp_path, [("2026-10001", date(2026, 5, 1)), ("2026-10002", date(2026, 7, 10))]
    )
    reiter = RechnungsuebersichtReiter(bestand)
    reiter._liste._filter.setText("10002")
    sichtbar = [
        z for z in range(reiter._liste._tabelle.rowCount())
        if not reiter._liste._tabelle.isRowHidden(z)
    ]
    assert len(sichtbar) == 1
    assert _spaltentexte(reiter, sichtbar[0])[2] == "2026-10002"


def test_status_ist_farblich_unterscheidbar(qapp, tmp_path):
    """AK5: Entwurf und Erzeugt sind optisch abgesetzt, damit offene Entwürfe auffallen."""
    bestand = _bestand_mit_rechnungen(
        tmp_path, [("2026-10001", date(2026, 5, 1)), ("2026-10002", date(2026, 7, 10))]
    )
    # Die neuere (erste Zeile) auf Erzeugt setzen
    bestand.kunden[0].bestellungen[0].rechnungen[1].status = RechnungsStatus.ERZEUGT
    reiter = RechnungsuebersichtReiter(bestand)
    tabelle = reiter._liste._tabelle
    status_spalte = 4
    farben = {
        tabelle.item(z, status_spalte).text(): tabelle.item(z, status_spalte).foreground().color()
        for z in range(tabelle.rowCount())
    }
    assert farben["Erzeugt"] == _FARBE_ERZEUGT
    assert farben["Entwurf"] == _FARBE_ENTWURF
    assert farben["Erzeugt"] != farben["Entwurf"]


def test_uebersicht_ist_nicht_editierbar(qapp, tmp_path):
    """AK6: Die Übersicht ist lesend."""
    from PySide6.QtWidgets import QAbstractItemView

    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    reiter = RechnungsuebersichtReiter(bestand)
    assert reiter._liste._tabelle.editTriggers() == QAbstractItemView.NoEditTriggers


def test_leerer_bestand_zeigt_leere_tabelle(qapp):
    reiter = RechnungsuebersichtReiter(erzeuge_leeren_datenbestand())
    assert reiter._liste._tabelle.rowCount() == 0


def test_hauptfenster_zeigt_uebersicht_statt_platzhalter(qapp, tmp_path):
    """AK3: Der Reiter ersetzt den Platzhalter."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    fenster = HauptFenster(bestand, daten_pfad=tmp_path / "d.scgr")
    widget = fenster._reiter_widgets[Reiter.RECHNUNGSUEBERSICHT]
    assert isinstance(widget, RechnungsuebersichtReiter)
    assert widget._liste._tabelle.rowCount() == 1


def _lege_rechnung_an(bestand, pfad, nummer: str, datum: date):
    """Legt eine Rechnung in der ersten Bestellung des ersten Kunden an."""
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=datum)
    rechnung.rechnungsnummer = nummer
    rechnung.positionen = [
        Position("art-1", "Beratung", Decimal("1"), Decimal("100.00"), Decimal("100.00"))
    ]
    return lege_rechnung_an(bestand, bestellung, rechnung, pfad=pfad)


def test_uebersicht_frischt_beim_wechsel_in_den_reiter_auf(qapp, tmp_path):
    """AK1: Eine erst nach dem Reiter-Aufbau angelegte Rechnung erscheint in der Übersicht.

    Der reale Weg: Die Reiter entstehen beim Aktivieren der Firma (damals ohne Rechnungen),
    erfasst wird danach. Ohne Auffrischen beim Anzeigen zeigte die Übersicht dauerhaft den
    Stand des Aufbauzeitpunkts, im Regelfall also gar nichts (Fund aus der Abnahme).
    """
    pfad = tmp_path / "d.scgr"
    bestand = erzeuge_seed()  # Stammdaten ohne Rechnungen
    fenster = HauptFenster(bestand, daten_pfad=pfad)
    fenster.show()
    uebersicht = fenster._reiter_widgets[Reiter.RECHNUNGSUEBERSICHT]
    assert uebersicht._liste._tabelle.rowCount() == 0

    _lege_rechnung_an(bestand, pfad, "2026-10001", date(2026, 7, 10))
    fenster.zeige_reiter(Reiter.RECHNUNGSUEBERSICHT)

    assert uebersicht._liste._tabelle.rowCount() == 1
    assert _spaltentexte(uebersicht, 0)[2] == "2026-10001"


def test_uebersicht_zeigt_geloeschte_rechnung_nicht_mehr(qapp, tmp_path):
    """AK1: Auch das Entfernen schlägt beim nächsten Anzeigen durch, nicht nur das Anlegen."""
    pfad = tmp_path / "d.scgr"
    bestand = erzeuge_seed()
    fenster = HauptFenster(bestand, daten_pfad=pfad)
    fenster.show()
    rechnung = _lege_rechnung_an(bestand, pfad, "2026-10001", date(2026, 7, 10))
    uebersicht = fenster._reiter_widgets[Reiter.RECHNUNGSUEBERSICHT]
    fenster.zeige_reiter(Reiter.RECHNUNGSUEBERSICHT)
    assert uebersicht._liste._tabelle.rowCount() == 1

    bestand.kunden[0].bestellungen[0].rechnungen.remove(rechnung)
    fenster.zeige_reiter(Reiter.RECHNUNGEN)
    fenster.zeige_reiter(Reiter.RECHNUNGSUEBERSICHT)

    assert uebersicht._liste._tabelle.rowCount() == 0
    assert uebersicht._ablage_knopf.isEnabled() is False


# --- Wege nach außen (S-0056 AK2/AK3, S-0057 AK3; 4T-0123) -------------------


def test_doppelklick_meldet_die_rechnung(qapp, tmp_path):
    """AK1: Der Doppelklick meldet die Rechnung; die Übersicht kennt den Ziel-Reiter nicht."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    reiter = RechnungsuebersichtReiter(bestand)
    gemeldet = []
    reiter.rechnung_geoeffnet.connect(gemeldet.append)

    reiter._liste._tabelle.cellDoubleClicked.emit(0, 0)

    assert gemeldet == [bestand.kunden[0].bestellungen[0].rechnungen[0]]


def test_doppelklick_oeffnet_die_rechnung_in_der_erfassung(qapp, tmp_path):
    """AK1: Über das Hauptfenster landet der Doppelklick im Rechnungen-Reiter, mit geladener
    Rechnung im Ändern-Modus."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    fenster = HauptFenster(bestand, daten_pfad=tmp_path / "d.scgr")
    uebersicht = fenster._reiter_widgets[Reiter.RECHNUNGSUEBERSICHT]
    rechnungen = fenster._reiter_widgets[Reiter.RECHNUNGEN]

    uebersicht._liste._tabelle.cellDoubleClicked.emit(0, 0)

    assert fenster._tabs.currentWidget() is rechnungen
    assert rechnungen._maske.rechnung is not None
    assert rechnungen._maske.rechnung.rechnungsnummer == "2026-10001"
    assert rechnungen._maske.ist_neu is False  # Ändern-Modus


def test_uebersicht_bleibt_beim_doppelklick_lesend(qapp, tmp_path):
    """AK2: Der Absprung verändert die Daten nicht."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    vorher = copy.deepcopy(bestand)
    fenster = HauptFenster(bestand, daten_pfad=tmp_path / "d.scgr")
    fenster._reiter_widgets[Reiter.RECHNUNGSUEBERSICHT]._liste._tabelle.cellDoubleClicked.emit(0, 0)
    assert bestand == vorher


def test_ablage_knopf_nur_bei_erzeugter_rechnung(qapp, tmp_path):
    """AK3: Für Entwürfe ist „Ablageort öffnen" nicht verfügbar."""
    bestand = _bestand_mit_rechnungen(
        tmp_path, [("2026-10001", date(2026, 5, 1)), ("2026-10002", date(2026, 7, 10))]
    )
    bestand.kunden[0].bestellungen[0].rechnungen[1].status = RechnungsStatus.ERZEUGT
    reiter = RechnungsuebersichtReiter(bestand)
    assert reiter._ablage_knopf.isEnabled() is False  # ohne Auswahl

    # Zeile 0 ist die neuere (10002, Erzeugt), Zeile 1 der Entwurf (10001)
    reiter._liste._tabelle.setCurrentCell(0, 0)
    assert reiter._ablage_knopf.isEnabled() is True
    reiter._liste._tabelle.setCurrentCell(1, 0)
    assert reiter._ablage_knopf.isEnabled() is False


def test_ablageort_folgt_dem_schema(qapp, tmp_path):
    """AK4: Der Ordner wird aus Ausgabe-Verzeichnis und Kundennummer hergeleitet."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    bestand.einstellungen.ausgabe_verzeichnis = str(tmp_path / "Ausgabe")
    reiter = RechnungsuebersichtReiter(bestand)
    rechnung = bestand.kunden[0].bestellungen[0].rechnungen[0]
    assert reiter.ablageort(rechnung) == tmp_path / "Ausgabe" / "D10002"


def test_fehlender_ablageort_meldet_lesbaren_hinweis(qapp, tmp_path, monkeypatch):
    """AK4: Fehlt der Ordner (etwa verschobene Dateien), erscheint ein Hinweis statt eines
    Fehlers, und es wird nichts geöffnet."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    bestand.einstellungen.ausgabe_verzeichnis = str(tmp_path / "nicht-da")
    bestand.kunden[0].bestellungen[0].rechnungen[0].status = RechnungsStatus.ERZEUGT
    reiter = RechnungsuebersichtReiter(bestand)
    reiter._liste._tabelle.setCurrentCell(0, 0)
    hinweise = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: hinweise.append(a))
    geoeffnet = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: geoeffnet.append(url))

    reiter._oeffne_ablageort()

    assert hinweise
    assert not geoeffnet


def test_ablageort_oeffnen_ruft_den_zielordner(qapp, tmp_path, monkeypatch):
    """AK4: Bei vorhandenem Ordner wird genau dieser geöffnet."""
    bestand = _bestand_mit_rechnungen(tmp_path, [("2026-10001", date(2026, 7, 10))])
    ordner = tmp_path / "Ausgabe" / "D10002"
    ordner.mkdir(parents=True)
    bestand.einstellungen.ausgabe_verzeichnis = str(tmp_path / "Ausgabe")
    bestand.kunden[0].bestellungen[0].rechnungen[0].status = RechnungsStatus.ERZEUGT
    reiter = RechnungsuebersichtReiter(bestand)
    reiter._liste._tabelle.setCurrentCell(0, 0)
    geoeffnet = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: geoeffnet.append(url))

    reiter._oeffne_ablageort()

    # Über Path vergleichen: QUrl liefert den Pfad mit Slashes zurück, auch unter Windows.
    assert [Path(u.toLocalFile()) for u in geoeffnet] == [ordner]
