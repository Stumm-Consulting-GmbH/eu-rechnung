"""Tests des UI-Sprach-Zustands (`ui.sprache`, S-0059), offscreen.

Die Oberfläche zieht ihre Texte aus demselben Katalog wie die Ausgabe, aber in der
UI-Sprache. Dieser Zustand ist prozessweit; die Tests stellen ihn nach jedem Fall wieder
her, damit sie sich nicht gegenseitig beeinflussen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from eu_rechnung.ui.sprache import (
    setze_ui_sprache,
    ui_kontext,
    ui_sprache,
    ui_text,
)


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    """Stellt nach jedem Test die Ausgangssprache wieder her (prozessweiter Zustand)."""
    vorher = ui_sprache()
    yield
    setze_ui_sprache(vorher)


def test_default_ist_deutsch():
    """Vor dem ersten Setzen gilt Deutsch, wie im Leerzustand ohne Firma."""
    assert ui_sprache() == "de"


def test_setzen_und_lesen():
    assert setze_ui_sprache("it") == "it"
    assert ui_sprache() == "it"


def test_unbekannte_sprache_wird_auf_deutsch_normiert():
    """Ein verfremdeter Wert in der Firma-Datei darf die Oberfläche nicht unbenutzbar machen."""
    assert setze_ui_sprache("kl") == "de"
    assert ui_sprache() == "de"


def test_none_ergibt_deutsch():
    """Ohne Startfirma gibt es keine UI-Sprache; dann gilt Deutsch (S-0059)."""
    assert setze_ui_sprache(None) == "de"


def test_ui_text_folgt_der_aktiven_sprache():
    setze_ui_sprache("de")
    assert ui_text("einstellungen.gruppe_sprache") == "Sprache"
    setze_ui_sprache("fr")
    assert ui_text("einstellungen.gruppe_sprache") == "Langue"


def test_ui_text_setzt_platzhalter_ein():
    setze_ui_sprache("en")
    assert ui_text("sichtteil.titel", nummer="2026-10001") == "Invoice 2026-10001"


def test_ui_kontext_formatiert_in_der_aktiven_sprache():
    from decimal import Decimal

    setze_ui_sprache("en")
    assert ui_kontext().geld(Decimal("1200")) == "1,200.00"
    setze_ui_sprache("de")
    assert ui_kontext().geld(Decimal("1200")) == "1.200,00"
