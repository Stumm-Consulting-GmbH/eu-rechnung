"""Tests des Sprachkatalogs (`eu_rechnung.texte`, S-0061).

Prüft die Auflösung je Sprache, den deutschen Rückfall (AK3), die Robustheit gegen
unbekannte Sprachwerte aus gespeicherten Daten und die Vollständigkeit der Sprachdateien.

Der Vollständigkeits-Test ist die automatische Absicherung des DoD-Kriteriums D5: Ein in
einer Sprache vergessener Schlüssel fällt hier auf und nicht erst beim Anwender, der dann
mitten in seiner Oberfläche einen deutschen Text sähe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eu_rechnung.texte import RUECKFALL, SPRACH_NAMEN, SPRACHEN, katalog, normierte_sprache, text

_SPRACHEN_ORDNER = (
    Path(__file__).resolve().parent.parent / "eu_rechnung" / "ressourcen" / "sprachen"
)


def test_jede_sprache_hat_eine_datei():
    for sprache in SPRACHEN:
        assert (_SPRACHEN_ORDNER / f"{sprache}.json").is_file()


def test_alle_sprachdateien_tragen_dieselben_schluessel():
    """D5-Absicherung: kein Schlüssel darf in einer der fünf Sprachen fehlen."""
    deutsch = set(katalog(RUECKFALL))
    assert deutsch, "die deutsche Sprachdatei ist leer"
    abweichungen = []
    for sprache in SPRACHEN:
        eigene = set(katalog(sprache))
        for fehlend in sorted(deutsch - eigene):
            abweichungen.append(f"{sprache}.json fehlt: {fehlend}")
        for ueberzaehlig in sorted(eigene - deutsch):
            abweichungen.append(f"{sprache}.json kennt unbekannten Schlüssel: {ueberzaehlig}")
    assert not abweichungen, "Sprachdateien weichen ab:\n" + "\n".join(abweichungen)


def test_sprachdateien_sind_gueltiges_json_ohne_leere_texte():
    """Kein Eintrag darf leer sein; `format.*` darf reines Leerzeichen sein.

    Die Ausnahme ist kein Schlupfloch, sondern ein echter Fall: Französisch trennt
    Tausender mit einem geschützten Leerzeichen (U+00A0). Für `strip()` ist das leer,
    fachlich ist es der korrekte Wert.
    """
    for sprache in SPRACHEN:
        daten = json.loads((_SPRACHEN_ORDNER / f"{sprache}.json").read_text(encoding="utf-8"))
        leere = [
            s
            for s, w in daten.items()
            if (str(w) == "" if s.startswith("format.") else not str(w).strip())
        ]
        assert not leere, f"{sprache}.json hat leere Texte: {leere}"


def test_text_liefert_die_zielsprache():
    assert text("sichtteil.rechnungsnummer", "de") == "Rechnungsnummer"
    assert text("sichtteil.rechnungsnummer", "en") == "Invoice number"
    assert text("sichtteil.rechnungsnummer", "fr") == "Numéro de facture"


def test_text_setzt_platzhalter_ein():
    assert text("sichtteil.titel", "de", nummer="2026-10001") == "Rechnung 2026-10001"
    assert text("sichtteil.titel", "es", nummer="2026-10001") == "Factura 2026-10001"


def test_fehlende_uebersetzung_faellt_auf_deutsch_zurueck(monkeypatch):
    """AK3: Fehlt ein einzelner Eintrag, erscheint der deutsche Text; nichts bricht."""
    unvollstaendig = dict(katalog("en"))
    del unvollstaendig["sichtteil.zahlbetrag"]
    monkeypatch.setattr(
        "eu_rechnung.texte.katalog",
        lambda sprache: unvollstaendig if sprache == "en" else katalog(sprache),
    )
    assert text("sichtteil.zahlbetrag", "en") == "Zahlbetrag"


def test_unbekannter_schluessel_wirft():
    """Ein Schlüssel, den auch Deutsch nicht kennt, ist ein Programmierfehler."""
    with pytest.raises(KeyError):
        text("sichtteil.gibt.es.nicht", "de")


@pytest.mark.parametrize(
    "eingabe, erwartet",
    [
        ("de", "de"),
        ("EN", "en"),
        ("  fr  ", "fr"),
        ("de-DE", "de"),  # BCP-47-artige Werte auf den Basiscode kürzen
        ("kl", "de"),  # unbekannte Sprache
        ("", "de"),
        (None, "de"),
    ],
)
def test_normierte_sprache(eingabe, erwartet):
    """Die Sprache stammt aus gespeicherten Daten und darf die Anwendung nie brechen."""
    assert normierte_sprache(eingabe) == erwartet


def test_text_mit_unbekannter_sprache_nutzt_deutsch():
    assert text("sichtteil.rechnungsnummer", "kl") == "Rechnungsnummer"


def test_sprachnamen_stehen_in_der_eigenen_sprache():
    """Ein Anwender muss seine Sprache auch in fremdsprachiger Oberfläche finden."""
    assert set(SPRACH_NAMEN) == set(SPRACHEN)
    assert SPRACH_NAMEN["it"] == "Italiano"
    assert SPRACH_NAMEN["fr"] == "Français"
