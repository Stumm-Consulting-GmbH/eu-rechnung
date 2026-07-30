"""Tests des Kunde-Reiters: Liste, Anlegen, Ändern, Löschen, Pflicht-Markierung (4T-0083)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from eu_rechnung.domain import Adresse, Kunde
from eu_rechnung.services import erzeuge_seed
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.kunde_reiter import KundeReiter


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _fuelle_pflichtfelder(reiter: KundeReiter, name: str) -> None:
    reiter._edits["name"].setText(name)
    reiter._edits["land"].setText("DE")
    reiter._edits["strasse"].setText("Hauptstr 1")
    reiter._edits["plz"].setText("10000")
    reiter._edits["ort"].setText("Berlin")
    reiter._edits["email"].setText("neu@kunde.de")


def test_liste_zeigt_aktive_kunden(qapp):
    reiter = KundeReiter(erzeuge_seed())
    assert reiter._liste._tabelle.rowCount() == 1


def test_neuer_kunde_belegt_kundennummer_vor(qapp):
    bestand = erzeuge_seed()  # naechste_debitornummer = 10003
    reiter = KundeReiter(bestand)
    reiter._neuer_kunde()
    assert reiter._edits["kundennummer"].text() == "D10003"


def test_anlegen_fuegt_kunde_hinzu_und_erhoeht_zaehler(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    vorher = bestand.einstellungen.naechste_debitornummer
    reiter._neuer_kunde()
    _fuelle_pflichtfelder(reiter, "Neukunde GmbH")
    reiter._bestaetigen()
    neu = [k for k in bestand.kunden if k.name == "Neukunde GmbH"]
    assert len(neu) == 1
    assert neu[0].id
    assert bestand.einstellungen.naechste_debitornummer == vorher + 1
    assert (tmp_path / "d.json").exists()


def test_ueberschriebene_kundennummer_laesst_zaehler_unveraendert(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    vorher = bestand.einstellungen.naechste_debitornummer
    reiter._neuer_kunde()
    _fuelle_pflichtfelder(reiter, "Manuelle Nummer GmbH")
    reiter._edits["kundennummer"].setText("D88888")  # Vorbelegung überschrieben
    reiter._bestaetigen()
    neu = [k for k in bestand.kunden if k.name == "Manuelle Nummer GmbH"]
    assert len(neu) == 1
    assert neu[0].kundennummer == "D88888"
    # Überschreiben verbraucht keine automatische Nummer (S-0043 AK3)
    assert bestand.einstellungen.naechste_debitornummer == vorher


def test_anlegen_blockiert_bei_fehlendem_pflichtfeld(qapp, tmp_path):
    bestand = erzeuge_seed()  # xrechnung_aktiv = True -> Adresse Pflicht
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    vorher = len(bestand.kunden)
    reiter._neuer_kunde()
    reiter._edits["name"].setText("Ohne Adresse")  # Straße/PLZ/Ort/E-Mail leer
    reiter._bestaetigen()
    assert len(bestand.kunden) == vorher
    assert reiter._fehler["strasse"].isHidden() is False


def test_anlegen_blockiert_bei_doppelter_nummer(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._neuer_kunde()
    _fuelle_pflichtfelder(reiter, "Zweitkunde")
    reiter._edits["kundennummer"].setText(bestand.kunden[0].kundennummer)  # existiert
    reiter._bestaetigen()
    assert reiter._fehler["kundennummer"].isHidden() is False


def test_pflicht_sterne_folgen_firma_schalter(qapp):
    bestand = erzeuge_seed()  # xrechnung_aktiv = True
    reiter = KundeReiter(bestand)
    reiter._lade_in_maske(bestand.kunden[0])
    assert reiter._pflicht["strasse"][0].text().endswith("*")  # bei xr Pflicht
    bestand.eigene_firma.xrechnung_aktiv = False
    reiter._aktualisiere_pflicht()
    assert not reiter._pflicht["strasse"][0].text().endswith("*")
    assert reiter._pflicht["name"][0].text().endswith("*")  # immer Pflicht


def test_ustid_stern_bei_reverse_charge(qapp):
    reiter = KundeReiter(erzeuge_seed())
    reiter._neuer_kunde()
    reiter._reverse_charge.setChecked(False)
    assert not reiter._pflicht["umsatzsteuer_id"][0].text().endswith("*")
    reiter._reverse_charge.setChecked(True)
    assert reiter._pflicht["umsatzsteuer_id"][0].text().endswith("*")


def test_aendern_uebernimmt_werte(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    kunde = bestand.kunden[0]
    reiter._lade_in_maske(kunde)
    reiter._edits["name"].setText("Geänderter Name GmbH")
    reiter._bestaetigen()
    assert kunde.name == "Geänderter Name GmbH"


def test_knopf_hebt_sich_bei_aenderung(qapp):
    reiter = KundeReiter(erzeuge_seed())
    reiter._lade_in_maske(reiter._datenbestand.kunden[0])
    assert reiter._geaendert is False
    reiter._edits["name"].setText("Neu")
    assert reiter._geaendert is True
    assert reiter._bestaetigen_knopf.styleSheet() != ""


def test_loeschen_kunde_mit_bestellungen_blockiert(qapp, tmp_path, monkeypatch):
    bestand = erzeuge_seed()  # Seed-Kunde hat eine Bestellung
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    infos: list = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a))
    reiter._liste._tabelle.setCurrentCell(0, 0)
    vorher = len(bestand.kunden)
    reiter._loeschen()
    assert len(bestand.kunden) == vorher
    assert infos


def test_loeschen_kunde_ohne_bestellungen(qapp, tmp_path, monkeypatch):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    neu = Kunde(
        id="k-neu",
        kundennummer="D50000",
        name="Leerkunde",
        adresse=Adresse("", "", "", "DE"),
        email="",
        umsatzsteuer_id="",
        reverse_charge=False,
    )
    bestand.kunden.append(neu)
    reiter._fuelle_liste()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    tabelle = reiter._liste._tabelle
    zeile = next(
        z for z in range(tabelle.rowCount()) if tabelle.item(z, 0).data(Qt.UserRole) is neu
    )
    tabelle.setCurrentCell(zeile, 0)
    reiter._loeschen()
    assert neu not in bestand.kunden


# --- 4T-0103: Anschreiben-Überschreibung (S-0036) --------------------------


def test_kunde_anschreiben_erbt_vom_standard(qapp, tmp_path):
    bestand = erzeuge_seed()
    bestand.einstellungen.standard_anschreibentext = "STANDARD"
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._neuer_kunde()
    assert reiter._anschreiben._text.toPlainText() == "STANDARD"  # geerbte Vorschau
    assert "globaler Standard" in reiter._anschreiben._hinweis.text()


def test_kunde_anschreiben_ueberschreiben_speichert(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._neuer_kunde()
    _fuelle_pflichtfelder(reiter, "Anschreib GmbH")
    reiter._anschreiben._schalter.setChecked(True)
    reiter._anschreiben._text.setPlainText("Eigener Kundentext")
    reiter._bestaetigen()
    neu = next(k for k in bestand.kunden if k.name == "Anschreib GmbH")
    assert neu.anschreibentext == "Eigener Kundentext"


def test_kunde_anschreiben_erbt_bleibt_none(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._neuer_kunde()
    _fuelle_pflichtfelder(reiter, "Erben GmbH")
    reiter._bestaetigen()  # Schalter aus (Default): erbt
    neu = next(k for k in bestand.kunden if k.name == "Erben GmbH")
    assert neu.anschreibentext is None


# --- 4T-0104: Individuelle Felder (S-0038, S-0040) -------------------------


def test_kunde_individuelle_felder_speichern(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._neuer_kunde()
    _fuelle_pflichtfelder(reiter, "Felder GmbH")
    name, aktiv, wert = reiter._felder._plaetze[0]
    name.setText("Projekt")
    aktiv.setChecked(True)
    wert.setText("P-42")
    reiter._bestaetigen()
    neu = next(k for k in bestand.kunden if k.name == "Felder GmbH")
    assert [(f.name, f.aktiv, f.wert) for f in neu.individuelle_felder] == [
        ("Projekt", True, "P-42")
    ]


# --- Währung mit Vererbung (S-0062 AK3, 4T-0132) ---------------------------


def test_waehrung_bietet_erbt_und_die_liste_an(qapp):
    """AK3: „erbt" ist die Vorgabe und nennt den Wert, der dann greift."""
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    bestand.einstellungen.standardwaehrung = "EUR"
    reiter = KundeReiter(bestand)
    eintraege = [
        (reiter._waehrung._auswahl.itemText(i), reiter._waehrung._auswahl.itemData(i))
        for i in range(reiter._waehrung._auswahl.count())
    ]
    assert eintraege == [("erbt (EUR)", None), ("EUR", "EUR"), ("CHF", "CHF")]
    assert reiter._waehrung.wert() is None  # neuer Kunde erbt


def test_erbt_eintrag_folgt_der_standardwaehrung(qapp):
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    bestand.einstellungen.standardwaehrung = "CHF"
    reiter = KundeReiter(bestand)
    assert reiter._waehrung._auswahl.itemText(0) == "erbt (CHF)"


def test_gesetzte_waehrung_wird_geladen_und_gespeichert(qapp, tmp_path):
    from eu_rechnung.persistence import lade

    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = KundeReiter(bestand, auto_speicher=auto)
    kunde = bestand.kunden[0]
    reiter._lade_in_maske(kunde)
    reiter._waehrung._auswahl.setCurrentIndex(reiter._waehrung._auswahl.findData("CHF"))
    reiter._bestaetigen()
    assert kunde.waehrung == "CHF"
    assert lade(tmp_path / "d.json").kunden[0].waehrung == "CHF"

    reiter._lade_in_maske(kunde)
    assert reiter._waehrung.wert() == "CHF"


def test_zurueck_auf_erbt_setzt_none(qapp, tmp_path):
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = KundeReiter(bestand, auto_speicher=auto)
    kunde = bestand.kunden[0]
    kunde.waehrung = "EUR"
    reiter._lade_in_maske(kunde)
    reiter._waehrung._auswahl.setCurrentIndex(0)  # erbt
    reiter._bestaetigen()
    assert kunde.waehrung is None


def test_entfernte_waehrung_bleibt_am_kunden_sichtbar(qapp):
    """Ein gespeicherter Wert darf beim Öffnen nicht still auf „erbt" fallen."""
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR"]  # JPY ist nicht (mehr) in der Liste
    kunde = bestand.kunden[0]
    kunde.waehrung = "JPY"
    reiter = KundeReiter(bestand)
    reiter._lade_in_maske(kunde)
    assert reiter._waehrung.wert() == "JPY"
    assert reiter._geaendert is False


def test_waehrung_laden_markiert_nicht_als_geaendert(qapp):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand)
    reiter._lade_in_maske(bestand.kunden[0])
    assert reiter._geaendert is False


# --- Rechnungssprache (S-0082 AK1/AK3, 4T-0137) ----------------------------


def test_sprache_bietet_erbt_und_die_fuenf_sprachen(qapp):
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand)
    eintraege = [
        (reiter._sprache._auswahl.itemText(i), reiter._sprache._auswahl.itemData(i))
        for i in range(reiter._sprache._auswahl.count())
    ]
    assert eintraege[0] == ("erbt (Deutsch)", None)
    assert eintraege[1:] == [
        ("Deutsch", "de"),
        ("English", "en"),
        ("Italiano", "it"),
        ("Français", "fr"),
        ("Español", "es"),
    ]


def test_sprache_nennt_den_rueckfall_als_herkunft(qapp):
    """AK3: Der Kunde ist die oberste Ebene; er erbt vom festen Rückfall Deutsch."""
    bestand = erzeuge_seed()
    reiter = KundeReiter(bestand)
    assert reiter._sprache._hinweis.text() == "Erbt von: Vorgabe"


def test_gesetzte_sprache_wird_geladen_und_gespeichert(qapp, tmp_path):
    from eu_rechnung.persistence import lade

    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = KundeReiter(bestand, auto_speicher=auto)
    kunde = bestand.kunden[0]
    reiter._lade_in_maske(kunde)
    reiter._sprache._auswahl.setCurrentIndex(reiter._sprache._auswahl.findData("it"))
    reiter._bestaetigen()
    assert kunde.rechnungssprache == "it"
    assert lade(tmp_path / "d.json").kunden[0].rechnungssprache == "it"

    reiter._lade_in_maske(kunde)
    assert reiter._sprache.wert() == "it"


def test_sprache_zurueck_auf_erbt_setzt_none(qapp, tmp_path):
    bestand = erzeuge_seed()
    auto = AutoSpeicher(bestand, tmp_path / "d.json")
    reiter = KundeReiter(bestand, auto_speicher=auto)
    kunde = bestand.kunden[0]
    kunde.rechnungssprache = "fr"
    reiter._lade_in_maske(kunde)
    reiter._sprache._auswahl.setCurrentIndex(0)  # erbt
    reiter._bestaetigen()
    assert kunde.rechnungssprache is None


# --- Filtern, Sortieren, Aktiv-Umschalter (K2; S-0016, S-0012; 4T-0161) -----


def _sichtbare_namen(reiter: KundeReiter) -> list[str]:
    """Die Kundennamen der sichtbaren Zeilen (Spalte 1), in Anzeige-Reihenfolge."""
    tabelle = reiter._liste._tabelle
    return [
        tabelle.item(z, 1).text()
        for z in range(tabelle.rowCount())
        if not tabelle.isRowHidden(z)
    ]


def _bestand_mit_kunden(*eintraege: tuple[str, str, str]) -> "object":
    """Ein Bestand mit genau den angegebenen Kunden (Nummer, Name, Ort)."""
    bestand = erzeuge_seed()
    bestand.kunden.clear()
    for i, (nummer, name, ort) in enumerate(eintraege, start=1):
        bestand.kunden.append(
            Kunde(
                id=f"k-{i}",
                kundennummer=nummer,
                name=name,
                adresse=Adresse(strasse="", plz="", ort=ort, land="DE"),
                email="",
                umsatzsteuer_id="",
                reverse_charge=False,
            )
        )
    return bestand


def test_kundenliste_ist_standardmaessig_alphabetisch_nach_name(qapp):
    """S-0016 AK4: Ausgangszustand alphabetisch nach Name, nicht nach Kundennummer."""
    bestand = _bestand_mit_kunden(
        ("D10001", "Zeta AG", "Berlin"),
        ("D10002", "Alpha GmbH", "Hamburg"),
        ("D10003", "Mitte KG", "Köln"),
    )
    reiter = KundeReiter(bestand)
    assert _sichtbare_namen(reiter) == ["Alpha GmbH", "Mitte KG", "Zeta AG"]


def test_kundenliste_sortiert_nach_kundennummer(qapp):
    """S-0016 AK3: Sortieren über die Spaltenköpfe, hier die erste Spalte."""
    bestand = _bestand_mit_kunden(
        ("D10003", "Alpha GmbH", "Berlin"), ("D10001", "Zeta AG", "Hamburg")
    )
    reiter = KundeReiter(bestand)
    reiter._liste._tabelle.sortByColumn(0, Qt.AscendingOrder)
    assert _sichtbare_namen(reiter) == ["Zeta AG", "Alpha GmbH"]


def test_kundenfilter_trifft_nummer_name_und_ort(qapp):
    """S-0016 AK2: Filtern über alle drei angezeigten Felder."""
    bestand = _bestand_mit_kunden(
        ("D10001", "Zeta AG", "Berlin"), ("D10002", "Alpha GmbH", "Hamburg")
    )
    reiter = KundeReiter(bestand)
    for muster, erwartet in [("D10002", "Alpha GmbH"), ("zeta", "Zeta AG"), ("hamburg", "Alpha GmbH")]:
        reiter._liste._filter.setText(muster)
        assert _sichtbare_namen(reiter) == [erwartet], f"Filter „{muster}“"


def test_kundenliste_blendet_inaktive_aus(qapp):
    """S-0012 AK5: Standard nur aktive. Der Seed hält nur einen aktiven Kunden, an dem sich
    das Ausblenden nicht beobachten lässt; deshalb ein eigener Bestand."""
    bestand = _bestand_mit_kunden(("D10001", "Aktiv AG", "Berlin"), ("D10002", "Inaktiv AG", "Köln"))
    bestand.kunden[1].aktiv = False
    reiter = KundeReiter(bestand)
    assert _sichtbare_namen(reiter) == ["Aktiv AG"]


def test_kunden_umschalter_zeigt_inaktive(qapp):
    """S-0012 AK5: Der Umschalter holt sie zurück."""
    bestand = _bestand_mit_kunden(("D10001", "Aktiv AG", "Berlin"), ("D10002", "Inaktiv AG", "Köln"))
    bestand.kunden[1].aktiv = False
    reiter = KundeReiter(bestand)
    reiter._liste._inaktive.setChecked(True)
    assert _sichtbare_namen(reiter) == ["Aktiv AG", "Inaktiv AG"]
