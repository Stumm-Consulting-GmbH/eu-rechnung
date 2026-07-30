"""Selbsttest der gebündelten Assets im gefrorenen Zustand (4T-0183, S-0053).

**Warum es dieses Programm gibt.** Ob eine Datei im Bundle *liegt*, ist noch kein Beleg,
dass die Anwendung sie zur Laufzeit *findet*. Für PDF/A hängt daran alles: Ohne das
sRGB-ICC-Profil fehlt der OutputIntent, ohne die eingebettete Schrift die
Schrifteinbettung, und beides macht das Dokument ungültig. Der Fehler wäre besonders
tückisch, weil die Anwendung normal startet und erst beim Erzeugen einer Rechnung
scheitert.

Dieses Programm läuft dieselbe Kette wie die Oberfläche, aber ohne Oberfläche: Seed-Bestand,
Rechnung vorbelegen, anlegen, XRechnung und ZUGFeRD erzeugen. Paketiert mit derselben
Build-Konfiguration wie die Anwendung (`skripte/build_gemeinsam.py`) prüft es damit die
Asset-Auflösung unter Auslieferungsbedingungen: keine Python-Umgebung, keine
Projektdateien, Ressourcen nur aus dem Bundle.

**Grenze der Aussage:** Es ist ein eigenes Artefakt, nicht die ausgelieferte .exe, und es
bedient keine Oberfläche. Der Durchlauf auf einem System ohne Python mit der echten
Anwendung bleibt davon unberührt (4T-0184).

Aufruf (Zielverzeichnis für die Ergebnisse als erstes Argument):

    .\\.venv\\Scripts\\python.exe skripte\\bundle_selbsttest.py Daten\\bundle-selbsttest

Gearbeitet wird ausschließlich im Zielverzeichnis; der Datenbestand des Anwenders wird
nicht angefasst. Rückgabe 0 bei Erfolg, 1 bei jedem Fehlschlag.
"""

from __future__ import annotations

import importlib.resources
import sys
import traceback
from decimal import Decimal
from pathlib import Path

_BEFUNDE: list[str] = []


def _pruefe(bezeichnung: str, bedingung: bool, zusatz: str = "") -> None:
    """Hält ein Prüfergebnis fest und meldet es sofort auf der Konsole."""
    marke = "OK   " if bedingung else "FEHLT"
    print(f"[{marke}] {bezeichnung}{f' — {zusatz}' if zusatz else ''}")
    if not bedingung:
        _BEFUNDE.append(bezeichnung)


def pruefe_ressourcen() -> None:
    """Die drei Auflösungswege einzeln, damit ein Fehlschlag benennbar bleibt."""
    from eu_rechnung.texte import SPRACHEN, katalog, text

    # 1. Sprachdateien im eigenen Paket. Geprüft wird der geladene Katalog, nicht ein
    #    bestimmter Schlüssel: Der Selbsttest soll die Auflösung der Datei belegen und
    #    nicht bei jeder Umbenennung eines Textes fehlschlagen. Die Stichprobe nimmt
    #    deshalb den ersten Schlüssel des deutschen Katalogs; dass jeder Schlüssel in
    #    allen fünf Sprachen steht, erzwingt bereits `tests/test_texte.py`.
    probe = next(iter(katalog("de")), None)
    for sprache in SPRACHEN:
        try:
            eintraege = katalog(sprache)
            beschriftung = text(probe, sprache) if probe else ""
        except Exception as fehler:  # noqa: BLE001 — Befund statt Abbruch
            _pruefe(f"Sprachkatalog {sprache}", False, repr(fehler))
        else:
            _pruefe(
                f"Sprachkatalog {sprache}",
                bool(eintraege) and bool(beschriftung),
                f"{len(eintraege)} Texte, Probe „{probe}“ = „{beschriftung}“",
            )

    # 2. sRGB-ICC-Profil im eigenen Paket (PDF/A-OutputIntent, E-007).
    try:
        icc = (
            importlib.resources.files("eu_rechnung")
            .joinpath("ressourcen", "sRGB2014.icc")
            .read_bytes()
        )
    except Exception as fehler:  # noqa: BLE001
        _pruefe("sRGB-ICC-Profil", False, repr(fehler))
    else:
        _pruefe("sRGB-ICC-Profil", len(icc) > 0, f"{len(icc)} Bytes")

    # 3. Sichtteil-Schrift im **Fremdpaket** ReportLab: der gefährdete Weg, weil er nicht
    #    über `importlib.resources` des eigenen Pakets läuft.
    try:
        import os

        import reportlab

        ordner = Path(os.path.dirname(reportlab.__file__)) / "fonts"
        vorhanden = [n for n in ("Vera.ttf", "VeraBd.ttf") if (ordner / n).is_file()]
    except Exception as fehler:  # noqa: BLE001
        _pruefe("Sichtteil-Schrift (Vera)", False, repr(fehler))
    else:
        _pruefe("Sichtteil-Schrift (Vera)", len(vorhanden) == 2, ", ".join(vorhanden))

    # 4. Programm-Icon: gehört nicht zu S-0053, wird aber über denselben Weg aufgelöst.
    try:
        ico = (
            importlib.resources.files("eu_rechnung")
            .joinpath("ressourcen", "icon.ico")
            .read_bytes()
        )
    except Exception as fehler:  # noqa: BLE001
        _pruefe("Programm-Icon", False, repr(fehler))
    else:
        _pruefe("Programm-Icon", len(ico) > 0, f"{len(ico)} Bytes")


def erzeuge_ausgaben(ziel: Path) -> list[Path]:
    """Läuft die Erzeugungskette der Oberfläche nachgebildet, über die Service-Schicht.

    Bewusst nicht direkt über `export`: Geprüft werden soll der Weg, den die Anwendung
    nimmt, samt Pflichtprüfung, Ablageschema und Statusfortschreibung.
    """
    from eu_rechnung.services import (
        Format,
        berechne_gesamtpreis,
        erstelle_ausgaben,
        erzeuge_seed,
        lege_rechnung_an,
        vorbelege_rechnung,
    )

    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung)

    # Die Vorbelegung setzt Menge 0 und Gesamtpreis 0 (S-0029); für eine ausgabefähige
    # Rechnung braucht es Mengen. Der Gesamtpreis wird über dieselbe Service-Funktion
    # nachgezogen, die die Maske nutzt: Eine Menge ohne passenden Gesamtpreis verletzt
    # die EN-16931-Rechenregel für die Positionssumme, und das fiele erst im Validator
    # auf.
    for lauf, position in enumerate(rechnung.positionen, start=1):
        position.menge = Decimal(lauf)
        position.gesamtpreis = berechne_gesamtpreis(position.menge, position.einzelpreis)

    # Der Datenbestand landet im Zielverzeichnis, nicht am Standardort: Ein Selbsttest
    # darf den Bestand des Anwenders nicht anfassen.
    lege_rechnung_an(bestand, bestellung, rechnung, pfad=ziel / "selbsttest.scgr")

    ergebnis = erstelle_ausgaben(
        rechnung,
        bestellung.bestellnummer,
        bestellung.waehrung,
        {Format.XRECHNUNG, Format.ZUGFERD},
        ausgabe_verzeichnis=ziel,
    )
    for befund in ergebnis.pflicht_befunde:
        _BEFUNDE.append(f"Pflichtangabe fehlt: {befund}")
    if ergebnis.fehler is not None:
        _BEFUNDE.append(f"Erzeugungsfehler: {ergebnis.fehler}")

    _pruefe("XRechnung und ZUGFeRD erzeugt", len(ergebnis.erzeugte_dateien) == 2,
            ", ".join(p.name for p in ergebnis.erzeugte_dateien))
    return ergebnis.erzeugte_dateien


def main() -> int:
    ziel = Path(sys.argv[1] if len(sys.argv) > 1 else "bundle-selbsttest").resolve()
    ziel.mkdir(parents=True, exist_ok=True)
    gefroren = getattr(sys, "frozen", False)
    print(f"Bundle-Selbsttest — {'gefrorenes Bundle' if gefroren else 'Python-Umgebung'}")
    print(f"Zielverzeichnis: {ziel}\n")

    try:
        pruefe_ressourcen()
        print()
        dateien = erzeuge_ausgaben(ziel)
    except Exception:  # noqa: BLE001 — jeder Fehlschlag ist ein Befund, kein Absturz
        traceback.print_exc()
        _BEFUNDE.append("Abbruch mit Ausnahme")
        dateien = []

    print()
    for datei in dateien:
        print(f"  {datei} ({datei.stat().st_size} Bytes)")
    if _BEFUNDE:
        print(f"\nFEHLGESCHLAGEN, {len(_BEFUNDE)} Befund(e):")
        for befund in _BEFUNDE:
            print(f"  - {befund}")
        return 1
    print("\nAlle Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
