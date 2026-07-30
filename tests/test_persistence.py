"""Tests des JSON-Repositorys (`repository.py`): Roundlauf über eine echte Datei,
Erhalt echter Umlaute und die Schema-Fehlerfälle, die zu `PersistenzFehler`
führen.
"""

import json

import pytest

from eu_rechnung.persistence import lade, speichere
from eu_rechnung.persistence.repository import PersistenzFehler
from eu_rechnung.persistence.serialisierung import zu_json


def test_speichern_laden_roundtrip(beispiel_datenbestand, tmp_path):
    pfad = tmp_path / "daten.json"
    speichere(beispiel_datenbestand, pfad)
    assert lade(pfad) == beispiel_datenbestand


def test_umlaute_echt_in_datei(beispiel_datenbestand, tmp_path):
    """Die Datei wird mit `ensure_ascii=False` geschrieben (echte Umlaute)."""
    pfad = tmp_path / "daten.json"
    speichere(beispiel_datenbestand, pfad)
    text = pfad.read_text(encoding="utf-8")
    assert "München" in text
    assert "\\u" not in text  # keine ASCII-Unicode-Escapes


def test_speichern_legt_verzeichnis_an(beispiel_datenbestand, tmp_path):
    """`speichere` erzeugt fehlende Elternverzeichnisse."""
    pfad = tmp_path / "neu" / "unterordner" / "daten.json"
    speichere(beispiel_datenbestand, pfad)
    assert pfad.exists()


def test_lade_nicht_existierende_datei(tmp_path):
    with pytest.raises(PersistenzFehler):
        lade(tmp_path / "gibt-es-nicht.json")


def test_lade_kaputtes_json(tmp_path):
    pfad = tmp_path / "kaputt.json"
    pfad.write_text("{ kein gueltiges JSON ", encoding="utf-8")
    with pytest.raises(PersistenzFehler):
        lade(pfad)


def test_lade_fehlendes_pflichtfeld(beispiel_datenbestand, tmp_path):
    """Ohne `eigene_firma` verletzt die Datei das Schema."""
    daten = zu_json(beispiel_datenbestand)
    del daten["eigene_firma"]
    pfad = tmp_path / "ohne_firma.json"
    pfad.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PersistenzFehler):
        lade(pfad)


def test_lade_falsche_schema_version(beispiel_datenbestand, tmp_path):
    """`schema_version` != 3 verletzt das Schema (`const: 3`)."""
    daten = zu_json(beispiel_datenbestand)
    daten["schema_version"] = 99
    pfad = tmp_path / "version2.json"
    pfad.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PersistenzFehler):
        lade(pfad)


def test_lade_alte_v2_datei_wird_abgelehnt(beispiel_datenbestand, tmp_path):
    """AK4 (4T-0093): Eine v2-Datei (`schema_version` 2) wird beim Laden klar abgelehnt.
    Die Struktur-Änderungen auf v3 (Preis-Wertobjekt, Obergrenze) erforderten eine echte
    Migration, die es bewusst nicht gibt (keine produktiven v2-Daten); daher const 3."""
    daten = zu_json(beispiel_datenbestand)
    daten["schema_version"] = 2
    pfad = tmp_path / "alt_v2.json"
    pfad.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PersistenzFehler):
        lade(pfad)


def test_speichern_laesst_keine_tmp_reste(beispiel_datenbestand, tmp_path):
    """Nach dem atomaren Schreiben liegt nur die Zieldatei vor, keine .tmp-Reste."""
    pfad = tmp_path / "daten.json"
    speichere(beispiel_datenbestand, pfad)
    assert pfad.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_speichern_haelt_alte_datei_bei_schreibfehler(
    beispiel_datenbestand, tmp_path, monkeypatch
):
    """Schlägt das Schreiben fehl, bleibt die zuvor gespeicherte Datei intakt (AK3)."""
    pfad = tmp_path / "daten.json"
    speichere(beispiel_datenbestand, pfad)
    alt = pfad.read_text(encoding="utf-8")

    def kaputt(*a, **k):
        raise OSError("Datentraeger voll")

    monkeypatch.setattr(json, "dump", kaputt)
    with pytest.raises(PersistenzFehler):
        speichere(beispiel_datenbestand, pfad)

    assert pfad.read_text(encoding="utf-8") == alt  # unveraendert
    assert list(tmp_path.glob("*.tmp")) == []  # temporaere Datei aufgeraeumt
