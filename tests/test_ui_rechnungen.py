"""Tests des Rechnungen-Reiters: Leerzustand-Hinweis und Stammdaten-Aktualität (4T-0086).

Prüft, dass der Reiter bei leeren Stammdaten einen klaren Hinweis zeigt und „Neue
Rechnung" sperrt, bei vorhandenen Stammdaten frei gibt, und dass während der Session neu
gepflegte Kunden und Bestellungen nach dem Auffrischen erscheinen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from eu_rechnung.domain import Adresse, Bestellung, Kunde, Position, RechnungsStatus
from eu_rechnung.services import (
    erzeuge_leeren_datenbestand,
    erzeuge_seed,
    lege_rechnung_an,
    vorbelege_rechnung,
)
from eu_rechnung.ui.rechnungen_reiter import RechnungenReiter


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_leerzustand_hinweis_ohne_kunden(qapp):
    reiter = RechnungenReiter(erzeuge_leeren_datenbestand())
    assert reiter._hinweis.isHidden() is False  # klarer Hinweis sichtbar
    assert reiter._neu_knopf.isEnabled() is False  # „Neue Rechnung" gesperrt


def test_kein_hinweis_mit_stammdaten(qapp):
    reiter = RechnungenReiter(erzeuge_seed())
    assert reiter._hinweis.isHidden() is True
    assert reiter._neu_knopf.isEnabled() is True


def test_aktualisierung_zeigt_neu_gepflegte_stammdaten(qapp):
    bestand = erzeuge_leeren_datenbestand()
    reiter = RechnungenReiter(bestand)
    assert reiter._kunde_box.count() == 0
    bestellung = Bestellung(
        id="b1",
        bestellnummer="B-1",
        beginn_datum=date(2026, 5, 1),
        ende_datum=date(2026, 5, 31),
        zahlungsfrist=30,
        zahlungsbedingung="30 Tage",
    )
    kunde = Kunde(
        id="k1",
        kundennummer="D1",
        name="Neu GmbH",
        adresse=Adresse(strasse="", plz="", ort="", land="DE"),
        email="",
        umsatzsteuer_id="",
        reverse_charge=False,
        bestellungen=[bestellung],
    )
    bestand.kunden.append(kunde)
    reiter._aktualisiere_stammdaten()  # löst im laufenden Programm das showEvent aus
    assert reiter._kunde_box.count() == 1
    assert reiter._hinweis.isHidden() is True
    assert reiter._neu_knopf.isEnabled() is True


def test_neuer_artikel_erscheint_in_der_maske_nach_auffrischen(qapp):
    """Fund aus Cluster 4 (S-0024 AK7): Ein im Artikel-Reiter nach dem Aufbau des
    Rechnungen-Reiters angelegter Artikel muss ohne Neustart in „Position aus Artikel"
    erscheinen. Die Maske hielt bis dahin die Artikelliste vom Aufbauzeitpunkt."""
    from decimal import Decimal

    from eu_rechnung.domain import Artikel, ArtikelTyp, Preis

    bestand = erzeuge_seed()
    reiter = RechnungenReiter(bestand)
    neu = Artikel(
        id="neu-1",
        artikelname="Frisch angelegt",
        vorschlagspreis=Preis(Decimal("50.00"), "EUR"),
        typ=ArtikelTyp.PRODUKT,
        aktiv=True,
    )
    bestand.artikel.append(neu)
    assert neu not in reiter._maske._aktive_artikel()  # vor dem Auffrischen unbekannt

    reiter._aktualisiere_stammdaten()  # das showEvent im laufenden Programm

    assert neu in reiter._maske._aktive_artikel()


def test_geloeschter_artikel_verschwindet_aus_der_maske_nach_auffrischen(qapp):
    """Kehrseite desselben Funds: Ein im Artikel-Reiter gelöschter Artikel darf in
    „Position aus Artikel" nicht mehr angeboten werden. Auch das ist eine Änderung der
    Listenstruktur, die die kopierte Artikelliste der Maske ohne Auffrischen nicht sah."""
    bestand = erzeuge_seed()
    reiter = RechnungenReiter(bestand)
    weg = bestand.artikel[0]
    bestand.artikel.remove(weg)
    assert weg in reiter._maske._aktive_artikel()  # Kopie kennt ihn noch

    reiter._aktualisiere_stammdaten()

    assert weg not in reiter._maske._aktive_artikel()


# --- 4T-0100: eingebettete Maske, Anlegen, Liste ---------------------------


def test_maske_ist_eingebettetes_qwidget(qapp):
    """Die Maske ist ein eingebetteter Detailbereich, kein modales Popup mehr (S-0024)."""
    reiter = RechnungenReiter(erzeuge_seed())
    assert isinstance(reiter._maske, QWidget)
    assert not isinstance(reiter._maske, QDialog)


def test_maske_im_leerzustand_gesperrt(qapp):
    reiter = RechnungenReiter(erzeuge_leeren_datenbestand())
    assert reiter._maske.rechnung is None
    assert reiter._maske.isEnabled() is False  # ohne gewählte Bestellung gesperrt


def test_neue_rechnung_aktiviert_und_belegt_maske(qapp):
    reiter = RechnungenReiter(erzeuge_seed())
    reiter._neue_rechnung()
    assert reiter._maske.ist_neu is True
    assert reiter._maske.rechnung is not None
    assert reiter._maske.isEnabled() is True
    assert reiter._maske._nummer.text() == "2026-10001"  # aus der Vorbelegung


def test_anlegen_ueber_maske_erscheint_in_liste(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = RechnungenReiter(bestand, daten_pfad=tmp_path / "d.json")
    reiter._neue_rechnung()
    reiter._maske._pos_tabelle.item(0, 1).setText("2")  # eine Menge eintragen
    reiter._maske._bestaetigen()  # prüft, warnt (keine), meldet an den Reiter
    bestellung = bestand.kunden[0].bestellungen[0]
    assert len(bestellung.rechnungen) == 1
    assert reiter._liste._tabelle.rowCount() == 1
    # Nach dem Anlegen führt die Maske die Rechnung im Ändern-Modus weiter (4T-0101).
    assert reiter._maske.ist_neu is False
    assert reiter._maske.rechnung is not None


def test_feld_nahe_validierung_bei_leerer_nummer(qapp, tmp_path):
    bestand = erzeuge_seed()
    reiter = RechnungenReiter(bestand, daten_pfad=tmp_path / "d.json")
    reiter._neue_rechnung()
    reiter._maske._pos_tabelle.item(0, 1).setText("1")  # Menge, damit nur die Nummer fehlt
    reiter._maske._nummer.setText("")  # Pflichtfeld leeren
    reiter._maske._bestaetigen()
    assert reiter._maske._fehler["rechnungsnummer"].isHidden() is False  # Hinweis am Feld
    assert bestand.kunden[0].bestellungen[0].rechnungen == []  # nichts angelegt


def test_liste_sortiert_neueste_zuerst(qapp, tmp_path):
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    daten = tmp_path / "d.json"
    r1 = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 1, 15))
    r1.positionen = [Position("art-1", "A", Decimal("1"), Decimal("100.00"), Decimal("100.00"))]
    lege_rechnung_an(bestand, bestellung, r1, pfad=daten)
    r2 = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 6, 20))
    r2.positionen = [Position("art-1", "A", Decimal("1"), Decimal("100.00"), Decimal("100.00"))]
    lege_rechnung_an(bestand, bestellung, r2, pfad=daten)
    reiter = RechnungenReiter(bestand, daten_pfad=daten)
    tabelle = reiter._liste._tabelle
    assert tabelle.item(0, 0).text() == r2.rechnungsnummer  # neueste zuerst (S-0028)


def test_erzeugt_anzeige_in_lokaler_zeit(qapp):
    """„Zuletzt erzeugt am" wird aus dem UTC-Stempel in lokale Zeit umgerechnet."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    stempel = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    rechnung.zuletzt_erzeugt_am = stempel
    erwartet = stempel.astimezone().strftime("%d.%m.%Y %H:%M")
    assert RechnungenReiter._erzeugt_text(rechnung) == erwartet


# --- 4T-0101: Ändern und Löschen -------------------------------------------


def _reiter_mit_rechnung(tmp_path):
    """Reiter auf einem Seed mit genau einer angelegten Rechnung (Einzelpreis = Bestellwert)."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    daten = tmp_path / "d.json"
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = [
        Position("art-1", "A", Decimal("1"), Decimal("1200.00"), Decimal("1200.00"))
    ]
    lege_rechnung_an(bestand, bestellung, rechnung, pfad=daten)
    reiter = RechnungenReiter(bestand, daten_pfad=daten)
    return reiter, bestellung, rechnung


def test_auswahl_laedt_rechnung_zum_aendern(qapp, tmp_path):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)
    reiter._liste.waehle_objekt(rechnung)  # Klick auf die Zeile
    assert reiter._maske.ist_neu is False
    assert reiter._maske._nummer.text() == rechnung.rechnungsnummer
    assert reiter._maske.rechnung is not rechnung  # Maske arbeitet auf einer Kopie


def test_aendern_speichert_und_id_bleibt(qapp, tmp_path):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)
    alte_id = rechnung.id
    reiter._liste.waehle_objekt(rechnung)
    reiter._maske._zahlung.setText("Sofort netto")
    reiter._maske._bestaetigen()
    aktualisiert = bestellung.rechnungen[0]
    assert aktualisiert.zahlungsbedingung == "Sofort netto"
    assert aktualisiert.id == alte_id  # id bleibt unverändert (S-0026)


def test_verwerfen_beim_aendern_laesst_original_unberuehrt(qapp, tmp_path):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)
    reiter._liste.waehle_objekt(rechnung)
    reiter._maske._pos_tabelle.item(0, 1).setText("9")  # Menge in der Kopie ändern
    reiter._maske._verwerfen()
    # Das Original bleibt unberührt, weil die Maske auf einer Kopie arbeitet (S-0026)
    assert rechnung.positionen[0].menge == Decimal("1")


def test_loeschen_entfernt_rechnung(qapp, tmp_path, monkeypatch):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)
    reiter._liste.waehle_objekt(rechnung)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    reiter._loeschen()
    assert bestellung.rechnungen == []
    assert reiter._liste._tabelle.rowCount() == 0


def test_loeschen_abbruch_behaelt_rechnung(qapp, tmp_path, monkeypatch):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)
    reiter._liste.waehle_objekt(rechnung)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    reiter._loeschen()
    assert bestellung.rechnungen == [rechnung]  # nichts gelöscht


def test_loeschen_erzeugt_weist_auf_dateien_hin(qapp, tmp_path, monkeypatch):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)
    rechnung.status = RechnungsStatus.ERZEUGT
    reiter._liste.waehle_objekt(rechnung)
    erfasst = {}

    def frage(parent, titel, text, *args, **kwargs):
        erfasst["text"] = text
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "question", frage)
    reiter._loeschen()
    assert "unberührt" in erfasst["text"]  # Hinweis auf erzeugte Dateien (S-0027)


# --- 4T-0108: Eindeutigkeits-Warnung bei doppelter Rechnungsnummer (S-0045) --


def test_warnung_bei_doppelter_nummer_speichert_bei_ja(qapp, tmp_path, monkeypatch):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)  # bestehende Rechnung
    reiter._neue_rechnung()
    reiter._maske._nummer.setText(rechnung.rechnungsnummer)  # dieselbe Nummer -> Dublette
    reiter._maske._pos_tabelle.item(0, 1).setText("1")  # Menge; Preis = Bestellwert (keine Positions-Warnung)
    gerufen = {"n": 0}

    def warn(*a, **k):
        gerufen["n"] += 1
        return QMessageBox.Yes

    monkeypatch.setattr(QMessageBox, "warning", warn)
    reiter._maske._bestaetigen()
    assert gerufen["n"] == 1  # Dubletten-Warnung gezeigt (AK1)
    assert len(bestellung.rechnungen) == 2  # trotz Warnung gespeichert (AK2, Warn-statt-Sperr)


def test_warnung_bei_doppelter_nummer_bricht_bei_nein_ab(qapp, tmp_path, monkeypatch):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)
    reiter._neue_rechnung()
    reiter._maske._nummer.setText(rechnung.rechnungsnummer)  # Dublette
    reiter._maske._pos_tabelle.item(0, 1).setText("1")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)
    reiter._maske._bestaetigen()
    assert len(bestellung.rechnungen) == 1  # abgelehnt, nichts gespeichert


def test_keine_warnung_bei_eindeutiger_nummer(qapp, tmp_path, monkeypatch):
    reiter, bestellung, rechnung = _reiter_mit_rechnung(tmp_path)
    reiter._neue_rechnung()  # eindeutige, fortgeschriebene Vorbelegung
    reiter._maske._pos_tabelle.item(0, 1).setText("1")
    gerufen = {"n": 0}

    def warn(*a, **k):
        gerufen["n"] += 1
        return QMessageBox.Yes

    monkeypatch.setattr(QMessageBox, "warning", warn)
    reiter._maske._bestaetigen()
    assert gerufen["n"] == 0  # keine Warnung (AK3)
    assert len(bestellung.rechnungen) == 2  # gespeichert


# --- Deaktivierte Kunden und Bestellungen (S-0015 AK1, S-0024, 4T-0159) -----


def _bestand_mit_rechnung(tmp_path):
    """Seed plus eine angelegte Rechnung; liefert (bestand, kunde, bestellung, rechnung, pfad)."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    daten = tmp_path / "d.json"
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 1, 15))
    rechnung.positionen = [
        Position("art-1", "A", Decimal("1"), Decimal("100.00"), Decimal("100.00"))
    ]
    lege_rechnung_an(bestand, bestellung, rechnung, pfad=daten)
    return bestand, kunde, bestellung, rechnung, daten


def test_deaktivierter_kunde_wird_nicht_mehr_angeboten(qapp, tmp_path):
    """AK1: Genau das ist der Zweck des Deaktivierens."""
    bestand, kunde, _, _, daten = _bestand_mit_rechnung(tmp_path)
    zweiter = Kunde(
        id="k-2",
        kundennummer="10002",
        name="Zweiter Kunde",
        adresse=Adresse(strasse="", plz="", ort="", land="DE"),
        email="z@example.org",
        umsatzsteuer_id="",
        reverse_charge=False,
    )
    bestand.kunden.append(zweiter)
    kunde.aktiv = False
    reiter = RechnungenReiter(bestand, daten_pfad=daten)
    angeboten = [reiter._kunde_box.itemData(i) for i in range(reiter._kunde_box.count())]
    assert kunde not in angeboten
    assert zweiter in angeboten


def test_absprung_erreicht_die_rechnung_eines_deaktivierten_kunden(qapp, tmp_path):
    """AK4: „bleibt aber mit Bestellungen und Rechnungen erhalten" (S-0015 AK1, zweiter Teil).

    Ohne den Zusatz-Weg fände `_waehle_in_box` den Kunden nicht, die Auswahl bliebe stumm
    stehen und die Liste zeigte eine andere Rechnung als die Maske.
    """
    bestand, kunde, bestellung, rechnung, daten = _bestand_mit_rechnung(tmp_path)
    kunde.aktiv = False
    reiter = RechnungenReiter(bestand, daten_pfad=daten)

    reiter.zeige_objekt(rechnung)

    assert reiter._kunde_box.currentData() is kunde
    assert reiter._bestellung_box.currentData() is bestellung
    assert reiter._markierte_rechnung() is rechnung


def test_absprung_erreicht_die_rechnung_einer_deaktivierten_bestellung(qapp, tmp_path):
    """Derselbe Weg für die Bestellungs-Auswahl, die schon vor 4T-0159 gefiltert hat."""
    bestand, kunde, bestellung, rechnung, daten = _bestand_mit_rechnung(tmp_path)
    bestellung.aktiv = False
    reiter = RechnungenReiter(bestand, daten_pfad=daten)

    reiter.zeige_objekt(rechnung)

    assert reiter._bestellung_box.currentData() is bestellung
    assert reiter._markierte_rechnung() is rechnung


def test_auffrischen_haelt_den_deaktivierten_kunden_der_offenen_rechnung(qapp, tmp_path):
    """Ein `showEvent` darf dem Anwender die offene Rechnung nicht wegziehen."""
    bestand, kunde, bestellung, rechnung, daten = _bestand_mit_rechnung(tmp_path)
    kunde.aktiv = False
    reiter = RechnungenReiter(bestand, daten_pfad=daten)
    reiter.zeige_objekt(rechnung)

    reiter._aktualisiere_stammdaten()

    assert reiter._kunde_box.currentData() is kunde
    assert reiter._bestellung_box.currentData() is bestellung
    assert reiter._markierte_rechnung() is rechnung


def test_auffrischen_entfernt_den_deaktivierten_kunden_ohne_offene_rechnung(qapp, tmp_path):
    """Der Weg des Anwenders: Kunde im Kunde-Reiter deaktivieren, zurück zu den Rechnungen.

    Der Kunde ist hier nur gewählt, weil die Box nach dem Aufbau auf ihren ersten Eintrag
    zeigt, nicht weil jemand ihn gewählt hätte. Er darf sich davon nicht selbst in der
    Auswahl halten, sonst ließe sich für ihn weiter eine Rechnung anlegen (S-0015 AK1).
    """
    bestand, kunde, _, _, daten = _bestand_mit_rechnung(tmp_path)
    zweiter = Kunde(
        id="k-2",
        kundennummer="10002",
        name="Zweiter Kunde",
        adresse=Adresse(strasse="", plz="", ort="", land="DE"),
        email="z@example.org",
        umsatzsteuer_id="",
        reverse_charge=False,
    )
    bestand.kunden.append(zweiter)
    reiter = RechnungenReiter(bestand, daten_pfad=daten)
    assert reiter._kunde_box.currentData() is kunde  # Ausgangslage: der erste ist gewählt

    kunde.aktiv = False
    reiter._aktualisiere_stammdaten()

    angeboten = [reiter._kunde_box.itemData(i) for i in range(reiter._kunde_box.count())]
    assert kunde not in angeboten
    assert reiter._kunde_box.currentData() is zweiter


def test_neue_rechnung_bleibt_fuer_aktive_kunden_moeglich(qapp, tmp_path):
    """Der Filter darf den Regelfall nicht beschädigen."""
    bestand, kunde, bestellung, _, daten = _bestand_mit_rechnung(tmp_path)
    reiter = RechnungenReiter(bestand, daten_pfad=daten)
    assert reiter._kunde_box.currentData() is kunde
    assert reiter._aktuelle_bestellung() is bestellung
    assert reiter._neu_knopf.isEnabled() is True
