"""Tests des Firma-Reiters und des Bankverbindungs-Dialogs (4T-0078), offscreen.

Prüft, dass der Reiter die aktive Firma lädt, die Pflicht-Markierung dem Schalter
folgt, die Eingaben zurückgeschrieben werden und das Bestätigen bei gültigen Daten
speichert, bei ungültigen blockiert. Zudem die Sichtbarkeit offener Änderungen am
Bestätigen-Knopf (4T-0088).
"""

from __future__ import annotations

import os
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from eu_rechnung.domain import Bankverbindung
from eu_rechnung.services import erzeuge_seed
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.bankverbindung_dialog import BankverbindungDialog
from eu_rechnung.ui.firma_reiter import FirmaReiter


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_firma_reiter_laedt_seed_firma(qapp):
    reiter = FirmaReiter(erzeuge_seed())
    assert reiter._edits["name"].text() == "Muster Consulting GmbH"
    assert reiter._edits["land"].text() == "CH"
    assert reiter._schalter.isChecked() is True
    assert reiter._bank_tabelle.rowCount() == 1


def test_pflicht_markierung_folgt_schalter(qapp):
    reiter = FirmaReiter(erzeuge_seed())
    label_email = reiter._pflicht["email"][0]
    assert label_email.text().endswith("*")  # bei aktiver XRechnung Pflicht
    reiter._schalter.setChecked(False)
    assert not label_email.text().endswith("*")
    assert reiter._pflicht["name"][0].text().endswith("*")  # immer Pflicht


def test_uebernahme_schreibt_in_firma(qapp):
    bestand = erzeuge_seed()
    reiter = FirmaReiter(bestand)
    reiter._edits["name"].setText("Neue Firma GmbH")
    reiter._edits["hausnummer"].setText("42")
    reiter._uebernehme_in_firma(bestand.eigene_firma)
    assert bestand.eigene_firma.name == "Neue Firma GmbH"
    assert bestand.eigene_firma.adresse.hausnummer == "42"


def test_steuersatz_feld_laedt_und_uebernimmt(qapp):
    """Der Standard-Steuersatz der Firma wird geladen und als Decimal zurückgeschrieben (S-0079)."""
    bestand = erzeuge_seed()
    bestand.eigene_firma.standard_steuersatz = Decimal("19")
    reiter = FirmaReiter(bestand)
    assert reiter._edits["steuersatz"].text() == "19,00"  # deutsche Notation
    reiter._edits["steuersatz"].setText("7,7")
    reiter._uebernehme_in_firma(bestand.eigene_firma)
    assert bestand.eigene_firma.standard_steuersatz == Decimal("7.7")


def test_bestaetigen_mit_fehler_laesst_firma_unveraendert(qapp, tmp_path):
    """Schlägt die Prüfung fehl, bleibt das echte Firma-Objekt unverändert, und Verwerfen
    holt den gespeicherten Wert zurück (Regression: Kandidat-Prüfung statt Direkt-Mutation)."""
    bestand = erzeuge_seed()
    original = bestand.eigene_firma.name
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = FirmaReiter(bestand, auto_speicher=auto)
    reiter._edits["name"].setText("")  # Pflichtfeld leeren, Bestätigen schlägt fehl
    reiter._bestaetigen()
    assert bestand.eigene_firma.name == original  # echtes Objekt nicht korrumpiert
    reiter._lade_aus_firma()  # Verwerfen
    assert reiter._edits["name"].text() == original


def test_bestaetigen_speichert_bei_gueltig(qapp, tmp_path):
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = FirmaReiter(bestand, auto_speicher=auto)
    reiter._bestaetigen()
    assert (tmp_path / "firma.json").exists()


def test_bestaetigen_blockiert_bei_fehler(qapp, tmp_path):
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = FirmaReiter(bestand, auto_speicher=auto)
    reiter._edits["name"].setText("")  # Pflichtfeld leeren
    reiter._bestaetigen()
    assert reiter._fehler["name"].isHidden() is False  # Hinweis am Feld sichtbar
    assert not (tmp_path / "firma.json").exists()  # nichts gespeichert


def test_bank_befund_erscheint_am_bank_label(qapp, tmp_path):
    """Bankverbindungs-Befunde erscheinen gesammelt am Bank-Sammel-Label (AK1)."""
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = FirmaReiter(bestand, auto_speicher=auto)
    reiter._schalter.setChecked(True)  # XRechnung aktiv -> Bankverbindung Pflicht
    reiter._bankverbindungen.clear()
    reiter._fuelle_bank_tabelle()
    reiter._bestaetigen()
    assert reiter._fehler["bank"].isHidden() is False
    assert not (tmp_path / "firma.json").exists()


def test_bankverbindung_dialog_liefert_werte(qapp):
    dialog = BankverbindungDialog(["EUR", "CHF"])
    dialog._kontoinhaber.setText("Test AG")
    dialog._iban.setText("CH09 0000 0000 0000 0000 1")
    dialog._waehrung.setCurrentText("CHF")
    b = dialog.bankverbindung()
    assert b.kontoinhaber == "Test AG"
    assert b.waehrung == "CHF"


# --- Währungsliste im Bankverbindungs-Dialog (S-0062, 4T-0139) --------------


def test_bankverbindung_dialog_nutzt_stammdaten_waehrungsliste(qapp):
    """AK1: Die Währungsauswahl kommt aus der übergebenen Stammdaten-Liste, nicht aus einer
    festen Kurzliste."""
    dialog = BankverbindungDialog(["EUR", "CHF", "GBP"])
    eintraege = [dialog._waehrung.itemText(i) for i in range(dialog._waehrung.count())]
    assert eintraege == ["EUR", "CHF", "GBP"]


def test_bankverbindung_dialog_erlaubt_freie_waehrung(qapp):
    """AK2: Ein Wert außerhalb der Liste bleibt über die freie Eingabe erfassbar."""
    dialog = BankverbindungDialog(["EUR"])
    dialog._kontoinhaber.setText("Test AG")
    dialog._iban.setText("US64")
    dialog._waehrung.setCurrentText("USD")  # nicht in der Liste
    assert dialog.bankverbindung().waehrung == "USD"


def test_bankverbindungsliste_zeigt_mindestens_fuenf_zeilen(qapp):
    reiter = FirmaReiter(erzeuge_seed())
    tabelle = reiter._bank_tabelle
    zeile_h = tabelle.verticalHeader().defaultSectionSize()
    assert tabelle.minimumHeight() >= 5 * zeile_h


# --- Sichtbarkeit offener Änderungen am Bestätigen-Knopf (4T-0088) ----------


def test_knopf_initial_nicht_hervorgehoben(qapp):
    """Nach dem Laden gibt es keine offenen Änderungen (AK5)."""
    reiter = FirmaReiter(erzeuge_seed())
    assert reiter._geaendert is False
    assert reiter._bestaetigen_knopf.styleSheet() == ""


def test_feldaenderung_hebt_knopf_hervor(qapp):
    """Eine Feld-Eingabe markiert offene Änderungen (AK1)."""
    reiter = FirmaReiter(erzeuge_seed())
    reiter._edits["name"].setText("Geänderte Firma GmbH")
    assert reiter._geaendert is True
    assert reiter._bestaetigen_knopf.styleSheet() != ""


def test_schalteraenderung_hebt_knopf_hervor(qapp):
    """Der XRechnung-Schalter zählt ebenfalls als Änderung (AK1)."""
    reiter = FirmaReiter(erzeuge_seed())
    reiter._schalter.setChecked(not reiter._schalter.isChecked())
    assert reiter._geaendert is True


def test_bankaenderung_hebt_knopf_hervor(qapp):
    """Auch eine Bank-Operation markiert offene Änderungen (AK1)."""
    reiter = FirmaReiter(erzeuge_seed())
    assert reiter._geaendert is False
    reiter._bank_tabelle.setCurrentCell(0, 0)
    reiter._bank_entfernen()
    assert reiter._geaendert is True


def test_bestaetigen_setzt_knopf_zurueck(qapp, tmp_path):
    """Nach erfolgreichem Bestätigen ist der Knopf wieder normal (AK2)."""
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = FirmaReiter(bestand, auto_speicher=auto)
    reiter._edits["name"].setText("Neuer Name GmbH")
    assert reiter._geaendert is True
    reiter._bestaetigen()
    assert reiter._geaendert is False
    assert reiter._bestaetigen_knopf.styleSheet() == ""


def test_verwerfen_setzt_knopf_zurueck(qapp):
    """Verwerfen lädt den gespeicherten Stand und räumt die Markierung ab (AK3)."""
    reiter = FirmaReiter(erzeuge_seed())
    reiter._edits["name"].setText("Zwischenstand GmbH")
    assert reiter._geaendert is True
    reiter._lade_aus_firma()  # Verwerfen
    assert reiter._geaendert is False
    assert reiter._bestaetigen_knopf.styleSheet() == ""


def test_knopf_bleibt_bei_validierungsfehler_hervorgehoben(qapp, tmp_path):
    """Schlägt die Prüfung fehl, bleibt der offene Stand sichtbar (AK4)."""
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = FirmaReiter(bestand, auto_speicher=auto)
    reiter._edits["name"].setText("")  # Pflichtfeld leeren
    reiter._bestaetigen()
    assert reiter._geaendert is True
    assert reiter._bestaetigen_knopf.styleSheet() != ""


# --- Entfernen aus der Detailmaske (S-0002 AK4, 4T-0159) --------------------


def test_bankverbindung_dialog_bietet_entfernen_nur_beim_aendern(qapp):
    """AK4: Beim Ändern gibt es den Weg, beim Hinzufügen wäre er sinnlos."""
    aendern = BankverbindungDialog(["EUR"], Bankverbindung("A", "Bank", "DE02", "X", "EUR"))
    hinzufuegen = BankverbindungDialog(["EUR"])
    assert _entfernen_knopf(aendern) is not None
    assert _entfernen_knopf(hinzufuegen) is None


def test_bankverbindung_dialog_meldet_entfernen(qapp):
    """AK4: Der Knopf schließt den Dialog mit dem eigenen Ergebnis-Code."""
    dialog = BankverbindungDialog(["EUR"], Bankverbindung("A", "Bank", "DE02", "X", "EUR"))
    _entfernen_knopf(dialog).click()
    assert dialog.result() == BankverbindungDialog.ENTFERNEN


def test_entfernen_aus_der_detailmaske_nimmt_die_bankverbindung_raus(qapp, tmp_path, monkeypatch):
    """AK4: Der Dialog-Weg wirkt wie das Entfernen in der Liste."""
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = FirmaReiter(bestand, auto_speicher=auto)
    reiter._bankverbindungen.append(Bankverbindung("Zweite", "Bank", "DE99", "X", "CHF"))
    reiter._fuelle_bank_tabelle()
    vorher = len(reiter._bankverbindungen)
    entfernte = reiter._bankverbindungen[1]
    reiter._bank_tabelle.selectRow(1)

    monkeypatch.setattr(BankverbindungDialog, "exec", lambda self: BankverbindungDialog.ENTFERNEN)
    reiter._bank_aendern()

    assert len(reiter._bankverbindungen) == vorher - 1
    assert entfernte not in reiter._bankverbindungen
    assert reiter._geaendert is True  # offener Stand, erst „Bestätigen" speichert


def test_abbruch_der_detailmaske_laesst_die_bankverbindungen_unveraendert(qapp, tmp_path, monkeypatch):
    """AK4: Nur der Entfernen-Knopf entfernt; „Abbrechen" fasst nichts an."""
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = FirmaReiter(bestand, auto_speicher=auto)
    vorher = list(reiter._bankverbindungen)
    reiter._bank_tabelle.selectRow(0)

    monkeypatch.setattr(BankverbindungDialog, "exec", lambda self: QDialog.Rejected)
    reiter._bank_aendern()

    assert reiter._bankverbindungen == vorher
    assert reiter._geaendert is False


def _entfernen_knopf(dialog: BankverbindungDialog):
    """Der Entfernen-Knopf des Dialogs, oder None, wenn er keinen trägt."""
    from PySide6.QtWidgets import QDialogButtonBox

    box = dialog.findChild(QDialogButtonBox)
    for knopf in box.buttons():
        if box.buttonRole(knopf) == QDialogButtonBox.DestructiveRole:
            return knopf
    return None
