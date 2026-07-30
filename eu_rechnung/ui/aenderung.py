"""Bestätigen-Knopf-Hervorhebung bei offenen Änderungen als gemeinsamer Baustein (S-0072, 4T-0088).

Kleiner UI-Baustein, den alle Erfassungsmasken (Firma, Artikel, Kunde, Bestellung,
Einstellungen, Rechnung) teilen: Solange seit dem Laden Felder verändert und noch nicht
bestätigt wurden, hebt sich der Bestätigen-Knopf farblich hervor (blau). Zuvor trug jede
Maske dieselbe Stil-Konstante und dasselbe Methodenpaar wortgleich; hier sind sie einmal
zusammengeführt, damit Farbe und Logik nicht auseinanderlaufen (analog `feld_fehler`).

Nutzung: die Maske erbt `AenderungsKnopfMixin` vor der Qt-Basis, legt `self._geaendert` und
`self._lade_laeuft` an, hält den Bestätigen-Knopf unter `self._bestaetigen_knopf` und hängt
`self._markiere_geaendert` an die Änderungssignale ihrer Felder.
"""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

# Blauer Aktionsknopf bei offenen Änderungen.
KNOPF_GEAENDERT_STIL = "background-color: #0067c0; color: white; font-weight: bold;"


class AenderungsKnopfMixin:
    """Verwaltet den Geändert-Zustand und die Hervorhebung des Bestätigen-Knopfs.

    Erwartet von der erbenden Maske `self._bestaetigen_knopf` (QPushButton), `self._geaendert`
    (bool) und `self._lade_laeuft` (bool, unterdrückt die Markierung beim programmatischen
    Befüllen). Der Baustein bringt keine eigene Qt-Basis und keinen Konstruktor mit, damit er
    sich als Mixin mit `QWidget` verträgt.
    """

    _bestaetigen_knopf: QPushButton
    _geaendert: bool
    _lade_laeuft: bool

    def _markiere_geaendert(self, *args) -> None:
        """Meldet eine Feld- oder Schalter-Änderung als offenen Stand.

        Während des Ladens (`_lade_laeuft`) werden die von `setText`/`setChecked` ausgelösten
        Signale ignoriert, damit das Befüllen der Maske nicht als Änderung zählt.
        """
        if self._lade_laeuft:
            return
        self._setze_geaendert(True)

    def _setze_geaendert(self, geaendert: bool) -> None:
        """Hebt den Bestätigen-Knopf bei offenen Änderungen hervor (S-0072, 4T-0088)."""
        self._geaendert = geaendert
        self._bestaetigen_knopf.setStyleSheet(KNOPF_GEAENDERT_STIL if geaendert else "")
