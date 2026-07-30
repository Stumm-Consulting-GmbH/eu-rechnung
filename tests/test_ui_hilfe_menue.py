"""Tests des Hilfe-Menüs und des F1-Zugangs (4T-0149, S-0076), offscreen.

Prüft den **Zugang**, nicht die Inhalte: dass die Menüleiste neben „Datei" ein Menü
„Hilfe" mit den beiden Einträgen trägt, dass F1 die Prozesshilfe unabhängig vom Fokus
öffnet und dass beides auch ohne aktive Firma bedienbar ist. Die beiden Dialoge sind in
diesem Stand noch Gerüste (Inhalt in 4T-0150 und 4T-0151); die Tests prüfen deshalb, dass
der richtige Dialog erzeugt und geöffnet wird, nicht was darin steht.

Die Dialoge werden nicht wirklich angezeigt: `exec` ist gepatcht, sonst blockierte der
Test auf einem modalen Fenster.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from eu_rechnung.services import erzeuge_seed
from eu_rechnung.ui import hauptfenster as hauptfenster_modul
from eu_rechnung.ui.hauptfenster import HauptFenster
from eu_rechnung.ui.hilfe_dialog import HilfeDialog
from eu_rechnung.ui.sprache import setze_ui_sprache
from eu_rechnung.ui.ueber_dialog import UeberDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    """Der UI-Sprach-Zustand ist prozessweit; nach jedem Test zurückstellen."""
    yield
    setze_ui_sprache("de")


def _menue_titel(fenster: HauptFenster) -> list[str]:
    """Die Titel der Menüs der Menüleiste, in ihrer Reihenfolge."""
    return [aktion.text() for aktion in fenster.menuBar().actions()]


def _fange_dialog(monkeypatch, klasse) -> list:
    """Ersetzt `exec` der Dialog-Klasse und sammelt die geöffneten Instanzen."""
    geoeffnet: list = []
    monkeypatch.setattr(klasse, "exec", lambda self: geoeffnet.append(self))
    return geoeffnet


def test_menueleiste_zeigt_datei_und_hilfe(qapp):
    """AK1: Neben dem bestehenden Menü „Datei" steht das Menü „Hilfe"."""
    fenster = HauptFenster(erzeuge_seed())
    assert _menue_titel(fenster) == ["&Datei", "&Hilfe"]


def test_hilfe_menue_hat_beide_eintraege_mit_kuerzel(qapp):
    """AK2: Die Einträge „Hilfe" (Kürzel F1, sichtbar) und „Über…"."""
    fenster = HauptFenster(erzeuge_seed())
    eintraege = [aktion.text() for aktion in fenster._hilfe_menue.actions()]
    assert eintraege == ["Hilfe", "Über…"]
    # Qt zeigt das Kürzel einer Aktion im Menü an; gesetzt ist es damit auch sichtbar.
    assert fenster._hilfe_aktion.shortcut() == QKeySequence(Qt.Key_F1)
    assert fenster._hilfe_aktion.shortcut().toString() == "F1"


def test_f1_oeffnet_die_hilfe_aus_einem_eingabefeld(qapp, monkeypatch):
    """AK3: F1 greift unabhängig vom Fokus.

    Der eigentliche Nachweis der Anforderung, und zwar mit einem echten Tastendruck: Der
    Fokus liegt auf einem Eingabefeld tief in einem Reiter, nicht auf dem Fenster. Ein an
    ein Widget gebundenes Kürzel bliebe hier wirkungslos.
    """
    fenster = HauptFenster(erzeuge_seed())
    hilfen = _fange_dialog(monkeypatch, HilfeDialog)
    fenster.show()
    QTest.qWaitForWindowExposed(fenster)
    fenster.activateWindow()
    try:
        felder = fenster.findChildren(QLineEdit)
        assert felder, "Erwartet: Eingabefelder in den Reitern"
        felder[0].setFocus()
        assert felder[0].hasFocus()

        QTest.keyClick(fenster, Qt.Key_F1)
        assert len(hilfen) == 1 and isinstance(hilfen[0], HilfeDialog)
    finally:
        fenster.close()


def test_f1_haengt_am_fenster_nicht_am_menue(qapp):
    """Absicherung der Mechanik hinter AK3: Kontext und Registrierung.

    Beides ist nötig: `WindowShortcut` lässt das Kürzel im ganzen Fenster greifen, und
    ohne die Registrierung am Fenster griffe es erst, nachdem das Menü einmal geöffnet
    wurde.
    """
    fenster = HauptFenster(erzeuge_seed())
    assert fenster._hilfe_aktion.shortcutContext() == Qt.WindowShortcut
    assert fenster._hilfe_aktion in fenster.actions()


def test_menue_eintraege_oeffnen_ihre_dialoge(qapp, monkeypatch):
    """AK4: „Hilfe" öffnet die Prozesshilfe, „Über…" den Über-Dialog."""
    fenster = HauptFenster(erzeuge_seed())
    hilfen = _fange_dialog(monkeypatch, HilfeDialog)
    ueber = _fange_dialog(monkeypatch, UeberDialog)

    fenster._hilfe_aktion.trigger()
    assert len(hilfen) == 1 and isinstance(hilfen[0], HilfeDialog)
    assert ueber == []

    fenster._ueber_aktion.trigger()
    assert len(ueber) == 1 and isinstance(ueber[0], UeberDialog)
    assert len(hilfen) == 1


def test_hilfe_menue_ist_ohne_aktive_firma_bedienbar(qapp, monkeypatch):
    """AK5: Menü und beide Einträge sind auch im Leerzustand da und lösen aus.

    Der wichtigste Fall der Story: Die Prozesshilfe erklärt gerade das Anlegen der
    ersten Firma und muss deshalb vor der ersten Firma erreichbar sein.
    """
    fenster = HauptFenster()
    assert fenster._tabs.count() == 0  # tatsächlich Leerzustand
    assert "&Hilfe" in _menue_titel(fenster)
    assert fenster._hilfe_aktion.isEnabled()
    assert fenster._ueber_aktion.isEnabled()

    hilfen = _fange_dialog(monkeypatch, HilfeDialog)
    fenster._hilfe_aktion.trigger()
    assert len(hilfen) == 1


def test_hilfe_menue_folgt_der_sprache(qapp):
    """AK6: Menü, Einträge und Dialog-Titel kommen aus dem Katalog, nicht aus
    Konstanten; sie werden beim Aufbau geholt."""
    setze_ui_sprache("es")
    fenster = HauptFenster(erzeuge_seed())
    assert _menue_titel(fenster) == ["&Archivo", "A&yuda"]
    eintraege = [aktion.text() for aktion in fenster._hilfe_menue.actions()]
    assert eintraege == ["Ayuda", "Acerca de…"]
    assert HilfeDialog().windowTitle() == "Ayuda"
    assert UeberDialog().windowTitle() == "Acerca de"


def test_mnemonics_der_menues_kollidieren_nicht(qapp):
    """Die Tastatur-Kürzel der Menütitel müssen sich je Sprache unterscheiden.

    Im Spanischen belegt „&Archivo" das A, deshalb trägt die Hilfe dort „A&yuda".
    """
    for sprache in ("de", "en", "it", "fr", "es"):
        setze_ui_sprache(sprache)
        fenster = HauptFenster(erzeuge_seed())
        buchstaben = [
            titel[titel.index("&") + 1].upper()
            for titel in _menue_titel(fenster)
            if "&" in titel
        ]
        assert len(buchstaben) == len(set(buchstaben)), f"Mnemonic-Kollision in {sprache}"
