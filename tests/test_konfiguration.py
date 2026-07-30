"""Tests der App-Konfiguration: Liste zuletzt geöffneter Firmen (S-0071 AK4).

Dazu der Vermerk der zuletzt aktiven Firma (S-0083): Er trennt „zuletzt benutzt"
(Komfort-Liste) von „beim Beenden aktiv" (Autostart), damit ein bewusstes Schließen
über das Programm-Ende hinaus wirkt.
"""

import json
from pathlib import Path

from eu_rechnung.persistence.konfiguration import (
    MAX_ZULETZT_GEOEFFNET,
    AppKonfiguration,
    existierende_zuletzt_geoeffnet,
    lade_konfiguration,
    merke_zuletzt_geoeffnet,
    speichere_konfiguration,
    vergiss_aktive_firma,
)


def test_speichern_laden_roundtrip(tmp_path):
    pfad = tmp_path / "konfig.json"
    konfig = AppKonfiguration(zuletzt_geoeffnet=[str(tmp_path / "a.scgr")])
    speichere_konfiguration(konfig, pfad)
    assert lade_konfiguration(pfad).zuletzt_geoeffnet == konfig.zuletzt_geoeffnet


def test_lade_fehlende_datei_ergibt_leere_konfig(tmp_path):
    assert lade_konfiguration(tmp_path / "gibt-es-nicht.json").zuletzt_geoeffnet == []


def test_lade_kaputte_datei_ergibt_leere_konfig(tmp_path):
    pfad = tmp_path / "kaputt.json"
    pfad.write_text("{ kein gueltiges JSON ", encoding="utf-8")
    assert lade_konfiguration(pfad).zuletzt_geoeffnet == []


def test_merke_setzt_pfad_nach_vorne(tmp_path):
    a, b = tmp_path / "a.scgr", tmp_path / "b.scgr"
    konfig = merke_zuletzt_geoeffnet(AppKonfiguration(), a)
    konfig = merke_zuletzt_geoeffnet(konfig, b)
    assert Path(konfig.zuletzt_geoeffnet[0]) == b  # zuletzt gemerkt steht vorne
    assert Path(konfig.zuletzt_geoeffnet[1]) == a


def test_merke_dedupliziert(tmp_path):
    a, b = tmp_path / "a.scgr", tmp_path / "b.scgr"
    konfig = merke_zuletzt_geoeffnet(AppKonfiguration(), a)
    konfig = merke_zuletzt_geoeffnet(konfig, b)
    konfig = merke_zuletzt_geoeffnet(konfig, a)  # a erneut geöffnet
    assert len(konfig.zuletzt_geoeffnet) == 2
    assert Path(konfig.zuletzt_geoeffnet[0]) == a  # rückt wieder nach vorne


def test_merke_kappt_auf_maximum(tmp_path):
    konfig = AppKonfiguration()
    for i in range(MAX_ZULETZT_GEOEFFNET + 5):
        konfig = merke_zuletzt_geoeffnet(konfig, tmp_path / f"firma-{i}.scgr")
    assert len(konfig.zuletzt_geoeffnet) == MAX_ZULETZT_GEOEFFNET
    jüngster = f"firma-{MAX_ZULETZT_GEOEFFNET + 4}.scgr"
    assert Path(konfig.zuletzt_geoeffnet[0]).name == jüngster


def test_existierende_filtert_tote_pfade(tmp_path):
    da = tmp_path / "da.scgr"
    da.write_text("{}", encoding="utf-8")
    weg = tmp_path / "weg.scgr"  # nie angelegt
    konfig = AppKonfiguration(zuletzt_geoeffnet=[str(da), str(weg)])
    assert existierende_zuletzt_geoeffnet(konfig) == [da]


def test_merke_ueber_datei_bleibt_erhalten(tmp_path):
    """Gemerkte Pfade überstehen Speichern und Laden (persistente Recent-Liste)."""
    pfad = tmp_path / "konfig.json"
    konfig = merke_zuletzt_geoeffnet(AppKonfiguration(), tmp_path / "firma.scgr")
    speichere_konfiguration(konfig, pfad)
    assert lade_konfiguration(pfad).zuletzt_geoeffnet == konfig.zuletzt_geoeffnet


# --- Vermerk der zuletzt aktiven Firma (S-0083) -------------------------------


def test_merke_setzt_zugleich_die_aktive_firma(tmp_path):
    """Wer gemerkt wird, ist auch die aktive Firma: Beide Aufrufer aktivieren sie."""
    konfig = merke_zuletzt_geoeffnet(AppKonfiguration(), tmp_path / "a.scgr")
    assert Path(konfig.zuletzt_aktiv) == tmp_path / "a.scgr"


def test_vergiss_aktive_firma_leert_nur_den_vermerk(tmp_path):
    """Nach dem Schließen ist keine Firma aktiv, die Komfort-Liste bleibt vollständig."""
    konfig = merke_zuletzt_geoeffnet(AppKonfiguration(), tmp_path / "a.scgr")

    danach = vergiss_aktive_firma(konfig)

    assert danach.zuletzt_aktiv is None
    assert danach.zuletzt_geoeffnet == konfig.zuletzt_geoeffnet


def test_vergessener_vermerk_uebersteht_speichern_und_laden(tmp_path):
    """Das Schließen muss den Programmneustart überdauern, sonst wäre es wirkungslos."""
    pfad = tmp_path / "konfig.json"
    konfig = vergiss_aktive_firma(
        merke_zuletzt_geoeffnet(AppKonfiguration(), tmp_path / "a.scgr")
    )

    speichere_konfiguration(konfig, pfad)

    geladen = lade_konfiguration(pfad)
    assert geladen.zuletzt_aktiv is None
    assert geladen.zuletzt_geoeffnet  # Firma bleibt wählbar


def test_fehlendes_feld_deutet_den_ersten_eintrag_als_aktiv(tmp_path):
    """Bestandskonfigurationen ohne das Feld verhalten sich wie bisher (Autostart).

    Vor S-0083 gab es den Vermerk nicht; dort war die zuletzt geöffnete Firma zugleich
    die aktive. Ohne diese Deutung startete eine bestehende Installation nach dem Update
    unerwartet leer.
    """
    pfad = tmp_path / "konfig.json"
    pfad.write_text(
        json.dumps(
            {"schema_version": 1, "zuletzt_geoeffnet": [str(tmp_path / "a.scgr")]}
        ),
        encoding="utf-8",
    )

    assert Path(lade_konfiguration(pfad).zuletzt_aktiv) == tmp_path / "a.scgr"


def test_ausdrueckliches_null_bleibt_geschlossen(tmp_path):
    """Ein geschriebenes `null` heißt „geschlossen" und wird nicht zurückgedeutet."""
    pfad = tmp_path / "konfig.json"
    pfad.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "zuletzt_geoeffnet": [str(tmp_path / "a.scgr")],
                "zuletzt_aktiv": None,
            }
        ),
        encoding="utf-8",
    )

    assert lade_konfiguration(pfad).zuletzt_aktiv is None
