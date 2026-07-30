"""Tests des automatischen Speicherns (4T-0077), offscreen.

Prüft den `AutoSpeicher`-Dienst: erfolgreiches Speichern setzt den Zustand auf
gespeichert, ein Schreibfehler löst den Wiederholen-Dialog aus und meldet den
ungespeicherten Zustand über das Signal; das Hauptfenster kennzeichnet den Zustand
im Fenstertitel (AK4). Der Wiederholen-Dialog wird gemockt, statt ihn anzuzeigen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import eu_rechnung.ui.auto_speicher as auto_modul
from eu_rechnung.persistence import PersistenzFehler
from eu_rechnung.services import erzeuge_seed
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.hauptfenster import HauptFenster


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_speichern_erfolg_setzt_zustand_und_schreibt(qapp, tmp_path):
    auto = AutoSpeicher(erzeuge_seed(), tmp_path / "daten.json")
    assert auto.speichere_jetzt() is True
    assert auto.ungespeichert is False
    assert (tmp_path / "daten.json").exists()


def test_schreibfehler_mit_abbruch_meldet_ungespeichert(qapp, tmp_path, monkeypatch):
    auto = AutoSpeicher(erzeuge_seed(), tmp_path / "daten.json")
    zustaende: list[bool] = []
    auto.ungespeichert_geaendert.connect(zustaende.append)

    def kaputt(*a, **k):
        raise PersistenzFehler("Datei gesperrt")

    monkeypatch.setattr(auto_modul, "speichere", kaputt)
    monkeypatch.setattr(AutoSpeicher, "_frage_wiederholen", lambda self, p, f: False)

    assert auto.speichere_jetzt() is False
    assert auto.ungespeichert is True
    assert zustaende == [True]  # genau ein Wechsel auf ungespeichert


def test_schreibfehler_dann_wiederholen_erfolgreich(qapp, tmp_path, monkeypatch):
    auto = AutoSpeicher(erzeuge_seed(), tmp_path / "daten.json")
    echt = auto_modul.speichere
    aufrufe = {"n": 0}

    def erst_fehler(datenbestand, pfad):
        aufrufe["n"] += 1
        if aufrufe["n"] == 1:
            raise PersistenzFehler("temporaer gesperrt")
        echt(datenbestand, pfad)

    monkeypatch.setattr(auto_modul, "speichere", erst_fehler)
    monkeypatch.setattr(AutoSpeicher, "_frage_wiederholen", lambda self, p, f: True)

    assert auto.speichere_jetzt() is True
    assert auto.ungespeichert is False
    assert aufrufe["n"] == 2  # erst Fehler, dann erfolgreicher Retry
    assert (tmp_path / "daten.json").exists()


def test_hauptfenster_titel_kennzeichnet_ungespeichert(qapp, tmp_path):
    fenster = HauptFenster(erzeuge_seed(), daten_pfad=tmp_path / "daten.json")
    assert "nicht gespeichert" not in fenster.windowTitle()
    fenster._auto_speicher._setze_zustand(True)
    assert "nicht gespeichert" in fenster.windowTitle()
    fenster._auto_speicher._setze_zustand(False)
    assert "nicht gespeichert" not in fenster.windowTitle()
