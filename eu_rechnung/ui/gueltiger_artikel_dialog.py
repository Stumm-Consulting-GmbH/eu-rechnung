"""Popup-Detailmaske zum Erfassen eines gültigen Artikels einer Bestellung (S-0018).

Das Hinzufügen und Ändern eines gültigen Artikels läuft über diesen Dialog, damit die
Übersichtsliste in der Bestellungs-Maske schlank bleibt (dasselbe Muster wie die
Bankverbindungen der Firma). Er trägt die Artikel-Auswahl (nur aktive Artikel), den aus
dem Vorschlagspreis vorbelegten, überschreibbaren Einzelpreis und die optionale Obergrenze
(Art Menge oder Betrag und Wert). Die Betragsfelder nutzen den gemeinsamen
Betrags-Baustein.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from eu_rechnung.domain import Artikel, GueltigerArtikel, Obergrenze, ObergrenzeArt
from eu_rechnung.ui.betrag import format_betrag, parse_betrag
from eu_rechnung.ui.sprache import ui_text

# Auswahl der Obergrenze-Art: (Katalog-Schlüssel, Enum-Wert); None = keine Obergrenze.
#
# Zuvor war der deutsche Anzeigetext zugleich der Schlüssel dieses dicts. Das ging nicht
# mehr, sobald die Anzeige übersetzt wird: Der Text hätte den Zustand der Auswahl bestimmt
# und wäre beim Import auf Deutsch eingefroren. Die Zuordnung läuft nun über die
# Combobox-`data` (Enum-Wert), unabhängig vom angezeigten Text.
_ARTEN = [
    ("gueltiger_artikel.art_keine", None),
    ("gueltiger_artikel.art_menge", ObergrenzeArt.MENGE),
    ("gueltiger_artikel.art_betrag", ObergrenzeArt.BETRAG),
]


class GueltigerArtikelDialog(QDialog):
    """Erfasst oder ändert einen gültigen Artikel einer Bestellung."""

    def __init__(
        self,
        aktive_artikel: list[Artikel],
        belegwaehrung: str,
        vorhanden: GueltigerArtikel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(ui_text("gueltiger_artikel.titel"))
        self.setMinimumWidth(460)
        self._artikel = list(aktive_artikel)
        self._belegwaehrung = belegwaehrung

        self._auswahl = QComboBox()
        for artikel in self._artikel:
            self._auswahl.addItem(artikel.artikelname, artikel.id)
        self._auswahl.currentIndexChanged.connect(self._auf_artikel_wechsel)

        self._einzelpreis = QLineEdit()
        self._art = QComboBox()
        for schluessel, enum_wert in _ARTEN:
            self._art.addItem(ui_text(schluessel), enum_wert)
        self._art.currentIndexChanged.connect(self._auf_art_wechsel)
        self._grenzwert = QLineEdit()
        self._grenzwert.setPlaceholderText(ui_text("gueltiger_artikel.obergrenze_platzhalter"))

        form = QFormLayout(self)
        form.addRow(ui_text("gueltiger_artikel.feld_artikel"), self._auswahl)
        form.addRow(ui_text("gueltiger_artikel.feld_einzelpreis"), self._einzelpreis)
        form.addRow(ui_text("gueltiger_artikel.feld_obergrenze"), self._art)
        form.addRow(ui_text("gueltiger_artikel.feld_obergrenze_wert"), self._grenzwert)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._pruefe_und_akzeptiere)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

        if vorhanden is not None:
            self._lade(vorhanden)
        else:
            self._auf_artikel_wechsel()  # Einzelpreis aus dem ersten Artikel vorbelegen
        self._auf_art_wechsel()

    # --- Vorbelegung --------------------------------------------------------

    def _artikel_zu_id(self, artikel_id) -> Artikel | None:
        return next((a for a in self._artikel if a.id == artikel_id), None)

    def _auf_artikel_wechsel(self, *args) -> None:
        """Belegt den Einzelpreis aus dem Vorschlagspreis vor, aber nur bei passender Belegwährung.

        Weicht die Preiswährung des Artikels von der Belegwährung ab, gibt es keine
        Vorbelegung und keine Umrechnung; der Einzelpreis wird dann manuell gepflegt (S-0019).
        """
        artikel = self._artikel_zu_id(self._auswahl.currentData())
        if artikel is not None and artikel.vorschlagspreis.waehrung == self._belegwaehrung:
            self._einzelpreis.setText(format_betrag(artikel.vorschlagspreis.betrag))
        else:
            self._einzelpreis.clear()

    def _gewaehlte_art(self) -> ObergrenzeArt | None:
        """Die gewählte Obergrenze-Art aus der Auswahl-`data`, unabhängig vom Anzeigetext.

        Qt reicht die `data` durch ein QVariant und gibt aus `ObergrenzeArt.MENGE` den
        blanken String `"menge"` zurück (das Enum erbt von `str`). Der Wert wird deshalb
        zurückgewandelt: Sonst trüge `Obergrenze.art` einen `str` statt des Enums, was
        heute nur zufällig gutgeht, weil sich beide gleich vergleichen und serialisieren.
        """
        wert = self._art.currentData()
        return ObergrenzeArt(wert) if wert is not None else None

    def _auf_art_wechsel(self, *args) -> None:
        """Schaltet das Wertfeld je nach gewählter Obergrenze-Art frei oder gesperrt."""
        gesetzt = self._gewaehlte_art() is not None
        self._grenzwert.setEnabled(gesetzt)
        if not gesetzt:
            self._grenzwert.clear()

    def _lade(self, gueltiger: GueltigerArtikel) -> None:
        index = self._auswahl.findData(gueltiger.artikel_id)
        if index >= 0:
            self._auswahl.setCurrentIndex(index)
        self._einzelpreis.setText(format_betrag(gueltiger.einzelpreis))
        if gueltiger.obergrenze is not None:
            self._art.setCurrentIndex(self._art.findData(gueltiger.obergrenze.art))
            self._grenzwert.setText(format_betrag(gueltiger.obergrenze.wert))

    # --- Prüfung und Ergebnis ----------------------------------------------

    def _pruefe_und_akzeptiere(self) -> None:
        if self._auswahl.currentData() is None:
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("gueltiger_artikel.pflicht_artikel"),
            )
            return
        if parse_betrag(self._einzelpreis.text()) is None:
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("gueltiger_artikel.fehler_einzelpreis"),
            )
            return
        if self._gewaehlte_art() is not None and parse_betrag(self._grenzwert.text()) is None:
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("gueltiger_artikel.fehler_obergrenze"),
            )
            return
        self.accept()

    def gueltiger_artikel(self) -> GueltigerArtikel:
        """Der erfasste gültige Artikel (nach `exec`)."""
        art = self._gewaehlte_art()
        obergrenze = None
        if art is not None:
            obergrenze = Obergrenze(art=art, wert=parse_betrag(self._grenzwert.text()))
        return GueltigerArtikel(
            artikel_id=self._auswahl.currentData(),
            einzelpreis=parse_betrag(self._einzelpreis.text()),
            obergrenze=obergrenze,
        )
