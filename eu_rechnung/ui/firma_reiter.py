"""Firma-Reiter: Erfassungs- und Änderungsmaske der eigenen Firma (S-0002, S-0004).

Zeigt die Daten der aktiven Firma in einer gegliederten Maske und ändert sie: oben
der Schalter „XRechnung aktivieren", darunter die Feldgruppen Firma, Adresse und
Kontakt sowie die Bankverbindungs-Liste (Hinzufügen und Ändern über einen
Popup-Dialog, Entfernen direkt in der Liste). Die Pflicht-Markierung folgt dem
Schalter und wechselt beim Umschalten sofort. Beim Bestätigen wird die Firma
stufenabhängig geprüft (`services.pruefe_firma`) und über das automatische Speichern
in die Firma-Datei geschrieben. Anlegen und Ändern nutzen dieselbe Maske (leer bzw.
vorbelegt, Muster K1); im aktuellen Stand ist die aktive Firma vorbelegt.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.domain import Adresse, Bankverbindung, Datenbestand, EigeneFirma
from eu_rechnung.services import pruefe_firma
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.bankverbindung_dialog import BankverbindungDialog
from eu_rechnung.ui.betrag import format_betrag, parse_betrag
from eu_rechnung.ui.aenderung import AenderungsKnopfMixin
from eu_rechnung.ui.feld_fehler import FeldFehlerMixin
from eu_rechnung.ui.sprache import befund_text, ui_text

# Feldgruppen: (Gruppen-Schlüssel, [(Feldname, Text-Schlüssel, Pflichtstufe), ...]).
# Pflichtstufe: "immer" (EN-Pflicht), "xr" (nur bei aktiver XRechnung), "opt" (nie).
#
# Die Konstante trägt **Katalog-Schlüssel, keine Texte**: Ein `ui_text()` an dieser Stelle
# liefe beim Import des Moduls, also bevor `app.main` die UI-Sprache gesetzt hat, und
# fröre die Beschriftungen dauerhaft auf Deutsch ein. Aufgelöst wird erst im Aufbau
# (`_baue_gruppe`) und bei jeder Pflicht-Markierung.
_GRUPPEN = [
    (
        "firma.gruppe_firma",
        [
            ("name", "firma.feld_name", "immer"),
            ("namenszusatz1", "firma.feld_namenszusatz1", "opt"),
            ("namenszusatz2", "firma.feld_namenszusatz2", "opt"),
            ("mwst", "firma.feld_mwst", "immer"),
            ("steuersatz", "firma.feld_steuersatz", "opt"),
        ],
    ),
    (
        "firma.gruppe_adresse",
        [
            ("strasse", "firma.feld_strasse", "xr"),
            ("hausnummer", "firma.feld_hausnummer", "opt"),
            ("plz", "firma.feld_plz", "xr"),
            ("ort", "firma.feld_ort", "xr"),
            ("land", "firma.feld_land", "immer"),
        ],
    ),
    (
        "firma.gruppe_kontakt",
        [
            ("kontakt", "firma.feld_kontakt", "xr"),
            ("telefon", "firma.feld_telefon", "xr"),
            ("email", "firma.feld_email", "xr"),
        ],
    ),
]


class FirmaReiter(FeldFehlerMixin, AenderungsKnopfMixin, QWidget):
    """Reiter mit der Erfassungs- und Änderungsmaske der eigenen Firma."""

    def __init__(
        self,
        datenbestand: Datenbestand,
        *,
        auto_speicher: AutoSpeicher | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._datenbestand = datenbestand
        self._auto = auto_speicher or AutoSpeicher(datenbestand)
        self._edits: dict[str, QLineEdit] = {}
        # schlüssel -> (Label, Basistext, Pflichtstufe) für die Live-Markierung
        self._pflicht: dict[str, tuple[QLabel, str, str]] = {}
        self._fehler: dict[str, QLabel] = {}
        self._bankverbindungen: list[Bankverbindung] = []
        self._geaendert = False
        self._lade_laeuft = False  # unterdrückt Änderungs-Signale beim Befüllen
        self._baue_ui()
        self._lade_aus_firma()

    # --- Aufbau -------------------------------------------------------------

    def _baue_ui(self) -> None:
        inhalt = QWidget()
        layout = QVBoxLayout(inhalt)

        self._schalter = QCheckBox(ui_text("firma.schalter_xrechnung"))
        self._schalter.toggled.connect(self._aktualisiere_pflicht)
        self._schalter.toggled.connect(self._markiere_geaendert)
        layout.addWidget(self._schalter)

        for gruppen_schluessel, felder in _GRUPPEN:
            layout.addWidget(self._baue_gruppe(gruppen_schluessel, felder))
        layout.addWidget(self._baue_bank_box(), 1)

        leiste = QHBoxLayout()
        leiste.addStretch(1)
        verwerfen = QPushButton(ui_text("allgemein.knopf_verwerfen"))
        verwerfen.clicked.connect(self._lade_aus_firma)
        self._bestaetigen_knopf = QPushButton(ui_text("allgemein.knopf_bestaetigen"))
        self._bestaetigen_knopf.setDefault(True)
        self._bestaetigen_knopf.clicked.connect(self._bestaetigen)
        leiste.addWidget(verwerfen)
        leiste.addWidget(self._bestaetigen_knopf)
        layout.addLayout(leiste)

        bereich = QScrollArea()
        bereich.setWidgetResizable(True)
        bereich.setWidget(inhalt)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(bereich)

    def _baue_gruppe(self, gruppen_schluessel: str, felder) -> QGroupBox:
        box = QGroupBox(ui_text(gruppen_schluessel))
        form = QFormLayout(box)
        for schluessel, text_schluessel, stufe in felder:
            feld = QLineEdit()
            feld.textChanged.connect(self._markiere_geaendert)
            anzeige = ui_text(text_schluessel)
            label = QLabel(anzeige)
            self._edits[schluessel] = feld
            self._pflicht[schluessel] = (label, anzeige, stufe)
            form.addRow(label, feld)
            form.addRow(self._fehler_label(schluessel))
        return box

    def _baue_bank_box(self) -> QGroupBox:
        self._bank_box = QGroupBox(ui_text("firma.gruppe_bankverbindungen"))
        layout = QVBoxLayout(self._bank_box)
        self._bank_tabelle = QTableWidget(0, 3)
        self._bank_tabelle.setHorizontalHeaderLabels(
            [
                ui_text("allgemein.feld_waehrung"),
                ui_text("bankverbindung.feld_iban"),
                ui_text("bankverbindung.feld_kontoinhaber"),
            ]
        )
        self._bank_tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._bank_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._bank_tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Mindestens fünf Bankverbindungen gleichzeitig sichtbar halten (plus Kopf).
        kopf_h = self._bank_tabelle.horizontalHeader().sizeHint().height()
        zeile_h = self._bank_tabelle.verticalHeader().defaultSectionSize()
        self._bank_tabelle.setMinimumHeight(
            kopf_h + 5 * zeile_h + 2 * self._bank_tabelle.frameWidth()
        )
        layout.addWidget(self._bank_tabelle)

        leiste = QHBoxLayout()
        hinzu = QPushButton(ui_text("allgemein.knopf_hinzufuegen"))
        hinzu.clicked.connect(self._bank_hinzufuegen)
        aendern = QPushButton(ui_text("allgemein.knopf_aendern"))
        aendern.clicked.connect(self._bank_aendern)
        entf = QPushButton(ui_text("allgemein.knopf_entfernen"))
        entf.clicked.connect(self._bank_entfernen)
        leiste.addWidget(hinzu)
        leiste.addWidget(aendern)
        leiste.addWidget(entf)
        leiste.addStretch(1)
        layout.addLayout(leiste)
        layout.addWidget(self._fehler_label("bank"))
        return self._bank_box

    # --- Pflicht-Markierung -------------------------------------------------

    def _aktualisiere_pflicht(self) -> None:
        """Setzt die Pflicht-Sterne je nach Schalterstellung (live).

        Der Basistext stammt aus dem Aufbau und steht damit bereits in der UI-Sprache; der
        Stern wird nur angehängt.
        """
        xr = self._schalter.isChecked()
        for label, basis, stufe in self._pflicht.values():
            pflicht = stufe == "immer" or (stufe == "xr" and xr)
            label.setText(f"{basis} *" if pflicht else basis)
        bank_titel = ui_text("firma.gruppe_bankverbindungen")
        self._bank_box.setTitle(f"{bank_titel} *" if xr else bank_titel)

    # --- Laden und Zurückschreiben -----------------------------------------

    def _lade_aus_firma(self) -> None:
        self._lade_laeuft = True
        f = self._datenbestand.eigene_firma
        zusatz = list(f.namenszusatz) + ["", ""]
        werte = {
            "name": f.name,
            "namenszusatz1": zusatz[0],
            "namenszusatz2": zusatz[1],
            "mwst": f.mehrwertsteuer_id,
            "strasse": f.adresse.strasse,
            "hausnummer": f.adresse.hausnummer,
            "plz": f.adresse.plz,
            "ort": f.adresse.ort,
            "land": f.adresse.land,
            "kontakt": f.kontakt_name,
            "telefon": f.telefon,
            "email": f.email,
            "steuersatz": format_betrag(f.standard_steuersatz),
        }
        for schluessel, wert in werte.items():
            self._edits[schluessel].setText(wert)
        self._schalter.setChecked(f.xrechnung_aktiv)
        self._bankverbindungen = [
            Bankverbindung(b.kontoinhaber, b.bank, b.iban, b.bic, b.waehrung)
            for b in f.bankverbindungen
        ]
        self._fuelle_bank_tabelle()
        self._aktualisiere_pflicht()
        self._loesche_fehler()
        self._lade_laeuft = False
        self._setze_geaendert(False)

    def _fuelle_bank_tabelle(self) -> None:
        self._bank_tabelle.setRowCount(0)
        for bank in self._bankverbindungen:
            zeile = self._bank_tabelle.rowCount()
            self._bank_tabelle.insertRow(zeile)
            for spalte, wert in enumerate([bank.waehrung, bank.iban, bank.kontoinhaber]):
                self._bank_tabelle.setItem(zeile, spalte, QTableWidgetItem(wert))

    def _leere_firma(self) -> EigeneFirma:
        """Baut ein leeres Firma-Objekt als Prüf-Kandidat (vor der Übernahme ins echte Objekt)."""
        return EigeneFirma(
            name="",
            adresse=Adresse(strasse="", plz="", ort="", land=""),
            mehrwertsteuer_id="",
            email="",
            telefon="",
            kontakt_name="",
        )

    def _uebernehme_in_firma(self, firma: EigeneFirma) -> None:
        """Schreibt die Maske-Eingaben in das übergebene Firma-Objekt (Kandidat oder echtes)."""
        firma.name = self._edits["name"].text().strip()
        firma.namenszusatz = [
            self._edits["namenszusatz1"].text().strip(),
            self._edits["namenszusatz2"].text().strip(),
        ]
        firma.mehrwertsteuer_id = self._edits["mwst"].text().strip()
        firma.adresse.strasse = self._edits["strasse"].text().strip()
        firma.adresse.hausnummer = self._edits["hausnummer"].text().strip()
        firma.adresse.plz = self._edits["plz"].text().strip()
        firma.adresse.ort = self._edits["ort"].text().strip()
        firma.adresse.land = self._edits["land"].text().strip()
        firma.kontakt_name = self._edits["kontakt"].text().strip()
        firma.telefon = self._edits["telefon"].text().strip()
        firma.email = self._edits["email"].text().strip()
        firma.standard_steuersatz = parse_betrag(self._edits["steuersatz"].text()) or Decimal("0")
        firma.xrechnung_aktiv = self._schalter.isChecked()
        firma.bankverbindungen = list(self._bankverbindungen)

    # --- Aktionen -----------------------------------------------------------

    def _markierte_bank(self) -> int:
        zeile = self._bank_tabelle.currentRow()
        return zeile if 0 <= zeile < len(self._bankverbindungen) else -1

    def _bank_hinzufuegen(self) -> None:
        dialog = BankverbindungDialog(
            self._datenbestand.einstellungen.waehrungsliste, parent=self
        )
        if dialog.exec() == QDialog.Accepted:
            self._bankverbindungen.append(dialog.bankverbindung())
            self._fuelle_bank_tabelle()
            self._markiere_geaendert()

    def _bank_aendern(self) -> None:
        zeile = self._markierte_bank()
        if zeile < 0:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("firma.bank_bitte_auswaehlen"),
            )
            return
        dialog = BankverbindungDialog(
            self._datenbestand.einstellungen.waehrungsliste,
            self._bankverbindungen[zeile],
            parent=self,
        )
        ergebnis = dialog.exec()
        if ergebnis == QDialog.Accepted:
            self._bankverbindungen[zeile] = dialog.bankverbindung()
        elif ergebnis == BankverbindungDialog.ENTFERNEN:
            del self._bankverbindungen[zeile]
        else:
            return
        self._fuelle_bank_tabelle()
        self._markiere_geaendert()

    def _bank_entfernen(self) -> None:
        zeile = self._markierte_bank()
        if zeile < 0:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("firma.bank_bitte_auswaehlen"),
            )
            return
        del self._bankverbindungen[zeile]
        self._fuelle_bank_tabelle()
        self._markiere_geaendert()

    def _bestaetigen(self) -> None:
        self._loesche_fehler()
        # Erst einen Kandidaten prüfen; das echte Objekt wird nie mit ungültigen Daten
        # überschrieben, damit Verwerfen den gespeicherten Stand zuverlässig zurückholt.
        kandidat = self._leere_firma()
        self._uebernehme_in_firma(kandidat)
        befunde = pruefe_firma(kandidat)
        if befunde:
            gesammelt: dict[str, list[str]] = {}
            for befund in befunde:
                gesammelt.setdefault(befund.feld, []).append(befund_text(befund))
            for feld, texte in gesammelt.items():
                self._zeige_feld_fehler(feld, "\n".join(texte))
            return
        self._uebernehme_in_firma(self._datenbestand.eigene_firma)
        if self._auto.speichere_jetzt(self):
            self._setze_geaendert(False)
