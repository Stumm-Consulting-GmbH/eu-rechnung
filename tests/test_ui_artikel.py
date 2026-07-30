"""Tests des Artikel-Reiters: Liste, Anlegen, Ändern, Löschen, Filter (4T-0082), offscreen."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from eu_rechnung.domain import Artikel, ArtikelTyp, Preis
from eu_rechnung.services import erzeuge_seed
from eu_rechnung.ui.artikel_reiter import ArtikelReiter
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.sprache import ui_text


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _zeile_von(reiter: ArtikelReiter, artikel: Artikel) -> int:
    """Zeilenindex eines Artikels in der (sortierten/gefilterten) Liste."""
    tabelle = reiter._liste._tabelle
    for zeile in range(tabelle.rowCount()):
        if tabelle.item(zeile, 0).data(Qt.UserRole) is artikel:
            return zeile
    return -1


def test_liste_zeigt_standardmaessig_nur_aktive(qapp):
    bestand = erzeuge_seed()
    bestand.artikel[0].aktiv = False
    reiter = ArtikelReiter(bestand)
    assert reiter._liste._tabelle.rowCount() == 1


def test_umschalter_zeigt_inaktive(qapp):
    bestand = erzeuge_seed()
    bestand.artikel[0].aktiv = False
    reiter = ArtikelReiter(bestand)
    reiter._liste._inaktive.setChecked(True)
    assert reiter._liste._tabelle.rowCount() == 2


def test_anlegen_fuegt_artikel_hinzu_und_speichert(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._neuer_artikel()
    reiter._name.setText("Zusatzleistung")
    reiter._betrag.setText("500,00")
    reiter._waehrung.setCurrentText("EUR")
    reiter._bestaetigen()
    neu = [a for a in bestand.artikel if a.artikelname == "Zusatzleistung"]
    assert len(neu) == 1
    assert neu[0].id  # systemvergebene id
    assert neu[0].vorschlagspreis.betrag == Decimal("500.00")
    assert neu[0].aktiv is True
    assert (tmp_path / "d.json").exists()


def test_anlegen_blockiert_bei_fehlendem_namen(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    vorher = len(bestand.artikel)
    reiter._neuer_artikel()
    reiter._name.setText("")
    reiter._betrag.setText("100")
    reiter._bestaetigen()
    assert len(bestand.artikel) == vorher
    assert reiter._fehler["name"].isHidden() is False


def test_anlegen_blockiert_bei_dublette(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._neuer_artikel()
    reiter._name.setText(bestand.artikel[0].artikelname)
    reiter._betrag.setText("100")
    reiter._bestaetigen()
    assert reiter._fehler["name"].isHidden() is False


def test_anlegen_blockiert_bei_ungueltigem_betrag(qapp):
    reiter = ArtikelReiter(erzeuge_seed())
    reiter._neuer_artikel()
    reiter._name.setText("Neuer Posten")
    reiter._betrag.setText("keine Zahl")
    reiter._bestaetigen()
    assert reiter._fehler["betrag"].isHidden() is False


def test_aendern_uebernimmt_werte(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    art = bestand.artikel[0]
    reiter._lade_in_maske(art)
    reiter._betrag.setText("1.500,00")
    reiter._bestaetigen()
    assert art.vorschlagspreis.betrag == Decimal("1500.00")


def test_knopf_hebt_sich_bei_aenderung_und_faellt_nach_bestaetigen(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._lade_in_maske(bestand.artikel[0])
    assert reiter._geaendert is False
    reiter._name.setText(bestand.artikel[0].artikelname + " (neu)")
    assert reiter._geaendert is True
    assert reiter._bestaetigen_knopf.styleSheet() != ""
    reiter._bestaetigen()
    assert reiter._geaendert is False
    assert reiter._bestaetigen_knopf.styleSheet() == ""


def test_loeschen_referenzierter_artikel_blockiert(qapp, tmp_path, monkeypatch):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    infos: list = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a))
    reiter._liste._tabelle.setCurrentCell(0, 0)  # beide Seed-Artikel sind referenziert
    vorher = len(bestand.artikel)
    reiter._loeschen()
    assert len(bestand.artikel) == vorher
    assert infos


def test_loeschen_unreferenzierter_artikel(qapp, tmp_path, monkeypatch):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    neu = Artikel(
        id="art-neu", artikelname="Loeschbar", vorschlagspreis=Preis(Decimal("10"), "EUR")
    )
    bestand.artikel.append(neu)
    reiter._fuelle_liste()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    reiter._liste._tabelle.setCurrentCell(_zeile_von(reiter, neu), 0)
    reiter._loeschen()
    assert neu not in bestand.artikel


def test_anlegen_uebernimmt_typ_mit_default_leistung(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    reiter._neuer_artikel()
    assert ArtikelTyp(reiter._typ.currentData()) is ArtikelTyp.LEISTUNG  # Default Leistung
    reiter._name.setText("Handbuch")
    reiter._betrag.setText("40,00")
    reiter._typ.setCurrentIndex(reiter._typ.findData(ArtikelTyp.PRODUKT))
    reiter._bestaetigen()
    neu = [a for a in bestand.artikel if a.artikelname == "Handbuch"][0]
    assert neu.typ is ArtikelTyp.PRODUKT


def test_aendern_uebernimmt_typ(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = ArtikelReiter(bestand, auto_speicher=AutoSpeicher(bestand, tmp_path / "d.json"))
    art = bestand.artikel[0]
    art.typ = ArtikelTyp.LEISTUNG
    reiter._lade_in_maske(art)
    assert ArtikelTyp(reiter._typ.currentData()) is ArtikelTyp.LEISTUNG  # aus dem Artikel vorbelegt
    reiter._typ.setCurrentIndex(reiter._typ.findData(ArtikelTyp.PRODUKT))
    reiter._bestaetigen()
    assert art.typ is ArtikelTyp.PRODUKT


def test_liste_zeigt_typ_spalte(qapp):
    bestand = erzeuge_seed()
    bestand.artikel[0].typ = ArtikelTyp.PRODUKT
    reiter = ArtikelReiter(bestand)
    tabelle = reiter._liste._tabelle
    kopf = [tabelle.horizontalHeaderItem(i).text() for i in range(tabelle.columnCount())]
    assert ui_text("artikel.feld_typ") in kopf
    zeile = _zeile_von(reiter, bestand.artikel[0])
    spalte = kopf.index(ui_text("artikel.feld_typ"))
    assert tabelle.item(zeile, spalte).text() == ui_text("artikel.typ_produkt")


# --- Währung stammt aus der Währungstabelle (S-0005 AK4, 4T-0159) -----------


def test_waehrungsauswahl_ist_geschlossen(qapp):
    """AK4: Freitext hätte eine Währung außerhalb der Tabelle zugelassen."""
    reiter = ArtikelReiter(erzeuge_seed())
    assert reiter._waehrung.isEditable() is False


def test_waehrungsauswahl_bietet_die_waehrungsliste(qapp):
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF", "GBP"]
    reiter = ArtikelReiter(bestand)
    reiter._neuer_artikel()
    eintraege = [reiter._waehrung.itemText(i) for i in range(reiter._waehrung.count())]
    assert eintraege == ["EUR", "CHF", "GBP"]


def test_bestandswaehrung_ausserhalb_der_liste_bleibt_sichtbar(qapp):
    """Ein gespeicherter Wert darf beim Öffnen nicht still auf die Standardwährung fallen.

    Dasselbe Muster wie bei der Kunden-Währung
    (`test_ui_kunde.py::test_entfernte_waehrung_bleibt_am_kunden_sichtbar`).
    """
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR"]
    bestand.einstellungen.standardwaehrung = "EUR"
    artikel = bestand.artikel[0]
    artikel.vorschlagspreis = Preis(Decimal("10.00"), "JPY")  # nicht (mehr) in der Liste
    reiter = ArtikelReiter(bestand)
    reiter._lade_in_maske(artikel)
    assert reiter._waehrung.currentText() == "JPY"
    assert reiter._geaendert is False


def test_bestandswaehrung_ausserhalb_der_liste_wird_beim_bestaetigen_gemeldet(qapp, tmp_path):
    """Sichtbar heißt nicht gültig: Der Befund erscheint feld-nah, statt still zu passieren."""
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR"]
    bestand.einstellungen.standardwaehrung = "EUR"
    artikel = bestand.artikel[0]
    artikel.vorschlagspreis = Preis(Decimal("10.00"), "JPY")
    auto = AutoSpeicher(bestand, tmp_path / "firma.json")
    reiter = ArtikelReiter(bestand, auto_speicher=auto)
    reiter._lade_in_maske(artikel)
    reiter._bestaetigen()
    assert reiter._fehler["waehrung"].isHidden() is False
    assert not (tmp_path / "firma.json").exists()


# --- Filtern und Sortieren (K2; S-0010 AK2 bis AK4, 4T-0161) ----------------


def _sichtbare_namen(reiter: ArtikelReiter) -> list[str]:
    """Die Artikelnamen der sichtbaren Zeilen, in ihrer Anzeige-Reihenfolge."""
    tabelle = reiter._liste._tabelle
    return [
        tabelle.item(z, 0).text()
        for z in range(tabelle.rowCount())
        if not tabelle.isRowHidden(z)
    ]


def _bestand_mit_artikeln(*namen_preise: tuple[str, str]) -> "object":
    """Ein Bestand mit genau den angegebenen Artikeln; der Seed hat zu wenige für Reihenfolge."""
    bestand = erzeuge_seed()
    bestand.artikel.clear()
    for i, (name, preis) in enumerate(namen_preise, start=1):
        bestand.artikel.append(
            Artikel(
                id=f"a-{i}",
                artikelname=name,
                vorschlagspreis=Preis(Decimal(preis), "EUR"),
            )
        )
    return bestand


def test_liste_ist_standardmaessig_alphabetisch_nach_name(qapp):
    """AK4: Ausgangszustand alphabetisch nach Name."""
    bestand = _bestand_mit_artikeln(("Zeta", "100.00"), ("Alpha", "200.00"), ("Mitte", "50.00"))
    reiter = ArtikelReiter(bestand)
    assert _sichtbare_namen(reiter) == ["Alpha", "Mitte", "Zeta"]


def test_sortierung_nach_preis_ist_numerisch(qapp):
    """AK3: Der Preis sortiert nach Zahlwert, nicht nach Anzeigetext.

    Alphabetisch käme „1.000,00" vor „90,00"; der `sortierwert` der Spalte verhindert das.
    Genau dafür gibt es ihn, und genau das war ungetestet.
    """
    bestand = _bestand_mit_artikeln(("A", "1000.00"), ("B", "90.00"), ("C", "200.00"))
    reiter = ArtikelReiter(bestand)
    reiter._liste._tabelle.sortByColumn(1, Qt.AscendingOrder)
    assert _sichtbare_namen(reiter) == ["B", "C", "A"]


def test_sortierung_nach_name_absteigend(qapp):
    """AK3: Ein zweiter Klick auf den Spaltenkopf dreht die Richtung."""
    bestand = _bestand_mit_artikeln(("Alpha", "1.00"), ("Zeta", "2.00"))
    reiter = ArtikelReiter(bestand)
    reiter._liste._tabelle.sortByColumn(0, Qt.DescendingOrder)
    assert _sichtbare_namen(reiter) == ["Zeta", "Alpha"]


def test_filter_grenzt_die_liste_ein(qapp):
    """AK2: Der Textfilter wirkt über die angezeigten Felder (K2)."""
    bestand = _bestand_mit_artikeln(("Beratung", "1.00"), ("Schulung", "2.00"))
    reiter = ArtikelReiter(bestand)
    reiter._liste._filter.setText("schul")  # ohne Rücksicht auf Groß-/Kleinschreibung
    assert _sichtbare_namen(reiter) == ["Schulung"]


def test_filter_trifft_auch_preis_und_waehrung(qapp):
    """AK2 nennt Name, Preis und Währung; der gemeinsame Baustein sucht über alle Spalten."""
    bestand = _bestand_mit_artikeln(("Beratung", "1234.00"), ("Schulung", "99.00"))
    reiter = ArtikelReiter(bestand)
    reiter._liste._filter.setText("1.234")  # Anzeigetext des Preises in deutscher Notation
    assert _sichtbare_namen(reiter) == ["Beratung"]


def test_leerer_filter_zeigt_alles_wieder(qapp):
    bestand = _bestand_mit_artikeln(("Beratung", "1.00"), ("Schulung", "2.00"))
    reiter = ArtikelReiter(bestand)
    reiter._liste._filter.setText("schul")
    reiter._liste._filter.setText("")
    assert _sichtbare_namen(reiter) == ["Beratung", "Schulung"]
