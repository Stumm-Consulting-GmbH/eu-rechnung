"""Tests der Firma-Datei-Verwaltung im Hauptfenster (4T-0079, S-0071), offscreen.

Prüft Anlegen, Öffnen und Wechseln einer Firma über das Menü „Datei": der aktive
Datenbestand, der Zielpfad und das automatische Speichern werden ersetzt, die Reiter
frisch aufgebaut und die Liste zuletzt geöffneter Firmen fortgeschrieben. Die
Datei-Dialoge (`firma_dialoge`) werden gemockt statt angezeigt.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import eu_rechnung.ui.firma_dialoge as firma_dialoge
import eu_rechnung.ui.hauptfenster as hauptfenster_modul
from eu_rechnung.app import ermittle_start_firma
from eu_rechnung.persistence import lade, speichere
from eu_rechnung.persistence.konfiguration import lade_konfiguration
from eu_rechnung.persistence.sperre import SperrStatus
from eu_rechnung.services import erzeuge_leeren_datenbestand, erzeuge_seed
from eu_rechnung.ui.firma_reiter import FirmaReiter
from eu_rechnung.ui.hauptfenster import HauptFenster, Reiter


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _firma_datei(pfad: Path, name: str) -> Path:
    """Legt eine Firma-Datei mit unterscheidbarem Namen an."""
    bestand = erzeuge_seed()
    bestand.eigene_firma.name = name
    speichere(bestand, pfad)
    return pfad


def _fenster(tmp_path, aktive: Path):
    konfig = tmp_path / "konfig.json"
    return HauptFenster(lade(aktive), daten_pfad=aktive, konfig_pfad=konfig)


def test_start_firma_wird_in_zuletzt_geoeffnet_aufgenommen(qapp, tmp_path):
    firma = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, firma)
    gespeichert = lade_konfiguration(fenster._konfig_pfad)
    assert [Path(p).name for p in gespeichert.zuletzt_geoeffnet] == ["a.scgr"]


def test_firma_oeffnen_wechselt_aktive_firma(qapp, tmp_path, monkeypatch):
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    b = _firma_datei(tmp_path / "b.scgr", "Firma B")
    fenster = _fenster(tmp_path, a)
    monkeypatch.setattr(firma_dialoge, "oeffne_firma", lambda parent=None: (lade(b), b))
    fenster._firma_oeffnen()
    assert fenster._datenbestand.eigene_firma.name == "Firma B"
    assert fenster._daten_pfad == b
    reiter = fenster._reiter_widgets[Reiter.FIRMA]
    assert isinstance(reiter, FirmaReiter)
    assert reiter._edits["name"].text() == "Firma B"  # Reiter neu gebaut, zeigt Firma B


def test_firma_oeffnen_abbruch_laesst_aktive_firma(qapp, tmp_path, monkeypatch):
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    monkeypatch.setattr(firma_dialoge, "oeffne_firma", lambda parent=None: None)
    fenster._firma_oeffnen()
    assert fenster._datenbestand.eigene_firma.name == "Firma A"
    assert fenster._daten_pfad == a


def test_neue_firma_legt_leere_firma_an_und_aktiviert(qapp, tmp_path, monkeypatch):
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    neu_pfad = tmp_path / "neu.scgr"
    bestand = erzeuge_leeren_datenbestand()
    speichere(bestand, neu_pfad)
    monkeypatch.setattr(
        firma_dialoge, "lege_neue_firma_an", lambda parent=None: (bestand, neu_pfad)
    )
    fenster._neue_firma()
    assert fenster._daten_pfad == neu_pfad
    assert fenster._datenbestand.eigene_firma.name == ""
    assert fenster._tabs.currentWidget() is fenster._reiter_widgets[Reiter.FIRMA]


def test_zuletzt_geoeffnet_menue_listet_firmen(qapp, tmp_path):
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    b = _firma_datei(tmp_path / "b.scgr", "Firma B")
    fenster = _fenster(tmp_path, a)
    fenster._lade_firma_aus_pfad(b)  # b öffnen: Recent = [b, a]
    namen = [aktion.text() for aktion in fenster._zuletzt_menue.actions()]
    assert namen == ["b.scgr", "a.scgr"]


def test_wechsel_haengt_auto_speicher_auf_neuen_pfad_um(qapp, tmp_path):
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    b = _firma_datei(tmp_path / "b.scgr", "Firma B")
    fenster = _fenster(tmp_path, a)
    fenster._lade_firma_aus_pfad(b)
    assert fenster._auto_speicher._pfad == b  # Auto-Save schreibt jetzt nach b


# --- Datei-Sperre gegen Mehrfachstart (4T-0081, S-0073) -----------------------


def test_lade_firma_bei_belegter_sperre_meldet_und_bricht_ab(qapp, tmp_path, monkeypatch):
    """AK2: Eine in anderer Instanz belegte Datei wird nicht geladen; Meldung."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    monkeypatch.setattr(
        firma_dialoge.sperre, "erwerbe_sperre", lambda p: SperrStatus.BELEGT
    )
    gemeldet = []
    monkeypatch.setattr(
        firma_dialoge.QMessageBox, "warning", lambda *a, **k: gemeldet.append(True)
    )
    assert firma_dialoge.lade_firma(a) is None
    assert gemeldet  # verständliche Meldung wurde gezeigt


def test_lade_firma_bei_verwaister_sperre_uebernimmt_nach_ja(qapp, tmp_path, monkeypatch):
    """AK3: Eine verwaiste Sperre wird nach Bestätigung übernommen, dann geladen."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    monkeypatch.setattr(
        firma_dialoge.sperre, "erwerbe_sperre", lambda p: SperrStatus.VERWAIST
    )
    uebernommen = []
    monkeypatch.setattr(
        firma_dialoge.sperre, "uebernimm_sperre", lambda p: uebernommen.append(p)
    )
    monkeypatch.setattr(
        firma_dialoge.QMessageBox,
        "question",
        lambda *a, **k: firma_dialoge.QMessageBox.Yes,
    )
    ergebnis = firma_dialoge.lade_firma(a)
    assert ergebnis is not None and ergebnis[0].eigene_firma.name == "Firma A"
    assert uebernommen == [a]


def test_closeevent_gibt_datei_sperre_frei(qapp, tmp_path, monkeypatch):
    """Beim Schließen wird die Sperre der aktiven Firma freigegeben (S-0073)."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    freigegeben = []
    monkeypatch.setattr(
        "eu_rechnung.ui.hauptfenster.sperre.gib_sperre_frei",
        lambda p: freigegeben.append(Path(p)),
    )
    fenster.close()
    assert Path(a) in freigegeben


# --- Beschädigte Datei beim Öffnen (AK1, 4T-0166) -----------------------------


def test_lade_firma_bei_beschaedigter_datei_meldet_und_gibt_sperre_frei(
    qapp, tmp_path, monkeypatch
):
    """AK1: Eine beschädigte Firma-Datei wird beim Öffnen nicht geladen.

    `lade_firma` erwirbt die Sperre der freien Datei, scheitert am defekten JSON, zeigt eine
    verständliche Meldung und gibt die eben erworbene Sperre wieder frei, statt abzustürzen
    oder still einen leeren Bestand zu liefern. Der Persistenz-Fehlerfall selbst ist auf
    Modul-Ebene geprüft (`test_persistence.test_lade_kaputtes_json`); hier zählt der Weg über
    die Oberfläche samt Sperr-Freigabe.
    """
    kaputt = tmp_path / "kaputt.scgr"
    kaputt.write_text("{ kein gueltiges JSON ", encoding="utf-8")
    freigegeben = []
    monkeypatch.setattr(
        firma_dialoge.sperre, "gib_sperre_frei", lambda p: freigegeben.append(Path(p))
    )
    gemeldet = []
    monkeypatch.setattr(
        firma_dialoge.QMessageBox, "warning", lambda *a, **k: gemeldet.append(True)
    )

    ergebnis = firma_dialoge.lade_firma(kaputt)

    assert ergebnis is None  # nicht geladen
    assert gemeldet  # verständliche Meldung gezeigt
    assert Path(kaputt) in freigegeben  # erworbene Sperre wieder freigegeben


# --- Aktive Firma schließen (4T-0176, S-0083) ---------------------------------


def test_schliessen_aktion_nur_bei_aktiver_firma(qapp, tmp_path):
    """AK1: Ohne aktive Firma ist der Menü-Eintrag inaktiv, mit aktiver Firma bedienbar."""
    leer = HauptFenster(konfig_pfad=tmp_path / "konfig.json")
    assert leer._schliessen_aktion.isEnabled() is False

    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    assert fenster._schliessen_aktion.isEnabled() is True


def test_schliessen_fuehrt_in_den_leerzustand(qapp, tmp_path):
    """AK2: Nach dem Schließen zeigt das Fenster die Leerfläche, die Reiter sind abgebaut."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)

    fenster._firma_schliessen()

    assert fenster._datenbestand is None
    assert fenster._stapel.currentWidget() is fenster._leer_hinweis
    assert fenster._tabs.count() == 0  # keine Maske lebt auf dem alten Bestand weiter
    assert fenster._reiter_widgets == {}
    assert fenster._schliessen_aktion.isEnabled() is False


def test_schliessen_gibt_die_datei_sperre_frei(qapp, tmp_path, monkeypatch):
    """AK3: Die Sperre wird freigegeben, damit die Datei sofort wieder öffenbar ist."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    freigegeben = []
    monkeypatch.setattr(
        "eu_rechnung.ui.hauptfenster.sperre.gib_sperre_frei",
        lambda p: freigegeben.append(Path(p)),
    )

    fenster._firma_schliessen()

    assert Path(a) in freigegeben
    assert fenster._gesperrter_pfad is None


def test_schliessen_laesst_die_firma_in_zuletzt_geoeffnet(qapp, tmp_path):
    """AK4: Die geschlossene Firma bleibt in der Liste und ist von dort wieder ladbar."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)

    fenster._firma_schliessen()

    assert [aktion.text() for aktion in fenster._zuletzt_menue.actions()] == ["a.scgr"]
    fenster._lade_firma_aus_pfad(a)
    assert fenster._datenbestand.eigene_firma.name == "Firma A"
    assert fenster._stapel.currentWidget() is fenster._tabs


def test_schliessen_fragt_bei_gespeichertem_stand_nicht(qapp, tmp_path, monkeypatch):
    """AK5: Ist alles gespeichert, wird ohne Rückfrage geschlossen."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    gefragt = []

    def _nicht_erwartet(self):
        gefragt.append(True)
        return True

    monkeypatch.setattr(HauptFenster, "_frage_ungespeichert_schliessen", _nicht_erwartet)

    fenster._firma_schliessen()

    assert not gefragt  # keine Warnung ohne Datenrisiko
    assert fenster._datenbestand is None


def test_schliessen_bricht_bei_ungespeichertem_stand_ab(qapp, tmp_path, monkeypatch):
    """AK6: Bei ungespeichertem Stand wird gefragt; „Abbrechen" lässt alles unverändert."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    fenster._auto_speicher._setze_zustand(True)  # fehlgeschlagenes Speichern nachgestellt
    monkeypatch.setattr(
        HauptFenster, "_frage_ungespeichert_schliessen", lambda self: False
    )

    fenster._firma_schliessen()

    assert fenster._datenbestand is not None  # Firma bleibt aktiv
    assert fenster._auto_speicher is not None
    assert fenster._gesperrter_pfad == Path(a)  # Sperre weiterhin gehalten
    assert fenster._stapel.currentWidget() is fenster._tabs


def test_schliessen_verwirft_ungespeicherten_stand_nach_bestaetigung(
    qapp, tmp_path, monkeypatch
):
    """AK6: Nach „Trotzdem schließen" wird trotz ungespeichertem Stand geschlossen."""
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    fenster._auto_speicher._setze_zustand(True)
    monkeypatch.setattr(
        HauptFenster, "_frage_ungespeichert_schliessen", lambda self: True
    )

    fenster._firma_schliessen()

    assert fenster._datenbestand is None
    assert fenster._stapel.currentWidget() is fenster._leer_hinweis


def test_schliessen_verhindert_den_autostart_beim_naechsten_start(qapp, tmp_path):
    """AK8: Nach dem Schließen startet die Anwendung leer, statt die Firma erneut zu laden.

    Der Durchtest zeigte den Fall: Schließen, beenden, neu starten — und die Firma war
    wieder da, weil der Start die Zuletzt-geöffnet-Liste auswertete. Maßgeblich ist jetzt
    der Vermerk der zuletzt aktiven Firma, den das Schließen löscht; die Firma bleibt in
    der Liste wählbar (AK4).
    """
    a = _firma_datei(tmp_path / "a.scgr", "Firma A")
    fenster = _fenster(tmp_path, a)
    assert ermittle_start_firma(fenster._konfig_pfad) is not None  # vorher: Autostart

    fenster._firma_schliessen()

    konfig = lade_konfiguration(fenster._konfig_pfad)
    assert konfig.zuletzt_aktiv is None
    assert [Path(p).name for p in konfig.zuletzt_geoeffnet] == ["a.scgr"]
    assert ermittle_start_firma(fenster._konfig_pfad) is None  # nachher: leerer Start


# --- Übergebene Firma-Datei beim Programmstart (4T-0185, S-0054) --------------


def test_uebergebene_firma_wird_geoeffnet(qapp, tmp_path):
    """AK1: Ein übergebener Pfad macht die Firma aktiv, über den gemeinsamen Ladeweg."""
    a = _firma_datei(tmp_path / "doppelklick.scgr", "Firma Doppelklick")
    fenster = HauptFenster(konfig_pfad=tmp_path / "konfig.json")
    assert fenster._datenbestand is None, "Vorbedingung: Leerzustand"

    fenster.oeffne_uebergebene_firma(a)

    assert fenster._datenbestand is not None
    assert fenster._datenbestand.eigene_firma.name == "Firma Doppelklick"
    assert fenster._daten_pfad == a
    assert a.name.replace(".scgr", "") in fenster.windowTitle()


def test_uebergebene_firma_pflegt_liste_und_autostart(qapp, tmp_path):
    """AK3: Sperre, Zuletzt-Liste und Autostart-Vermerk wie beim manuellen Öffnen."""
    a = _firma_datei(tmp_path / "doppelklick.scgr", "Firma Doppelklick")
    konfig_pfad = tmp_path / "konfig.json"
    fenster = HauptFenster(konfig_pfad=konfig_pfad)

    fenster.oeffne_uebergebene_firma(a)

    konfig = lade_konfiguration(konfig_pfad)
    assert konfig.zuletzt_aktiv is not None
    assert Path(konfig.zuletzt_aktiv) == a.resolve()
    assert [Path(p) for p in konfig.zuletzt_geoeffnet] == [a.resolve()]
    assert fenster._gesperrter_pfad == a


def test_uebergebene_datei_mit_fremder_endung_wird_abgewiesen(qapp, tmp_path, monkeypatch):
    """AK4: Eine fremde Datei wird verständlich abgelehnt, nicht am Schema zerbrochen."""
    fremd = tmp_path / "notizen.txt"
    fremd.write_text("kein Firma-Dokument", encoding="utf-8")
    gemeldet = []
    monkeypatch.setattr(
        hauptfenster_modul.QMessageBox, "warning", lambda *a, **k: gemeldet.append(a[1:3])
    )
    fenster = HauptFenster(konfig_pfad=tmp_path / "konfig.json")

    fenster.oeffne_uebergebene_firma(fremd)

    assert gemeldet, "die Ablehnung wird gemeldet"
    assert fenster._datenbestand is None, "das Fenster bleibt im Leerzustand"


def test_uebergebene_datei_nicht_vorhanden_meldet_der_ladeweg(qapp, tmp_path, monkeypatch):
    """AK4: Fehlt die Datei, meldet der gemeinsame Ladeweg; Leerzustand bleibt."""
    gemeldet = []
    monkeypatch.setattr(
        firma_dialoge.QMessageBox, "warning", lambda *a, **k: gemeldet.append(True)
    )
    fenster = HauptFenster(konfig_pfad=tmp_path / "konfig.json")

    fenster.oeffne_uebergebene_firma(tmp_path / "gibtsnicht.scgr")

    assert gemeldet
    assert fenster._datenbestand is None


def test_uebergebene_datei_bei_belegter_sperre_bleibt_leer(qapp, tmp_path, monkeypatch):
    """AK5: Eine in anderer Instanz belegte Datei verhält sich wie beim manuellen Öffnen."""
    a = _firma_datei(tmp_path / "doppelklick.scgr", "Firma Doppelklick")
    monkeypatch.setattr(
        firma_dialoge.sperre, "erwerbe_sperre", lambda p: SperrStatus.BELEGT
    )
    gemeldet = []
    monkeypatch.setattr(
        firma_dialoge.QMessageBox, "warning", lambda *a, **k: gemeldet.append(True)
    )
    fenster = HauptFenster(konfig_pfad=tmp_path / "konfig.json")

    fenster.oeffne_uebergebene_firma(a)

    assert gemeldet
    assert fenster._datenbestand is None
