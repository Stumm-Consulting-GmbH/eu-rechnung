"""Validierung der erzeugten Ausgaben gegen die Norm.

Bietet eine einheitliche Ergebnisstruktur, eine eingebaute (Java-freie)
XSD-Prüfung und optional zuschaltbare Wrapper für KoSIT (XRechnung/EN 16931)
und veraPDF (PDF/A-3). Die Tool-Pfade kommen als Konfiguration herein, damit
die `export`-Schicht UI-unabhängig und testbar bleibt (kein Hardcoding).

Die Schematron-/Geschäftsregel-Prüfung läuft ausschließlich über KoSIT, nicht
über das factur-x-Schematron: Letzteres lehnt die XRechnung-CIUS-Guideline-ID
ab (E-008). Die eingebaute Prüfung beschränkt sich daher auf XSD.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from facturx import xml_check_xsd

# Zeitlimit (Sekunden) für die externen Java-Werkzeuge.
_TIMEOUT = 180


@dataclass
class ValidierungsErgebnis:
    """Einheitliches Urteil eines Prüfers, von UI und Tests gemeinsam genutzt."""

    gueltig: bool
    pruefer: str
    befunde: list[str] = field(default_factory=list)


# --- Eingebaut, ohne Java ---------------------------------------------------


def pruefe_xsd(
    xml: bytes, *, flavor: str = "factur-x", level: str = "en16931"
) -> ValidierungsErgebnis:
    """Prüft das CII-XML gegen die EN-16931-XSD (eingebaut, kein Java)."""
    try:
        xml_check_xsd(xml, flavor=flavor, level=level)
        return ValidierungsErgebnis(True, "XSD (factur-x)")
    except Exception as e:
        return ValidierungsErgebnis(False, "XSD (factur-x)", [_kompakt(str(e))])


# --- Optional: KoSIT (XRechnung-CIUS + EN 16931) ----------------------------


@dataclass
class KositKonfig:
    """Pfade zum projektlokalen KoSIT-Validator (git-ignoriert unter werkzeuge/)."""

    validator_jar: Path
    szenarien: Path
    repository: Path
    java: str = "java"


def pruefe_kosit(xml: bytes, konfig: KositKonfig) -> ValidierungsErgebnis:
    """Prüft das CII-XML über den KoSIT-Validator (Schematron-Goldstandard)."""
    with tempfile.TemporaryDirectory(prefix="kosit-") as tmp:
        ziel = Path(tmp) / "rechnung.xml"
        ziel.write_bytes(xml)
        # KoSIT prüft per System.in.available(), ob XML über eine Pipe kommt.
        # Unter Windows wirft available() "Unzulässige Funktion", wenn stdin kein
        # echtes Handle ist (umgeleitet/ohne Konsole, z.B. GUI-.exe oder Tests).
        # Ein leerer Datei-stdin liefert available()=0, dann läuft KoSIT normal.
        leer = Path(tmp) / "leer.in"
        leer.write_bytes(b"")
        argv = [
            konfig.java,
            "-jar",
            str(konfig.validator_jar),
            "-s",
            str(konfig.szenarien),
            "-r",
            str(konfig.repository),
            str(ziel),
            "-o",
            str(tmp),
        ]
        with open(leer, "rb") as stdin_datei:
            fehler = _starte(argv, stdin=stdin_datei)
        if fehler:
            return ValidierungsErgebnis(False, "KoSIT", [fehler])
        report = ziel.with_name("rechnung-report.xml")
        if not report.exists():
            return ValidierungsErgebnis(False, "KoSIT", ["KoSIT hat keinen Report erzeugt."])
        inhalt = report.read_text(encoding="utf-8")
        gueltig = re.search(r'<rep:report\b[^>]*\bvalid="true"', inhalt) is not None
        befunde = [] if gueltig else _kosit_befunde(inhalt)
        return ValidierungsErgebnis(gueltig, "KoSIT (XRechnung 3.0.2)", befunde)


def _kosit_befunde(report: str) -> list[str]:
    # KoSIT legt die Befunde als <rep:message level="error|fatal" ...>Text</rep:message>
    # ab; Warnungen (level="warning") machen das Dokument nicht ungültig.
    treffer = re.findall(
        r'<rep:message\b[^>]*\blevel="(?:error|fatal)"[^>]*>(.*?)</rep:message>',
        report,
        re.DOTALL,
    )
    befunde = [_kompakt(t) for t in treffer if t.strip()]
    return befunde or ["KoSIT meldet das Dokument als ungültig (Details im Report)."]


# --- Optional: veraPDF (PDF/A) ----------------------------------------------


@dataclass
class VeraPdfKonfig:
    """Pfad zum projektlokalen veraPDF-CLI (git-ignoriert unter werkzeuge/)."""

    verapdf: Path  # verapdf.bat bzw. verapdf
    flavor: str = "3b"


def pruefe_verapdf(pdf: bytes, konfig: VeraPdfKonfig) -> ValidierungsErgebnis:
    """Prüft das PDF gegen PDF/A (Default 3b) über veraPDF."""
    pruefer = f"veraPDF (PDF/A-{konfig.flavor})"
    with tempfile.TemporaryDirectory(prefix="verapdf-") as tmp:
        ziel = Path(tmp) / "dokument.pdf"
        ziel.write_bytes(pdf)
        argv = [str(konfig.verapdf), "-f", konfig.flavor, str(ziel)]
        bericht = _starte(argv, gib_stdout=True)
        if not isinstance(bericht, str):
            return ValidierungsErgebnis(False, pruefer, [bericht])
        treffer = re.search(r'isCompliant="(true|false)"', bericht)
        if not treffer:
            return ValidierungsErgebnis(False, pruefer, ["Kein verwertbarer veraPDF-Report."])
        gueltig = treffer.group(1) == "true"
        befunde = [] if gueltig else _verapdf_befunde(bericht)
        return ValidierungsErgebnis(gueltig, pruefer, befunde)


def _verapdf_befunde(bericht: str) -> list[str]:
    rules = re.findall(r'<rule\b[^>]*\bclause="([^"]*)"[^>]*\btestNumber="([^"]*)"', bericht)
    befunde = [f"Verstoß gegen Klausel {c} (Test {t})" for c, t in rules]
    return befunde or ["veraPDF meldet das PDF als nicht konform (Details im Report)."]


# --- Hilfen -----------------------------------------------------------------


def _starte(argv: list[str], *, gib_stdout: bool = False, stdin=None):
    """Führt ein externes Werkzeug aus. Gibt bei Erfolg None bzw. stdout zurück,
    bei Problemen eine lesbare Fehlermeldung als String. `stdin` wird an den
    Prozess durchgereicht (KoSIT braucht ein echtes Handle, siehe `pruefe_kosit`)."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TIMEOUT,
            stdin=stdin,
        )
    except FileNotFoundError:
        return f"Werkzeug nicht gefunden: {argv[0]}"
    except subprocess.TimeoutExpired:
        return f"Zeitüberschreitung nach {_TIMEOUT}s: {argv[0]}"
    return proc.stdout if gib_stdout else None


def _kompakt(text: str) -> str:
    """Normalisiert Whitespace für eine knappe Befundzeile."""
    return re.sub(r"\s+", " ", text).strip()
