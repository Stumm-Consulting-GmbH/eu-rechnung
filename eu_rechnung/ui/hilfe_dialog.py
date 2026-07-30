"""Prozessorientierte Hilfe, erreichbar über „Hilfe → Hilfe" und die Taste F1 (S-0078).

Bewusst **schlank**: Sie erklärt den empfohlenen Arbeitsablauf, nicht die einzelnen
Funktionen. Eine Detail-Funktionsbeschreibung der Masken und Felder ist ausdrücklich
ausgeschlossen; das hält die Hilfe pflegearm und lenkt einen neuen Nutzer nicht ab.

Aufbau: Einleitung, ein Hinweis auf die Einstellungen als jederzeit änderbare Vorgaben, die
sechs Stufen des Ablaufs mit je Tätigkeit und Ergebnis, ein Hinweis auf die
Rechnungsübersicht zum Wiederfinden und der Vermerk, dass der Ablauf eine Empfehlung ist.
Einstellungen und Rechnungsübersicht rahmen den Ablauf, statt eigene Stufen zu sein: Sie sind
keine Schritte der Kette (S-0078, AK7/AK8).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.ui.sprache import ui_text

# Die Stufen des Ablaufs in ihrer Reihenfolge; je Stufe ein Titel- und ein Text-Schlüssel.
# Die Reihenfolge ist die fachliche Kette (jede Stufe setzt die vorige voraus) und zugleich
# die Nummerierung in der Anzeige.
_STUFEN: tuple[str, ...] = (
    "firma",
    "artikel",
    "kunden",
    "bestellung",
    "rechnung_erfassen",
    "rechnung_erstellen",
)


class HilfeDialog(QDialog):
    """Fenster der F1-Prozesshilfe."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Texte beim Aufbau holen, nicht in Modul-Konstanten: Die UI-Sprache steht erst
        # nach dem Anwendungsstart fest (siehe ui/sprache.py).
        self.setWindowTitle(ui_text("hilfe.titel"))
        self.resize(560, 620)

        inhalt = QWidget()
        spalte = QVBoxLayout(inhalt)
        spalte.addWidget(self._absatz("hilfe.einleitung"))
        spalte.addSpacing(6)
        spalte.addWidget(self._absatz("hilfe.vorgaben"))
        spalte.addSpacing(10)

        for nummer, stufe in enumerate(_STUFEN, start=1):
            titel = self._absatz(f"hilfe.stufe_{stufe}_titel", praefix=f"{nummer}. ")
            schrift = titel.font()
            schrift.setBold(True)
            titel.setFont(schrift)
            spalte.addWidget(titel)
            spalte.addWidget(self._absatz(f"hilfe.stufe_{stufe}_text"))
            spalte.addSpacing(8)

        spalte.addWidget(self._absatz("hilfe.uebersicht"))
        spalte.addSpacing(6)
        spalte.addWidget(self._absatz("hilfe.empfehlung"))
        spalte.addStretch()

        # Scrollbar, weil der Ablauf länger ist als ein bequemes Fenster und die Texte je
        # nach Sprache unterschiedlich viel Platz brauchen.
        bereich = QScrollArea()
        bereich.setWidget(inhalt)
        bereich.setWidgetResizable(True)

        layout = QVBoxLayout(self)
        layout.addWidget(bereich)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        layout.addWidget(knoepfe)

    @staticmethod
    def _absatz(schluessel: str, praefix: str = "") -> QLabel:
        """Ein umbrechender Textabsatz aus dem Sprachkatalog.

        Der Umbruch ist der Grund für diesen Helfer: Ohne ihn meldet ein `QLabel` die volle
        Satzbreite als Wunschgröße, und die Hilfe besteht ausschließlich aus ganzen Sätzen.
        """
        absatz = QLabel(praefix + ui_text(schluessel))
        absatz.setWordWrap(True)
        return absatz
