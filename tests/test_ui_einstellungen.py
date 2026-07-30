"""Tests des Einstellungen-Reiters (S-0035, S-0044), offscreen."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from eu_rechnung.domain import Position
from eu_rechnung.persistence import lade
from eu_rechnung.services import erzeuge_seed, lege_rechnung_an, vorbelege_rechnung
from eu_rechnung.texte import SPRACHEN
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.einstellungen_reiter import EinstellungenReiter
from eu_rechnung.ui.hauptfenster import HauptFenster, Reiter


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_laedt_standardtext(qapp):
    bestand = erzeuge_seed()
    bestand.einstellungen.standard_anschreibentext = "Sehr geehrte Damen und Herren"
    reiter = EinstellungenReiter(bestand)
    assert reiter._standard.toPlainText() == "Sehr geehrte Damen und Herren"


def test_speichern_uebernimmt_und_trimmt(qapp, tmp_path):
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._standard.setPlainText("  Neuer Standardtext  ")
    reiter._bestaetigen()
    assert bestand.einstellungen.standard_anschreibentext == "Neuer Standardtext"


def test_leerer_text_wird_feldnah_abgelehnt(qapp):
    bestand = erzeuge_seed()
    bestand.einstellungen.standard_anschreibentext = "Vorher"
    reiter = EinstellungenReiter(bestand)
    reiter._standard.setPlainText("   ")
    reiter._bestaetigen()
    assert reiter._fehler["standard_anschreibentext"].isHidden() is False  # Hinweis am Feld
    assert bestand.einstellungen.standard_anschreibentext == "Vorher"  # nicht überschrieben


# --- Nummernkreise (S-0044) ------------------------------------------------


def test_laedt_nummernkreise(qapp):
    bestand = erzeuge_seed()
    bestand.einstellungen.naechste_debitornummer = 10042
    bestand.einstellungen.naechste_rechnungsnummer = {"2026": 10005}
    reiter = EinstellungenReiter(bestand)
    assert reiter._debitor.text() == "10042"
    assert reiter._jahre.rowCount() == 1
    assert reiter._jahre.item(0, 0).text() == "2026"
    assert reiter._jahre.item(0, 1).text() == "10005"


def test_debitornummer_editieren(qapp, tmp_path):
    bestand = erzeuge_seed()
    bestand.einstellungen.naechste_debitornummer = 10003
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._debitor.setText("10050")
    reiter._bestaetigen()
    assert bestand.einstellungen.naechste_debitornummer == 10050
    assert (tmp_path / "d.json").exists()


def test_jahres_zaehler_editieren(qapp, tmp_path):
    bestand = erzeuge_seed()
    bestand.einstellungen.naechste_rechnungsnummer = {"2026": 10005}
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._jahre.item(0, 1).setText("10020")
    reiter._bestaetigen()
    assert bestand.einstellungen.naechste_rechnungsnummer == {"2026": 10020}


def test_neues_jahr_anlegen(qapp, tmp_path):
    bestand = erzeuge_seed()
    bestand.einstellungen.naechste_rechnungsnummer = {"2026": 10005}
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._jahr_hinzufuegen()
    zeile = reiter._jahre.rowCount() - 1
    reiter._jahre.item(zeile, 0).setText("2027")
    reiter._jahre.item(zeile, 1).setText("10001")
    reiter._bestaetigen()
    assert bestand.einstellungen.naechste_rechnungsnummer == {"2026": 10005, "2027": 10001}


def test_ungueltige_debitornummer_wird_feldnah_abgelehnt(qapp, tmp_path):
    bestand = erzeuge_seed()
    bestand.einstellungen.naechste_debitornummer = 10003
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._debitor.setText("abc")
    reiter._bestaetigen()
    assert reiter._fehler["debitornummer"].isHidden() is False
    assert bestand.einstellungen.naechste_debitornummer == 10003  # unverändert


def test_nicht_positiver_jahres_zaehler_wird_feldnah_abgelehnt(qapp, tmp_path):
    bestand = erzeuge_seed()
    bestand.einstellungen.naechste_rechnungsnummer = {"2026": 10005}
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._jahre.item(0, 1).setText("0")
    reiter._bestaetigen()
    assert reiter._fehler["rechnungsnummer"].isHidden() is False
    assert bestand.einstellungen.naechste_rechnungsnummer == {"2026": 10005}  # unverändert


def _lege_rechnung_an(bestand, pfad, datum=date(2026, 7, 10)):
    """Legt eine Rechnung an; das schreibt den Jahres-Zähler außerhalb des Reiters fort."""
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=datum)
    rechnung.positionen = [
        Position("art-1", "Beratung", Decimal("1"), Decimal("100.00"), Decimal("100.00"))
    ]
    return lege_rechnung_an(bestand, bestellung, rechnung, pfad=pfad)


def test_zaehlerstand_wird_beim_anzeigen_nachgezogen(qapp, tmp_path):
    """AK3: Die Anzeige zeigt den Stand, den die nächste Vergabe wirklich nutzt.

    Die Zähler wachsen außerhalb dieses Reiters weiter (jede angelegte Rechnung, jeder
    Kunde). Ohne Auffrischen beim Anzeigen zeigte die Maske dauerhaft ihren Ladestand.
    """
    pfad = tmp_path / "d.scgr"
    bestand = erzeuge_seed()
    bestand.einstellungen.naechste_rechnungsnummer = {"2026": 500}
    fenster = HauptFenster(bestand, daten_pfad=pfad)
    fenster.show()
    einstellungen = fenster._reiter_widgets[Reiter.EINSTELLUNGEN]
    fenster.zeige_reiter(Reiter.EINSTELLUNGEN)
    assert einstellungen._jahre.item(0, 1).text() == "500"

    _lege_rechnung_an(bestand, pfad)
    fenster.zeige_reiter(Reiter.RECHNUNGEN)
    fenster.zeige_reiter(Reiter.EINSTELLUNGEN)

    assert einstellungen._jahre.item(0, 1).text() == "501"


def test_bestaetigen_setzt_vergebene_nummern_nicht_zurueck(qapp, tmp_path):
    """AK3: Ein Bestätigen darf den fortgeschriebenen Zähler nicht überschreiben.

    Sonst erhielte die nächste Rechnung eine bereits vergebene Nummer, ohne dass der
    Anwender in diesem Reiter etwas an den Nummernkreisen geändert hätte.
    """
    pfad = tmp_path / "d.scgr"
    bestand = erzeuge_seed()
    bestand.einstellungen.naechste_rechnungsnummer = {"2026": 500}
    fenster = HauptFenster(bestand, daten_pfad=pfad)
    fenster.show()
    einstellungen = fenster._reiter_widgets[Reiter.EINSTELLUNGEN]
    fenster.zeige_reiter(Reiter.EINSTELLUNGEN)

    _lege_rechnung_an(bestand, pfad)
    fenster.zeige_reiter(Reiter.RECHNUNGEN)
    fenster.zeige_reiter(Reiter.EINSTELLUNGEN)
    einstellungen._bestaetigen()

    assert bestand.einstellungen.naechste_rechnungsnummer == {"2026": 501}


def test_offene_aenderung_ueberlebt_den_reiterwechsel(qapp, tmp_path):
    """Das Auffrischen darf dem Anwender eine offene Eingabe nicht wegziehen."""
    pfad = tmp_path / "d.scgr"
    bestand = erzeuge_seed()
    fenster = HauptFenster(bestand, daten_pfad=pfad)
    fenster.show()
    einstellungen = fenster._reiter_widgets[Reiter.EINSTELLUNGEN]
    fenster.zeige_reiter(Reiter.EINSTELLUNGEN)
    einstellungen._standard.setPlainText("Noch nicht bestätigt")

    fenster.zeige_reiter(Reiter.RECHNUNGEN)
    fenster.zeige_reiter(Reiter.EINSTELLUNGEN)

    assert einstellungen._standard.toPlainText() == "Noch nicht bestätigt"


# --- Ausgabe-Verzeichnis (S-0057, 4T-0121) ----------------------------------


def test_laedt_ausgabe_verzeichnis(qapp, tmp_path):
    """AK1: Ein gepflegtes Verzeichnis erscheint beim Laden im Feld."""
    bestand = erzeuge_seed()
    bestand.einstellungen.ausgabe_verzeichnis = str(tmp_path / "Ausgabe")
    reiter = EinstellungenReiter(bestand)
    assert reiter._ausgabe.text() == str(tmp_path / "Ausgabe")


def test_ausgabe_verzeichnis_ist_pflegbar(qapp, tmp_path):
    """AK1: Die Eingabe wird übernommen, getrimmt und gespeichert."""
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._ausgabe.setText(f"  {tmp_path / 'Rechnungen'}  ")
    reiter._bestaetigen()
    assert bestand.einstellungen.ausgabe_verzeichnis == str(tmp_path / "Rechnungen")


def test_leeres_ausgabe_verzeichnis_ist_zulaessig(qapp, tmp_path):
    """Leer bleibt erlaubt: Ohne Verzeichnis schlägt die Erstellung eines vor (S-0057 AK1),
    die Einstellungen erzwingen es nicht."""
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._ausgabe.setText("")
    reiter._bestaetigen()
    assert bestand.einstellungen.ausgabe_verzeichnis == ""
    assert reiter._fehler["ausgabe_verzeichnis"].isHidden() is True


# --- UI-Sprache (S-0059) ----------------------------------------------------


def _reiter_mit_sprache(bestand, tmp_path, monkeypatch):
    """Reiter samt unterdrücktem Neustart-Hinweis (er ist modal und blockierte den Test)."""
    gezeigt = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: gezeigt.append(a[1:]) or QMessageBox.Ok
    )
    reiter = EinstellungenReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    return reiter, gezeigt


def test_sprachauswahl_bietet_alle_fuenf_sprachen(qapp):
    """AK1: Eine der fünf UI-Sprachen ist wählbar."""
    reiter = EinstellungenReiter(erzeuge_seed())
    kuerzel = [reiter._sprache.itemData(i) for i in range(reiter._sprache.count())]
    assert kuerzel == list(SPRACHEN)


def test_sprachnamen_stehen_in_der_eigenen_sprache(qapp):
    """Wer die Oberfläche nicht liest, muss seine Sprache trotzdem finden."""
    reiter = EinstellungenReiter(erzeuge_seed())
    namen = [reiter._sprache.itemText(i) for i in range(reiter._sprache.count())]
    assert namen == ["Deutsch", "English", "Italiano", "Français", "Español"]


def test_laedt_die_eingestellte_sprache(qapp):
    bestand = erzeuge_seed()
    bestand.einstellungen.ui_sprache = "it"
    reiter = EinstellungenReiter(bestand)
    assert reiter._sprache.currentData() == "it"


def test_unbekannte_sprache_erscheint_als_deutsch(qapp):
    """Ein verfremdeter Wert in der Firma-Datei darf die Maske nicht brechen."""
    bestand = erzeuge_seed()
    bestand.einstellungen.ui_sprache = "kl"
    reiter = EinstellungenReiter(bestand)
    assert reiter._sprache.currentData() == "de"


def test_sprachwahl_wird_gespeichert(qapp, tmp_path, monkeypatch):
    """AK2: Die Wahl landet in den Einstellungen und damit in der Firma-Datei."""
    bestand = erzeuge_seed()
    reiter, _ = _reiter_mit_sprache(bestand, tmp_path, monkeypatch)
    reiter._sprache.setCurrentIndex(reiter._sprache.findData("fr"))
    reiter._bestaetigen()
    assert bestand.einstellungen.ui_sprache == "fr"
    assert lade(tmp_path / "d.json").einstellungen.ui_sprache == "fr"


def test_geaenderte_sprache_weist_auf_den_neustart_hin(qapp, tmp_path, monkeypatch):
    """AK3: Die Umschaltung wirkt erst beim nächsten Start, das muss der Anwender erfahren."""
    bestand = erzeuge_seed()
    reiter, gezeigt = _reiter_mit_sprache(bestand, tmp_path, monkeypatch)
    reiter._sprache.setCurrentIndex(reiter._sprache.findData("en"))
    reiter._bestaetigen()
    assert len(gezeigt) == 1


def test_unveraenderte_sprache_weist_nicht_auf_den_neustart_hin(qapp, tmp_path, monkeypatch):
    """Wer nur den Anschreibentext ändert, soll keinen Neustart-Hinweis sehen."""
    bestand = erzeuge_seed()
    reiter, gezeigt = _reiter_mit_sprache(bestand, tmp_path, monkeypatch)
    reiter._standard.setPlainText("Guten Tag,")
    reiter._bestaetigen()
    assert gezeigt == []


def test_sprachwechsel_laesst_daten_und_rechnungssprachen_unberuehrt(qapp, tmp_path, monkeypatch):
    """AK5: Die Umschaltung ändert nur Oberflächen-Texte, keine Belege."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    kunde.rechnungssprache = "it"
    bestellung = kunde.bestellungen[0]
    rechnung = bestellung.rechnungen[0] if bestellung.rechnungen else None
    vorher_kunde, vorher_name = kunde.rechnungssprache, kunde.name
    vorher_rechnung = rechnung.rechnungssprache if rechnung else None

    reiter, _ = _reiter_mit_sprache(bestand, tmp_path, monkeypatch)
    reiter._sprache.setCurrentIndex(reiter._sprache.findData("es"))
    reiter._bestaetigen()

    assert bestand.einstellungen.ui_sprache == "es"
    assert kunde.rechnungssprache == vorher_kunde  # unverändert „it"
    assert kunde.name == vorher_name
    if rechnung is not None:
        assert rechnung.rechnungssprache == vorher_rechnung


# --- Währungen (S-0062 AK1/AK2, 4T-0132) -----------------------------------


def test_laedt_waehrungsliste_und_standardwaehrung(qapp):
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    bestand.einstellungen.standardwaehrung = "CHF"
    reiter = EinstellungenReiter(bestand)
    assert reiter._lese_waehrungen() == ["EUR", "CHF"]
    assert reiter._standardwaehrung.currentText() == "CHF"
    assert reiter._geaendert is False  # Befüllen ist keine Anwender-Änderung


def test_standardwaehrung_bietet_nur_die_liste_an(qapp):
    """AK2: Die Auswahl kommt aus der Tabelle, beide können nicht auseinanderlaufen."""
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    reiter = EinstellungenReiter(bestand)
    angeboten = [
        reiter._standardwaehrung.itemText(i) for i in range(reiter._standardwaehrung.count())
    ]
    assert angeboten == ["EUR", "CHF"]


def test_neue_waehrung_erscheint_sofort_in_der_standardauswahl(qapp):
    """Wer eine Währung anlegt, soll sie ohne Zwischenspeichern als Standard wählen können."""
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR"]
    reiter = EinstellungenReiter(bestand)
    reiter._waehrung_hinzufuegen()
    reiter._waehrungen.item(1, 0).setText("CHF")
    angeboten = [
        reiter._standardwaehrung.itemText(i) for i in range(reiter._standardwaehrung.count())
    ]
    assert angeboten == ["EUR", "CHF"]
    assert reiter._standardwaehrung.currentText() == "EUR"  # die Wahl bleibt stehen
    assert reiter._geaendert is True


def test_waehrungen_speichern(qapp, tmp_path):
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._waehrung_hinzufuegen()
    reiter._waehrungen.item(reiter._waehrungen.rowCount() - 1, 0).setText("CHF")
    reiter._standardwaehrung.setCurrentIndex(reiter._standardwaehrung.findText("CHF"))
    reiter._bestaetigen()
    assert "CHF" in bestand.einstellungen.waehrungsliste
    assert bestand.einstellungen.standardwaehrung == "CHF"
    assert lade(tmp_path / "d.json").einstellungen.standardwaehrung == "CHF"


def test_ungueltiger_waehrungscode_wird_feldnah_abgelehnt(qapp):
    bestand = erzeuge_seed()
    vorher = list(bestand.einstellungen.waehrungsliste)
    reiter = EinstellungenReiter(bestand)
    reiter._waehrung_hinzufuegen()
    reiter._waehrungen.item(reiter._waehrungen.rowCount() - 1, 0).setText("eur")
    reiter._bestaetigen()
    assert reiter._fehler["waehrungsliste"].isHidden() is False
    assert bestand.einstellungen.waehrungsliste == vorher  # nicht überschrieben


def test_leere_zeile_zaehlt_nicht_als_waehrung(qapp, tmp_path):
    """Eine angelegte, aber nicht befüllte Zeile darf das Speichern nicht blockieren."""
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = EinstellungenReiter(bestand, auto_speicher=auto)
    reiter._waehrung_hinzufuegen()
    reiter._bestaetigen()
    assert bestand.einstellungen.waehrungsliste == ["EUR"]


def test_benutzte_waehrung_laesst_sich_nicht_entfernen(qapp, monkeypatch):
    """Sonst zeigte eine Bestellung eine Belegwährung, die es nicht mehr gibt."""
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    reiter = EinstellungenReiter(bestand)
    gezeigt = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: gezeigt.append(a[2]) or QMessageBox.Ok
    )
    reiter._waehrungen.setCurrentCell(0, 0)  # EUR: Standardwährung des Seeds
    reiter._waehrung_entfernen()
    assert reiter._lese_waehrungen() == ["EUR", "CHF"]  # nichts entfernt
    assert len(gezeigt) == 1
    assert "EUR" in gezeigt[0]


def test_unbenutzte_waehrung_laesst_sich_entfernen(qapp):
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "JPY"]
    reiter = EinstellungenReiter(bestand)
    reiter._waehrungen.setCurrentCell(1, 0)  # JPY: nirgends in Gebrauch
    reiter._waehrung_entfernen()
    assert reiter._lese_waehrungen() == ["EUR"]
    assert reiter._geaendert is True


def test_entfernen_ohne_auswahl_weist_freundlich_hin(qapp, monkeypatch):
    bestand = erzeuge_seed()
    reiter = EinstellungenReiter(bestand)
    gezeigt = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: gezeigt.append(a[2]) or QMessageBox.Ok
    )
    reiter._waehrungen.setCurrentCell(-1, -1)
    reiter._waehrung_entfernen()
    assert len(gezeigt) == 1
    assert reiter._lese_waehrungen() == ["EUR"]
