"""Repository für den Datenbestand: Laden und Speichern als eine lokale
JSON-Datei.

Speichern serialisiert den Datenbestand und schreibt UTF-8 mit echten Umlauten
und Einrückung. Laden validiert zunächst gegen das JSON-Schema (verständliche
Fehlermeldung bei Struktur- oder Versionsabweichung) und rekonstruiert dann
die Domänenobjekte.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import jsonschema

from eu_rechnung.domain import Datenbestand
from eu_rechnung.persistence.schema import DATENBESTAND_SCHEMA
from eu_rechnung.persistence.serialisierung import von_json, zu_json

# Datendatei im git-ignorierten Daten/-Ordner (sensible Daten, nicht ins Repo).
STANDARD_PFAD = Path("Daten") / "daten.json"


class PersistenzFehler(Exception):
    """Fehler beim Laden oder Speichern des Datenbestands."""


def speichere(datenbestand: Datenbestand, pfad: Path | str = STANDARD_PFAD) -> None:
    """Serialisiert den Datenbestand und schreibt ihn atomar als JSON-Datei.

    Es wird zuerst vollständig in eine temporäre Datei im Zielordner geschrieben und
    diese dann per `os.replace` atomar über die Zieldatei geschoben; so ist die
    Datendatei zu keinem Zeitpunkt halb geschrieben, und ein Abbruch während des
    Speicherns lässt den letzten vollständigen Stand intakt (S-0072). Schlägt das
    Schreiben fehl (Datei gesperrt, Datenträger voll), wird `PersistenzFehler`
    geworfen und die vorhandene Datei bleibt unverändert.
    """
    pfad = Path(pfad)
    daten = zu_json(datenbestand)
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        # Temporäre Datei im Zielordner, damit os.replace atomar bleibt (ein
        # dateisystemübergreifendes Ersetzen wäre es nicht).
        fd, tmp_name = tempfile.mkstemp(
            dir=pfad.parent, prefix=pfad.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(daten, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, pfad)
        except BaseException:
            # Bei jedem Fehler die temporäre Datei aufräumen; das Ziel bleibt intakt.
            _entferne_leise(tmp_name)
            raise
    except OSError as fehler:
        raise PersistenzFehler(
            f"Datendatei konnte nicht gespeichert werden: {fehler}"
        ) from fehler


def _entferne_leise(pfad: str) -> None:
    """Entfernt eine (temporäre) Datei, ohne bei Fehlern zu stören."""
    try:
        os.remove(pfad)
    except OSError:
        pass


def lade(pfad: Path | str = STANDARD_PFAD) -> Datenbestand:
    """Lädt die JSON-Datei, validiert die Struktur und baut den Datenbestand."""
    pfad = Path(pfad)
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise PersistenzFehler(f"Datendatei konnte nicht gelesen werden: {e}") from e

    try:
        jsonschema.validate(daten, DATENBESTAND_SCHEMA)
    except jsonschema.ValidationError as e:
        raise PersistenzFehler(
            f"Datendatei entspricht nicht dem erwarteten Schema: {e.message}"
        ) from e

    return von_json(Datenbestand, daten)
