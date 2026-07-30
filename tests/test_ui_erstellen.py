"""Tests der Erstellen-Aktion in der Oberfläche (4T-0074), offscreen.

Prüft den Formatwahl-Dialog, die Auswahl der markierten Rechnung und den vollen
UI-Erstellungslauf (mit gemockten Dialogen): Dateien werden geschrieben, der
Status auf „Erzeugt" gesetzt und persistiert.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from eu_rechnung.domain import Position, RechnungsStatus
from eu_rechnung.persistence import lade
from eu_rechnung.services import Format, erzeuge_seed, lege_rechnung_an, vorbelege_rechnung
from eu_rechnung.ui.erstellen_dialog import FormatDialog
from eu_rechnung.ui.rechnungen_reiter import RechnungenReiter
from eu_rechnung.ui.sprache import ui_text


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_formatdialog_liefert_gewaehlte_formate(qapp):
    dialog = FormatDialog()
    assert dialog.formate() == {Format.XRECHNUNG, Format.ZUGFERD}  # Default: beide
    dialog._zugferd.setChecked(False)
    assert dialog.formate() == {Format.XRECHNUNG}


def _reiter_mit_rechnung(tmp_path):
    bestand = erzeuge_seed()
    daten = tmp_path / "daten.json"
    # Ausgabe-Verzeichnis gepflegt: Die Erstellung fragt dann nicht nach (S-0057 AK1).
    bestand.einstellungen.ausgabe_verzeichnis = str(tmp_path / "Ausgabe")
    reiter = RechnungenReiter(bestand, daten_pfad=daten)
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = [
        Position("", "Beratung", Decimal("10"), Decimal("1200.00"), Decimal("12000.00"))
    ]
    lege_rechnung_an(bestand, bestellung, rechnung, pfad=daten)
    reiter._fuelle_liste()
    reiter._liste.waehle_objekt(rechnung)
    return reiter, daten


def test_markierte_rechnung_aus_liste(qapp, tmp_path):
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    rechnung = reiter._markierte_rechnung()
    assert rechnung is not None
    assert rechnung.rechnungsnummer == "2026-10001"


def test_erstellen_ueber_ui_schreibt_und_persistiert(qapp, tmp_path, monkeypatch):
    reiter, daten = _reiter_mit_rechnung(tmp_path)
    # Dialoge unterdrücken: Format = beide; Info-/Warn-Popups verschlucken.
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(
        FormatDialog, "formate", lambda self: {Format.XRECHNUNG, Format.ZUGFERD}
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    reiter._rechnung_erstellen()

    ausgabe = tmp_path / "Ausgabe"
    assert (ausgabe / "D10002" / "2026-10001.xml").exists()
    assert (ausgabe / "D10002" / "2026-10001.pdf").exists()
    # Status am Objekt gesetzt und persistiert
    rechnung = reiter._datenbestand.kunden[0].bestellungen[0].rechnungen[0]
    assert rechnung.status is RechnungsStatus.ERZEUGT
    assert rechnung.zuletzt_erzeugt_am is not None
    # Markierung bleibt nach der Erstellung erhalten
    assert reiter._markierte_rechnung() is rechnung
    wieder = lade(daten)
    assert wieder.kunden[0].bestellungen[0].rechnungen[0].status is RechnungsStatus.ERZEUGT


def test_erstellen_blockiert_bei_fehlender_pflichtangabe(qapp, tmp_path, monkeypatch):
    """Fehlende Pflichtangabe der aktiven Stufe: verständliche Meldung, keine Datei (4T-0113 AK1)."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    rechnung = reiter._markierte_rechnung()
    rechnung.kaeufer.email = ""  # bei aktiver XRechnung (Seed-Default) CIUS-Pflicht
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    meldungen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: meldungen.append(a))

    reiter._rechnung_erstellen()

    assert meldungen  # Pflichtmeldung erschien
    assert not (tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml").exists()  # keine Datei


def test_erstellen_bricht_bei_abgelehntem_schalter_hinweis_ab(qapp, tmp_path, monkeypatch):
    """Inaktive XRechnung: Hinweis erscheint; bei Ablehnung wird nichts erzeugt (4T-0113 AK2)."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    reiter._markierte_rechnung().verkaeufer.xrechnung_aktiv = False
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    gefragt = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: gefragt.append(a) or QMessageBox.No)

    reiter._rechnung_erstellen()

    assert gefragt  # Schalter-Hinweis erschien
    assert not (tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml").exists()


def test_erstellen_bei_inaktiver_xrechnung_nach_bestaetigung_erzeugt(qapp, tmp_path, monkeypatch):
    """Inaktive XRechnung: nach Bestätigung des Hinweises wird regulär erzeugt (4T-0113 AK2)."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    reiter._markierte_rechnung().verkaeufer.xrechnung_aktiv = False
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

    reiter._rechnung_erstellen()

    assert (tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml").exists()


def test_erstellen_speichert_offene_maskenaenderung_zuerst(qapp, tmp_path, monkeypatch):
    """Offene Änderung in der geladenen Maske wird vor der Erstellung gespeichert (4T-0113 AK3)."""
    reiter, daten = _reiter_mit_rechnung(tmp_path)
    rechnung = reiter._markierte_rechnung()
    reiter._auf_auswahl(rechnung)  # Ändern-Modus: Maske lädt die Rechnung
    reiter._maske._zahlung.setText("Netto 14 Tage")  # offene Änderung
    assert reiter._maske.geaendert
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    # Die freie Beispiel-Position löst beim Speichern eine Warnung aus; sie wird bestätigt.
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)

    reiter._rechnung_erstellen()

    gespeichert = reiter._datenbestand.kunden[0].bestellungen[0].rechnungen[0]
    assert gespeichert.zahlungsbedingung == "Netto 14 Tage"  # vor der Erstellung gespeichert
    assert (tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml").exists()
    assert lade(daten).kunden[0].bestellungen[0].rechnungen[0].zahlungsbedingung == "Netto 14 Tage"


def test_masken_erstellen_knopf_loest_erstellung_aus(qapp, tmp_path, monkeypatch):
    """Die Erstellen-Aktion ist auch in der Detailmaske verfügbar (4T-0113 AK4)."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    reiter._auf_auswahl(reiter._markierte_rechnung())  # Maske im Ändern-Modus
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    reiter._maske._erstellen_angefordert()  # entspricht dem Klick auf den Masken-Knopf

    assert (tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml").exists()


def test_erstellen_knopf_nur_im_aendern_modus_aktiv(qapp, tmp_path):
    """Der Masken-Erstellen-Knopf ist nur bei gespeicherter Rechnung aktiv (4T-0113 AK4)."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    reiter._auf_auswahl(reiter._markierte_rechnung())  # Ändern-Modus
    assert reiter._maske._erstellen_knopf.isEnabled()
    reiter._neue_rechnung()  # Anlege-Modus
    assert not reiter._maske._erstellen_knopf.isEnabled()


# --- Standard-Vorschlag für das Ausgabe-Verzeichnis (S-0057 AK1, 4T-0121) ----


def _reiter_ohne_ausgabe_verzeichnis(tmp_path):
    """Wie `_reiter_mit_rechnung`, aber ohne gepflegtes Ausgabe-Verzeichnis."""
    reiter, daten = _reiter_mit_rechnung(tmp_path)
    reiter._datenbestand.einstellungen.ausgabe_verzeichnis = ""
    return reiter, daten


def test_vorschlag_wird_uebernommen_und_gespeichert(qapp, tmp_path, monkeypatch):
    """AK2: Ohne Verzeichnis wird eines vorgeschlagen; bei Zustimmung wird es übernommen,
    gespeichert und die Erstellung läuft dorthin."""
    reiter, daten = _reiter_ohne_ausgabe_verzeichnis(tmp_path)
    monkeypatch.setattr(
        QStandardPaths, "writableLocation", staticmethod(lambda ort: str(tmp_path))
    )
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    gefragt = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: gefragt.append(a) or QMessageBox.Yes
    )

    reiter._rechnung_erstellen()

    assert gefragt  # der Vorschlag wurde angeboten
    erwartet = str(tmp_path / "EU-Rechnung Ausgabe")
    assert reiter._datenbestand.einstellungen.ausgabe_verzeichnis == erwartet
    assert (Path(erwartet) / "D10002" / "2026-10001.xml").exists()
    assert lade(daten).einstellungen.ausgabe_verzeichnis == erwartet  # persistiert


def test_abbruch_des_vorschlags_erzeugt_nichts(qapp, tmp_path, monkeypatch):
    """AK2: Bricht der Anwender ab, entsteht keine Datei und nichts wird gespeichert."""
    reiter, _ = _reiter_ohne_ausgabe_verzeichnis(tmp_path)
    monkeypatch.setattr(
        QStandardPaths, "writableLocation", staticmethod(lambda ort: str(tmp_path))
    )
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel)

    reiter._rechnung_erstellen()

    assert reiter._datenbestand.einstellungen.ausgabe_verzeichnis == ""
    assert not (tmp_path / "EU-Rechnung Ausgabe").exists()


def test_gepflegtes_verzeichnis_fragt_nicht_nach(qapp, tmp_path, monkeypatch):
    """AK2: Die Frage kommt nur einmal; mit gepflegtem Verzeichnis erscheint sie nicht."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)  # Verzeichnis gesetzt
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    gefragt = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: gefragt.append(a) or QMessageBox.Yes
    )

    reiter._rechnung_erstellen()

    assert not gefragt
    assert (tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml").exists()


# --- Ausgabestand in der Maske nach dem Lauf (S-0032 AK4, 4T-0160) ----------


def test_maske_zeigt_den_ausgabestand_nach_dem_lauf(qapp, tmp_path, monkeypatch):
    """AK4: „in Liste **und** Maske sichtbar".

    `_waehle_in_liste` laedt die Maske bewusst nicht neu; ohne den zusaetzlichen Aufruf
    stuende dort weiter „Entwurf", waehrend die Liste daneben „Erzeugt" zeigt.
    """
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    assert reiter._maske._status_anzeige.text() == ui_text("rechnung.status_entwurf")
    assert reiter._maske._erzeugt_anzeige.text() == "—"

    reiter._rechnung_erstellen()

    assert reiter._maske._status_anzeige.text() == ui_text("rechnung.status_erzeugt")
    assert reiter._maske._erzeugt_anzeige.text() != "—"


def test_maske_bleibt_nach_dem_lauf_am_selben_original(qapp, tmp_path, monkeypatch):
    """Das erneute Zeigen darf den Aendern-Kontext nicht verlieren, sonst legte das
    naechste Bestaetigen eine zweite Rechnung an."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: {Format.XRECHNUNG})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    rechnung = reiter._datenbestand.kunden[0].bestellungen[0].rechnungen[0]

    reiter._rechnung_erstellen()

    assert reiter._bearbeitete_original is rechnung
    assert reiter._maske.ist_neu is False


# --- Überschreiben-Abfrage über die Oberfläche (S-0031, 4T-0161) ------------


def _erstellen_vorbereiten(monkeypatch, formate):
    """Format-Dialog und Info-Popups unterdrücken; die Erstellung läuft dann durch."""
    monkeypatch.setattr(FormatDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(FormatDialog, "formate", lambda self: formate)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)


def _fange_fragen(monkeypatch, antworten):
    """Ersetzt `QMessageBox.question` und beantwortet je Aufruf der Reihe nach.

    Liefert die Liste der gestellten Fragetexte, damit der Test prüfen kann, wonach
    tatsächlich gefragt wurde.
    """
    gestellt: list[str] = []

    def frage(parent, titel, text, *a, **k):
        gestellt.append(text)
        return antworten[len(gestellt) - 1]

    monkeypatch.setattr(QMessageBox, "question", frage)
    return gestellt


def test_ueberschreiben_frage_nennt_den_dateinamen(qapp, tmp_path, monkeypatch):
    """S-0031 AK1: Die Abfrage nennt die betroffene Datei.

    Bis 4T-0161 war nur die Service-Ebene mit Lambda-Callbacks geprüft; `_frage_ueberschreiben`
    selbst löste kein Test aus, obwohl der Story-Vermerk „UI-Tests" behauptete.
    """
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    ziel = tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml"
    ziel.parent.mkdir(parents=True)
    ziel.write_text("alt", encoding="utf-8")
    _erstellen_vorbereiten(monkeypatch, {Format.XRECHNUNG})
    gestellt = _fange_fragen(monkeypatch, [QMessageBox.Yes])

    reiter._rechnung_erstellen()

    assert len(gestellt) == 1
    assert "2026-10001.xml" in gestellt[0]


def test_ueberschreiben_bestaetigt_ersetzt_die_datei(qapp, tmp_path, monkeypatch):
    """S-0031 AK2: „Ja" ersetzt."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    ziel = tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml"
    ziel.parent.mkdir(parents=True)
    ziel.write_text("alt", encoding="utf-8")
    _erstellen_vorbereiten(monkeypatch, {Format.XRECHNUNG})
    _fange_fragen(monkeypatch, [QMessageBox.Yes])

    reiter._rechnung_erstellen()

    assert ziel.read_text(encoding="utf-8") != "alt"


def test_ueberschreiben_abgelehnt_laesst_die_datei_stehen(qapp, tmp_path, monkeypatch):
    """S-0031 AK2: „Nein" lässt unverändert und schreibt nichts."""
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    ziel = tmp_path / "Ausgabe" / "D10002" / "2026-10001.xml"
    ziel.parent.mkdir(parents=True)
    ziel.write_text("alt", encoding="utf-8")
    _erstellen_vorbereiten(monkeypatch, {Format.XRECHNUNG})
    _fange_fragen(monkeypatch, [QMessageBox.No])

    reiter._rechnung_erstellen()

    assert ziel.read_text(encoding="utf-8") == "alt"
    rechnung = reiter._datenbestand.kunden[0].bestellungen[0].rechnungen[0]
    assert rechnung.status is RechnungsStatus.ENTWURF  # nichts geschrieben, kein Fortschritt


def test_bei_zwei_kollisionen_wird_je_datei_einzeln_gefragt(qapp, tmp_path, monkeypatch):
    """S-0031 AK3: „bei mehreren Dateien je Datei einzeln gefragt".

    Der Fall war nie durchgespielt: Die Service-Tests nutzen je nur ein Format, und ein
    gemeinsames Ja/Nein für beide Dateien wäre hier nicht aufgefallen.
    """
    reiter, _ = _reiter_mit_rechnung(tmp_path)
    ordner = tmp_path / "Ausgabe" / "D10002"
    ordner.mkdir(parents=True)
    xml, pdf = ordner / "2026-10001.xml", ordner / "2026-10001.pdf"
    xml.write_text("alt-xml", encoding="utf-8")
    pdf.write_bytes(b"alt-pdf")
    _erstellen_vorbereiten(monkeypatch, {Format.XRECHNUNG, Format.ZUGFERD})
    # Erste Datei ja, zweite nein: Die Antworten gelten je Datei, nicht pauschal.
    gestellt = _fange_fragen(monkeypatch, [QMessageBox.Yes, QMessageBox.No])

    reiter._rechnung_erstellen()

    assert len(gestellt) == 2, "je Datei eine eigene Frage"
    namen = sorted(n.split("2026-10001")[1][:4] for n in gestellt)
    assert namen == [".pdf", ".xml"], f"gefragt wurde nach: {gestellt}"
    # Genau eine der beiden Dateien wurde ersetzt.
    ersetzt = [xml.read_text(encoding="utf-8") != "alt-xml", pdf.read_bytes() != b"alt-pdf"]
    assert ersetzt.count(True) == 1
