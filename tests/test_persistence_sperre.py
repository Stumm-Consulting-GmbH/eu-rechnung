"""Tests der Datei-Sperre gegen Mehrfachstart (4T-0081, S-0073).

Prüft Erwerb, die Erkennung eigener, belegter und verwaister Sperren, die Übernahme
und die Freigabe. Die plattformabhängige Prozess-Lebendprüfung (`_prozess_laeuft`)
wird für die Fremd-Prozess-Fälle gemockt; alle Sperr-Dateien liegen in `tmp_path`.
"""

from __future__ import annotations

import json
import os
import socket

from eu_rechnung.persistence import sperre
from eu_rechnung.persistence.sperre import (
    SperrStatus,
    erwerbe_sperre,
    gib_sperre_frei,
    sperr_pfad,
    uebernimm_sperre,
)


def _schreibe_fremde_sperre(firma_pfad, pid: int) -> None:
    """Legt eine Sperr-Datei mit fremder PID (aber diesem Rechner) an."""
    sperr_pfad(firma_pfad).write_text(
        json.dumps(
            {"pid": pid, "host": socket.gethostname(), "seit": "2026-07-11T00:00:00Z"}
        ),
        encoding="utf-8",
    )


def test_sperr_pfad_haengt_endung_an(tmp_path):
    assert sperr_pfad(tmp_path / "firma.scgr") == tmp_path / "firma.scgr.lock"


def test_erwerb_auf_freier_datei(tmp_path):
    firma = tmp_path / "firma.scgr"
    assert erwerbe_sperre(firma) is SperrStatus.ERWORBEN
    assert sperr_pfad(firma).is_file()


def test_eigene_sperre_gilt_als_erworben(tmp_path):
    firma = tmp_path / "firma.scgr"
    erwerbe_sperre(firma)  # eigene Sperre anlegen
    assert erwerbe_sperre(firma) is SperrStatus.ERWORBEN  # gleiche PID → erneut erworben


def test_fremde_laufende_sperre_ist_belegt(tmp_path, monkeypatch):
    firma = tmp_path / "firma.scgr"
    _schreibe_fremde_sperre(firma, pid=999_999)
    monkeypatch.setattr(sperre, "_prozess_laeuft", lambda kennung: True)
    assert erwerbe_sperre(firma) is SperrStatus.BELEGT


def test_fremde_tote_sperre_ist_verwaist(tmp_path, monkeypatch):
    firma = tmp_path / "firma.scgr"
    _schreibe_fremde_sperre(firma, pid=999_999)
    monkeypatch.setattr(sperre, "_prozess_laeuft", lambda kennung: False)
    assert erwerbe_sperre(firma) is SperrStatus.VERWAIST


def test_defekte_sperre_ist_verwaist(tmp_path):
    firma = tmp_path / "firma.scgr"
    sperr_pfad(firma).write_text("kein json", encoding="utf-8")
    assert erwerbe_sperre(firma) is SperrStatus.VERWAIST


def test_uebernimm_schreibt_eigene_kennung(tmp_path):
    firma = tmp_path / "firma.scgr"
    _schreibe_fremde_sperre(firma, pid=999_999)
    uebernimm_sperre(firma)
    kennung = json.loads(sperr_pfad(firma).read_text(encoding="utf-8"))
    assert kennung["pid"] == os.getpid()
    assert kennung["host"] == socket.gethostname()


def test_gib_frei_entfernt_eigene_sperre(tmp_path):
    firma = tmp_path / "firma.scgr"
    erwerbe_sperre(firma)
    gib_sperre_frei(firma)
    assert not sperr_pfad(firma).exists()


def test_gib_frei_laesst_fremde_sperre_bestehen(tmp_path):
    firma = tmp_path / "firma.scgr"
    _schreibe_fremde_sperre(firma, pid=999_999)
    gib_sperre_frei(firma)
    assert sperr_pfad(firma).is_file()  # fremde Sperre bleibt unangetastet


def test_gib_frei_ohne_sperre_ist_geraeuschlos(tmp_path):
    gib_sperre_frei(tmp_path / "firma.scgr")  # darf nicht werfen
