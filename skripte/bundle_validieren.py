"""Norm-Validierung der Ausgaben des Bundle-Selbsttests (4T-0183, S-0053).

Zweiter Schritt des Nachweises: `bundle_selbsttest.py` erzeugt im gefrorenen Bundle
XRechnung und ZUGFeRD, dieses Skript prüft sie gegen die Goldstandard-Werkzeuge. Es läuft
bewusst **außerhalb** des Bundles in der Entwicklungsumgebung, denn KoSIT und veraPDF sind
Java-Werkzeuge; die Anwendung selbst ruft zur Laufzeit keinen externen Validator (E-005).

Damit ist der Nachweis mit zwei Befehlen wiederholbar, statt bei jedem Build erneut von
Hand zu laufen:

    .\\dist\\bundle-selbsttest\\bundle-selbsttest.exe Daten\\bundle-selbsttest
    .\\.venv\\Scripts\\python.exe skripte\\bundle_validieren.py Daten\\bundle-selbsttest

Voraussetzung sind Java und die projektlokalen Werkzeuge unter `werkzeuge/` (Beschaffung
siehe Architektur). Rückgabe 0, wenn alle Prüfer zustimmen, sonst 1.
"""

from __future__ import annotations

import sys
from pathlib import Path

from eu_rechnung.export.validation import (
    KositKonfig,
    VeraPdfKonfig,
    pruefe_kosit,
    pruefe_verapdf,
    pruefe_xsd,
)

_WERKZEUGE = Path(__file__).resolve().parent.parent / "werkzeuge"


def main() -> int:
    ordner = Path(sys.argv[1] if len(sys.argv) > 1 else "Daten/bundle-selbsttest").resolve()
    xmls = sorted(ordner.rglob("*.xml"))
    pdfs = sorted(ordner.rglob("*.pdf"))
    if not xmls or not pdfs:
        print(f"Keine Ausgabedateien unter {ordner} gefunden; erst den Selbsttest laufen lassen.")
        return 1

    kosit = KositKonfig(
        validator_jar=_WERKZEUGE / "kosit" / "validator-1.6.2-standalone.jar",
        szenarien=_WERKZEUGE / "kosit" / "config" / "scenarios.xml",
        repository=_WERKZEUGE / "kosit" / "config",
    )
    verapdf = VeraPdfKonfig(verapdf=_WERKZEUGE / "verapdf" / "verapdf.bat")

    xml, pdf = xmls[0].read_bytes(), pdfs[0].read_bytes()
    print(f"XRechnung: {xmls[0].name}\nZUGFeRD:   {pdfs[0].name}\n")

    ergebnisse = [
        pruefe_xsd(xml),
        pruefe_kosit(xml, kosit),
        pruefe_verapdf(pdf, verapdf),
    ]
    for ergebnis in ergebnisse:
        marke = "OK   " if ergebnis.gueltig else "FEHLT"
        print(f"[{marke}] {ergebnis.pruefer}")
        for befund in ergebnis.befunde:
            print(f"        - {befund}")

    if all(e.gueltig for e in ergebnisse):
        print("\nAlle Prüfer bestätigen die Ausgaben aus dem Bundle.")
        return 0
    print("\nMindestens ein Prüfer hat die Ausgabe zurückgewiesen.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
