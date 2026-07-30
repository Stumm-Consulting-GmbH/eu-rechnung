"""Wiederverwendbarer Listen-Baustein mit Filtern und Sortieren (S-0010, Muster K2).

Zeigt eine Liste beliebiger Objekte in einer Tabelle mit vom Nutzer bedienbarem
Sortieren (Klick auf den Spaltenkopf) und einem freien Textfilter über alle angezeigten
Felder. Optional blendet ein „inaktive anzeigen"-Umschalter Objekte mit einem
aktiv-Flag aus (Default: nur aktive; S-0006). Je Spalte ist eine Einfärbung des
Zellentexts möglich (`Spalte.vordergrund`), um Zustände optisch abzusetzen. Die Zeilen
führen ihr Objekt über `Qt.UserRole` mit, sodass die Auswahl auch bei Filter und
Sortierung stabil auf das richtige Objekt verweist.

Der Baustein ist entitätsunabhängig: Artikel, Kunde und Bestellung konfigurieren ihn
über eine Spaltenliste und ein optionales aktiv-Attribut.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.ui.sprache import ui_text


class Spalte:
    """Spaltendefinition: Titel, Anzeigetext je Objekt, optionaler Sortierwert und Farbe.

    `anzeige` liefert den in der Zelle dargestellten Text. Ist `sortierwert` gesetzt,
    wird die Spalte danach sortiert (etwa numerisch für Beträge), sonst alphabetisch
    nach dem Anzeigetext. `vordergrund` färbt den Zellentext je Objekt ein und macht
    damit Zustände optisch unterscheidbar (etwa Entwurf gegenüber Erzeugt, S-0056); ohne
    Angabe oder bei Rückgabe `None` bleibt die Standardfarbe.
    """

    def __init__(
        self,
        titel: str,
        anzeige: Callable[[Any], str],
        *,
        sortierwert: Callable[[Any], Any] | None = None,
        vordergrund: Callable[[Any], QColor | None] | None = None,
    ) -> None:
        self.titel = titel
        self.anzeige = anzeige
        self.sortierwert = sortierwert
        self.vordergrund = vordergrund


class _SortierItem(QTableWidgetItem):
    """Tabellenzelle, die nach einem eigenen (etwa numerischen) Wert sortiert."""

    def __init__(self, text: str, sortierwert: Any) -> None:
        super().__init__(text)
        self._sortierwert = sortierwert

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _SortierItem):
            return self._sortierwert < other._sortierwert
        return super().__lt__(other)


class ObjektListe(QWidget):
    """Tabelle mit Textfilter, Spalten-Sortierung und optionalem aktiv-Filter."""

    #: Meldet die aktuelle Auswahl (das Objekt der markierten Zeile oder None).
    auswahl_geaendert = Signal(object)
    #: Meldet einen Doppelklick auf eine Zeile (das Objekt).
    objekt_aktiviert = Signal(object)

    def __init__(
        self,
        spalten: list[Spalte],
        *,
        aktiv_attribut: str | None = None,
        standard_sortierspalte: int = 0,
        standard_absteigend: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._spalten = spalten
        self._aktiv_attribut = aktiv_attribut
        self._standard_sortierspalte = standard_sortierspalte
        self._standard_absteigend = standard_absteigend
        self._objekte: list[Any] = []
        self._baue_ui()

    # --- Aufbau -------------------------------------------------------------

    def _baue_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        kopf = QHBoxLayout()
        kopf.addWidget(QLabel(ui_text("liste.filter_label")))
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(ui_text("liste.filter_platzhalter"))
        self._filter.textChanged.connect(self._wende_textfilter_an)
        kopf.addWidget(self._filter, 1)
        if self._aktiv_attribut is not None:
            self._inaktive = QCheckBox(ui_text("liste.inaktive_anzeigen"))
            self._inaktive.toggled.connect(self._neu_aufbauen)
            kopf.addWidget(self._inaktive)
        else:
            self._inaktive = None
        layout.addLayout(kopf)

        self._tabelle = QTableWidget(0, len(self._spalten))
        self._tabelle.setHorizontalHeaderLabels([s.titel for s in self._spalten])
        self._tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tabelle.setSortingEnabled(True)
        richtung = Qt.DescendingOrder if self._standard_absteigend else Qt.AscendingOrder
        self._tabelle.sortByColumn(self._standard_sortierspalte, richtung)
        # Mindestens fünf Zeilen sichtbar halten (plus Kopf).
        kopf_h = self._tabelle.horizontalHeader().sizeHint().height()
        zeile_h = self._tabelle.verticalHeader().defaultSectionSize()
        self._tabelle.setMinimumHeight(kopf_h + 5 * zeile_h + 2 * self._tabelle.frameWidth())
        self._tabelle.currentCellChanged.connect(self._auf_auswahl)
        self._tabelle.cellDoubleClicked.connect(self._auf_doppelklick)
        layout.addWidget(self._tabelle, 1)

    # --- Befüllen -----------------------------------------------------------

    def setze_objekte(self, objekte: list[Any]) -> None:
        """Übernimmt die Objektliste und baut die Tabelle nach den Filtern neu auf."""
        self._objekte = list(objekte)
        self._neu_aufbauen()

    def _sichtbare_objekte(self) -> list[Any]:
        """Objekte nach dem aktiv-Filter (Textfilter wirkt getrennt über Zeilen-Ausblenden)."""
        if self._aktiv_attribut is None or (self._inaktive and self._inaktive.isChecked()):
            return list(self._objekte)
        return [o for o in self._objekte if getattr(o, self._aktiv_attribut)]

    def _neu_aufbauen(self) -> None:
        self._tabelle.setSortingEnabled(False)
        self._tabelle.setRowCount(0)
        for objekt in self._sichtbare_objekte():
            zeile = self._tabelle.rowCount()
            self._tabelle.insertRow(zeile)
            for spalte_i, spalte in enumerate(self._spalten):
                text = spalte.anzeige(objekt)
                if spalte.sortierwert is not None:
                    item = _SortierItem(text, spalte.sortierwert(objekt))
                else:
                    item = QTableWidgetItem(text)
                if spalte.vordergrund is not None:
                    farbe = spalte.vordergrund(objekt)
                    if farbe is not None:
                        item.setForeground(farbe)
                if spalte_i == 0:
                    item.setData(Qt.UserRole, objekt)
                self._tabelle.setItem(zeile, spalte_i, item)
        self._tabelle.setSortingEnabled(True)
        self._wende_textfilter_an()

    def _wende_textfilter_an(self) -> None:
        muster = self._filter.text().strip().casefold()
        for zeile in range(self._tabelle.rowCount()):
            if not muster:
                self._tabelle.setRowHidden(zeile, False)
                continue
            treffer = any(
                muster in (self._tabelle.item(zeile, spalte_i).text().casefold())
                for spalte_i in range(len(self._spalten))
                if self._tabelle.item(zeile, spalte_i) is not None
            )
            self._tabelle.setRowHidden(zeile, not treffer)

    # --- Auswahl ------------------------------------------------------------

    def aktuelles_objekt(self) -> Any | None:
        """Das Objekt der markierten Zeile, oder None ohne gültige Auswahl."""
        zeile = self._tabelle.currentRow()
        if zeile < 0 or self._tabelle.isRowHidden(zeile):
            return None
        item = self._tabelle.item(zeile, 0)
        return item.data(Qt.UserRole) if item is not None else None

    def waehle_objekt(self, objekt: Any) -> None:
        """Markiert die Zeile des angegebenen Objekts, sofern sie sichtbar ist."""
        for zeile in range(self._tabelle.rowCount()):
            item = self._tabelle.item(zeile, 0)
            if item is not None and item.data(Qt.UserRole) is objekt:
                self._tabelle.setCurrentCell(zeile, 0)
                return

    def auswahl_aufheben(self) -> None:
        """Hebt die aktuelle Zeilenauswahl auf (etwa beim Wechsel in den Anlegen-Modus)."""
        self._tabelle.clearSelection()
        self._tabelle.setCurrentCell(-1, -1)

    def _auf_auswahl(self, *args) -> None:
        self.auswahl_geaendert.emit(self.aktuelles_objekt())

    def _auf_doppelklick(self, zeile: int, _spalte: int) -> None:
        item = self._tabelle.item(zeile, 0)
        if item is not None:
            self.objekt_aktiviert.emit(item.data(Qt.UserRole))
