"""Feld-nahe Validierungshinweise für Erfassungsmasken (4T-0097).

Kleiner UI-Baustein, den die Stammdaten-Masken (Firma, Artikel, Kunde, Bestellung) und die
Rechnungsmaske gemeinsam nutzen: je Feld ein rotes, zunächst verstecktes Fehler-Label, das beim Bestätigen den
zum Feld gehörenden Prüfbefund zeigt. Das Muster ist in 4T-0082/4T-0083 entstanden und
hier als Mixin zusammengeführt, damit alle Masken dieselbe Darstellung teilen.

Nutzung: der Reiter erbt `FeldFehlerMixin`, legt vor dem UI-Aufbau `self._fehler` als
leeres Dictionary an, erzeugt je Feld ein Label über `self._fehler_label(feldschluessel)`
und ruft beim Bestätigen `self._loesche_fehler()` sowie je Befund
`self._zeige_feld_fehler(feld, text)`.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

# Rote Schrift für Validierungshinweise am Feld.
FEHLER_STIL = "color: #c00000;"


class FeldFehlerMixin:
    """Verwaltet feld-nahe Fehler-Labels über `self._fehler: dict[str, QLabel]`.

    Erwartet, dass die erbende Klasse `self._fehler` vor dem ersten `_fehler_label`
    als Dictionary anlegt. Der Baustein bringt keine eigene Qt-Basis und keinen
    Konstruktor mit, damit er sich als erste Basis mit `QWidget` verträgt.
    """

    _fehler: dict[str, QLabel]

    def _fehler_label(self, feld: str) -> QLabel:
        """Erzeugt ein verstecktes rotes Label und merkt es unter `feld` vor."""
        label = QLabel("")
        label.setStyleSheet(FEHLER_STIL)
        label.setWordWrap(True)
        label.setVisible(False)
        self._fehler[feld] = label
        return label

    def _loesche_fehler(self) -> None:
        """Blendet alle Fehler-Labels aus und leert ihren Text."""
        for label in self._fehler.values():
            label.setText("")
            label.setVisible(False)

    def _zeige_feld_fehler(self, feld: str, text: str) -> None:
        """Zeigt `text` am Label des Feldes `feld`, sofern eines vorgemerkt ist."""
        label = self._fehler.get(feld)
        if label is not None:
            label.setText(text)
            label.setVisible(True)
