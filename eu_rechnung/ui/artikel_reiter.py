"""Artikel-Reiter: Liste und eingebettete Detailmaske zur Artikel-Pflege (S-0006 bis S-0010).

Master-Detail im selben Reiter, einheitlich zum Firma-Muster: links die Artikel-Liste
(wiederverwendbarer `ObjektListe`-Baustein mit Filtern, Sortieren und „inaktive anzeigen"),
rechts die Detailmaske für Anlegen und Ändern (dieselbe Maske, leer bzw. vorbelegt; Muster
K1). Der Bestätigen-Knopf hebt offene Änderungen hervor (blau, S-0072/4T-0088); die Prüfung
(`services.pruefe_artikel`) zeigt Befunde am betroffenen Feld. Löschen erfolgt hart nur bei
fehlender Bestell-Referenz und nach Sicherheitsabfrage, sonst über das Deaktivieren
(aktiv-Schalter). Jede bestätigte Operation speichert automatisch.

Die Betrags-Helfer sind bewusst analog zu `rechnungsmaske` gehalten; eine spätere
Extraktion in einen gemeinsamen Geld-Baustein ist möglich.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.domain import Artikel, ArtikelTyp, Datenbestand, Preis
from eu_rechnung.services import artikel_referenziert, pruefe_artikel
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.betrag import format_betrag, parse_betrag
from eu_rechnung.ui.aenderung import AenderungsKnopfMixin
from eu_rechnung.ui.feld_fehler import FeldFehlerMixin
from eu_rechnung.ui.liste import ObjektListe, Spalte
from eu_rechnung.ui.sprache import befund_text, ui_text

# Artikel-Typ-Auswahl: Leistung (Default) vor Produkt (S-0066).
_TYP_OPTIONEN = [
    ("artikel.typ_leistung", ArtikelTyp.LEISTUNG),
    ("artikel.typ_produkt", ArtikelTyp.PRODUKT),
]


class ArtikelReiter(FeldFehlerMixin, AenderungsKnopfMixin, QWidget):
    """Reiter mit Artikel-Liste und eingebetteter Anlege-/Änderungsmaske."""

    def __init__(
        self,
        datenbestand: Datenbestand,
        *,
        auto_speicher: AutoSpeicher | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._datenbestand = datenbestand
        self._auto = auto_speicher or AutoSpeicher(datenbestand)
        self._aktueller: Artikel | None = None  # in der Maske bearbeitet; None = Anlegen
        self._geaendert = False
        self._lade_laeuft = False
        self._fehler: dict[str, QLabel] = {}
        self._baue_ui()
        self._fuelle_liste()
        self._neuer_artikel()

    # --- Aufbau -------------------------------------------------------------

    def _baue_ui(self) -> None:
        layout = QHBoxLayout(self)

        # Links: Liste plus Neu/Löschen.
        links = QVBoxLayout()
        self._liste = ObjektListe(
            [
                Spalte(ui_text("artikel.feld_name"), lambda a: a.artikelname),
                Spalte(
                    ui_text("artikel.feld_vorschlagspreis"),
                    lambda a: format_betrag(a.vorschlagspreis.betrag),
                    sortierwert=lambda a: a.vorschlagspreis.betrag,
                ),
                Spalte(ui_text("allgemein.feld_waehrung"), lambda a: a.vorschlagspreis.waehrung),
                Spalte(
                    ui_text("artikel.feld_typ"),
                    lambda a: ui_text(
                        "artikel.typ_produkt" if a.typ is ArtikelTyp.PRODUKT else "artikel.typ_leistung"
                    ),
                ),
                Spalte(
                    ui_text("allgemein.spalte_aktiv"),
                    lambda a: ui_text("allgemein.ja" if a.aktiv else "allgemein.nein"),
                ),
            ],
            aktiv_attribut="aktiv",
        )
        self._liste.auswahl_geaendert.connect(self._auf_auswahl)
        links.addWidget(self._liste, 1)

        knoepfe = QHBoxLayout()
        neu = QPushButton(ui_text("artikel.knopf_neu"))
        neu.clicked.connect(self._neuer_artikel)
        self._loeschen_knopf = QPushButton(ui_text("allgemein.knopf_loeschen"))
        self._loeschen_knopf.clicked.connect(self._loeschen)
        knoepfe.addWidget(neu)
        knoepfe.addWidget(self._loeschen_knopf)
        knoepfe.addStretch(1)
        links.addLayout(knoepfe)
        layout.addLayout(links, 3)

        # Rechts: Detailmaske (Verhältnis 3:2, damit die Einzelpflege mitwächst); scrollbar
        # wie die übrigen Masken, damit hohe Inhalte bei kleiner Fensterhöhe nicht anstoßen.
        bereich = QScrollArea()
        bereich.setWidgetResizable(True)
        bereich.setWidget(self._baue_maske())
        layout.addWidget(bereich, 2)

    def _baue_maske(self) -> QGroupBox:
        box = QGroupBox(ui_text("artikel.gruppe"))
        aussen = QVBoxLayout(box)
        form = QFormLayout()

        self._name = QLineEdit()
        self._name.textChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("artikel.feld_name"), self._name)
        form.addRow(self._fehler_label("name"))

        preis_zeile = QHBoxLayout()
        self._betrag = QLineEdit()
        self._betrag.setPlaceholderText(ui_text("artikel.betrag_platzhalter"))
        self._betrag.textChanged.connect(self._markiere_geaendert)
        self._waehrung = QComboBox()  # geschlossen: nur Werte aus der Währungstabelle (S-0005 AK4)
        self._waehrung.currentTextChanged.connect(self._markiere_geaendert)
        preis_zeile.addWidget(self._betrag, 1)
        preis_zeile.addWidget(self._waehrung)
        form.addRow(ui_text("artikel.feld_vorschlagspreis"), preis_zeile)
        form.addRow(self._fehler_label("betrag"))
        form.addRow(self._fehler_label("waehrung"))

        self._typ = QComboBox()
        for schluessel, enum_wert in _TYP_OPTIONEN:
            self._typ.addItem(ui_text(schluessel), enum_wert)
        self._typ.currentIndexChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("artikel.feld_typ"), self._typ)

        self._aktiv = QCheckBox(ui_text("allgemein.aktiv"))
        self._aktiv.toggled.connect(self._markiere_geaendert)
        form.addRow("", self._aktiv)
        aussen.addLayout(form)
        aussen.addStretch(1)

        leiste = QHBoxLayout()
        leiste.addStretch(1)
        verwerfen = QPushButton(ui_text("allgemein.knopf_verwerfen"))
        verwerfen.clicked.connect(self._verwerfen)
        self._bestaetigen_knopf = QPushButton(ui_text("allgemein.knopf_bestaetigen"))
        self._bestaetigen_knopf.setDefault(True)
        self._bestaetigen_knopf.clicked.connect(self._bestaetigen)
        leiste.addWidget(verwerfen)
        leiste.addWidget(self._bestaetigen_knopf)
        aussen.addLayout(leiste)
        return box

    # --- Währungsauswahl ----------------------------------------------------

    def _fuelle_waehrungen(self, aktuell: str | None) -> None:
        """Füllt die Währungs-Combobox aus der Einstellungsliste; `aktuell` wird gesetzt.

        Die Auswahl ist geschlossen, weil die Währung aus der Währungstabelle stammen muss
        (S-0005 AK4). Ein Bestandswert außerhalb der Liste erscheint dennoch am Ende, sonst
        fiele er beim Öffnen still auf die Standardwährung und wäre beim nächsten Bestätigen
        verloren; dasselbe Muster trägt `VererbungsAuswahl` für die Kunden-Währung. Sichtbar
        heißt nicht gültig: `pruefe_artikel` meldet ihn beim Bestätigen feld-nah.
        """
        einst = self._datenbestand.einstellungen
        self._lade_laeuft = True
        self._waehrung.clear()
        self._waehrung.addItems(einst.waehrungsliste)
        wert = aktuell or einst.standardwaehrung
        if wert and self._waehrung.findText(wert) < 0:
            self._waehrung.addItem(wert)
        self._waehrung.setCurrentText(wert)
        self._lade_laeuft = False

    # --- Liste --------------------------------------------------------------

    def _fuelle_liste(self) -> None:
        self._liste.setze_objekte(self._datenbestand.artikel)

    def _auf_auswahl(self, artikel: object) -> None:
        """Auswahl in der Liste lädt den Artikel in die Maske (offene Änderungen entfallen)."""
        if isinstance(artikel, Artikel):
            self._lade_in_maske(artikel)

    # --- Laden und Zurückschreiben ------------------------------------------

    def _lade_in_maske(self, artikel: Artikel | None) -> None:
        """Zeigt einen Artikel (Ändern) oder leert die Maske (Anlegen)."""
        self._lade_laeuft = True
        self._aktueller = artikel
        if artikel is None:
            self._name.setText("")
            self._betrag.setText("")
            self._aktiv.setChecked(True)
            self._fuelle_waehrungen(None)
            self._typ.setCurrentIndex(self._typ.findData(ArtikelTyp.LEISTUNG))
        else:
            self._name.setText(artikel.artikelname)
            self._betrag.setText(format_betrag(artikel.vorschlagspreis.betrag))
            self._aktiv.setChecked(artikel.aktiv)
            self._fuelle_waehrungen(artikel.vorschlagspreis.waehrung)
            self._typ.setCurrentIndex(self._typ.findData(artikel.typ))
        self._loesche_fehler()
        self._lade_laeuft = False
        self._setze_geaendert(False)

    def _neuer_artikel(self) -> None:
        self._lade_in_maske(None)

    def _verwerfen(self) -> None:
        self._lade_in_maske(self._aktueller)

    # --- Aktionen -----------------------------------------------------------

    def _bestaetigen(self) -> None:
        self._loesche_fehler()
        name = self._name.text().strip()
        waehrung = self._waehrung.currentText().strip()
        betrag = parse_betrag(self._betrag.text())

        feld_fehler: dict[str, str] = {}
        if betrag is None:
            feld_fehler["betrag"] = ui_text("artikel.fehler_betrag")

        kandidat = Artikel(
            id=self._aktueller.id if self._aktueller else "",
            artikelname=name,
            vorschlagspreis=Preis(betrag=betrag or Decimal("0"), waehrung=waehrung),
            aktiv=self._aktiv.isChecked(),
            typ=ArtikelTyp(self._typ.currentData()),
        )
        ignoriere = self._aktueller.id if self._aktueller else None
        for befund in pruefe_artikel(kandidat, self._datenbestand, ignoriere_id=ignoriere):
            feld_fehler.setdefault(befund.feld, befund_text(befund))

        if feld_fehler:
            for feld, text in feld_fehler.items():
                self._zeige_feld_fehler(feld, text)
            return

        if self._aktueller is None:
            kandidat.id = str(uuid.uuid4())
            self._datenbestand.artikel.append(kandidat)
            self._aktueller = kandidat
        else:
            self._aktueller.artikelname = name
            self._aktueller.vorschlagspreis = Preis(betrag=betrag, waehrung=waehrung)
            self._aktueller.aktiv = self._aktiv.isChecked()
            self._aktueller.typ = ArtikelTyp(self._typ.currentData())

        if self._auto.speichere_jetzt(self):
            self._setze_geaendert(False)
        self._fuelle_liste()

    def _loeschen(self) -> None:
        artikel = self._liste.aktuelles_objekt()
        if not isinstance(artikel, Artikel):
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("artikel.bitte_auswaehlen"),
            )
            return
        if artikel_referenziert(self._datenbestand, artikel.id):
            QMessageBox.information(
                self,
                ui_text("artikel.loeschen_gesperrt_titel"),
                ui_text("artikel.loeschen_gesperrt_text"),
            )
            return
        antwort = QMessageBox.question(
            self,
            ui_text("artikel.loeschen_titel"),
            ui_text("artikel.loeschen_frage", name=artikel.artikelname),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if antwort != QMessageBox.Yes:
            return
        self._datenbestand.artikel.remove(artikel)
        self._auto.speichere_jetzt(self)
        self._fuelle_liste()
        self._neuer_artikel()
