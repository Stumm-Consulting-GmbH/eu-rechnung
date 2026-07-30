"""App-Konfiguration außerhalb der Firma-Dateien: zuletzt geöffnete Firmen.

Hält die anwendungsweite Konfiguration in einer kleinen JSON-Datei, getrennt von
den Firma-Datenbeständen. Aktuell trägt sie die Liste der zuletzt geöffneten
Firma-Dateien (S-0071 AK4) für schnelles Laden. Die Konfiguration ist Komfort,
kein kritischer Datenbestand: Lese- und Schreibfehler führen nicht zu einem harten
Fehler, sondern zu einer leeren beziehungsweise unveränderten Liste, damit eine
defekte Konfig die Firma-Operationen nie blockiert.

Das Modul ist UI-frei; der Ablageort der Konfig-Datei wird als Pfad hereingereicht
(die plattformgerechte Ermittlung liegt in der Anwendungsschicht).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

#: Höchstzahl der Einträge in der Liste zuletzt geöffneter Firmen.
MAX_ZULETZT_GEOEFFNET = 10

_SCHEMA_VERSION = 1


@dataclass
class AppKonfiguration:
    """Anwendungsweite Konfiguration: zuletzt geöffnete Firmen und die zuletzt aktive."""

    zuletzt_geoeffnet: list[str] = field(default_factory=list)
    #: Firma, die zuletzt aktiv war, als Vorgabe für den nächsten Start. `None` heißt
    #: „keine Firma aktiv": so bleibt ein bewusstes Schließen (S-0083) über das
    #: Programm-Ende hinaus wirksam, während die Firma in der Liste oben stehen bleibt.
    zuletzt_aktiv: str | None = None


def lade_konfiguration(pfad: Path | str) -> AppKonfiguration:
    """Lädt die Konfiguration; bei fehlender oder defekter Datei eine leere.

    Die Konfiguration ist unkritisch: Jeder Lese- oder Strukturfehler ergibt eine
    leere `AppKonfiguration`, statt einen Fehler zu werfen.
    """
    pfad = Path(pfad)
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, json.JSONDecodeError):
        return AppKonfiguration()
    if not isinstance(daten, dict):
        return AppKonfiguration()
    liste = daten.get("zuletzt_geoeffnet", [])
    if not isinstance(liste, list):
        return AppKonfiguration()
    # Nur Strings übernehmen, defensiv gegen manuell verfremdete Dateien.
    zuletzt = [p for p in liste if isinstance(p, str)]
    # Ein fehlendes `zuletzt_aktiv` stammt aus einer Konfiguration von vor dem Schließen
    # (S-0083). Dort war die zuletzt geöffnete Firma zugleich die aktive; genau so wird
    # das Feld hergeleitet, statt solche Bestände unerwartet leer starten zu lassen. Ein
    # ausdrückliches `null` bedeutet dagegen „geschlossen" und bleibt es.
    if "zuletzt_aktiv" in daten:
        aktiv = daten["zuletzt_aktiv"]
        aktiv = aktiv if isinstance(aktiv, str) else None
    else:
        aktiv = zuletzt[0] if zuletzt else None
    return AppKonfiguration(zuletzt_geoeffnet=zuletzt, zuletzt_aktiv=aktiv)


def speichere_konfiguration(konfig: AppKonfiguration, pfad: Path | str) -> None:
    """Schreibt die Konfiguration atomar als JSON; Schreibfehler werden geschluckt.

    Ein fehlgeschlagenes Speichern der Komfort-Konfiguration darf die auslösende
    Firma-Operation nicht abbrechen, daher wird ein `OSError` hier bewusst nicht
    weitergereicht.
    """
    pfad = Path(pfad)
    daten = {
        "schema_version": _SCHEMA_VERSION,
        "zuletzt_geoeffnet": list(konfig.zuletzt_geoeffnet),
        "zuletzt_aktiv": konfig.zuletzt_aktiv,
    }
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=pfad.parent, prefix=pfad.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(daten, f, ensure_ascii=False, indent=2)
            os.replace(tmp_name, pfad)
        except BaseException:
            _entferne_leise(tmp_name)
            raise
    except OSError:
        pass  # Komfort-Konfig: Schreibfehler nicht eskalieren


def _entferne_leise(pfad: str) -> None:
    """Entfernt eine (temporäre) Datei, ohne bei Fehlern zu stören."""
    try:
        os.remove(pfad)
    except OSError:
        pass


def merke_zuletzt_geoeffnet(
    konfig: AppKonfiguration, firma_pfad: Path | str
) -> AppKonfiguration:
    """Setzt eine Firma-Datei an die Spitze der Zuletzt-geöffnet-Liste.

    Der Pfad wird absolut normiert, ein bereits vorhandener Eintrag (auf Windows
    auch bei abweichender Groß-/Kleinschreibung) zunächst entfernt und der Pfad
    vorne eingefügt; die Liste wird auf `MAX_ZULETZT_GEOEFFNET` gekappt. Gibt eine
    neue `AppKonfiguration` zurück.
    """
    neuer = os.path.abspath(str(firma_pfad))
    schluessel = os.path.normcase(neuer)
    behalten = [
        p
        for p in konfig.zuletzt_geoeffnet
        if os.path.normcase(os.path.abspath(p)) != schluessel
    ]
    neue_liste = [neuer, *behalten][:MAX_ZULETZT_GEOEFFNET]
    # Wer gemerkt wird, ist auch der aktive: Beide Aufrufer (Anlegen und Laden) machen
    # die Firma zugleich zur aktiven Firma der Instanz.
    return AppKonfiguration(zuletzt_geoeffnet=neue_liste, zuletzt_aktiv=neuer)


def vergiss_aktive_firma(konfig: AppKonfiguration) -> AppKonfiguration:
    """Vermerkt, dass keine Firma mehr aktiv ist (S-0083), ohne die Liste zu ändern.

    Nach dem bewussten Schließen soll die Anwendung auch beim nächsten Start leer
    öffnen; ohne diesen Vermerk zöge der Autostart die Firma sofort wieder herein und
    das Schließen wäre über das Programm-Ende hinaus wirkungslos. Die Firma bleibt in
    der Zuletzt-geöffnet-Liste, denn sie soll von dort mit einem Klick wieder ladbar
    sein (S-0083 AK4); nur der Autostart entfällt.
    """
    return AppKonfiguration(
        zuletzt_geoeffnet=list(konfig.zuletzt_geoeffnet), zuletzt_aktiv=None
    )


def existierende_zuletzt_geoeffnet(konfig: AppKonfiguration) -> list[Path]:
    """Liefert die zuletzt geöffneten Firma-Dateien, die noch existieren.

    Tote Pfade (verschoben, gelöscht) werden übersprungen, damit die Liste dem
    Anwender nur ladbare Firmen anbietet.
    """
    ergebnis: list[Path] = []
    for p in konfig.zuletzt_geoeffnet:
        pfad = Path(p)
        if pfad.is_file():
            ergebnis.append(pfad)
    return ergebnis
