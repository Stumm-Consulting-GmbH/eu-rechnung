"""Tests des Anwendungsstarts: Startfirma und UI-Sprache (4T-0079, 4T-0127).

Deckt die Startlogik ab (`ermittle_start_firma`, `standard_konfig_pfad`): ist eine
zuletzt geöffnete Firma ladbar, liefert sie den Startbestand, sonst `None` (das
Fenster startet dann im Leerzustand, geprüft in test_ui_leerzustand.py, 4T-0080).

Dazu die Qt-Übersetzung, die der UI-Sprache folgt (S-0059). Die Sprache steht in den
Einstellungen und damit in der Firma-Datei; ohne Startfirma bleibt es bei Deutsch.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from PySide6.QtWidgets import QMessageBox

from eu_rechnung.app import (
    ermittle_start_firma,
    ermittle_startzustand,
    ermittle_uebergabe_pfad,
    installiere_qt_uebersetzung,
    standard_konfig_pfad,
    ui_sprache_der_datei,
)
from eu_rechnung.persistence import lade, speichere
from eu_rechnung.persistence.konfiguration import (
    AppKonfiguration,
    lade_konfiguration,
    merke_zuletzt_geoeffnet,
    speichere_konfiguration,
    vergiss_aktive_firma,
)
from eu_rechnung.services import erzeuge_seed


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _firma_datei(pfad, name):
    bestand = erzeuge_seed()
    bestand.eigene_firma.name = name
    speichere(bestand, pfad)
    return pfad


def test_ermittle_start_firma_laedt_zuletzt_geoeffnete(tmp_path):
    firma = _firma_datei(tmp_path / "a.scgr", "Firma A")
    konfig_pfad = tmp_path / "konfig.json"
    speichere_konfiguration(
        merke_zuletzt_geoeffnet(AppKonfiguration(), firma), konfig_pfad
    )
    start = ermittle_start_firma(konfig_pfad)
    assert start is not None
    geladen, pfad = start
    assert geladen.eigene_firma.name == "Firma A"
    assert pfad == firma


def test_ermittle_start_firma_ohne_recent_ergibt_none(tmp_path):
    assert ermittle_start_firma(tmp_path / "leer.json") is None


def test_ermittle_start_firma_bei_verschwundener_datei_ergibt_none(tmp_path):
    """Eine vermerkte, aber nicht mehr vorhandene Firma-Datei führt in den Leerzustand."""
    konfig_pfad = tmp_path / "konfig.json"
    speichere_konfiguration(
        merke_zuletzt_geoeffnet(AppKonfiguration(), tmp_path / "weg.scgr"), konfig_pfad
    )
    assert ermittle_start_firma(konfig_pfad) is None


def test_ermittle_start_firma_oeffnet_keine_ersatz_firma(tmp_path):
    """Fehlt die vermerkte Datei, wird keine ältere Firma ersatzweise geöffnet.

    Ein stiller Wechsel auf einen anderen Datenbestand wäre überraschender als eine leere
    Anwendung; der Anwender wählt dann über „Zuletzt geöffnet".
    """
    _firma_datei(tmp_path / "alt.scgr", "Firma Alt")
    konfig_pfad = tmp_path / "konfig.json"
    konfig = merke_zuletzt_geoeffnet(AppKonfiguration(), tmp_path / "alt.scgr")
    konfig = merke_zuletzt_geoeffnet(konfig, tmp_path / "weg.scgr")  # aktiv, aber weg
    speichere_konfiguration(konfig, konfig_pfad)

    assert ermittle_start_firma(konfig_pfad) is None


def test_ermittle_start_firma_nach_dem_schliessen_ergibt_none(tmp_path):
    """S-0083 AK8: Eine bewusst geschlossene Firma wird beim nächsten Start nicht geladen.

    Ohne diese Trennung machte der Autostart das Schließen wieder rückgängig, sobald das
    Programm neu startet. Die Firma bleibt dabei in der Zuletzt-geöffnet-Liste wählbar.
    """
    firma = _firma_datei(tmp_path / "a.scgr", "Firma A")
    konfig_pfad = tmp_path / "konfig.json"
    speichere_konfiguration(
        vergiss_aktive_firma(merke_zuletzt_geoeffnet(AppKonfiguration(), firma)),
        konfig_pfad,
    )

    assert ermittle_start_firma(konfig_pfad) is None
    assert lade_konfiguration(konfig_pfad).zuletzt_geoeffnet  # bleibt wählbar


def test_standard_konfig_pfad_endet_auf_konfigdatei(qapp):
    assert standard_konfig_pfad().name == "konfiguration.json"


def test_qt_uebersetzung_uebersetzt_standardknoepfe(qapp):
    """Die Qt-Standarddialoge sollen deutsche Knöpfe zeigen (Ja/Nein statt Yes/No)."""
    assert installiere_qt_uebersetzung(qapp, "de") is True
    box = QMessageBox()
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    texte = [b.text().replace("&", "") for b in box.buttons()]
    assert "Ja" in texte
    assert "Nein" in texte


@pytest.mark.parametrize("sprache", ["de", "en", "it", "fr", "es"])
def test_qt_uebersetzung_gibt_es_fuer_jede_ui_sprache(qapp, sprache):
    """AK4: Die Qt-Dialoge folgen der UI-Sprache; für alle fünf liegt eine qtbase-Datei bei."""
    assert installiere_qt_uebersetzung(qapp, sprache) is True


def test_qt_uebersetzung_ohne_datei_bricht_nicht(qapp):
    """Fehlt eine qtbase-Datei, bleiben die Qt-Dialoge englisch; das ist kein Fehler."""
    assert installiere_qt_uebersetzung(qapp, "xx") is False


def _standardknopf_texte() -> list[str]:
    box = QMessageBox()
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    return [b.text().replace("&", "") for b in box.buttons()]


def test_qt_uebersetzung_ersetzt_die_vorherige(qapp):
    """Ein Sprachwechsel darf keinen alten Translator wirksam lassen.

    Qt stapelt Translatoren und befragt sie der Reihe nach. `qtbase_en.qm` trägt als
    Quellsprache keine eigenen Texte; ohne Entfernen des Vorgängers zeigte eine englische
    Oberfläche deshalb die deutschen Knöpfe. Gefunden über das Prüf-Artefakt zu 4T-0127.
    """
    installiere_qt_uebersetzung(qapp, "de")
    assert "Ja" in _standardknopf_texte()

    installiere_qt_uebersetzung(qapp, "en")
    texte = _standardknopf_texte()
    assert "Yes" in texte
    assert "Ja" not in texte

    installiere_qt_uebersetzung(qapp, "fr")
    assert "Oui" in _standardknopf_texte()


# --- Übergebener Dateipfad beim Programmstart (4T-0185, S-0054) --------------


def test_uebergabe_pfad_wird_erkannt():
    """AK1: Das erste Argument gilt als Firma-Dateipfad; genau so ruft Windows auf."""
    assert ermittle_uebergabe_pfad(["app.exe", r"C:\Firmen\Muster.scgr"]) == Path(
        r"C:\Firmen\Muster.scgr"
    )


def test_ohne_argument_kein_uebergabe_pfad():
    """Ohne Argument bleibt es beim bisherigen Startverhalten."""
    assert ermittle_uebergabe_pfad(["app.exe"]) is None
    assert ermittle_uebergabe_pfad([]) is None
    assert ermittle_uebergabe_pfad(["app.exe", ""]) is None


def test_schalter_gilt_nicht_als_pfad():
    """Ein Schalter ist kein Dateipfad; sein Wert wird gar nicht betrachtet.

    Sonst deutete `-platform offscreen` das „offscreen" als Firma-Datei.
    """
    assert ermittle_uebergabe_pfad(["app.exe", "-platform", "offscreen"]) is None


def test_ui_sprache_der_datei_liest_die_einstellung(tmp_path):
    """Die UI-Sprache muss vor dem Fensteraufbau feststehen (S-0058)."""
    pfad = _firma_datei(tmp_path / "sprachtest.scgr", "Sprachtest")
    bestand = lade(pfad)
    bestand.einstellungen.ui_sprache = "es"
    speichere(bestand, pfad)
    assert ui_sprache_der_datei(pfad) == "es"


def test_ui_sprache_der_datei_bei_defekter_datei(tmp_path):
    """Unlesbar heißt Standardsprache, nicht Absturz; die Meldung gibt der Ladeweg."""
    kaputt = tmp_path / "kaputt.scgr"
    kaputt.write_text("{kein json", encoding="utf-8")
    assert ui_sprache_der_datei(kaputt) is None
    assert ui_sprache_der_datei(tmp_path / "gibtsnicht.scgr") is None


def test_uebergabe_hat_vorrang_vor_autostart(tmp_path):
    """AK2: Wer eine Firma-Datei doppelklickt, will diese sehen, nicht die zuletzt aktive."""
    aktiv = _firma_datei(tmp_path / "aktiv.scgr", "Zuletzt aktiv")
    uebergeben = _firma_datei(tmp_path / "doppelklick.scgr", "Doppelklick")
    konfig_pfad = tmp_path / "konfiguration.json"
    speichere_konfiguration(
        AppKonfiguration(zuletzt_geoeffnet=[str(aktiv)], zuletzt_aktiv=str(aktiv)),
        konfig_pfad,
    )

    zustand = ermittle_startzustand(["app.exe", str(uebergeben)], konfig_pfad)
    assert zustand.uebergabe == Path(str(uebergeben))
    assert zustand.start is None, "der Autostart-Vermerk darf nicht zusätzlich greifen"


def test_ohne_uebergabe_greift_der_autostart_vermerk(tmp_path):
    """Ohne Argument bleibt das Verhalten aus S-0083 unverändert."""
    aktiv = _firma_datei(tmp_path / "aktiv.scgr", "Zuletzt aktiv")
    konfig_pfad = tmp_path / "konfiguration.json"
    speichere_konfiguration(
        AppKonfiguration(zuletzt_geoeffnet=[str(aktiv)], zuletzt_aktiv=str(aktiv)),
        konfig_pfad,
    )

    zustand = ermittle_startzustand(["app.exe"], konfig_pfad)
    assert zustand.uebergabe is None
    assert zustand.start is not None
    assert zustand.start[1] == aktiv
