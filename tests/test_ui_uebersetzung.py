"""Tests der übersetzten Oberfläche (S-0061), offscreen.

Prüft, was Stichproben je Maske nicht zeigen: dass eine Maske ihre Texte **beim Aufbau**
aus dem Katalog holt und nicht beim Import des Moduls. Der Unterschied ist nicht
akademisch: Ein Text, der in einer Modul-Konstante steht, wird beim ersten Import
ausgewertet, also bevor `app.main` die UI-Sprache aus der Firma-Datei gesetzt hat. Die
Oberfläche bliebe dann dauerhaft deutsch, egal was eingestellt ist, und ein Test, der nur
eine Maske baut, bemerkte davon nichts.

Die Tests bauen deshalb jede Maske nach einem Sprachwechsel neu auf und erwarten die neue
Sprache.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from eu_rechnung.services import erzeuge_seed
from eu_rechnung.ui.artikel_reiter import ArtikelReiter
from eu_rechnung.ui.bankverbindung_dialog import BankverbindungDialog
from eu_rechnung.ui.datums_feld import DatumsFeld
from eu_rechnung.ui.erstellen_dialog import FormatDialog
from eu_rechnung.ui.hauptfenster import HauptFenster, Reiter
from eu_rechnung.ui.liste import ObjektListe, Spalte
from eu_rechnung.ui.sprache import setze_ui_sprache


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    """Der UI-Sprach-Zustand ist prozessweit; nach jedem Test zurückstellen."""
    yield
    setze_ui_sprache("de")


def _knopf_texte(widget) -> list[str]:
    from PySide6.QtWidgets import QPushButton

    return [k.text() for k in widget.findChildren(QPushButton)]


def test_reiterbeschriftungen_folgen_der_sprache(qapp):
    """Die Enum-Werte bleiben technisch, die Beschriftung kommt aus dem Katalog."""
    setze_ui_sprache("de")
    assert Reiter.FIRMA.anzeigename == "Firma"
    assert Reiter.RECHNUNGSUEBERSICHT.anzeigename == "Rechnungsübersicht"
    setze_ui_sprache("en")
    assert Reiter.FIRMA.anzeigename == "Company"
    assert Reiter.RECHNUNGSUEBERSICHT.anzeigename == "Invoice overview"
    # Der Wert selbst ist ein technischer Schlüssel und ändert sich nie.
    assert Reiter.FIRMA.value == "firma"


def test_hauptfenster_baut_menue_und_reiter_in_der_sprache(qapp):
    setze_ui_sprache("en")
    fenster = HauptFenster(erzeuge_seed())
    menues = [m.title() for m in fenster.menuBar().findChildren(type(fenster.menuBar().addMenu("x")))]
    assert any("File" in m for m in menues)
    reiter_titel = [fenster._tabs.tabText(i) for i in range(fenster._tabs.count())]
    assert "Company" in reiter_titel
    assert "Invoices" in reiter_titel
    assert "Firma" not in reiter_titel


def test_leerzustand_folgt_der_sprache(qapp):
    """Der Fenstertitel hängt den Zustand an den Produktnamen; nur der Zustand ist übersetzt."""
    setze_ui_sprache("fr")
    fenster = HauptFenster()
    assert fenster.windowTitle() == "SCG EU E-Rechnung Generator — aucune société ouverte"


def test_artikel_reiter_folgt_der_sprache(qapp):
    """Baut die Maske nach dem Sprachwechsel neu: fängt beim Import eingefrorene Texte."""
    setze_ui_sprache("it")
    reiter = ArtikelReiter(erzeuge_seed())
    texte = _knopf_texte(reiter)
    assert "Nuovo articolo" in texte
    assert "Conferma" in texte
    assert "Neuer Artikel" not in texte


def test_liste_folgt_der_sprache(qapp):
    setze_ui_sprache("es")
    liste = ObjektListe([Spalte("X", lambda o: str(o))], aktiv_attribut=None)
    assert liste._filter.placeholderText() == "buscar en todas las columnas …"


def test_dialoge_folgen_der_sprache(qapp):
    setze_ui_sprache("fr")
    assert BankverbindungDialog(["EUR"]).windowTitle() == "Coordonnées bancaires"
    assert FormatDialog().windowTitle() == "Générer la facture"


def test_datumsfeld_folgt_der_sprache(qapp):
    """Anzeigeformat und Locale müssen zusammenpassen: Das Feld liest im selben Format zurück."""
    setze_ui_sprache("de")
    assert DatumsFeld().displayFormat() == "dd.MM.yyyy"
    setze_ui_sprache("en")
    feld = DatumsFeld()
    assert feld.displayFormat() == "dd/MM/yyyy"
    assert feld.locale().language().name.lower().startswith("english")


def test_firma_reiter_folgt_der_sprache(qapp):
    """Die Feldgruppen stehen in einer Modul-Konstante: der Fall, der beim Import einfrieren würde."""
    from eu_rechnung.ui.firma_reiter import FirmaReiter

    setze_ui_sprache("en")
    reiter = FirmaReiter(erzeuge_seed())
    from PySide6.QtWidgets import QGroupBox

    gruppen = [g.title() for g in reiter.findChildren(QGroupBox)]
    assert "Address" in gruppen
    # Die Bankverbindungen tragen bei aktiver XRechnung den Pflicht-Stern am Gruppentitel.
    assert "Bank accounts *" in gruppen
    assert "Adresse" not in gruppen
    # Feldbeschriftung aus der Konstante, plus Pflicht-Stern
    label, basis, _ = reiter._pflicht["name"]
    assert basis == "Company name"
    assert label.text() == "Company name *"


def test_kunde_reiter_folgt_der_sprache(qapp):
    from eu_rechnung.ui.kunde_reiter import KundeReiter

    setze_ui_sprache("it")
    reiter = KundeReiter(erzeuge_seed())
    assert "Nuovo cliente" in _knopf_texte(reiter)
    assert reiter._pflicht["kundennummer"][1] == "Numero cliente"


def test_bestellung_reiter_folgt_der_sprache(qapp):
    from eu_rechnung.ui.bestellung_reiter import BestellungReiter

    setze_ui_sprache("es")
    reiter = BestellungReiter(erzeuge_seed())
    texte = _knopf_texte(reiter)
    assert "Nuevo pedido" in texte
    assert "Añadir" in texte
    assert "Neue Bestellung" not in texte


def test_gueltiger_artikel_dialog_folgt_der_sprache(qapp):
    """Die Obergrenze-Art hängt an der Auswahl-`data`, nicht mehr am Anzeigetext."""
    from eu_rechnung.domain import ObergrenzeArt
    from eu_rechnung.ui.gueltiger_artikel_dialog import GueltigerArtikelDialog

    bestand = erzeuge_seed()
    setze_ui_sprache("fr")
    dialog = GueltigerArtikelDialog(bestand.artikel, "EUR")
    assert dialog.windowTitle() == "Article valide"
    arten = [dialog._art.itemText(i) for i in range(dialog._art.count())]
    assert arten == ["aucun", "Quantité", "Montant"]

    # Die Zuordnung zum Enum bleibt vom Anzeigetext unabhängig. Geprüft wird
    # `_gewaehlte_art`, nicht `itemData`: Qt reicht die data durch ein QVariant und gibt
    # aus dem str-Enum den blanken String zurück; die Rückwandlung ist genau die Aufgabe
    # der Methode.
    for index, erwartet in enumerate([None, ObergrenzeArt.MENGE, ObergrenzeArt.BETRAG]):
        dialog._art.setCurrentIndex(index)
        gewaehlt = dialog._gewaehlte_art()
        assert gewaehlt is erwartet
        if erwartet is not None:
            assert isinstance(gewaehlt, ObergrenzeArt)


def test_rechnungsmaske_folgt_der_sprache(qapp):
    """Auch hier stehen die Parteifelder in einer Modul-Konstante (Import-Fallstrick)."""
    from PySide6.QtWidgets import QGroupBox

    from eu_rechnung.ui.rechnungsmaske import RechnungsMaske

    setze_ui_sprache("en")
    maske = RechnungsMaske(erzeuge_seed().artikel)
    gruppen = [g.title() for g in maske.findChildren(QGroupBox)]
    assert "Header data" in gruppen
    assert "Line items" in gruppen
    assert "Seller" in gruppen
    assert "Kopfdaten" not in gruppen
    texte = _knopf_texte(maske)
    assert "Free line" in texte
    assert "Generate invoice" in texte


def test_rechnungsmaske_nettosumme_folgt_der_sprache(qapp):
    from eu_rechnung.ui.rechnungsmaske import RechnungsMaske

    artikel = erzeuge_seed().artikel
    setze_ui_sprache("en")
    # Leerzustand ohne geladene Bestellung: kein Belegwährungs-Suffix, nur der Betrag (S-0064).
    assert RechnungsMaske(artikel)._summe_label.text() == "Net: 0.00"
    setze_ui_sprache("de")
    assert RechnungsMaske(artikel)._summe_label.text() == "Netto: 0,00"


def test_rechnungen_reiter_folgt_der_sprache(qapp):
    from eu_rechnung.ui.rechnungen_reiter import RechnungenReiter

    setze_ui_sprache("it")
    reiter = RechnungenReiter(erzeuge_seed())
    texte = _knopf_texte(reiter)
    assert "Nuova fattura" in texte
    assert "Elimina" in texte
    assert "Neue Rechnung" not in texte


def test_uebersicht_status_folgt_der_sprache_ohne_die_daten_zu_aendern(qapp):
    """Der Enum-Wert steht so in der Firma-Datei; übersetzt wird nur die Anzeige."""
    from eu_rechnung.domain import RechnungsStatus
    from eu_rechnung.ui.rechnungsuebersicht_reiter import _status_text

    class _Zeile:
        def __init__(self, status):
            self.rechnung = type("R", (), {"status": status})()

    setze_ui_sprache("en")
    assert _status_text(_Zeile(RechnungsStatus.ENTWURF)) == "Draft"
    assert _status_text(_Zeile(RechnungsStatus.ERZEUGT)) == "Generated"
    # Der gespeicherte Wert bleibt unangetastet.
    assert RechnungsStatus.ENTWURF.value == "Entwurf"
    assert RechnungsStatus.ERZEUGT.value == "Erzeugt"


def test_waehrungs_gruppen_folgen_der_sprache(qapp):
    """4T-0132: Die Auswahl-Einträge entstehen im Aufbau, nicht in einer Modul-Konstante.

    Der „erbt"-Eintrag ist der kritische Fall: Er wird zur Laufzeit aus zwei Teilen gebaut
    (Text plus geerbter Wert) und liefe in einer Konstante beim Import auf Deutsch fest.
    """
    from PySide6.QtWidgets import QGroupBox

    from eu_rechnung.ui.einstellungen_reiter import EinstellungenReiter
    from eu_rechnung.ui.kunde_reiter import KundeReiter

    setze_ui_sprache("en")
    bestand = erzeuge_seed()
    bestand.einstellungen.waehrungsliste = ["EUR", "CHF"]

    einstellungen = EinstellungenReiter(bestand)
    gruppen = [g.title() for g in einstellungen.findChildren(QGroupBox)]
    assert "Currencies" in gruppen
    assert "Währungen" not in gruppen
    assert einstellungen._waehrungen.horizontalHeaderItem(0).text() == "Currency (ISO 4217)"

    kunde = KundeReiter(bestand)
    kunde_gruppen = [g.title() for g in kunde.findChildren(QGroupBox)]
    assert "Defaults for documents" in kunde_gruppen
    assert kunde._waehrung._auswahl.itemText(0) == "inherited (EUR)"
