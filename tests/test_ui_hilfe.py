"""Tests der F1-Prozesshilfe (4T-0151, S-0078), offscreen.

Prüft den Inhalt gegen die Anforderung: die sechs Stufen in ihrer Reihenfolge, je Tätigkeit
und Ergebnis, die Einleitung, die beiden Rahmenteile (Einstellungen, Rechnungsübersicht) und
den Empfehlungs-Vermerk.

Zwei Tests sichern ab, was die Story ausdrücklich **nicht** will: dass die Hilfe zur
Funktionsbeschreibung auswächst (AK5) und dass die Rahmenteile zu Stufen werden (AK7/AK8).
Beides würde sonst schleichend passieren, ohne dass ein Test es merkt.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from eu_rechnung.texte import SPRACHEN, katalog
from eu_rechnung.ui.hilfe_dialog import _STUFEN, HilfeDialog
from eu_rechnung.ui.sprache import setze_ui_sprache


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    """Der UI-Sprach-Zustand ist prozessweit; nach jedem Test zurückstellen."""
    yield
    setze_ui_sprache("de")


def _absaetze(dialog: HilfeDialog) -> list[str]:
    return [label.text() for label in dialog.findChildren(QLabel)]


def test_zeigt_die_stufen_in_ihrer_reihenfolge(qapp):
    """AK1: Der Ablauf als geordnete Abfolge, Firma zuerst, Erstellen zuletzt."""
    absaetze = _absaetze(HilfeDialog())
    titel = [a for a in absaetze if a[:2] in {f"{n}." for n in range(1, 7)}]
    assert titel == [
        "1. Eigene Firma anlegen",
        "2. Artikel anlegen",
        "3. Kunden anlegen",
        "4. Bestellung zum Kunden anlegen",
        "5. Rechnung zur Bestellung erfassen",
        "6. Rechnung erstellen",
    ]


def test_nennt_je_stufe_taetigkeit_und_ergebnis(qapp):
    """AK2: Jede Stufe sagt, was zu tun ist und was dabei herauskommt."""
    text = "\n".join(_absaetze(HilfeDialog()))
    assert text.count("Ergebnis:") == len(_STUFEN)
    assert "Artikelstamm" in text  # Ergebnis der Artikel-Stufe
    assert "EN 16931" in text  # Ergebnis der letzten Stufe


def test_zeigt_einleitung_und_empfehlung(qapp):
    """AK3 und AK4: Der Ablauf baut aufeinander auf und ist eine Empfehlung."""
    text = "\n".join(_absaetze(HilfeDialog()))
    assert "aufeinander aufbauenden Ablauf" in text
    assert "Empfehlung" in text
    assert "keine vom Programm erzwungene Reihenfolge" in text


def test_rahmt_den_ablauf_mit_einstellungen_und_uebersicht(qapp):
    """AK7 und AK8: Beide Bereiche sind genannt, aber nicht als Stufen.

    Sie stehen bewusst außerhalb der Nummerierung: Die Einstellungen sind kein erster
    Schritt (es gibt Vorbelegungen), und nach der fertigen Rechnung ist nichts mehr zu tun.
    """
    absaetze = _absaetze(HilfeDialog())
    text = "\n".join(absaetze)
    assert "Einstellungen" in text
    assert "keine Stufe des Ablaufs" in text
    assert "Rechnungsübersicht" in text

    nummeriert = [a for a in absaetze if a[:2] in {f"{n}." for n in range(1, 9)}]
    assert len(nummeriert) == 6, "Nur der Ablauf ist nummeriert, die Rahmenteile nicht"


def test_bleibt_prozessorientiert(qapp):
    """AK5: Keine Detail-Funktionsbeschreibung der Masken.

    Ein grober, aber wirksamer Wächter: Die Hilfe darf nicht über Felder, Knöpfe oder
    Spalten reden. Schlägt der Test an, ist entweder ein Detail hineingerutscht oder die
    Anforderung wurde bewusst geändert; dann gehört die Story zuerst angefasst.
    """
    text = "\n".join(_absaetze(HilfeDialog())).lower()
    for detailwort in ("schaltfläche", "knopf", "spalte", "eingabefeld", "häkchen", "pflichtfeld"):
        assert detailwort not in text, f"Die Hilfe beschreibt Details: {detailwort!r}"


def test_texte_liegen_in_allen_sprachen_vor():
    """AK7 der Task-Sicht: Die Hilfe-Gruppe ist in allen fünf Sprachen vollständig.

    Ohne Qt: reiner Katalog-Vergleich.
    """
    erwartet = {"hilfe.titel", "hilfe.einleitung", "hilfe.vorgaben", "hilfe.uebersicht",
                "hilfe.empfehlung"}
    for stufe in _STUFEN:
        erwartet |= {f"hilfe.stufe_{stufe}_titel", f"hilfe.stufe_{stufe}_text"}
    for sprache in SPRACHEN:
        vorhanden = {k for k in katalog(sprache) if k.startswith("hilfe.")}
        assert vorhanden == erwartet, f"Hilfe-Texte unvollständig in {sprache}"


def test_hilfe_folgt_der_sprache(qapp):
    """Die Texte kommen beim Aufbau aus dem Katalog, nicht aus Konstanten."""
    setze_ui_sprache("it")
    text = "\n".join(_absaetze(HilfeDialog()))
    assert "1. Creare la propria azienda" in text
    assert "6. Generare la fattura" in text
    assert "raccomandazione" in text
    assert "Eigene Firma anlegen" not in text
