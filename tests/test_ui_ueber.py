"""Tests des Über-Dialogs (4T-0150, S-0077), offscreen.

Prüft die geforderten Angaben (Name, Zweck, Version, Herausgeber, Copyright,
Open-Source-Komponenten mit Lizenzen) und die Herkunft der Version aus der einen Quelle.

Der Test auf die Komponenten-Liste ist bewusst gegen `pyproject.toml` geführt und nicht
gegen eine Kopie der Erwartung: Er schlägt fehl, sobald eine Abhängigkeit dazukommt oder
verschwindet, ohne dass die Liste im Dialog mitgezogen wurde. Genau diese Drift wäre sonst
erst bei der Auslieferung aufgefallen, wo die Namensnennungspflichten greifen.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from eu_rechnung import COPYRIGHT_JAHR, HERAUSGEBER, PRODUKTNAME, __version__
from eu_rechnung.ui.sprache import setze_ui_sprache
from eu_rechnung.ui.ueber_dialog import _KOMPONENTEN, UeberDialog

WURZEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    """Der UI-Sprach-Zustand ist prozessweit; nach jedem Test zurückstellen."""
    yield
    setze_ui_sprache("de")


def _texte(dialog: UeberDialog) -> str:
    """Alle Beschriftungen des Dialogs als ein Text."""
    return "\n".join(label.text() for label in dialog.findChildren(QLabel))


def test_zeigt_name_und_zweck(qapp):
    """AK1: Anwendungsname und eine Kurzbeschreibung des Zwecks."""
    texte = _texte(UeberDialog())
    assert PRODUKTNAME in texte
    assert "EN 16931" in texte
    assert "XRechnung" in texte and "ZUGFeRD" in texte


def test_zeigt_die_programmversion(qapp):
    """AK2: Die Version, und zwar aus der einen Quelle."""
    assert __version__ in _texte(UeberDialog())


def test_zeigt_herausgeber_und_copyright(qapp):
    """AK3: Herausgeber und Copyright-Hinweis mit Jahr."""
    texte = _texte(UeberDialog())
    assert "Stumm-Consulting GmbH" in texte
    assert "Liestal" in texte
    assert f"© {COPYRIGHT_JAHR}" in texte
    assert HERAUSGEBER in texte


def test_zeigt_die_open_source_komponenten_mit_lizenzen(qapp):
    """AK4: Jede Komponente mit ihrer Lizenz, insbesondere die Apache-2.0-Attribution."""
    texte = _texte(UeberDialog())
    for name, lizenz in _KOMPONENTEN:
        assert name in texte, f"Komponente {name} fehlt im Dialog"
        assert lizenz in texte, f"Lizenz von {name} fehlt im Dialog"
    # Der in S-0077 ausdrücklich genannte Fall.
    assert "drafthorse — Apache-2.0" in texte


def test_komponentenliste_deckt_die_abhaengigkeiten_ab():
    """Die Liste im Dialog muss zu den Abhängigkeiten passen (Drift-Schutz).

    Ohne Qt: reiner Vergleich der Namen gegen `pyproject.toml`.
    """
    roh = tomllib.loads((WURZEL / "pyproject.toml").read_text(encoding="utf-8"))
    abhaengigkeiten = {
        # "factur-x==4.3" -> "factur-x"; "pypdf>=6.0" -> "pypdf"
        eintrag.split("==")[0].split(">=")[0].strip().lower()
        for eintrag in roh["project"]["dependencies"]
    }
    genannt = {name.split(" ")[0].lower() for name, _ in _KOMPONENTEN}
    assert genannt == abhaengigkeiten, (
        "Die Komponenten-Liste im Über-Dialog und die Abhängigkeiten in pyproject.toml "
        "sind auseinandergelaufen; auch Architektur.md mitziehen."
    )


def test_version_kommt_aus_einer_quelle():
    """`pyproject.toml` trägt keine eigene Version, sondern liest sie aus `__version__`."""
    roh = tomllib.loads((WURZEL / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in roh["project"], "Version doppelt gepflegt"
    assert "version" in roh["project"]["dynamic"]
    assert roh["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "eu_rechnung.__version__"
    }


def test_zweck_bricht_um_statt_den_dialog_zu_ziehen(qapp):
    """Der Zweck ist ein ganzer Satz und muss umbrechen.

    Ohne Wortumbruch meldet das Label die volle Satzbreite als Wunschgröße und zieht den
    Dialog in die Breite. Geprüft wird die Konfiguration, nicht die Pixelbreite: Die
    Testumgebung hat keine Schriften (`QFontDatabase.families()` ist leer) und rendert mit
    einem Ersatzmaß, das etwa doppelt so breit baut wie eine echte Schrift. Gemessene
    Breiten wären hier also wertlos; das Layout gehört am echten System geprüft.
    """
    dialog = UeberDialog()
    assert dialog.maximumWidth() == 520
    zweck = [label for label in dialog.findChildren(QLabel) if label.wordWrap()]
    assert len(zweck) == 1, "Genau der Zweck-Satz soll umbrechen"
    assert "EN 16931" in zweck[0].text()


def test_dialog_folgt_der_sprache(qapp):
    """AK6: Die Texte kommen beim Aufbau aus dem Katalog, nicht aus Konstanten."""
    setze_ui_sprache("fr")
    texte = _texte(UeberDialog())
    assert "Éditeur : Stumm-Consulting GmbH" in texte
    assert "Composants open source utilisés :" in texte
    # Produktname und Lizenzbezeichnungen sind Eigennamen und bleiben gleich.
    assert PRODUKTNAME in texte
    assert "MIT" in texte
    assert "Herausgeber" not in texte
