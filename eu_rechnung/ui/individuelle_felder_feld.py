"""Fünf-Plätze-Maskenteil für die individuellen Felder von Kunde und Bestellung (S-0040).

Wiederverwendbarer Baustein, den Kunde- und Bestellungs-Reiter teilen. Er zeigt fünf feste
Feld-Plätze, je Name, Aktiv-Schalter und Wert; die Obergrenze fünf ist damit strukturell
gesichert (S-0038). Ein Platz ohne Namen ist kein Feld; sein Aktiv-Schalter ist gesperrt, da
eine Aktivierung ohne Namen nicht zulässig ist (S-0038). Das Deaktivieren erhält Name und
Wert (verlustfrei); inaktive und leere Plätze sind dezent gekennzeichnet (S-0040). Änderungen
meldet der Baustein über das Signal `geaendert` an den Reiter (blauer Bestätigen-Knopf).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
)

from eu_rechnung.ui.sprache import ui_text

from eu_rechnung.domain import IndividuellesFeld

_PLAETZE = 5  # Obergrenze je Ebene (S-0038)
_INAKTIV_STIL = "color: #808080;"  # dezente Kennzeichnung inaktiver/leerer Plätze


class IndividuelleFelderFeld(QGroupBox):
    """Fünf-Plätze-Pflege der individuellen Felder einer Ebene (S-0038, S-0040)."""

    #: Meldet eine Änderung (Name, Aktiv oder Wert) an den umgebenden Reiter.
    geaendert = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(ui_text("individuelle_felder.gruppe"), parent)
        self._plaetze: list[tuple[QLineEdit, QCheckBox, QLineEdit]] = []
        self._lade_laeuft = False  # unterdrückt `geaendert` beim programmatischen Befüllen
        self._baue_ui()
        self.setze_felder([])  # initialer Zustand: leere Plätze, Aktiv-Schalter gesperrt

    def _baue_ui(self) -> None:
        raster = QGridLayout(self)
        raster.addWidget(QLabel(ui_text("allgemein.feld_name")), 0, 0)
        raster.addWidget(QLabel(ui_text("allgemein.spalte_aktiv")), 0, 1)
        raster.addWidget(QLabel(ui_text("individuelle_felder.spalte_wert")), 0, 2)
        raster.setColumnStretch(0, 1)
        raster.setColumnStretch(2, 2)
        for i in range(_PLAETZE):
            name = QLineEdit()
            aktiv = QCheckBox()
            wert = QLineEdit()
            name.textChanged.connect(lambda _t, idx=i: self._auf_name(idx))
            aktiv.toggled.connect(lambda _c, idx=i: self._auf_aktiv(idx))
            wert.textChanged.connect(self._auf_aenderung)
            raster.addWidget(name, i + 1, 0)
            raster.addWidget(aktiv, i + 1, 1)
            raster.addWidget(wert, i + 1, 2)
            self._plaetze.append((name, aktiv, wert))

    # --- Laden und Auslesen -------------------------------------------------

    def setze_felder(self, felder: list[IndividuellesFeld]) -> None:
        """Belegt die fünf Plätze aus den vorhandenen Feldern; überzählige werden ignoriert."""
        self._lade_laeuft = True
        for i, (name, aktiv, wert) in enumerate(self._plaetze):
            if i < len(felder):
                feld = felder[i]
                name.setText(feld.name)
                wert.setText(feld.wert)
                aktiv.setChecked(feld.aktiv)
            else:
                name.setText("")
                wert.setText("")
                aktiv.setChecked(False)
            self._aktualisiere_platz(i)
        self._lade_laeuft = False

    def felder(self) -> list[IndividuellesFeld]:
        """Die belegten Felder (Plätze mit Namen); leere Plätze werden übersprungen."""
        ergebnis: list[IndividuellesFeld] = []
        for name, aktiv, wert in self._plaetze:
            if name.text().strip():
                ergebnis.append(
                    IndividuellesFeld(
                        name=name.text().strip(),
                        aktiv=aktiv.isChecked(),
                        wert=wert.text().strip(),
                    )
                )
        return ergebnis

    # --- Reaktionen ---------------------------------------------------------

    def _auf_name(self, idx: int) -> None:
        self._aktualisiere_platz(idx)
        self._auf_aenderung()

    def _auf_aktiv(self, idx: int) -> None:
        self._aktualisiere_platz(idx)
        self._auf_aenderung()

    def _auf_aenderung(self, *args) -> None:
        if self._lade_laeuft:
            return
        self.geaendert.emit()

    def _aktualisiere_platz(self, idx: int) -> None:
        """Sperrt den Aktiv-Schalter ohne Namen und kennzeichnet inaktive/leere Plätze."""
        name, aktiv, wert = self._plaetze[idx]
        hat_namen = bool(name.text().strip())
        if not hat_namen and aktiv.isChecked():
            aktiv.setChecked(False)  # Aktivierung ohne Namen ist nicht zulässig (S-0038)
        aktiv.setEnabled(hat_namen)
        gedimmt = _INAKTIV_STIL if (not hat_namen or not aktiv.isChecked()) else ""
        name.setStyleSheet(gedimmt)
        wert.setStyleSheet(gedimmt)
