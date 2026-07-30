"""Tests des Anwendungsrahmens: Reiterleiste und Navigation (4T-0075), offscreen.

Prüft die feste Reiterleiste (sieben Tätigkeiten, je genau ein nicht schließbarer
Reiter), das Einhängen der Rechnungsansicht als Rechnungen-Reiter und der übrigen
als Platzhalter, den Zustandserhalt beim Reiterwechsel und das Absprung-
Grundgerüst (Reiter aktivieren und ein Objekt anzeigen).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication

from eu_rechnung import PRODUKTNAME
from eu_rechnung.domain import Position
from eu_rechnung.services import erzeuge_seed, lege_rechnung_an, vorbelege_rechnung
from eu_rechnung.ui.artikel_reiter import ArtikelReiter
from eu_rechnung.ui.bestellung_reiter import BestellungReiter
from eu_rechnung.ui.einstellungen_reiter import EinstellungenReiter
from eu_rechnung.ui.firma_reiter import FirmaReiter
from eu_rechnung.ui.kunde_reiter import KundeReiter
from eu_rechnung.ui.hauptfenster import HauptFenster, PlatzhalterReiter, Reiter
from eu_rechnung.ui.rechnungen_reiter import RechnungenReiter
from eu_rechnung.ui.rechnungsuebersicht_reiter import RechnungsuebersichtReiter

ERWARTETE_REITER = [
    "Firma",
    "Artikel",
    "Kunden",
    "Bestellungen",
    "Rechnungen",
    "Rechnungsübersicht",
    "Einstellungen",
]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _fenster_mit_rechnung(tmp_path):
    """HauptFenster auf einem Seed mit genau einer angelegten Rechnung."""
    bestand = erzeuge_seed()
    daten = tmp_path / "daten.json"
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = [
        Position("", "Beratung", Decimal("1"), Decimal("100.00"), Decimal("100.00"))
    ]
    lege_rechnung_an(bestand, bestellung, rechnung, pfad=daten)
    bestand.einstellungen.ausgabe_verzeichnis = str(tmp_path / "Ausgabe")
    fenster = HauptFenster(bestand, daten_pfad=daten)
    return fenster, rechnung


def test_reiterleiste_zeigt_sieben_taetigkeiten(qapp):
    fenster = HauptFenster(erzeuge_seed())
    assert fenster._tabs.count() == 7
    texte = [fenster._tabs.tabText(i) for i in range(fenster._tabs.count())]
    assert texte == ERWARTETE_REITER


def test_reiter_nicht_schliessbar(qapp):
    fenster = HauptFenster(erzeuge_seed())
    assert fenster._tabs.tabsClosable() is False


def test_echte_reiter_eingehaengt_rest_platzhalter(qapp):
    fenster = HauptFenster(erzeuge_seed())
    assert isinstance(fenster._reiter_widgets[Reiter.FIRMA], FirmaReiter)
    assert isinstance(fenster._reiter_widgets[Reiter.ARTIKEL], ArtikelReiter)
    assert isinstance(fenster._reiter_widgets[Reiter.KUNDEN], KundeReiter)
    assert isinstance(fenster._reiter_widgets[Reiter.BESTELLUNGEN], BestellungReiter)
    assert isinstance(fenster._reiter_widgets[Reiter.RECHNUNGEN], RechnungenReiter)
    assert isinstance(
        fenster._reiter_widgets[Reiter.RECHNUNGSUEBERSICHT], RechnungsuebersichtReiter
    )
    assert isinstance(fenster._reiter_widgets[Reiter.EINSTELLUNGEN], EinstellungenReiter)
    echt = {
        Reiter.FIRMA,
        Reiter.ARTIKEL,
        Reiter.KUNDEN,
        Reiter.BESTELLUNGEN,
        Reiter.RECHNUNGEN,
        Reiter.RECHNUNGSUEBERSICHT,
        Reiter.EINSTELLUNGEN,
    }
    for reiter in Reiter:
        if reiter in echt:
            continue
        assert isinstance(fenster._reiter_widgets[reiter], PlatzhalterReiter)


def test_absprung_aktiviert_reiter(qapp):
    fenster = HauptFenster(erzeuge_seed())
    fenster.zeige_reiter(Reiter.ARTIKEL)
    assert fenster._tabs.currentWidget() is fenster._reiter_widgets[Reiter.ARTIKEL]


def test_absprung_zeigt_objekt_im_rechnungen_reiter(qapp, tmp_path):
    fenster, rechnung = _fenster_mit_rechnung(tmp_path)
    fenster.zeige_reiter(Reiter.RECHNUNGEN, rechnung)
    rechnungen = fenster._reiter_widgets[Reiter.RECHNUNGEN]
    assert fenster._tabs.currentWidget() is rechnungen
    assert rechnungen._markierte_rechnung() is rechnung


def test_zustandserhalt_bei_reiterwechsel(qapp, tmp_path):
    fenster, rechnung = _fenster_mit_rechnung(tmp_path)
    rechnungen = fenster._reiter_widgets[Reiter.RECHNUNGEN]
    rechnungen._liste.waehle_objekt(rechnung)
    fenster.zeige_reiter(Reiter.KUNDEN)  # weg vom Rechnungen-Reiter
    fenster.zeige_reiter(Reiter.RECHNUNGEN)  # und zurück
    assert rechnungen._markierte_rechnung() is rechnung


# --- Fenstertitel mit der aktiven Firma (4T-0177, S-0084) ---------------------


def test_titel_nennt_die_firma_datei_vor_dem_produktnamen(qapp, tmp_path):
    """AK1: Der Titel beginnt mit dem Dateinamen ohne Endung, dann folgt der Produktname."""
    fenster = HauptFenster(erzeuge_seed(), daten_pfad=tmp_path / "Abnahmetest.scgr")
    assert fenster.windowTitle() == f"Abnahmetest — {PRODUKTNAME}"


def test_titel_haengt_ungespeichert_hinten_an(qapp, tmp_path):
    """AK2: Der Ungespeichert-Zusatz steht hinten; der Dateiname bleibt vorn."""
    fenster = HauptFenster(erzeuge_seed(), daten_pfad=tmp_path / "Abnahmetest.scgr")

    fenster._aktualisiere_titel(True)

    titel = fenster.windowTitle()
    assert titel.startswith(f"Abnahmetest — {PRODUKTNAME}")
    assert titel.endswith("nicht gespeichert")


def test_titel_ohne_aktive_firma_bleibt_unveraendert(qapp):
    """AK3: Ohne Firma gibt es keinen Dateinamen; der Titel nennt nur den Leerzustand."""
    fenster = HauptFenster()
    assert fenster.windowTitle() == f"{PRODUKTNAME} — keine Firma geöffnet"


def test_titel_folgt_dem_firma_wechsel(qapp, tmp_path):
    """AK4: Ein Wechsel der aktiven Firma zieht den Titel unmittelbar nach."""
    fenster = HauptFenster(erzeuge_seed(), daten_pfad=tmp_path / "Firma A.scgr")
    assert fenster.windowTitle().startswith("Firma A — ")

    fenster._setze_aktive_firma(erzeuge_seed(), tmp_path / "Firma B.scgr")

    assert fenster.windowTitle() == f"Firma B — {PRODUKTNAME}"
