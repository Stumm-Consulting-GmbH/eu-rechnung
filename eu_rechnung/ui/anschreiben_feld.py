"""Zwei-Zustands-Anschreiben-Maskenteil für Kunde und Bestellung (S-0036).

Wiederverwendbarer Baustein für die Vererbungskaskade des Anschreibentexts: er trennt
sichtbar den geerbten vom überschriebenen Text und zeigt die Herkunft.

- Zustand „erbt" (Schalter aus, Default): das Textfeld zeigt den geerbten Text als nicht
  editierbare Vorschau; ein Hinweis nennt die Herkunfts-Ebene.
- Zustand „überschrieben" (Schalter an): das Textfeld ist editierbar und trägt den eigenen
  Text der Ebene.

Der Ebenen-Wert ist `None` (erbt) oder der überschriebene Text; ein leerer überschriebener
Text zählt als Erben (`None`). Der Reiter reicht den geerbten Text und die Herkunft herein
(er kennt die höheren Ebenen) und wird über das Signal `geaendert` über Änderungen
informiert (für den blauen Bestätigen-Knopf).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QGroupBox, QLabel, QPlainTextEdit, QVBoxLayout

from eu_rechnung.ui.sprache import ui_text


class AnschreibenFeld(QGroupBox):
    """Anschreiben-Maskenteil mit den Zuständen „erbt" und „überschrieben" (S-0036)."""

    #: Meldet eine Änderung (Umschalten oder Texteingabe) an den umgebenden Reiter.
    geaendert = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(ui_text("anschreiben.gruppe"), parent)
        self._geerbt_text = ""
        self._herkunft = ""
        self._lade_laeuft = False  # unterdrückt `geaendert` beim programmatischen Befüllen
        self._baue_ui()

    def _baue_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._schalter = QCheckBox(ui_text("anschreiben.schalter_ueberschreiben"))
        self._schalter.toggled.connect(self._auf_schalter)
        layout.addWidget(self._schalter)
        self._hinweis = QLabel("")
        self._hinweis.setWordWrap(True)
        self._hinweis.setStyleSheet("color: #606060; font-style: italic;")
        layout.addWidget(self._hinweis)
        self._text = QPlainTextEdit()
        self._text.setMinimumHeight(70)
        self._text.textChanged.connect(self._auf_text)
        layout.addWidget(self._text)

    # --- Laden und Auslesen -------------------------------------------------

    def setze_wert(self, wert: str | None, *, geerbt_text: str, herkunft: str) -> None:
        """Lädt den Ebenen-Wert (None = erbt) samt geerbter Vorschau und ihrer Herkunft.

        `herkunft` ist ein Katalog-Schlüssel (`allgemein.herkunft_*`), kein fertiger
        Text: Sonst käme die Herkunft in der Sprache des aufrufenden Reiters herein und
        bliebe beim Sprachwechsel stehen.
        """
        self._lade_laeuft = True
        self._geerbt_text = geerbt_text
        self._herkunft = herkunft
        self._schalter.setChecked(wert is not None)
        self._text.setPlainText(wert if wert is not None else geerbt_text)
        self._aktualisiere_ansicht()
        self._lade_laeuft = False

    def aktualisiere_vererbung(self, *, geerbt_text: str, herkunft: str) -> None:
        """Aktualisiert nur die geerbte Vorschau (etwa wenn sich der Eltern-Kunde ändert)."""
        self._geerbt_text = geerbt_text
        self._herkunft = herkunft
        if not self._schalter.isChecked():
            self._lade_laeuft = True
            self._text.setPlainText(geerbt_text)
            self._lade_laeuft = False
        self._aktualisiere_hinweis()

    def wert(self) -> str | None:
        """Der Ebenen-Wert: None (erbt) oder der überschriebene Text (leer zählt als erbt)."""
        if not self._schalter.isChecked():
            return None
        return self._text.toPlainText().strip() or None

    # --- Zustandswechsel ----------------------------------------------------

    def _auf_schalter(self, checked: bool) -> None:
        if self._lade_laeuft:
            return
        if not checked:
            # Zurücksetzen: den überschriebenen Text verwerfen und die Vorschau zeigen.
            self._lade_laeuft = True
            self._text.setPlainText(self._geerbt_text)
            self._lade_laeuft = False
        # Beim Aktivieren bleibt der (bislang geerbte) Text als Startpunkt stehen.
        self._aktualisiere_ansicht()
        self.geaendert.emit()

    def _auf_text(self) -> None:
        if self._lade_laeuft:
            return
        self.geaendert.emit()

    def _aktualisiere_ansicht(self) -> None:
        self._text.setReadOnly(not self._schalter.isChecked())
        self._aktualisiere_hinweis()

    def _aktualisiere_hinweis(self) -> None:
        if self._schalter.isChecked():
            self._hinweis.setVisible(False)
        else:
            self._hinweis.setText(ui_text("allgemein.erbt_von", herkunft=ui_text(self._herkunft)))
            self._hinweis.setVisible(True)
