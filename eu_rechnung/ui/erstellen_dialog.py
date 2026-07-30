"""Dialog zur Formatwahl der Rechnungserstellung (S-0032).

Kleiner Auswahldialog für die Aktion „Rechnung erstellen": XRechnung, ZUGFeRD
oder beide. Die eigentliche Erzeugung und die Überschreib-Entscheidung liegen in
der Service-Schicht bzw. im Hauptfenster; dieser Dialog liefert nur die Auswahl.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.services import Format
from eu_rechnung.ui.sprache import ui_text


class FormatDialog(QDialog):
    """Auswahl der zu erstellenden Ausgabeformate (mindestens eines)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ui_text("erstellen.titel"))
        # Die Formatnamen sind Eigennamen der Norm und bleiben in jeder Sprache gleich.
        self._xrechnung = QCheckBox(ui_text("erstellen.format_xrechnung"))
        self._zugferd = QCheckBox(ui_text("erstellen.format_zugferd"))
        self._xrechnung.setChecked(True)
        self._zugferd.setChecked(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(ui_text("erstellen.frage")))
        layout.addWidget(self._xrechnung)
        layout.addWidget(self._zugferd)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._pruefe_und_akzeptiere)
        knoepfe.rejected.connect(self.reject)
        layout.addWidget(knoepfe)

    def _pruefe_und_akzeptiere(self) -> None:
        if not (self._xrechnung.isChecked() or self._zugferd.isChecked()):
            QMessageBox.warning(
                self,
                ui_text("erstellen.kein_format_titel"),
                ui_text("erstellen.kein_format_text"),
            )
            return
        self.accept()

    def formate(self) -> set[Format]:
        """Die gewählten Formate (nach `exec`)."""
        gewaehlt: set[Format] = set()
        if self._xrechnung.isChecked():
            gewaehlt.add(Format.XRECHNUNG)
        if self._zugferd.isChecked():
            gewaehlt.add(Format.ZUGFERD)
        return gewaehlt
