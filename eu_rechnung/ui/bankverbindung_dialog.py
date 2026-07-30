"""Popup-Detailmaske zum Erfassen einer Bankverbindung (S-0002).

Das Hinzufügen und Ändern einer Bankverbindung läuft über diesen Dialog, damit die
Übersichtsliste im Firma-Reiter schlank bleibt. Er trägt Kontoinhaber, IBAN, Währung
(Auswahl mit freier Eingabe), Bank und BIC. Die inhaltliche Prüfung (IBAN-Prüfziffer,
BIC-Format) übernimmt die Firma-Validierung beim Speichern (`services.pruefe_firma`);
der Dialog erzwingt nur die Kern-Pflichtfelder Kontoinhaber, IBAN und Währung.

Beim Ändern trägt er zusätzlich einen Entfernen-Knopf, denn S-0002 AK4 verlangt das
Entfernen in der Liste **und** aus der Detailmaske heraus. Er meldet es über den eigenen
Ergebnis-Code `ENTFERNEN`, damit der Aufrufer die Liste führt und der Dialog nichts über
sie wissen muss. Beim Hinzufügen entfällt der Knopf: Es gibt noch nichts zu entfernen.
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

from eu_rechnung.domain import Bankverbindung
from eu_rechnung.ui.sprache import ui_text


class BankverbindungDialog(QDialog):
    """Erfasst oder ändert eine Bankverbindung."""

    #: Ergebnis-Code neben `Accepted`/`Rejected`: Der Anwender will sie entfernen (S-0002 AK4).
    ENTFERNEN = QDialog.Accepted + 1

    def __init__(
        self,
        waehrungen: list[str],
        bankverbindung: Bankverbindung | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(ui_text("bankverbindung.titel"))
        # Breit genug, dass die vollständige IBAN und längere Banknamen sichtbar sind.
        self.setMinimumWidth(500)
        self._kontoinhaber = QLineEdit()
        self._iban = QLineEdit()
        self._waehrung = QComboBox()
        self._waehrung.setEditable(True)  # Auswahl aus der Währungsliste plus freie Eingabe
        self._waehrung.addItems(waehrungen)
        self._bank = QLineEdit()
        self._bic = QLineEdit()

        form = QFormLayout(self)
        form.addRow(ui_text("bankverbindung.feld_kontoinhaber"), self._kontoinhaber)
        form.addRow(ui_text("bankverbindung.feld_iban"), self._iban)
        form.addRow(ui_text("allgemein.feld_waehrung"), self._waehrung)
        form.addRow(ui_text("bankverbindung.feld_bank"), self._bank)
        form.addRow(ui_text("bankverbindung.feld_bic"), self._bic)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._pruefe_und_akzeptiere)
        knoepfe.rejected.connect(self.reject)
        if bankverbindung is not None:
            entfernen = knoepfe.addButton(
                ui_text("allgemein.knopf_entfernen"), QDialogButtonBox.DestructiveRole
            )
            # Ohne Rückfrage, wie das Entfernen in der Liste (`_bank_entfernen`); die
            # Firma-Maske ist erst mit „Bestätigen" gespeichert, „Verwerfen" holt alles zurück.
            entfernen.clicked.connect(lambda: self.done(self.ENTFERNEN))
        form.addRow(knoepfe)

        if bankverbindung is not None:
            self._lade(bankverbindung)

    def _lade(self, b: Bankverbindung) -> None:
        self._kontoinhaber.setText(b.kontoinhaber)
        self._iban.setText(b.iban)
        self._waehrung.setCurrentText(b.waehrung)
        self._bank.setText(b.bank)
        self._bic.setText(b.bic)

    def _pruefe_und_akzeptiere(self) -> None:
        if not self._kontoinhaber.text().strip() or not self._iban.text().strip():
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("bankverbindung.pflicht_kontoinhaber_iban"),
            )
            return
        if not self._waehrung.currentText().strip():
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("bankverbindung.pflicht_waehrung"),
            )
            return
        self.accept()

    def bankverbindung(self) -> Bankverbindung:
        """Die erfasste Bankverbindung (nach `exec`)."""
        return Bankverbindung(
            kontoinhaber=self._kontoinhaber.text().strip(),
            bank=self._bank.text().strip(),
            iban=self._iban.text().strip(),
            bic=self._bic.text().strip(),
            waehrung=self._waehrung.currentText().strip(),
        )
