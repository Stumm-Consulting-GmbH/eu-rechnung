"""Datei-Sperre gegen doppeltes Öffnen einer Firma-Datei (S-0073, 4T-0081).

Schützt eine Firma-Datei davor, in zwei Programm-Instanzen gleichzeitig aktiv zu
sein. Da jede Instanz nach jeder Operation automatisch speichert (S-0072), würden
zwei Instanzen auf derselben Datei sich wechselseitig überschreiben und Daten
verlieren. Der Mechanismus ist eine Sperr-Datei neben der Firma-Datei
(`<firma>.scgr.lock`, JSON mit Prozess-ID, Rechnername und Zeitpunkt).

Der Erwerb legt die Sperr-Datei exklusiv an. Existiert sie bereits, entscheidet die
eingetragene Kennung über den Status: gehört die Sperre dieser Instanz selbst, gilt
sie als erworben; läuft der fremde Prozess noch, ist die Datei belegt (aktive
Instanz); läuft er nicht mehr (etwa nach einem Absturz), ist die Sperre verwaist und
kann nach ausdrücklicher Bestätigung übernommen werden. Die Lebendprüfung eines
Prozesses ist plattformspezifisch (Windows über `ctypes`, sonst `os.kill`); sie ist
in `_prozess_laeuft` gekapselt und für Tests ersetzbar.

Rest-Risiko: Wird die Prozess-ID einer abgestürzten Instanz vom Betriebssystem an
einen fremden Prozess neu vergeben, erscheint eine verwaiste Sperre fälschlich als
belegt. Im lokalen Einzelbenutzerbetrieb ist das vernachlässigbar.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

#: Endung der Sperr-Datei, an den Firma-Dateinamen angehängt.
SPERR_ENDUNG = ".lock"


class SperrStatus(Enum):
    """Ergebnis eines Sperr-Erwerbs."""

    ERWORBEN = "erworben"  # Sperre gehört jetzt (oder schon) dieser Instanz
    BELEGT = "belegt"  # eine aktive Instanz hält die Sperre
    VERWAIST = "verwaist"  # Sperr-Datei ohne laufenden Prozess (übernehmbar)


def sperr_pfad(firma_pfad: Path | str) -> Path:
    """Pfad der Sperr-Datei zu einer Firma-Datei (`<firma>.scgr.lock`)."""
    firma_pfad = Path(firma_pfad)
    return firma_pfad.with_name(firma_pfad.name + SPERR_ENDUNG)


def erwerbe_sperre(firma_pfad: Path | str) -> SperrStatus:
    """Versucht, die Sperre für eine Firma-Datei zu erwerben.

    Legt die Sperr-Datei exklusiv an (`ERWORBEN`). Existiert sie schon, wird ihr
    Inhalt geprüft: eine eigene Sperre (gleiche PID und gleicher Rechnername) gilt als
    `ERWORBEN`; hält ein noch laufender fremder Prozess sie, ist sie `BELEGT`; sonst
    `VERWAIST`. Verwaiste Sperren werden nicht selbsttätig übernommen; das entscheidet
    `uebernimm_sperre` nach Bestätigung durch den Anwender.
    """
    pfad = sperr_pfad(firma_pfad)
    try:
        # Exklusiv anlegen: schlägt fehl, wenn die Sperr-Datei bereits existiert.
        with open(pfad, "x", encoding="utf-8") as f:
            json.dump(_eigene_kennung(), f, ensure_ascii=False, indent=2)
        return SperrStatus.ERWORBEN
    except FileExistsError:
        pass
    except OSError:
        # Sperr-Datei nicht anlegbar (etwa Schreibschutz): sicherheitshalber als
        # belegt behandeln, um doppeltes Schreiben zuverlässig auszuschließen.
        return SperrStatus.BELEGT

    kennung = _lies_sperre(pfad)
    if kennung is None:
        return SperrStatus.VERWAIST  # defekte/leere Sperr-Datei: übernehmbar
    if _ist_eigene(kennung):
        return SperrStatus.ERWORBEN
    if _prozess_laeuft(kennung):
        return SperrStatus.BELEGT
    return SperrStatus.VERWAIST


def uebernimm_sperre(firma_pfad: Path | str) -> None:
    """Übernimmt eine (verwaiste) Sperre, indem die eigene Kennung geschrieben wird."""
    _schreibe_sperre(sperr_pfad(firma_pfad))


def gib_sperre_frei(firma_pfad: Path | str) -> None:
    """Gibt die Sperre frei, wenn sie dieser Instanz gehört.

    Eine fremde Sperre (andere laufende Instanz) wird nicht angetastet. Fehler beim
    Löschen werden geschluckt, damit das Programm-Ende nie an der Sperre scheitert.
    """
    pfad = sperr_pfad(firma_pfad)
    kennung = _lies_sperre(pfad)
    if kennung is not None and not _ist_eigene(kennung):
        return  # fremde Sperre nicht entfernen
    try:
        pfad.unlink(missing_ok=True)
    except OSError:
        pass


# --- Interna --------------------------------------------------------------------


def _eigene_kennung() -> dict:
    """Kennung dieser Instanz für die Sperr-Datei (PID, Rechnername, Zeitpunkt UTC)."""
    return {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "seit": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _schreibe_sperre(pfad: Path) -> None:
    """Schreibt die Sperr-Datei mit der Kennung dieser Instanz (überschreibend)."""
    pfad.write_text(
        json.dumps(_eigene_kennung(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _lies_sperre(pfad: Path) -> dict | None:
    """Liest die Sperr-Datei; bei fehlender oder defekter Datei `None`."""
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return daten if isinstance(daten, dict) else None


def _ist_eigene(kennung: dict) -> bool:
    """True, wenn die Sperr-Kennung diese Instanz bezeichnet (PID und Rechnername)."""
    return (
        kennung.get("pid") == os.getpid()
        and kennung.get("host") == socket.gethostname()
    )


def _prozess_laeuft(kennung: dict) -> bool:
    """Prüft, ob der in der Sperre genannte Prozess noch läuft.

    Nur für Sperren desselben Rechners aussagekräftig; eine Sperre von einem anderen
    Host wird konservativ als laufend behandelt (nicht prüfbar, daher nur nach
    Bestätigung übernehmbar). Die eigentliche PID-Prüfung ist plattformabhängig.
    """
    if kennung.get("host") != socket.gethostname():
        return True
    pid = kennung.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    return _pid_laeuft(pid)


if sys.platform == "win32":

    def _pid_laeuft(pid: int) -> bool:
        """Windows: prüft über OpenProcess/GetExitCodeProcess, ob die PID aktiv ist."""
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False  # Prozess existiert nicht
        try:
            code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True  # Exit-Code nicht lesbar: konservativ als laufend werten
        finally:
            kernel32.CloseHandle(handle)

else:

    def _pid_laeuft(pid: int) -> bool:
        """POSIX: Signal 0 prüft die Existenz, ohne den Prozess zu beeinflussen."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # existiert, gehört aber einem anderen Nutzer
        return True
