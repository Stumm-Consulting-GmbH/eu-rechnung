"""Smoke-Tests der Basis-UI (Hauptfenster und Rechnungsmaske), offscreen.

Prueft die Verdrahtung ohne Event-Loop: dass die Maske eine vorbelegte Rechnung
korrekt anzeigt und die Eingaben zurueckschreibt, der Positions-Dialog den
Gesamtpreis berechnet und das Hauptfenster den Seed-Datenbestand auflistet. Die
Qt-Plattform wird auf "offscreen" gesetzt, damit die Tests ohne Display laufen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from eu_rechnung.domain import (
    Artikel,
    ArtikelTyp,
    Leistungszeitraum,
    Position,
    Preis,
    RechnungsStatus,
    Skonto,
)
from eu_rechnung.services import erzeuge_seed, vorbelege_rechnung
from eu_rechnung.ui.betrag import format_betrag
from eu_rechnung.ui.rechnungen_reiter import RechnungenReiter
from eu_rechnung.ui.sprache import ui_text
from eu_rechnung.ui.rechnungsmaske import (
    ArtikelPositionDialog,
    BestellPositionDialog,
    LeistungszeitraumDialog,
    PositionDialog,
    RechnungsMaske,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def seed_kunde_bestellung():
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    return bestand, kunde, kunde.bestellungen[0]


def _maske(bestand, bestellung, rechnung):
    """Baut die eingebettete Maske und zeigt eine Rechnung im Anlegen-Modus."""
    maske = RechnungsMaske(bestand.artikel)
    maske.zeige(rechnung, bestellung, ist_neu=True)
    return maske


def test_maske_zeigt_vorbelegte_werte(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._nummer.text() == "2026-10001"
    assert maske._reverse.isChecked() is True
    assert maske._verkaeufer_edits["name"].text() == "Muster Consulting GmbH"
    assert maske._kaeufer_edits["name"].text() == "Beispiel Kunde GmbH"
    assert maske._kaeufer_edits["ort"].text() == "München"


def test_maske_uebernimmt_eingaben(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._nummer.setText("2026-99999")
    maske._kaeufer_edits["ort"].setText("Hamburg")
    maske.rechnung.positionen.append(
        Position("", "Test", Decimal("2"), Decimal("100.00"), Decimal("200.00"))
    )
    maske._uebernehme_in_rechnung()
    # Die Maske arbeitet auf einer Kopie; die Eingaben landen dort, nicht im Original.
    assert maske.rechnung.rechnungsnummer == "2026-99999"
    assert maske.rechnung.kaeufer.adresse.ort == "Hamburg"
    assert maske.rechnung.kaeufer.name == "Beispiel Kunde GmbH"


def test_positiondialog_berechnet_gesamtpreis(qapp):
    dialog = PositionDialog("EUR")
    dialog._bezeichnung.setText("Beratung")
    dialog._menge.setText("3,5")
    dialog._einzelpreis.setText("1400")
    pos = dialog.position()
    assert pos.bezeichnung == "Beratung"
    assert pos.menge == Decimal("3.5")
    assert pos.gesamtpreis == Decimal("4900.00")


def test_positionsliste_zeigt_mindestens_fuenf_zeilen(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    tabelle = maske._pos_tabelle
    zeile_h = tabelle.verticalHeader().defaultSectionSize()
    # Mindesthöhe reicht für fünf Datenzeilen (plus Kopf, hier konservativ geprüft).
    assert tabelle.minimumHeight() >= 5 * zeile_h


def test_rechnungen_reiter_listet_seed(qapp):
    reiter = RechnungenReiter(erzeuge_seed())
    assert reiter._kunde_box.count() == 1
    assert reiter._bestellung_box.count() == 1
    assert reiter._liste._tabelle.rowCount() == 0  # noch keine Rechnung angelegt


def test_maske_zeigt_vorbelegte_positionen(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._pos_tabelle.rowCount() == 2  # zwei gültige Artikel, Menge 0
    assert maske._pos_tabelle.item(0, 1).text() == "0"


def test_menge_editieren_berechnet_gesamtpreis(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._pos_tabelle.item(0, 1).setText("5")  # Menge 5 bei Einzelpreis 1200
    assert maske.rechnung.positionen[0].menge == Decimal("5")
    assert maske.rechnung.positionen[0].gesamtpreis == Decimal("6000.00")


def test_verfuegbare_bestell_positionen_nach_loeschen(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._verfuegbare_bestell_positionen() == []  # alle vorhanden
    del maske.rechnung.positionen[0]
    assert [v[0] for v in maske._verfuegbare_bestell_positionen()] == ["art-1"]


# --- 4T-0105: übernommene individuelle Felder in der Rechnungsmaske (S-0040) ---


def test_maske_zeigt_uebernommene_felder(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._felder_tabelle.rowCount() == len(rechnung.individuelle_felder)
    assert rechnung.individuelle_felder  # der Seed trägt übernommene Felder
    assert maske._felder_tabelle.item(0, 0).text() == rechnung.individuelle_felder[0].name


# --- 4T-0144: Positions-Leistungszeitraum (S-0067/S-0068/S-0069) ---


def test_hinzufuegen_belegt_zeitraum_bei_leistung_und_frei(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._lz_von.setze_datum(date(2026, 8, 1))
    maske._lz_bis.setze_datum(date(2026, 8, 31))
    # Freie Position (ohne Artikel-Bezug) darf einen Zeitraum tragen (PO-Entscheidung 2026-07-16)
    # und wird aus dem Kopf-Zeitraum vorbelegt.
    maske._fuege_position_hinzu(Position("", "Freie Leistung", Decimal("1"), Decimal("100"), Decimal("100")))
    assert maske.rechnung.positionen[-1].leistungszeitraum == Leistungszeitraum(
        date(2026, 8, 1), date(2026, 8, 31)
    )


def test_hinzufuegen_ohne_zeitraum_bei_produkt(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    next(a for a in bestand.artikel if a.id == "art-2").typ = ArtikelTyp.PRODUKT
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._fuege_position_hinzu(Position("art-2", "Ware", Decimal("1"), Decimal("10"), Decimal("10")))
    assert maske.rechnung.positionen[-1].leistungszeitraum is None


def test_zeitraum_dialog_setzt_und_loescht(qapp):
    vorbelegung = Leistungszeitraum(date(2026, 8, 1), date(2026, 8, 31))
    # Ohne bestehenden Zeitraum ist die Angabe abgeschaltet und liefert None.
    dialog = LeistungszeitraumDialog(None, vorbelegung)
    assert dialog._aktiv.isChecked() is False
    assert dialog.zeitraum() is None
    # Eingeschaltet und geändert liefert er den erfassten Bereich.
    dialog._aktiv.setChecked(True)
    dialog._von.setze_datum(date(2026, 9, 1))
    dialog._bis.setze_datum(date(2026, 9, 30))
    assert dialog.zeitraum() == Leistungszeitraum(date(2026, 9, 1), date(2026, 9, 30))


# --- 4T-0146: Position aus einem Stammdaten-Artikel (S-0024 AK7) ---


def test_artikelpositiondialog_uebernimmt_aktiven_artikel(qapp):
    """AK2: Der Dialog übernimmt Artikel-Bezug, Artikelname und Menge 0; der Vorschlagspreis
    wird bei währungsgleichem Artikel als Einzelpreis übernommen."""
    artikel = [
        Artikel(id="art-x", artikelname="Testleistung", vorschlagspreis=Preis(Decimal("500.00"), "EUR"))
    ]
    dialog = ArtikelPositionDialog(artikel, "EUR")
    pos = dialog.position()
    assert pos.artikel_id == "art-x"
    assert pos.bezeichnung == "Testleistung"
    assert pos.menge == Decimal("0")
    assert pos.einzelpreis == Decimal("500.00")
    assert pos.gesamtpreis == Decimal("0.00")


def test_artikelpositiondialog_fremde_waehrung_ohne_betrag(qapp):
    """AK2/Währungsregel: Bei abweichender Vorschlagspreis-Währung bleibt der Einzelpreis
    leer (0) und wird selbst gepflegt (Product-Owner-Entscheidung 2026-07-16)."""
    artikel = [
        Artikel(id="art-x", artikelname="CHF-Artikel", vorschlagspreis=Preis(Decimal("500.00"), "CHF"))
    ]
    dialog = ArtikelPositionDialog(artikel, "EUR")  # Belegwährung EUR, Artikel CHF
    pos = dialog.position()
    assert pos.artikel_id == "art-x"
    assert pos.einzelpreis == Decimal("0")


def test_aktive_artikel_filtert_inaktive(qapp, seed_kunde_bestellung):
    """AK1: Der Weg aus dem Artikel-Stamm bietet nur aktive Artikel an."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    next(a for a in bestand.artikel if a.id == "art-2").aktiv = False
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert [a.id for a in maske._aktive_artikel()] == ["art-1"]


def test_position_aus_artikel_belegt_zeitraum_bei_leistung(qapp, seed_kunde_bestellung):
    """AK3: Der ganze Weg (Dialog → Einhängen) übernimmt den währungsgleichen Vorschlagspreis
    und belegt den Positions-Zeitraum bei einem Leistungs-Artikel aus dem Kopf vor."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._lz_von.setze_datum(date(2026, 8, 1))
    maske._lz_bis.setze_datum(date(2026, 8, 31))
    # art-1 ist eine Leistung (Default-Typ) und in EUR (Belegwährung).
    dialog = ArtikelPositionDialog(maske._aktive_artikel(), maske._belegwaehrung())
    maske._fuege_position_hinzu(dialog.position())
    letzte = maske.rechnung.positionen[-1]
    assert letzte.artikel_id == "art-1"
    assert letzte.einzelpreis == Decimal("1200.00")  # währungsgleich übernommen
    assert letzte.leistungszeitraum == Leistungszeitraum(date(2026, 8, 1), date(2026, 8, 31))


def test_maske_uebernimmt_editierte_felder(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._felder_tabelle.item(0, 1).setText("Geänderter Wert")
    maske._uebernehme_in_rechnung()
    assert maske.rechnung.individuelle_felder[0].wert == "Geänderter Wert"


# --- Skonto-Erfassung (S-0051, 4T-0116) -------------------------------------


def test_maske_erfasst_skonto(qapp, seed_kunde_bestellung):
    """Beide Felder gefüllt: Die Eingaben landen als Wertobjekt in der Rechnung; der
    Prozentsatz nimmt auch deutsche Dezimalschreibweise an (AK1, AK3)."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._skonto_tage.setText("14")
    maske._skonto_prozent.setText("2,5")
    maske._uebernehme_in_rechnung()
    assert maske.rechnung.skonto == Skonto(tage=14, prozent=Decimal("2.5"))


def test_maske_ohne_skonto_bleibt_none(qapp, seed_kunde_bestellung):
    """Leerfall: Ohne Eingabe trägt die Rechnung kein Skonto (AK2)."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._skonto_tage.text() == ""
    maske._uebernehme_in_rechnung()
    assert maske.rechnung.skonto is None


def test_maske_zeigt_geladenes_skonto(qapp, seed_kunde_bestellung):
    """Beim Laden erscheinen die gespeicherten Werte wieder in den Feldern (AK3)."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2.00"))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._skonto_tage.text() == "14"
    assert maske._skonto_prozent.text() == "2"


def test_maske_meldet_halbes_skonto(qapp, seed_kunde_bestellung):
    """Nur ein Feld gefüllt: feld-naher Fehler, und das Skonto wird nicht übernommen
    (AK2). Diese Regel kann nur die Maske prüfen, das Wertobjekt kennt den Zustand nicht."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._skonto_tage.setText("14")  # Prozentsatz fehlt
    maske._bestaetigen()
    assert maske._fehler["skonto_prozent"].isHidden() is False
    assert maske.rechnung.skonto is None


def test_maske_meldet_skonto_ueber_hundert_prozent(qapp, seed_kunde_bestellung):
    """Der Prozentsatz ist fachlich auf 100 begrenzt; der Service-Befund erscheint
    feld-nah (AK5)."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._skonto_tage.setText("14")
    maske._skonto_prozent.setText("150")
    maske._bestaetigen()
    assert maske._fehler["skonto_prozent"].isHidden() is False


def test_maske_meldet_gebrochene_skonto_tage(qapp, seed_kunde_bestellung):
    """Skonto-Tage sind ganzzahlig: „14,5" wird gemeldet statt still auf 14 gerundet."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._skonto_tage.setText("14,5")
    maske._skonto_prozent.setText("2")
    maske._bestaetigen()
    assert maske._fehler["skonto_tage"].isHidden() is False
    assert maske.rechnung.skonto is None


def test_maske_zeigt_vorbelegtes_skonto_der_bestellung(qapp, seed_kunde_bestellung):
    """S-0080: Ein in der Bestellung vereinbartes Skonto erscheint über die Vorbelegung in
    den Feldern der Rechnungsmaske."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    bestellung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._skonto_tage.text() == "14"
    assert maske._skonto_prozent.text() == "2"


def test_maske_zeigt_und_uebernimmt_zahlungsfrist(qapp, seed_kunde_bestellung):
    """S-0080 AK4/AK5: Die aus der Bestellung vorbelegte Zahlungsfrist ist in der Maske
    sichtbar und dort änderbar, ohne auf die Bestellung zurückzuwirken."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._zahlungsfrist.value() == bestellung.zahlungsfrist == 30
    maske._zahlungsfrist.setValue(14)
    maske._uebernehme_in_rechnung()
    assert maske.rechnung.zahlungsfrist == 14
    assert bestellung.zahlungsfrist == 30  # der Vertrag bleibt unberührt


# --- Rechnungssprache (S-0082 AK4/AK6, 4T-0137) ----------------------------


def test_maske_zeigt_die_aufgeloeste_sprache_ohne_erbt(qapp, seed_kunde_bestellung):
    """AK4: Die Rechnung trägt einen eigenen Wert; ein „erbt" gäbe es hier nicht."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    kunde.rechnungssprache = "it"
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._sprache.wert() == "it"  # aus der Kaskade vorbelegt
    eintraege = [
        maske._sprache._auswahl.itemData(i)
        for i in range(maske._sprache._auswahl.count())
    ]
    assert None not in eintraege  # kein Erb-Eintrag
    assert eintraege == ["de", "en", "it", "fr", "es"]


def test_sprache_der_rechnung_ist_aenderbar(qapp, seed_kunde_bestellung):
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._sprache._auswahl.setCurrentIndex(maske._sprache._auswahl.findData("es"))
    maske._uebernehme_in_rechnung()
    # Die Maske arbeitet auf einer Kopie; die Eingabe landet dort, nicht im Original.
    assert maske.rechnung.rechnungssprache == "es"
    assert rechnung.rechnungssprache == "de"


def test_erfasste_sprache_erscheint_im_sichtteil(qapp, seed_kunde_bestellung):
    """AK6: Die Kette Erfassung -> Kaskade -> Ausgabe, die vor 4T-0137 nirgends zusammenkam.

    Vor dieser Story war die Rechnungssprache in der Oberfläche nicht setzbar: Der Sichtteil
    war normvalide und mehrsprachig gebaut, aber jede erzeugte Rechnung blieb deutsch, weil
    keine Ebene je einen Wert trug.
    """
    from io import BytesIO

    from pypdf import PdfReader

    from eu_rechnung.export.pdf_sicht import erzeuge_sichtteil

    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)

    # Der Anwender wählt Spanisch, wie er es in der Maske täte.
    maske._sprache._auswahl.setCurrentIndex(maske._sprache._auswahl.findData("es"))
    maske._uebernehme_in_rechnung()

    pdf = erzeuge_sichtteil(maske.rechnung, bestellung.bestellnummer, bestellung.waehrung)
    text = "".join(seite.extract_text() for seite in PdfReader(BytesIO(pdf)).pages)
    assert "Número de factura" in text  # feste Sichtteil-Texte auf Spanisch
    assert "Rechnungsnummer" not in text
    assert PdfReader(BytesIO(pdf)).trailer["/Root"]["/Lang"] == "es"
    # Der Anschreibentext bleibt deutsch: Dynamische Inhalte werden nicht übersetzt
    # (S-0060 AK5); der Anwender erfasst sie in der Zielsprache.
    assert "Mit freundlichen Grüßen" in text


# --- Dynamische Belegwährung (S-0064, 4T-0134) -----------------------------


def test_maske_bezug_und_netto_folgen_der_belegwaehrung(qapp, seed_kunde_bestellung):
    """S-0064: Der Bezug-Titel und die Nettosumme tragen die Belegwährung der Bestellung,
    nicht mehr fest EUR."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    bestellung.waehrung = "CHF"
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert "CHF" in maske._bezug.text()
    assert maske._summe_label.text().endswith("CHF")


# --- Steuersatz-Erfassung in der Rechnungsmaske (S-0079 AK5, 4T-0138) -------


def test_maske_zeigt_vorbelegten_steuersatz(qapp, seed_kunde_bestellung):
    """AK1: Der aus der Firma vorbelegte Steuersatz erscheint im Feld der Rechnungsmaske."""
    from eu_rechnung.ui.betrag import format_betrag

    bestand, kunde, bestellung = seed_kunde_bestellung
    kunde.reverse_charge = False
    bestand.eigene_firma.standard_steuersatz = Decimal("19")
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._steuersatz.text() == format_betrag(Decimal("19"))


def test_maske_uebernimmt_steuersatz(qapp, seed_kunde_bestellung):
    """AK1: Der in der Maske gesetzte Satz landet an der Rechnung (deutsche Dezimalschreibweise)."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    kunde.reverse_charge = False
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._steuersatz.setText("7,7")
    maske._uebernehme_in_rechnung()
    assert maske.rechnung.steuersatz == Decimal("7.7")


def test_reverse_charge_deaktiviert_das_steuersatz_feld(qapp, seed_kunde_bestellung):
    """AK2: Bei Reverse-Charge ist das Feld deaktiviert (Satz gegenstandslos)."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._reverse.setChecked(True)
    assert maske._steuersatz.isEnabled() is False
    maske._reverse.setChecked(False)
    assert maske._steuersatz.isEnabled() is True


def test_fehlender_steuersatz_wird_sichtbar_gemeldet(qapp, seed_kunde_bestellung):
    """AK3: Nicht-RC ohne Satz meldet den Fehler am Feld, statt das Bestätigen ohne
    Reaktion abzubrechen (der ursprüngliche Bug)."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    kunde.reverse_charge = False
    bestand.eigene_firma.standard_steuersatz = Decimal("0")
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske.rechnung.positionen[0].menge = Decimal("5")
    gefeuert = []
    maske.bestaetigt.connect(lambda: gefeuert.append(True))
    maske._bestaetigen()
    assert not gefeuert  # Bestätigung bleibt blockiert
    assert maske._fehler["steuersatz"].isHidden() is False  # aber der Grund ist sichtbar


def test_gesetzter_steuersatz_erlaubt_das_bestaetigen(qapp, seed_kunde_bestellung):
    """AK3: Mit gesetztem Satz gelingt das Bestätigen."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    kunde.reverse_charge = False
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske.rechnung.positionen[0].menge = Decimal("5")
    maske._steuersatz.setText("19")
    gefeuert = []
    maske.bestaetigt.connect(lambda: gefeuert.append(True))
    maske._bestaetigen()
    assert gefeuert


def test_befund_ohne_feldlabel_wird_als_sammelmeldung_gezeigt(
    qapp, seed_kunde_bestellung, monkeypatch
):
    """AK4: Ein Befund für ein Feld ohne Label verschwindet nicht still, sondern erscheint
    als Sammelmeldung. Sicherheitsnetz gegen künftige „passiert nichts"-Fälle."""
    from PySide6.QtWidgets import QMessageBox

    from eu_rechnung.services import Befund

    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    gezeigt = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: gezeigt.append(a))
    maske._melde_befunde([Befund("gibt_es_nicht", "rechnung.steuersatz_fehlt")])
    assert gezeigt  # die Sammelmeldung erschien


# --- Bankverbindung nach Rechnungswährung (S-0065, 4T-0135) ----------------


def test_bankverbindung_vorbelegt_nach_belegwaehrung(qapp, seed_kunde_bestellung):
    """AK1/AK2: Die Auswahl bietet „(keine)" plus alle Konten und belegt das zur
    Belegwährung passende vor."""
    from eu_rechnung.domain import Bankverbindung

    bestand, kunde, bestellung = seed_kunde_bestellung
    chf = Bankverbindung(
        kontoinhaber="Muster", bank="Beispielbank", iban="CH11", bic="BEISCHZZ", waehrung="CHF"
    )
    bestand.eigene_firma.bankverbindungen.append(chf)
    bestellung.waehrung = "CHF"
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._bankverbindung.count() == 3  # (keine) + EUR + CHF
    assert maske._bankverbindung.currentData() == chf  # CHF vorbelegt


def test_bankverbindung_ohne_passende_waehrung_bleibt_leer(qapp, seed_kunde_bestellung):
    """AK2: Ohne passendes Konto bleibt die Auswahl auf „(keine)"."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    bestellung.waehrung = "USD"  # der Seed führt nur ein EUR-Konto
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._bankverbindung.currentData() is None


def test_bankverbindung_wahl_wird_uebernommen(qapp, seed_kunde_bestellung):
    """AK3: Die in der Maske gewählte Bankverbindung landet an der Rechnung."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._bankverbindung.setCurrentIndex(1)  # erstes echtes Konto
    maske._uebernehme_in_rechnung()
    assert maske.rechnung.bankverbindung == bestand.eigene_firma.bankverbindungen[0]


# --- Positions-Zeitraum gegen den Kopf-Zeitraum (S-0069 AK5, 4T-0147) -------


def test_zeitraum_dialog_lehnt_zeitraum_ausserhalb_des_kopfes_ab(qapp, monkeypatch):
    """S-0069 AK5: Ein Positions-Zeitraum außerhalb des Kopf-Zeitraums wird im Dialog gemeldet und
    nicht akzeptiert (BG-26 muss in BG-14 liegen)."""
    from PySide6.QtWidgets import QMessageBox

    kopf = Leistungszeitraum(date(2026, 8, 1), date(2026, 8, 31))
    dialog = LeistungszeitraumDialog(None, kopf)
    dialog._aktiv.setChecked(True)
    dialog._von.setze_datum(date(2026, 7, 15))  # vor dem Kopf-Beginn
    dialog._bis.setze_datum(date(2026, 8, 20))
    gezeigt = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: gezeigt.append(a))
    dialog._pruefe_und_akzeptiere()
    assert gezeigt  # die Meldung erschien; der Dialog akzeptiert nicht


def test_zeitraum_dialog_akzeptiert_zeitraum_innerhalb_des_kopfes(qapp, monkeypatch):
    """Gegenprobe: ein Zeitraum innerhalb des Kopf-Zeitraums wird ohne Meldung übernommen."""
    from PySide6.QtWidgets import QMessageBox

    kopf = Leistungszeitraum(date(2026, 8, 1), date(2026, 8, 31))
    dialog = LeistungszeitraumDialog(None, kopf)
    dialog._aktiv.setChecked(True)
    dialog._von.setze_datum(date(2026, 8, 10))
    dialog._bis.setze_datum(date(2026, 8, 20))
    gezeigt = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: gezeigt.append(a))
    dialog._pruefe_und_akzeptiere()
    assert not gezeigt
    assert dialog.zeitraum() == Leistungszeitraum(date(2026, 8, 10), date(2026, 8, 20))


# --- Kopf-Zeitraum zieht die Positionen nach (S-0085, 4T-0179) --------------


def _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung):
    """Vorbelegte Rechnung; ihre beiden Positionen tragen den Kopf-Zeitraum der Bestellung."""
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.leistungszeitraum == Leistungszeitraum(date(2026, 5, 1), date(2026, 5, 31))
    return rechnung


def test_kopf_zeitraum_zieht_folgende_positionen_nach(qapp, seed_kunde_bestellung):
    """AK1: Positionen mit dem bisherigen Kopf-Zeitraum übernehmen den neuen Wert."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung)
    maske = _maske(bestand, bestellung, rechnung)

    maske._lz_von.setze_datum(date(2026, 8, 1))
    maske._lz_bis.setze_datum(date(2026, 8, 31))

    neu = Leistungszeitraum(date(2026, 8, 1), date(2026, 8, 31))
    assert [p.leistungszeitraum for p in maske.rechnung.positionen] == [neu, neu]
    assert maske.rechnung.leistungszeitraum == neu


def test_kopf_zeitraum_laesst_abweichende_position_stehen(qapp, seed_kunde_bestellung):
    """AK2: Ein eigens erfasster, abweichender Positions-Zeitraum bleibt unangetastet."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung)
    eigen = Leistungszeitraum(date(2026, 5, 10), date(2026, 5, 20))
    rechnung.positionen[0].leistungszeitraum = eigen
    maske = _maske(bestand, bestellung, rechnung)

    maske._lz_von.setze_datum(date(2026, 8, 1))
    maske._lz_bis.setze_datum(date(2026, 8, 31))

    assert maske.rechnung.positionen[0].leistungszeitraum == eigen  # eigens gesetzt: bleibt
    assert maske.rechnung.positionen[1].leistungszeitraum == Leistungszeitraum(
        date(2026, 8, 1), date(2026, 8, 31)
    )


def test_kopf_zeitraum_gibt_position_ohne_zeitraum_keinen(qapp, seed_kunde_bestellung):
    """AK3: Eine bewusst leere Position bekommt durch das Nachziehen keinen Zeitraum."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung)
    rechnung.positionen[0].leistungszeitraum = None
    maske = _maske(bestand, bestellung, rechnung)

    maske._lz_von.setze_datum(date(2026, 8, 1))

    assert maske.rechnung.positionen[0].leistungszeitraum is None


def test_kopf_zeitraum_laesst_produkt_position_unberuehrt(qapp, seed_kunde_bestellung):
    """AK3: Produkt-Positionen tragen keinen Zeitraum und bekommen auch keinen."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    next(a for a in bestand.artikel if a.id == "art-2").typ = ArtikelTyp.PRODUKT
    rechnung = _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung)
    maske = _maske(bestand, bestellung, rechnung)
    produkt = next(p for p in maske.rechnung.positionen if p.artikel_id == "art-2")
    assert produkt.leistungszeitraum is None  # aus der Vorbelegung (S-0067)

    maske._lz_von.setze_datum(date(2026, 8, 1))
    maske._lz_bis.setze_datum(date(2026, 8, 31))

    assert produkt.leistungszeitraum is None


def test_nachgezogene_positionen_haben_eigene_zeitraum_objekte(qapp, seed_kunde_bestellung):
    """Ein geteiltes Objekt würde eine spätere Einzeländerung auf alle Positionen durchschlagen
    lassen; deshalb bekommt jede Position ihre eigene Kopie."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung)
    maske = _maske(bestand, bestellung, rechnung)

    maske._lz_von.setze_datum(date(2026, 8, 1))
    erste, zweite = maske.rechnung.positionen[0], maske.rechnung.positionen[1]
    assert erste.leistungszeitraum is not zweite.leistungszeitraum
    assert erste.leistungszeitraum is not maske.rechnung.leistungszeitraum

    erste.leistungszeitraum.bis = date(2026, 5, 15)
    assert zweite.leistungszeitraum.bis == date(2026, 5, 31)


def test_kopf_zeitraum_zieht_auch_beim_aendern_nach(qapp, seed_kunde_bestellung):
    """AK4: Die Regel gilt für eine geladene Rechnung genauso wie beim Anlegen."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung)
    maske = RechnungsMaske(bestand.artikel)
    maske.zeige(rechnung, bestellung, ist_neu=False)  # Ändern-Modus

    maske._lz_bis.setze_datum(date(2026, 6, 30))

    assert [p.leistungszeitraum for p in maske.rechnung.positionen] == [
        Leistungszeitraum(date(2026, 5, 1), date(2026, 6, 30))
    ] * 2


def test_neue_position_folgt_dem_aktuellen_kopf_zeitraum(qapp, seed_kunde_bestellung):
    """AK5: Die Vorbelegung beim Hinzufügen nutzt weiterhin den aktuellen Kopf-Zeitraum."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung)
    maske = _maske(bestand, bestellung, rechnung)
    maske._lz_von.setze_datum(date(2026, 8, 1))
    maske._lz_bis.setze_datum(date(2026, 8, 31))

    maske._fuege_position_hinzu(
        Position("", "Freie Leistung", Decimal("1"), Decimal("100"), Decimal("100"))
    )

    assert maske.rechnung.positionen[-1].leistungszeitraum == Leistungszeitraum(
        date(2026, 8, 1), date(2026, 8, 31)
    )


def test_laden_einer_rechnung_zieht_nichts_nach(qapp, seed_kunde_bestellung):
    """Das Befüllen der Maske ist keine Änderung durch den Anwender; es darf die Positionen
    nicht anfassen (sonst verlöre eine geladene Rechnung ihre abweichenden Zeiträume)."""
    bestand, kunde, bestellung = seed_kunde_bestellung
    rechnung = _rechnung_mit_kopfzeitraum(bestand, kunde, bestellung)
    eigen = Leistungszeitraum(date(2026, 5, 10), date(2026, 5, 20))
    rechnung.positionen[0].leistungszeitraum = eigen
    rechnung.positionen[1].leistungszeitraum = None

    maske = _maske(bestand, bestellung, rechnung)

    assert maske.rechnung.positionen[0].leistungszeitraum == eigen
    assert maske.rechnung.positionen[1].leistungszeitraum is None


# --- Ausgabestand in der Maske (S-0024 AK2, S-0032 AK4; 4T-0160) -------------


def test_maske_zeigt_status_und_erzeugt_zeitstempel(qapp):
    """AK2: Beide erscheinen als reine Anzeige, nicht nur in der Liste."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.status = RechnungsStatus.ERZEUGT
    rechnung.zuletzt_erzeugt_am = datetime(2026, 7, 10, 8, 30, tzinfo=timezone.utc)
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._status_anzeige.text() == ui_text("rechnung.status_erzeugt")
    assert "2026" in maske._erzeugt_anzeige.text()


def test_maske_zeigt_nie_erzeugte_rechnung_mit_gedankenstrich(qapp):
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._status_anzeige.text() == ui_text("rechnung.status_entwurf")
    assert maske._erzeugt_anzeige.text() == "—"


def test_ausgabestand_ist_keine_eingabe(qapp):
    """AK2 verlangt „reine Anzeige": Ein Eingabefeld lüde zum Ändern ein, was nur die
    Erstellung setzen darf."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert isinstance(maske._status_anzeige, QLabel)
    assert isinstance(maske._erzeugt_anzeige, QLabel)


# --- Steuersatz bei Reverse-Charge (S-0023 AK6, 4T-0160) --------------------


def test_reverse_charge_setzt_den_steuersatz_auf_null(qapp):
    """AK6: Das Sperren allein liess einen erfassten Satz stehen, der gespeichert wurde."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    kunde.reverse_charge = False
    bestand.eigene_firma.standard_steuersatz = Decimal("19")
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._steuersatz.text() == format_betrag(Decimal("19"))

    maske._reverse.setChecked(True)

    assert maske._steuersatz.isEnabled() is False
    assert maske._steuersatz.text() == format_betrag(Decimal("0"))


def test_uebernahme_erzwingt_null_bei_reverse_charge(qapp):
    """Die Invariante haengt nicht am Eingabefeld: Auch ein stehengebliebener Wert wird 0."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    kunde.reverse_charge = False
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._steuersatz.setText(format_betrag(Decimal("19")))
    maske._reverse.setChecked(True)
    maske._steuersatz.setText(format_betrag(Decimal("19")))  # trotz Sperre gesetzt

    maske._uebernehme_in_rechnung()  # arbeitet auf der Kopie der Maske

    assert maske._rechnung.reverse_charge is True
    assert maske._rechnung.steuersatz == Decimal("0")


# --- Obergrenzen-Stand in der Maske (S-0024 AK6, 4T-0160) -------------------


def test_obergrenzen_stand_bleibt_ohne_hoechstbetrag_unsichtbar(qapp):
    """Ohne Grenze keine Zeile: Sie behauptete sonst eine, die es nicht gibt."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    bestellung.gesamt_hoechstbetrag = None
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    assert maske._obergrenzen_label.isVisible() is False


def test_obergrenzen_stand_zeigt_verbrauch_und_rest(qapp):
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    bestellung.gesamt_hoechstbetrag = Decimal("10000.00")
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = [
        Position("art-1", "A", Decimal("2"), Decimal("1200.00"), Decimal("2400.00"))
    ]
    maske = _maske(bestand, bestellung, rechnung)
    text = maske._obergrenzen_label.text()
    assert format_betrag(Decimal("2400.00")) in text  # verbraucht
    assert format_betrag(Decimal("10000.00")) in text  # Grenze
    assert format_betrag(Decimal("7600.00")) in text  # Rest


def test_obergrenzen_stand_zaehlt_fruehere_rechnungen_mit(qapp):
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    bestellung.gesamt_hoechstbetrag = Decimal("10000.00")
    frueher = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 1))
    frueher.id = "r-1"
    frueher.positionen = [
        Position("art-1", "A", Decimal("1"), Decimal("1000.00"), Decimal("1000.00"))
    ]
    bestellung.rechnungen.append(frueher)
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = [
        Position("art-1", "A", Decimal("1"), Decimal("2000.00"), Decimal("2000.00"))
    ]
    maske = _maske(bestand, bestellung, rechnung)
    assert format_betrag(Decimal("3000.00")) in maske._obergrenzen_label.text()


# --- Gelöschte Bestellungs-Position wieder ergänzen (S-0024 AK4, 4T-0161) ---


def test_bestellpositiondialog_liefert_die_gewaehlte_position(qapp):
    """AK4: „gelöschte Bestellungs-Positionen wieder ergänzbar", mit Menge 0 und dem
    Einzelpreis aus der Bestellung (S-0029 AK3).

    Bis 4T-0161 rief kein Test den Dialog auf; geprüft war nur die Verfügbarkeits-Berechnung
    davor.
    """
    verfuegbar = [("art-2", "Schulung", Decimal("1400.00"))]
    dialog = BestellPositionDialog(verfuegbar, "EUR")
    position = dialog.position()
    assert position.artikel_id == "art-2"
    assert position.bezeichnung == "Schulung"
    assert position.menge == Decimal("0")
    assert position.einzelpreis == Decimal("1400.00")
    assert position.gesamtpreis == Decimal("0.00")


def test_bestellpositiondialog_waehlt_unter_mehreren(qapp):
    verfuegbar = [
        ("art-1", "Beratung", Decimal("1200.00")),
        ("art-2", "Schulung", Decimal("1400.00")),
    ]
    dialog = BestellPositionDialog(verfuegbar, "EUR")
    dialog._auswahl.setCurrentIndex(1)
    assert dialog.position().artikel_id == "art-2"


def test_geloeschte_position_ueber_den_dialog_wieder_ergaenzt(qapp, monkeypatch):
    """AK4 im Zusammenspiel: löschen, im Dialog wählen, wieder in der Rechnung."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    maske._pos_tabelle.setCurrentCell(0, 0)
    maske._position_entfernen()
    assert [p.artikel_id for p in maske._rechnung.positionen] == ["art-2"]

    monkeypatch.setattr(BestellPositionDialog, "exec", lambda self: 1)
    maske._position_aus_bestellung()

    assert sorted(p.artikel_id for p in maske._rechnung.positionen) == ["art-1", "art-2"]
    ergaenzt = next(p for p in maske._rechnung.positionen if p.artikel_id == "art-1")
    assert ergaenzt.menge == Decimal("0")
    assert ergaenzt.einzelpreis == bestellung.gueltige_artikel[0].einzelpreis


def test_ohne_verfuegbare_position_erscheint_ein_hinweis(qapp, monkeypatch):
    """Sind alle gültigen Artikel schon Position, gibt es nichts zu ergänzen."""
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    maske = _maske(bestand, bestellung, rechnung)
    gerufen = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: gerufen.append(a[2])
    )
    monkeypatch.setattr(
        BestellPositionDialog, "exec", lambda self: pytest.fail("Dialog darf nicht öffnen")
    )

    maske._position_aus_bestellung()

    assert gerufen == [ui_text("rechnung.alle_positionen_vorhanden")]
