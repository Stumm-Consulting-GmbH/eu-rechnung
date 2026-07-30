"""Tests des Bestellung-Reiters (4T-0084), offscreen.

Prüft, dass die globale Liste die Bestellungen über alle Kunden zeigt, die Detailmaske
lädt und zurückschreibt, das Anlegen die Bestellung am gewählten Kunden einhängt, die
feld-nahe Validierung greift (ohne das echte Objekt zu verändern) und die Verbrauchs-/
Restanzeige zum Gesamt-Höchstbetrag erscheint.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from eu_rechnung.domain import GueltigerArtikel, Skonto
from eu_rechnung.persistence import lade
from eu_rechnung.services import erzeuge_seed
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.bestellung_reiter import BestellungReiter
from eu_rechnung.ui.betrag import format_betrag
from eu_rechnung.ui.sprache import ui_text


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _reiter(tmp_path):
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "firma.scgr")
    return BestellungReiter(bestand, auto_speicher=auto), bestand


def test_liste_zeigt_bestellungen(qapp, tmp_path):
    reiter, _ = _reiter(tmp_path)
    assert reiter._liste._tabelle.rowCount() == 1  # eine Bestellung im Seed


def test_auswahl_laedt_gueltige_artikel(qapp, tmp_path):
    reiter, _ = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)  # Seed-Bestellung auswählen
    assert reiter._bestellnummer.text() == "4500000001"
    assert reiter._gueltige_tabelle.rowCount() == 2  # zwei gültige Artikel


def test_neue_bestellung_leert_maske(qapp, tmp_path):
    reiter, _ = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)
    reiter._neue_bestellung()
    assert reiter._bestellnummer.text() == ""
    assert reiter._gueltige_tabelle.rowCount() == 0
    assert reiter._kunde_combo.isEnabled() is True  # Kunde beim Anlegen wählbar


def test_anlegen_haengt_bestellung_am_kunden_ein(qapp, tmp_path):
    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    vorher = len(kunde.bestellungen)
    reiter._neue_bestellung()
    reiter._kunde_combo.setCurrentIndex(0)
    reiter._bestellnummer.setText("NEU-1")
    reiter._zahlungsbedingung.setText("Zahlbar in 30 Tagen.")
    reiter._gueltige_artikel.append(
        GueltigerArtikel(artikel_id="art-1", einzelpreis=Decimal("1200"))
    )
    reiter._bestaetigen()
    assert len(kunde.bestellungen) == vorher + 1
    assert (tmp_path / "firma.scgr").exists()


def test_anlegen_blockiert_ohne_bestellnummer(qapp, tmp_path):
    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    vorher = len(kunde.bestellungen)
    reiter._neue_bestellung()
    reiter._kunde_combo.setCurrentIndex(0)
    reiter._bestellnummer.setText("")  # Pflichtfeld leer
    reiter._bestaetigen()
    assert reiter._fehler["bestellnummer"].isHidden() is False
    assert len(kunde.bestellungen) == vorher  # nichts angelegt


def test_bestaetigen_mit_fehler_laesst_bestellung_unveraendert(qapp, tmp_path):
    reiter, bestand = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)  # Seed-Bestellung laden
    original = bestand.kunden[0].bestellungen[0].bestellnummer
    reiter._bestellnummer.setText("")  # Pflichtfeld leeren, Bestätigen schlägt fehl
    reiter._bestaetigen()
    assert bestand.kunden[0].bestellungen[0].bestellnummer == original


def test_gesamthoechstbetrag_zeigt_rest(qapp, tmp_path):
    reiter, _ = _reiter(tmp_path)
    reiter._neue_bestellung()
    reiter._gesamt.setText("10.000,00")
    assert reiter._gesamt_rest.isHidden() is False
    assert "Rest: 10.000,00" in reiter._gesamt_rest.text()  # Verbrauch 0 ohne Rechnungen


def test_knopf_hebt_sich_bei_aenderung(qapp, tmp_path):
    reiter, _ = _reiter(tmp_path)
    reiter._neue_bestellung()
    assert reiter._geaendert is False
    reiter._bestellnummer.setText("X")
    assert reiter._geaendert is True


def test_loeschen_ohne_rechnungen_entfernt(qapp, tmp_path, monkeypatch):
    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    reiter._liste._tabelle.setCurrentCell(0, 0)  # Seed-Bestellung ohne Rechnungen
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    reiter._loeschen()
    assert len(kunde.bestellungen) == 0


def test_loeschen_mit_rechnungen_blockiert(qapp, tmp_path, monkeypatch):
    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    kunde.bestellungen[0].rechnungen.append(object())  # nur die Nicht-Leere zaehlt hier
    reiter._fuelle_liste()
    reiter._liste._tabelle.setCurrentCell(0, 0)
    infos: list = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a))
    reiter._loeschen()
    assert infos  # Ablehnung mit Verweis auf Deaktivieren
    assert len(kunde.bestellungen) == 1  # nicht geloescht


# --- 4T-0103: Anschreiben-Überschreibung (S-0036) --------------------------


def test_bestellung_anschreiben_erbt_vom_kunden(qapp, tmp_path):
    reiter, bestand = _reiter(tmp_path)
    bestand.kunden[0].anschreibentext = "Kundentext"
    reiter._neue_bestellung()
    reiter._kunde_combo.setCurrentIndex(0)  # den Seed-Kunden wählen
    assert reiter._anschreiben._text.toPlainText() == "Kundentext"  # geerbte Vorschau
    assert "Kunde" in reiter._anschreiben._hinweis.text()


def test_bestellung_anschreiben_ueberschreiben_speichert(qapp, tmp_path):
    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    vorher = len(kunde.bestellungen)
    reiter._neue_bestellung()
    reiter._kunde_combo.setCurrentIndex(0)
    reiter._bestellnummer.setText("ANS-1")
    reiter._zahlungsbedingung.setText("Zahlbar in 30 Tagen.")
    reiter._gueltige_artikel.append(
        GueltigerArtikel(artikel_id="art-1", einzelpreis=Decimal("1200"))
    )
    reiter._anschreiben._schalter.setChecked(True)
    reiter._anschreiben._text.setPlainText("Bestelltext")
    reiter._bestaetigen()
    assert len(kunde.bestellungen) == vorher + 1
    assert kunde.bestellungen[-1].anschreibentext == "Bestelltext"


# --- 4T-0104: Individuelle Felder (S-0038, S-0040) -------------------------


def test_bestellung_laedt_vorhandene_felder(qapp, tmp_path):
    reiter, bestand = _reiter(tmp_path)
    erwartet = [f.name for f in bestand.kunden[0].bestellungen[0].individuelle_felder]
    reiter._liste._tabelle.setCurrentCell(0, 0)  # Seed-Bestellung laden
    geladen = [f.name for f in reiter._felder.felder()]
    assert geladen == erwartet


def test_bestellung_individuelle_felder_speichern(qapp, tmp_path):
    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    vorher = len(kunde.bestellungen)
    reiter._neue_bestellung()
    reiter._kunde_combo.setCurrentIndex(0)
    reiter._bestellnummer.setText("IF-1")
    reiter._zahlungsbedingung.setText("Zahlbar in 30 Tagen.")
    reiter._gueltige_artikel.append(
        GueltigerArtikel(artikel_id="art-1", einzelpreis=Decimal("1200"))
    )
    name, aktiv, wert = reiter._felder._plaetze[0]
    name.setText("Leistungspaket")
    aktiv.setChecked(True)
    wert.setText("#LP-7")
    reiter._bestaetigen()
    assert len(kunde.bestellungen) == vorher + 1
    neu = kunde.bestellungen[-1]
    assert (neu.individuelle_felder[0].name, neu.individuelle_felder[0].wert) == (
        "Leistungspaket",
        "#LP-7",
    )


# --- Vereinbartes Skonto (S-0080, 4T-0119) ----------------------------------


def test_skonto_wird_in_die_bestellung_uebernommen(qapp, tmp_path):
    """AK1/AK4: Die erfassten Werte landen als Wertobjekt an der Bestellung; der
    Prozentsatz nimmt auch deutsche Dezimalschreibweise an."""
    reiter, bestand = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)  # Seed-Bestellung laden
    reiter._skonto_tage.setText("14")
    reiter._skonto_prozent.setText("2,5")
    reiter._bestaetigen()
    assert bestand.kunden[0].bestellungen[0].skonto == Skonto(tage=14, prozent=Decimal("2.5"))


def test_bestellung_ohne_skonto_bleibt_none(qapp, tmp_path):
    """AK2: Ohne Eingabe trägt die Bestellung kein Skonto."""
    reiter, bestand = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)
    assert reiter._skonto_tage.text() == ""  # Seed vereinbart keines
    reiter._bestaetigen()
    assert bestand.kunden[0].bestellungen[0].skonto is None


def test_maske_zeigt_vereinbartes_skonto(qapp, tmp_path):
    """AK4: Beim Laden erscheinen die gespeicherten Werte wieder in den Feldern."""
    reiter, bestand = _reiter(tmp_path)
    bestand.kunden[0].bestellungen[0].skonto = Skonto(tage=14, prozent=Decimal("2.00"))
    reiter._fuelle_liste()
    reiter._liste._tabelle.setCurrentCell(0, 0)
    assert reiter._skonto_tage.text() == "14"
    assert reiter._skonto_prozent.text() == "2"


def test_halbes_skonto_wird_gemeldet(qapp, tmp_path):
    """AK2: Nur ein Feld gefüllt: feld-naher Fehler, und die Bestellung bleibt unverändert."""
    reiter, bestand = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)
    reiter._skonto_tage.setText("14")  # Prozentsatz fehlt
    reiter._bestaetigen()
    assert reiter._fehler["skonto_prozent"].isHidden() is False
    assert bestand.kunden[0].bestellungen[0].skonto is None


def test_skonto_ueber_hundert_prozent_wird_gemeldet(qapp, tmp_path):
    """AK3: Der Wertebereich der Bestellung ist derselbe wie an der Rechnung; der
    Service-Befund erscheint feld-nah und es wird nichts gespeichert."""
    reiter, bestand = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)
    reiter._skonto_tage.setText("14")
    reiter._skonto_prozent.setText("150")
    reiter._bestaetigen()
    assert reiter._fehler["skonto_prozent"].isHidden() is False
    assert bestand.kunden[0].bestellungen[0].skonto is None


# --- Rechnungssprache mit Vererbung (S-0082 AK2/AK3, 4T-0137) --------------


def test_sprache_erbt_vom_kunden(qapp, tmp_path):
    """AK3: Die Bestellung nennt die geerbte Sprache und dass sie vom Kunden stammt."""
    from eu_rechnung.ui.bestellung_reiter import _BestellZeile

    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    kunde.rechnungssprache = "it"
    reiter._lade_in_maske(_BestellZeile(kunde, kunde.bestellungen[0]))
    assert reiter._sprache._auswahl.itemText(0) == "erbt (Italiano)"
    assert reiter._sprache._hinweis.text() == "Erbt von: Kunde"
    assert reiter._sprache.wert() is None


def test_sprache_ohne_kundenwert_erbt_den_rueckfall(qapp, tmp_path):
    from eu_rechnung.ui.bestellung_reiter import _BestellZeile

    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    kunde.rechnungssprache = None
    reiter._lade_in_maske(_BestellZeile(kunde, kunde.bestellungen[0]))
    assert reiter._sprache._auswahl.itemText(0) == "erbt (Deutsch)"
    assert reiter._sprache._hinweis.text() == "Erbt von: Vorgabe"


def test_kundenwechsel_zieht_die_geerbte_sprache_nach(qapp, tmp_path):
    """Die Vorschau muss dem gewählten Kunden folgen, sonst zeigt sie den Vorgänger."""
    import copy

    reiter, bestand = _reiter(tmp_path)
    k1 = bestand.kunden[0]
    k1.rechnungssprache = "it"
    k2 = copy.deepcopy(k1)
    k2.id, k2.name, k2.kundennummer = "k2", "Zweiter", "D99"
    k2.rechnungssprache, k2.bestellungen = None, []
    bestand.kunden.append(k2)

    reiter._neue_bestellung()
    reiter._kunde_combo.setCurrentIndex(reiter._kunde_combo.findData(k1))
    assert reiter._sprache._auswahl.itemText(0) == "erbt (Italiano)"
    reiter._kunde_combo.setCurrentIndex(reiter._kunde_combo.findData(k2))
    assert reiter._sprache._auswahl.itemText(0) == "erbt (Deutsch)"
    assert reiter._sprache._hinweis.text() == "Erbt von: Vorgabe"


def test_sprache_ueberschreiben_und_speichern(qapp, tmp_path):
    from eu_rechnung.persistence import lade
    from eu_rechnung.ui.bestellung_reiter import _BestellZeile

    reiter, bestand = _reiter(tmp_path)
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    reiter._lade_in_maske(_BestellZeile(kunde, bestellung))
    reiter._sprache._auswahl.setCurrentIndex(reiter._sprache._auswahl.findData("fr"))
    reiter._bestaetigen()
    assert bestellung.rechnungssprache == "fr"
    assert lade(tmp_path / "firma.scgr").kunden[0].bestellungen[0].rechnungssprache == "fr"


# --- Währungs-Kaskade und Bestellungs-Vorbelegung (S-0063, 4T-0133) --------


def test_vorbelegung_nimmt_die_kundenwaehrung(qapp, tmp_path):
    """AK1: Beim Anlegen ist die Belegwährung aus der Kundenebene vorbelegt."""
    reiter, bestand = _reiter(tmp_path)
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    bestand.kunden[0].waehrung = "CHF"
    reiter._neue_bestellung()  # Combo mit dem geänderten Stand neu füllen
    assert reiter._waehrung.currentText() == "CHF"


def test_vorbelegung_faellt_auf_die_standardwaehrung(qapp, tmp_path):
    """AK1: Ohne Kundenwert greift die Standardwährung als Wurzel der Kaskade."""
    reiter, bestand = _reiter(tmp_path)
    bestand.einstellungen.waehrungsliste = ["EUR", "USD"]
    bestand.einstellungen.standardwaehrung = "USD"
    bestand.kunden[0].waehrung = None  # Kunde erbt
    reiter._neue_bestellung()
    assert reiter._waehrung.currentText() == "USD"


def test_kundenwechsel_zieht_die_waehrung_nach(qapp, tmp_path):
    """Die Vorbelegung muss dem gewählten Kunden folgen, sonst zeigt sie den Vorgänger."""
    import copy

    reiter, bestand = _reiter(tmp_path)
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    k1 = bestand.kunden[0]
    k1.waehrung = "CHF"
    k2 = copy.deepcopy(k1)
    k2.id, k2.name, k2.kundennummer = "k2", "Zweiter", "D99"
    k2.waehrung, k2.bestellungen = None, []  # erbt die Standardwährung (EUR)
    bestand.kunden.append(k2)

    reiter._neue_bestellung()
    reiter._kunde_combo.setCurrentIndex(reiter._kunde_combo.findData(k1))
    assert reiter._waehrung.currentText() == "CHF"
    reiter._kunde_combo.setCurrentIndex(reiter._kunde_combo.findData(k2))
    assert reiter._waehrung.currentText() == "EUR"


def test_belegwaehrung_bleibt_beim_aendern_fest(qapp, tmp_path):
    """AK2/S-0017: Der gespeicherte Belegwert hat Vorrang vor der Kaskade und wird geladen."""
    from eu_rechnung.ui.bestellung_reiter import _BestellZeile

    reiter, bestand = _reiter(tmp_path)
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    kunde = bestand.kunden[0]
    kunde.waehrung = None  # Kunde erbt EUR
    bestellung = kunde.bestellungen[0]
    bestellung.waehrung = "CHF"  # abweichender, fester Belegwert
    reiter._lade_in_maske(_BestellZeile(kunde, bestellung))
    assert reiter._waehrung.currentText() == "CHF"


def test_einzelpreis_vorbelegung_nur_bei_passender_belegwaehrung(qapp):
    """S-0063/S-0019: Der Einzelpreis wird aus dem Vorschlagspreis nur bei gleicher Währung
    vorbelegt; weicht die Belegwährung ab, bleibt er leer (keine Umrechnung)."""
    from eu_rechnung.ui.betrag import format_betrag
    from eu_rechnung.ui.gueltiger_artikel_dialog import GueltigerArtikelDialog

    bestand = erzeuge_seed()
    artikel = bestand.artikel  # art-1: Vorschlagspreis in EUR
    passend = GueltigerArtikelDialog(artikel, "EUR")
    assert passend._einzelpreis.text() == format_betrag(artikel[0].vorschlagspreis.betrag)
    abweichend = GueltigerArtikelDialog(artikel, "CHF")
    assert abweichend._einzelpreis.text() == ""


# --- Filtern, Sortieren, Aktiv-Umschalter (K2; S-0022, S-0018; 4T-0161) -----


def _sichtbare_nummern(reiter: BestellungReiter) -> list[str]:
    """Die Bestellnummern der sichtbaren Zeilen (Spalte 1), in Anzeige-Reihenfolge."""
    tabelle = reiter._liste._tabelle
    return [
        tabelle.item(z, 1).text()
        for z in range(tabelle.rowCount())
        if not tabelle.isRowHidden(z)
    ]


def _zweiter_kunde_mit_bestellung(bestand, name: str, nummer: str, beginn: date):
    """Ein zweiter Kunde mit einer Bestellung.

    Der Seed hält nur eine Bestellung; an einer einzigen Zeile lässt sich weder eine
    Reihenfolge noch ein Filter beobachten.
    """
    bestellung = deepcopy(bestand.kunden[0].bestellungen[0])
    bestellung.id = f"b-{nummer}"
    bestellung.bestellnummer = nummer
    bestellung.beginn_datum = beginn
    bestellung.rechnungen = []
    kunde = deepcopy(bestand.kunden[0])
    kunde.id = f"k-{nummer}"
    kunde.name = name
    kunde.kundennummer = nummer
    kunde.bestellungen = [bestellung]
    bestand.kunden.append(kunde)
    return kunde, bestellung


def test_bestellliste_ist_standardmaessig_alphabetisch_nach_kunde(qapp, tmp_path):
    """S-0022 AK4: Ausgangszustand alphabetisch nach Kunde."""
    bestand = erzeuge_seed()
    bestand.kunden[0].name = "Zeta AG"
    _zweiter_kunde_mit_bestellung(bestand, "Alpha GmbH", "111", date(2026, 1, 1))
    auto = AutoSpeicher(bestand, tmp_path / "firma.scgr")
    reiter = BestellungReiter(bestand, auto_speicher=auto)
    tabelle = reiter._liste._tabelle
    kunden = [tabelle.item(z, 0).text() for z in range(tabelle.rowCount())]
    assert kunden == ["Alpha GmbH", "Zeta AG"]


def test_bestellliste_sortiert_zeitraum_chronologisch(qapp, tmp_path):
    """S-0022 AK3: Der Zeitraum sortiert nach Beginn-Datum, nicht nach Anzeigetext.

    Alphabetisch käme der 01.12.2026 vor dem 02.01.2027; der `sortierwert` der Spalte
    verhindert das. Genau dafür gibt es ihn, und genau das war ungetestet.
    """
    bestand = erzeuge_seed()
    bestand.kunden[0].bestellungen[0].beginn_datum = date(2026, 12, 1)
    _zweiter_kunde_mit_bestellung(bestand, "Andere AG", "222", date(2027, 1, 2))
    auto = AutoSpeicher(bestand, tmp_path / "firma.scgr")
    reiter = BestellungReiter(bestand, auto_speicher=auto)
    reiter._liste._tabelle.sortByColumn(2, Qt.AscendingOrder)
    assert _sichtbare_nummern(reiter) == ["4500000001", "222"]


def test_bestellfilter_trifft_kunde_und_bestellnummer(qapp, tmp_path):
    """S-0022 AK2: Filtern über die angezeigten Felder."""
    bestand = erzeuge_seed()
    _zweiter_kunde_mit_bestellung(bestand, "Andere AG", "999888", date(2026, 1, 1))
    auto = AutoSpeicher(bestand, tmp_path / "firma.scgr")
    reiter = BestellungReiter(bestand, auto_speicher=auto)
    reiter._liste._filter.setText("999888")
    assert _sichtbare_nummern(reiter) == ["999888"]
    reiter._liste._filter.setText("andere")
    assert _sichtbare_nummern(reiter) == ["999888"]


def test_bestellliste_blendet_inaktive_aus(qapp, tmp_path):
    """S-0018 AK5: Standard nur aktive; der Filter greift über `_BestellZeile.aktiv`."""
    bestand = erzeuge_seed()
    _, zweite = _zweiter_kunde_mit_bestellung(bestand, "Andere AG", "777", date(2026, 1, 1))
    zweite.aktiv = False
    auto = AutoSpeicher(bestand, tmp_path / "firma.scgr")
    reiter = BestellungReiter(bestand, auto_speicher=auto)
    assert _sichtbare_nummern(reiter) == ["4500000001"]


def test_bestell_umschalter_zeigt_inaktive(qapp, tmp_path):
    """S-0018 AK5: Der Umschalter holt sie zurück."""
    bestand = erzeuge_seed()
    _, zweite = _zweiter_kunde_mit_bestellung(bestand, "Andere AG", "777", date(2026, 1, 1))
    zweite.aktiv = False
    auto = AutoSpeicher(bestand, tmp_path / "firma.scgr")
    reiter = BestellungReiter(bestand, auto_speicher=auto)
    reiter._liste._inaktive.setChecked(True)
    assert sorted(_sichtbare_nummern(reiter)) == ["4500000001", "777"]


def test_popup_bietet_nur_aktive_artikel(qapp, tmp_path):
    """S-0018 AK3: Ein deaktivierter Artikel erscheint nicht mehr im Picker."""
    reiter, bestand = _reiter(tmp_path)
    bestand.artikel[0].aktiv = False
    aktive = [a.artikelname for a in reiter._aktive_artikel()]
    assert bestand.artikel[0].artikelname not in aktive
    assert bestand.artikel[1].artikelname in aktive


def test_gueltige_tabelle_zeigt_obergrenze_verbraucht_und_rest(qapp, tmp_path):
    """S-0018 AK6: Die drei Spalten tragen den Verbrauchsstand je gültigem Artikel."""
    reiter, bestand = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)
    kopf = [
        reiter._gueltige_tabelle.horizontalHeaderItem(s).text()
        for s in range(reiter._gueltige_tabelle.columnCount())
    ]
    assert kopf[2:] == [
        ui_text("bestellung.spalte_obergrenze"),
        ui_text("bestellung.spalte_verbraucht"),
        ui_text("bestellung.spalte_rest"),
    ]
    # Seed: art-1 mit Mengen-Obergrenze 20, keine Rechnungen, also nichts verbraucht.
    assert format_betrag(Decimal("20")) in reiter._gueltige_tabelle.item(0, 2).text()
    assert reiter._gueltige_tabelle.item(0, 3).text() == format_betrag(Decimal("0"))
    assert reiter._gueltige_tabelle.item(0, 4).text() == format_betrag(Decimal("20"))


def test_gueltige_tabelle_ohne_obergrenze_zeigt_striche(qapp, tmp_path):
    """Ohne Grenze bleibt nichts zu verbrauchen; die Zellen behaupten keine Zahlen."""
    reiter, bestand = _reiter(tmp_path)
    for g in bestand.kunden[0].bestellungen[0].gueltige_artikel:
        g.obergrenze = None
    reiter._liste._tabelle.setCurrentCell(0, 0)
    assert reiter._gueltige_tabelle.item(0, 2).text() == "–"
    assert reiter._gueltige_tabelle.item(0, 3).text() == "–"
    assert reiter._gueltige_tabelle.item(0, 4).text() == "–"


# --- Deaktivieren als Regelfall (S-0021 AK1/AK4, 4T-0161) -------------------


def test_deaktivieren_ueber_die_maske_speichert(qapp, tmp_path):
    """S-0021 AK1: Das Deaktivieren ist der Regelweg, das harte Löschen die Ausnahme.

    Bis 4T-0161 setzte kein UI-Test `_aktiv.setChecked(False)`; geprüft war nur das Löschen.
    """
    reiter, bestand = _reiter(tmp_path)
    bestellung = bestand.kunden[0].bestellungen[0]
    reiter._liste._tabelle.setCurrentCell(0, 0)

    reiter._aktiv.setChecked(False)
    reiter._bestaetigen()

    assert bestellung.aktiv is False
    wieder = lade(tmp_path / "firma.scgr")
    assert wieder.kunden[0].bestellungen[0].aktiv is False


def test_deaktivierte_bestellung_verschwindet_aus_der_liste(qapp, tmp_path):
    """S-0021 AK1: „in der Standardliste ausgeblendet", die Wirkung des Deaktivierens."""
    reiter, bestand = _reiter(tmp_path)
    reiter._liste._tabelle.setCurrentCell(0, 0)

    reiter._aktiv.setChecked(False)
    reiter._bestaetigen()

    assert _sichtbare_nummern(reiter) == []


def test_deaktivierte_bestellung_bleibt_mit_ihren_daten_erhalten(qapp, tmp_path):
    """S-0021 AK1: „bleibt erhalten", Deaktivieren löscht nichts."""
    reiter, bestand = _reiter(tmp_path)
    bestellung = bestand.kunden[0].bestellungen[0]
    vorher = len(bestellung.gueltige_artikel)
    reiter._liste._tabelle.setCurrentCell(0, 0)

    reiter._aktiv.setChecked(False)
    reiter._bestaetigen()

    assert bestellung in bestand.kunden[0].bestellungen
    assert len(bestellung.gueltige_artikel) == vorher
