"""Erstellungslogik: aus einer Rechnung die Ausgabedateien erzeugen (UI-frei).

Ruft die `export`-Schicht (XRechnung-CII, ZUGFeRD), schreibt die Dateien an den
Zielort und schreibt bei Erfolg Status und Erzeugungs-Zeitstempel der Rechnung
fort (S-0030). Der Datei-Überschreibfall wird je Zieldatei über einen von der
Oberfläche injizierten Callback entschieden (S-0031); diese Schicht kennt keine
Dialoge.

Vor der Erzeugung wird die Rechnung zweistufig gegen die Pflichtfelder der aktiven
Stufe geprüft (`pruefe_rechnung_fuer_ausgabe`, S-0047/S-0049); fehlende Pflichtangaben
werden als strukturierte Befunde gemeldet, es entsteht keine Datei. Beide Steuerfälle
werden unterstützt (Reverse-Charge und Normalsteuerfall).

Der Ablageort folgt dem deterministischen Schema
`<Ausgabe-Verzeichnis>/<Kundennummer>/<Rechnungsnummer>.<Endung>` (S-0057). Das
Ausgabe-Verzeichnis kommt aus den Einstellungen der Firma-Datei; ein Pfad je Rechnung wird
bewusst nicht gespeichert, damit `zielordner_der_rechnung` den Ort jederzeit neu herleiten
kann (Grundlage für „Ablageort öffnen").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from eu_rechnung.domain import Rechnung, RechnungsStatus
from eu_rechnung.export.cii_xml import erzeuge_cii
from eu_rechnung.export.zugferd import erzeuge_zugferd
from eu_rechnung.services.befund import Befund
from eu_rechnung.services.rechnung import pruefe_rechnung_fuer_ausgabe

# Trägt die technische Ursache eines Erzeugungsfehlers, die dem Anwender erspart bleibt
# (S-0032 AK3). Ohne konfiguriertes Logging geht sie nach stderr, was bei der Entwicklung
# genügt; eine Log-Datei für die ausgelieferte .exe ist ein eigenes Thema (1P-0006).
_log = logging.getLogger(__name__)

# Rückfall-Ausgabeverzeichnis (git-ignoriert unter Daten/), wenn die Einstellungen noch
# keines tragen. Der reguläre Weg setzt es aus `einstellungen.ausgabe_verzeichnis` (S-0057).
STANDARD_AUSGABE = Path("Daten") / "Ausgabe"

# Unter Windows in Datei- und Ordnernamen unzulässige Zeichen (plus Schrägstriche als
# Pfadtrenner). Rechnungs- und Kundennummer sind frei erfassbar und können sie enthalten.
_UNZULAESSIGE_ZEICHEN = '<>:"/\\|?*'


def _sicherer_name(text: str) -> str:
    """Macht einen frei erfassten Wert als Datei- oder Ordnernamen verwendbar.

    Ersetzt unzulässige Zeichen durch `-` und trimmt Leerraum sowie Punkte am Ende (die
    Windows still entfernt). Ein leerer Rest wird zu `unbenannt`, damit nie ein Pfad ohne
    Namensbestandteil entsteht.
    """
    for zeichen in _UNZULAESSIGE_ZEICHEN:
        text = text.replace(zeichen, "-")
    return text.strip().rstrip(".").strip() or "unbenannt"


def zielordner_der_rechnung(
    rechnung: Rechnung, ausgabe_verzeichnis: Path | str = STANDARD_AUSGABE
) -> Path:
    """Zielordner einer Rechnung nach dem Ablageschema: `<Ausgabe-Verzeichnis>/<Kundennummer>`.

    Der Ablageort ergibt sich deterministisch aus Verzeichnis und Kundennummer; es wird kein
    Pfad je Rechnung gespeichert (S-0057). Damit findet auch „Ablageort öffnen" den Ordner
    ohne gespeicherte Referenz wieder.
    """
    return Path(ausgabe_verzeichnis) / _sicherer_name(rechnung.kaeufer.kundennummer)


class Format(str, Enum):
    """Wählbares Ausgabeformat der Erstellung."""

    XRECHNUNG = "XRechnung"
    ZUGFERD = "ZUGFeRD"


# Callback: entscheidet je kollidierender Zieldatei über das Überschreiben.
UeberschreibEntscheidung = Callable[[Path], bool]


@dataclass
class ErstellungsErgebnis:
    """Ergebnis eines Erstellungslaufs für die Rückmeldung an die Oberfläche."""

    erzeugte_dateien: list[Path] = field(default_factory=list)
    uebersprungen: list[Path] = field(default_factory=list)
    # Erzeugungsfehler als Befund ohne Feldbezug; die Oberfläche löst ihn in ihrer Sprache
    # auf und zeigt ihn als Dialog.
    fehler: Befund | None = None
    # Fehlende Pflichtangaben der aktiven Stufe; nicht leer -> keine Datei geschrieben,
    # Status unverändert (S-0047/S-0049).
    pflicht_befunde: list[Befund] = field(default_factory=list)


def _dateiname(rechnung: Rechnung, endung: str) -> str:
    """Dateiname nach dem Ablageschema: `<Rechnungsnummer>.<Endung>` (S-0057)."""
    return f"{_sicherer_name(rechnung.rechnungsnummer)}.{endung}"


def erstelle_ausgaben(
    rechnung: Rechnung,
    bestellnummer: str,
    waehrung: str,
    formate: set[Format],
    *,
    ausgabe_verzeichnis: Path | str = STANDARD_AUSGABE,
    ueberschreiben: UeberschreibEntscheidung | None = None,
    jetzt: datetime | None = None,
) -> ErstellungsErgebnis:
    """Erzeugt die gewählten Ausgabeformate und schreibt sie an den Zielort.

    `bestellnummer` (BT-13) und `waehrung` (BT-5, die Belegwährung) stammen aus der
    Bestellung der Rechnung und werden an die Erzeuger durchgereicht (S-0064).

    Geschrieben wird nach dem Ablageschema `<Ausgabe-Verzeichnis>/<Kundennummer>/
    <Rechnungsnummer>.<Endung>` (S-0057); den Kundenordner bildet
    `zielordner_der_rechnung`.

    Vor der Erzeugung wird die Rechnung zweistufig gegen die Pflichtfelder der aktiven
    Stufe geprüft (`pruefe_rechnung_fuer_ausgabe`); bei Befunden entsteht keine Datei und
    `pflicht_befunde` trägt die feldbezogenen Meldungen (Status unverändert). Bei bereits
    vorhandener gleichnamiger Datei entscheidet `ueberschreiben` je Datei (True =
    überschreiben, False = auslassen); ohne Callback werden kollidierende Dateien
    ausgelassen. Wird mindestens eine Datei geschrieben, gehen Status auf „Erzeugt" und
    `zuletzt_erzeugt_am` (UTC, sekundengenau); andernfalls bleibt beides unverändert.
    Erzeugungsfehler werden als lesbare Meldung im Ergebnis zurückgegeben, nicht geworfen.
    `jetzt` ist injizierbar (Testbarkeit).
    """
    ergebnis = ErstellungsErgebnis()
    zielordner = zielordner_der_rechnung(rechnung, ausgabe_verzeichnis)

    # Pflichtprüfung vor der Ausgabe: zweistufig gegen die aktive Stufe der eingefrorenen
    # Verkäufer-Kopie (S-0047/S-0049). Der Normalsteuerfall-Satz (Kategorie S) ist Teil
    # dieser Prüfung. Bei Befunden keine Datei; Status und Zeitstempel bleiben unverändert.
    befunde = pruefe_rechnung_fuer_ausgabe(rechnung)
    if befunde:
        ergebnis.pflicht_befunde = befunde
        return ergebnis

    # 1. Erst alle gewählten Formate im Speicher erzeugen. Schlägt eines fehl,
    #    wird gar nichts geschrieben (Status bleibt unverändert).
    try:
        erzeugnisse: list[tuple[Path, bytes]] = []
        if Format.XRECHNUNG in formate:
            xml = erzeuge_cii(rechnung, bestellnummer, waehrung)
            erzeugnisse.append((zielordner / _dateiname(rechnung, "xml"), xml))
        if Format.ZUGFERD in formate:
            pdf = erzeuge_zugferd(rechnung, bestellnummer, waehrung)
            erzeugnisse.append((zielordner / _dateiname(rechnung, "pdf"), pdf))
    except Exception:
        # Der Anwender bekommt eine lesbare Meldung ohne Technik-Auszug (S-0032 AK3): Eine
        # rohe Ausnahme („KeyError: 'bt-10'") sagt ihm nichts und beunruhigt ihn nur. Die
        # technische Ursache geht ins Log, damit sie beim Nachstellen nicht verloren ist.
        _log.exception("Ausgabedateien konnten nicht erzeugt werden")
        ergebnis.fehler = Befund("", "erstellen.fehler_erzeugung")
        return ergebnis

    if not erzeugnisse:
        ergebnis.fehler = Befund("", "erstellen.fehler_kein_format")
        return ergebnis

    # 2. Schreiben, je Datei den Überschreibfall abfragen.
    zielordner.mkdir(parents=True, exist_ok=True)
    for zielpfad, daten in erzeugnisse:
        if zielpfad.exists():
            erlaubt = ueberschreiben(zielpfad) if ueberschreiben else False
            if not erlaubt:
                ergebnis.uebersprungen.append(zielpfad)
                continue
        zielpfad.write_bytes(daten)
        ergebnis.erzeugte_dateien.append(zielpfad)

    # 3. Statusfortschreibung nur, wenn wirklich geschrieben wurde.
    if ergebnis.erzeugte_dateien:
        stempel = jetzt or datetime.now(timezone.utc)
        if stempel.tzinfo is None:
            stempel = stempel.replace(tzinfo=timezone.utc)
        rechnung.status = RechnungsStatus.ERZEUGT
        rechnung.zuletzt_erzeugt_am = stempel.astimezone(timezone.utc).replace(microsecond=0)
    return ergebnis
