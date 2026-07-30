"""Tests der Erstellungslogik (Ausgabedateien, Status, Überschreiben), Java-frei.

Die Norm-Validierung der erzeugten Dateien (KoSIT/veraPDF) liegt im Goldstandard
(4T-0021); hier wird die Erstellungs-Orchestrierung geprüft: Schreiben, Status-
und Zeitstempel-Fortschreibung und die Überschreib-Entscheidung.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from eu_rechnung.domain import RechnungsStatus
from eu_rechnung.services import Format, erstelle_ausgaben, zielordner_der_rechnung
from eu_rechnung.texte import text

_JETZT = datetime(2026, 7, 10, 9, 30, 0, tzinfo=timezone.utc)


# --- Ablageschema (S-0057, 4T-0121) -----------------------------------------


def test_zielordner_folgt_dem_ablageschema(beispiel_rechnung, tmp_path):
    """AK3: `<Ausgabe-Verzeichnis>/<Kundennummer>`; der Ordner wird aus der Rechnung
    hergeleitet, nicht gespeichert."""
    rechnung, _, _ = beispiel_rechnung
    assert zielordner_der_rechnung(rechnung, tmp_path) == tmp_path / "D10002"


def test_erstellung_legt_kunden_unterordner_an(beispiel_rechnung, tmp_path):
    """AK3: Die Dateien landen im Unterordner der Kundennummer."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    ergebnis = erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG}, ausgabe_verzeichnis=tmp_path
    )
    assert ergebnis.erzeugte_dateien == [tmp_path / "D10002" / "2026-10001.xml"]
    assert (tmp_path / "D10002" / "2026-10001.xml").exists()


def test_unzulaessige_zeichen_werden_ersetzt(beispiel_rechnung, tmp_path):
    """AK4: Kunden- und Rechnungsnummer sind frei erfassbar; unzulässige Zeichen dürfen
    den Pfad nicht sprengen."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.kaeufer.kundennummer = "D/10002:X"
    rechnung.rechnungsnummer = "2026/10001*"
    ergebnis = erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG}, ausgabe_verzeichnis=tmp_path
    )
    assert ergebnis.erzeugte_dateien == [tmp_path / "D-10002-X" / "2026-10001-.xml"]
    assert (tmp_path / "D-10002-X" / "2026-10001-.xml").exists()


def test_leere_kundennummer_ergibt_gueltigen_ordner(beispiel_rechnung, tmp_path):
    """AK4: Auch ohne Kundennummer entsteht ein gültiger Pfad statt eines Ordners ohne Namen."""
    rechnung, _, _ = beispiel_rechnung
    rechnung.kaeufer.kundennummer = "   "
    assert zielordner_der_rechnung(rechnung, tmp_path) == tmp_path / "unbenannt"


def test_erstellung_schreibt_beide_formate_und_setzt_status(beispiel_rechnung, tmp_path):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    ergebnis = erstelle_ausgaben(
        rechnung,
        bestellnummer,
        waehrung,
        {Format.XRECHNUNG, Format.ZUGFERD},
        ausgabe_verzeichnis=tmp_path,
        jetzt=_JETZT,
    )
    assert ergebnis.fehler is None
    assert sorted(p.name for p in ergebnis.erzeugte_dateien) == ["2026-10001.pdf", "2026-10001.xml"]
    assert all(p.exists() for p in ergebnis.erzeugte_dateien)
    assert rechnung.status is RechnungsStatus.ERZEUGT
    assert rechnung.zuletzt_erzeugt_am == _JETZT


def test_erstellung_nur_xrechnung(beispiel_rechnung, tmp_path):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    ergebnis = erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG}, ausgabe_verzeichnis=tmp_path, jetzt=_JETZT
    )
    assert [p.name for p in ergebnis.erzeugte_dateien] == ["2026-10001.xml"]
    assert (tmp_path / "D10002" / "2026-10001.xml").exists()
    assert not (tmp_path / "D10002" / "2026-10001.pdf").exists()


def test_ohne_kollision_ohne_callback_wird_geschrieben(beispiel_rechnung, tmp_path):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    ergebnis = erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG}, ausgabe_verzeichnis=tmp_path
    )
    assert len(ergebnis.erzeugte_dateien) == 1
    assert not ergebnis.uebersprungen


def test_ueberschreiben_abgelehnt_laesst_status_unveraendert(beispiel_rechnung, tmp_path):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    # 1. Lauf: Datei anlegen
    erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG}, ausgabe_verzeichnis=tmp_path, jetzt=_JETZT
    )
    # Status zuruecksetzen, um die Unveraenderlichkeit bei Abbruch zu pruefen
    rechnung.status = RechnungsStatus.ENTWURF
    rechnung.zuletzt_erzeugt_am = None
    # 2. Lauf: Ueberschreiben ablehnen -> nichts geschrieben, Status unveraendert
    ergebnis = erstelle_ausgaben(
        rechnung,
        bestellnummer,
        waehrung,
        {Format.XRECHNUNG},
        ausgabe_verzeichnis=tmp_path,
        ueberschreiben=lambda p: False,
        jetzt=_JETZT,
    )
    assert ergebnis.erzeugte_dateien == []
    assert len(ergebnis.uebersprungen) == 1
    assert rechnung.status is RechnungsStatus.ENTWURF
    assert rechnung.zuletzt_erzeugt_am is None


def test_ueberschreiben_erlaubt_ersetzt(beispiel_rechnung, tmp_path):
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG}, ausgabe_verzeichnis=tmp_path, jetzt=_JETZT
    )
    ergebnis = erstelle_ausgaben(
        rechnung,
        bestellnummer,
        waehrung,
        {Format.XRECHNUNG},
        ausgabe_verzeichnis=tmp_path,
        ueberschreiben=lambda p: True,
        jetzt=_JETZT,
    )
    assert len(ergebnis.erzeugte_dateien) == 1
    assert not ergebnis.uebersprungen


def test_nicht_rc_ohne_steuersatz_wird_als_pflichtbefund_abgewiesen(beispiel_rechnung, tmp_path):
    """Nicht-Reverse-Charge ohne Steuersatz (Satz 0) ist nicht normkonform: Pflichtbefund am
    Feld Steuersatz, nichts geschrieben (S-0079, S-0047/S-0049)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False  # steuersatz bleibt 0
    ergebnis = erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG}, ausgabe_verzeichnis=tmp_path
    )
    assert any(b.feld == "steuersatz" for b in ergebnis.pflicht_befunde)
    assert ergebnis.erzeugte_dateien == []
    assert not any(tmp_path.iterdir())  # nichts geschrieben


def test_ausgabe_ohne_pflichtangaben_blockiert(beispiel_rechnung, tmp_path):
    """Fehlende Pflichtangaben der aktiven Stufe verhindern die Ausgabe und liefern
    feldbezogene Befunde statt einer Datei (S-0047/S-0049 AK2)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.verkaeufer.xrechnung_aktiv = True
    rechnung.kaeufer.name = ""  # EN-Pflicht (beide Stufen)
    rechnung.kaeufer.adresse.strasse = ""  # zusätzliche CIUS-Pflicht
    ergebnis = erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG, Format.ZUGFERD}, ausgabe_verzeichnis=tmp_path
    )
    felder = {b.feld for b in ergebnis.pflicht_befunde}
    assert "kaeufer_name" in felder
    assert "kaeufer_strasse" in felder
    assert ergebnis.erzeugte_dateien == []
    assert ergebnis.fehler is None  # kein technischer Fehler, sondern Pflichtbefunde
    assert not any(tmp_path.iterdir())  # nichts geschrieben


def test_normalfall_mit_steuersatz_wird_erzeugt(beispiel_rechnung, tmp_path):
    """Nicht-Reverse-Charge mit Steuersatz erzeugt die Ausgabe regulär (S-0079)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    rechnung.reverse_charge = False
    rechnung.steuersatz = Decimal("19")
    ergebnis = erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG}, ausgabe_verzeichnis=tmp_path, jetzt=_JETZT
    )
    assert ergebnis.fehler is None
    assert [p.name for p in ergebnis.erzeugte_dateien] == ["2026-10001.xml"]
    assert rechnung.status is RechnungsStatus.ERZEUGT


# --- Fehlerpfad ohne Technik-Auszug (S-0032 AK3, 4T-0160) -------------------


def test_erzeugungsfehler_meldet_ohne_technik_auszug(beispiel_rechnung, tmp_path, monkeypatch, caplog):
    """AK3: Eine rohe Ausnahme sagt dem Anwender nichts; sie gehoert ins Log, nicht in den Satz.

    Bis 4T-0160 stand der `str(e)` im Nutzertext, obwohl der Kommentar daneben „lesbare
    Meldung statt Technik-Auszug" versprach. Der Pfad war von keinem Test beruehrt.
    """
    rechnung, bestellnummer, waehrung = beispiel_rechnung

    def kaputt(*args, **kwargs):
        raise KeyError("bt-10")

    monkeypatch.setattr("eu_rechnung.services.erstellung.erzeuge_cii", kaputt)
    with caplog.at_level(logging.ERROR):
        ergebnis = erstelle_ausgaben(
            rechnung, bestellnummer, waehrung, {Format.XRECHNUNG},
            ausgabe_verzeichnis=tmp_path, jetzt=_JETZT,
        )

    assert ergebnis.fehler is not None
    assert ergebnis.fehler.schluessel == "erstellen.fehler_erzeugung"
    assert ergebnis.fehler.werte == {}  # kein Platzhalter, also kein Technik-Auszug
    assert "bt-10" not in text(ergebnis.fehler.schluessel, "de")
    # Die technische Ursache ist nicht verloren, sie steht im Log.
    assert "bt-10" in caplog.text
    assert not ergebnis.erzeugte_dateien


def test_erzeugungsfehler_laesst_status_und_dateien_unveraendert(beispiel_rechnung, tmp_path, monkeypatch):
    """Schlaegt ein Format fehl, wird gar nichts geschrieben (Status bleibt Entwurf)."""
    rechnung, bestellnummer, waehrung = beispiel_rechnung
    vorher = rechnung.status

    def kaputt(*args, **kwargs):
        raise RuntimeError("Zeichensatz")

    monkeypatch.setattr("eu_rechnung.services.erstellung.erzeuge_zugferd", kaputt)
    ergebnis = erstelle_ausgaben(
        rechnung, bestellnummer, waehrung, {Format.XRECHNUNG, Format.ZUGFERD},
        ausgabe_verzeichnis=tmp_path, jetzt=_JETZT,
    )

    assert ergebnis.fehler is not None
    assert rechnung.status == vorher
    assert rechnung.zuletzt_erzeugt_am is None
    assert not list(tmp_path.rglob("*.xml"))  # auch das gelungene Format bleibt ungeschrieben
