"""Automatisches Speichern mit Fehlerbehandlung und Ungespeichert-Zustand (S-0072).

Zentraler `ui`-Dienst, über den die Oberfläche nach jeder bestätigten Operation die
aktive Datei speichert. Er kapselt Datenbestand und Zielpfad und schreibt atomar
über die `persistence`-Schicht. Schlägt das Speichern fehl, bietet er einen
Wiederholen/Abbrechen-Dialog an und meldet den ungespeicherten Zustand über das
Signal `ungespeichert_geaendert`, das die Oberfläche sichtbar kennzeichnet (etwa im
Fenstertitel). Der ungespeicherte Datenbestand bleibt im Programm erhalten.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from eu_rechnung.domain import Datenbestand
from eu_rechnung.persistence import STANDARD_PFAD, PersistenzFehler, speichere
from eu_rechnung.ui.sprache import ui_text


class AutoSpeicher(QObject):
    """Speichert den Datenbestand automatisch und verwaltet den Ungespeichert-Zustand."""

    #: Meldet Änderungen des Ungespeichert-Zustands (True = nicht gespeichert).
    ungespeichert_geaendert = Signal(bool)

    def __init__(
        self,
        datenbestand: Datenbestand,
        pfad: Path | str = STANDARD_PFAD,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._datenbestand = datenbestand
        self._pfad = pfad
        self._ungespeichert = False

    @property
    def ungespeichert(self) -> bool:
        """True, wenn Änderungen noch nicht auf die Datei geschrieben sind."""
        return self._ungespeichert

    def speichere_jetzt(self, parent: QWidget | None = None) -> bool:
        """Speichert den Datenbestand; bei Schreibfehler mit Wiederholen-Dialog.

        Gibt True bei Erfolg zurück, False bei Abbruch durch den Anwender. Nach
        einem Abbruch bleibt der ungespeicherte Zustand gesetzt; der Datenbestand
        selbst bleibt im Programm erhalten.
        """
        while True:
            try:
                speichere(self._datenbestand, self._pfad)
            except PersistenzFehler as fehler:
                self._setze_zustand(True)
                if not self._frage_wiederholen(parent, fehler):
                    return False
                continue
            self._setze_zustand(False)
            return True

    def melde_gespeichert(self) -> None:
        """Meldet, dass der Stand extern erfolgreich gespeichert wurde.

        Setzt den Ungespeichert-Zustand zurück, wenn eine Operation den Datenbestand
        an der Service-Schicht selbst persistiert hat (etwa das Anlegen einer
        Rechnung).
        """
        self._setze_zustand(False)

    def _setze_zustand(self, ungespeichert: bool) -> None:
        if ungespeichert != self._ungespeichert:
            self._ungespeichert = ungespeichert
            self.ungespeichert_geaendert.emit(ungespeichert)

    def _frage_wiederholen(self, parent: QWidget | None, fehler: Exception) -> bool:
        """Fragt nach einem Schreibfehler, ob erneut gespeichert werden soll."""
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(ui_text("auto_speicher.fehler_titel"))
        box.setText(ui_text("auto_speicher.fehler_text", fehler=fehler))
        wiederholen = box.addButton(
            ui_text("auto_speicher.wiederholen"), QMessageBox.AcceptRole
        )
        box.addButton(ui_text("auto_speicher.abbrechen"), QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is wiederholen
