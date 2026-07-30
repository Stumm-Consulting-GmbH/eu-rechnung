"""Einstellungen-Reiter: globale Programm-Einstellungen (S-0035, S-0044, S-0059).

Der globale Standard-Anschreibentext (Wurzelwert der Anschreiben-Vererbungskaskade, F-0007),
die Sprache der Bedienoberfläche (S-0059) und die Nummernkreise: die nächste Kundennummer
(Präfix D) und die Jahres-Zähler der Rechnungsnummer, je Jahr korrigierbar und um ein neues
Jahr erweiterbar (F-0009, S-0044). Nur positive ganze Zahlen sind zulässig; die nächste
Vergabe nutzt den korrigierten Stand. Feld-nahe Prüfung über den geteilten
`FeldFehlerMixin`, blauer Bestätigen-Knopf bei offenen Änderungen (S-0072), automatisches
Speichern.

Alle Texte kommen aus dem Sprachkatalog (`ui.sprache.ui_text`) und folgen der UI-Sprache
(S-0061). Ausgenommen sind die Sprachnamen der Auswahl selbst: Sie stehen in ihrer eigenen
Sprache, damit ein Anwender sie auch in einer fremdsprachigen Oberfläche findet.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.domain import Datenbestand
from eu_rechnung.services import pruefe_einstellungen, waehrung_referenziert
from eu_rechnung.texte import SPRACH_NAMEN, SPRACHEN, normierte_sprache
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.aenderung import AenderungsKnopfMixin
from eu_rechnung.ui.feld_fehler import FeldFehlerMixin
from eu_rechnung.ui.sprache import befund_text, ui_text


class EinstellungenReiter(FeldFehlerMixin, AenderungsKnopfMixin, QWidget):
    """Reiter zur Pflege der globalen Einstellungen (Standard-Anschreibentext und Nummernkreise)."""

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
        self._fehler: dict[str, QLabel] = {}
        self._geaendert = False
        self._lade_laeuft = False  # unterdrückt Änderungs-Signale beim Befüllen
        self._baue_ui()
        self._lade_aus_einstellungen()

    # --- Aufbau -------------------------------------------------------------

    def _baue_ui(self) -> None:
        layout = QVBoxLayout(self)

        box = QGroupBox(ui_text("einstellungen.gruppe_anschreiben"))
        form = QFormLayout(box)
        self._standard = QPlainTextEdit()
        self._standard.setPlaceholderText(ui_text("einstellungen.standardtext_platzhalter"))
        self._standard.textChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("einstellungen.feld_standardtext"), self._standard)
        form.addRow(self._fehler_label("standard_anschreibentext"))
        layout.addWidget(box)

        layout.addWidget(self._baue_sprache())
        layout.addWidget(self._baue_waehrungen())
        layout.addWidget(self._baue_ausgabe())
        layout.addWidget(self._baue_nummernkreise())
        layout.addStretch(1)

        leiste = QHBoxLayout()
        leiste.addStretch(1)
        verwerfen = QPushButton(ui_text("allgemein.knopf_verwerfen"))
        verwerfen.clicked.connect(self._lade_aus_einstellungen)
        self._bestaetigen_knopf = QPushButton(ui_text("allgemein.knopf_bestaetigen"))
        self._bestaetigen_knopf.setDefault(True)
        self._bestaetigen_knopf.clicked.connect(self._bestaetigen)
        leiste.addWidget(verwerfen)
        leiste.addWidget(self._bestaetigen_knopf)
        layout.addLayout(leiste)

    def _baue_sprache(self) -> QGroupBox:
        """Gruppe „Sprache": die Sprache der Bedienoberfläche (S-0059 AK1).

        Die Sprachnamen stehen bewusst in ihrer eigenen Sprache und werden nicht übersetzt:
        Wer die Oberfläche in einer Sprache vorfindet, die er nicht liest, muss seine
        eigene trotzdem finden können.
        """
        box = QGroupBox(ui_text("einstellungen.gruppe_sprache"))
        form = QFormLayout(box)
        self._sprache = QComboBox()
        for kuerzel in SPRACHEN:
            self._sprache.addItem(SPRACH_NAMEN[kuerzel], kuerzel)
        self._sprache.currentIndexChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("einstellungen.feld_ui_sprache"), self._sprache)

        hinweis = QLabel(ui_text("einstellungen.sprache_hinweis"))
        hinweis.setWordWrap(True)
        hinweis.setEnabled(False)  # dezent, als erläuternder Hinweis erkennbar
        form.addRow(hinweis)
        return box

    def _waehle_sprache(self, sprache: str) -> None:
        """Stellt die Auswahl auf eine Sprache; unbekannte Werte landen auf Deutsch."""
        index = self._sprache.findData(normierte_sprache(sprache))
        self._sprache.setCurrentIndex(index)

    def _baue_waehrungen(self) -> QGroupBox:
        """Gruppe „Währungen": die pflegbare Liste und die Standardwährung daraus (S-0062).

        Die Standardwährung ist eine Auswahl **aus der Tabelle**, kein freies Feld: Beide
        können so nicht auseinanderlaufen, und der Anwender sieht sofort, was zur Wahl steht.
        """
        box = QGroupBox(ui_text("einstellungen.gruppe_waehrungen"))
        aussen = QVBoxLayout(box)

        aussen.addWidget(QLabel(ui_text("einstellungen.waehrungsliste")))
        self._waehrungen = QTableWidget(0, 1)
        self._waehrungen.setHorizontalHeaderLabels([ui_text("einstellungen.spalte_waehrung")])
        self._waehrungen.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._waehrungen.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self._waehrungen.setSelectionBehavior(QAbstractItemView.SelectRows)
        kopf_h = self._waehrungen.horizontalHeader().sizeHint().height()
        zeile_h = self._waehrungen.verticalHeader().defaultSectionSize()
        self._waehrungen.setMinimumHeight(
            kopf_h + 4 * zeile_h + 2 * self._waehrungen.frameWidth()
        )
        self._waehrungen.itemChanged.connect(self._waehrungen_geaendert)
        aussen.addWidget(self._waehrungen)
        aussen.addWidget(self._fehler_label("waehrungsliste"))

        knopf_zeile = QHBoxLayout()
        hinzu = QPushButton(ui_text("einstellungen.knopf_waehrung_hinzufuegen"))
        hinzu.clicked.connect(self._waehrung_hinzufuegen)
        entfernen = QPushButton(ui_text("allgemein.knopf_entfernen"))
        entfernen.clicked.connect(self._waehrung_entfernen)
        knopf_zeile.addWidget(hinzu)
        knopf_zeile.addWidget(entfernen)
        knopf_zeile.addStretch(1)
        aussen.addLayout(knopf_zeile)

        form = QFormLayout()
        self._standardwaehrung = QComboBox()
        self._standardwaehrung.currentIndexChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("einstellungen.feld_standardwaehrung"), self._standardwaehrung)
        form.addRow(self._fehler_label("standardwaehrung"))
        aussen.addLayout(form)

        hinweis = QLabel(ui_text("einstellungen.waehrung_hinweis"))
        hinweis.setWordWrap(True)
        hinweis.setEnabled(False)  # dezent, als erläuternder Hinweis erkennbar
        aussen.addWidget(hinweis)
        return box

    def _baue_ausgabe(self) -> QGroupBox:
        """Ausgabe-Verzeichnis: Wurzel der Ablage erzeugter Rechnungen (S-0057)."""
        box = QGroupBox(ui_text("einstellungen.gruppe_ausgabe"))
        form = QFormLayout(box)
        self._ausgabe = QLineEdit()
        self._ausgabe.setPlaceholderText(ui_text("einstellungen.ausgabe_platzhalter"))
        self._ausgabe.textChanged.connect(self._markiere_geaendert)
        waehlen = QPushButton(ui_text("einstellungen.knopf_ordner_waehlen"))
        waehlen.clicked.connect(self._waehle_ausgabe_verzeichnis)

        zeile = QHBoxLayout()
        zeile.addWidget(self._ausgabe)
        zeile.addWidget(waehlen)
        zeile_w = QWidget()
        zeile_w.setLayout(zeile)
        form.addRow(ui_text("einstellungen.feld_ausgabe_verzeichnis"), zeile_w)
        form.addRow(self._fehler_label("ausgabe_verzeichnis"))
        return box

    def _waehle_ausgabe_verzeichnis(self) -> None:
        """Ordner-Auswahl; startet im gesetzten Verzeichnis, sonst in „Dokumente"."""
        start = self._ausgabe.text().strip() or QStandardPaths.writableLocation(
            QStandardPaths.DocumentsLocation
        )
        ordner = QFileDialog.getExistingDirectory(
            self, ui_text("einstellungen.ordner_dialog_titel"), start
        )
        if ordner:
            self._ausgabe.setText(ordner)

    def _baue_nummernkreise(self) -> QGroupBox:
        """Gruppe „Nummernkreise": nächste Kundennummer und Jahres-Zähler der Rechnungsnummer."""
        box = QGroupBox(ui_text("einstellungen.gruppe_nummernkreise"))
        aussen = QVBoxLayout(box)

        form = QFormLayout()
        self._debitor = QLineEdit()
        self._debitor.setPlaceholderText(ui_text("einstellungen.debitor_platzhalter"))
        self._debitor.textChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("einstellungen.feld_debitor"), self._debitor)
        form.addRow(self._fehler_label("debitornummer"))
        aussen.addLayout(form)

        aussen.addWidget(QLabel(ui_text("einstellungen.rechnungsnummer_je_jahr")))
        self._jahre = QTableWidget(0, 2)
        self._jahre.setHorizontalHeaderLabels(
            [ui_text("einstellungen.spalte_jahr"), ui_text("einstellungen.spalte_naechste_nummer")]
        )
        self._jahre.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._jahre.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        kopf_h = self._jahre.horizontalHeader().sizeHint().height()
        zeile_h = self._jahre.verticalHeader().defaultSectionSize()
        self._jahre.setMinimumHeight(kopf_h + 4 * zeile_h + 2 * self._jahre.frameWidth())
        self._jahre.itemChanged.connect(self._markiere_geaendert)
        aussen.addWidget(self._jahre)
        aussen.addWidget(self._fehler_label("rechnungsnummer"))

        knopf_zeile = QHBoxLayout()
        jahr_knopf = QPushButton(ui_text("einstellungen.knopf_jahr_hinzufuegen"))
        jahr_knopf.clicked.connect(self._jahr_hinzufuegen)
        knopf_zeile.addWidget(jahr_knopf)
        knopf_zeile.addStretch(1)
        aussen.addLayout(knopf_zeile)
        return box

    # --- Laden und Zurückschreiben -----------------------------------------

    def showEvent(self, event) -> None:
        """Beim Anzeigen des Reiters die Einstellungen neu einlesen (S-0044 AK3).

        Nötig wegen der Nummernkreise: Sie wachsen **außerhalb** dieses Reiters weiter,
        mit jeder angelegten Rechnung und jedem angelegten Kunden. Der Reiter entsteht
        einmal beim Aktivieren der Firma und hielte sonst dauerhaft seinen Ladestand. Das
        wäre nicht nur eine falsche Anzeige: Ein „Bestätigen" schriebe den veralteten
        Zähler zurück, und die nächste Rechnung erhielte eine bereits vergebene Nummer.

        Offene, noch nicht bestätigte Eingaben bleiben unangetastet; sie neu zu laden
        zöge dem Anwender weg, woran er gerade arbeitet. Der blaue Bestätigen-Knopf
        zeigt diesen Zustand an.
        """
        super().showEvent(event)
        if not self._geaendert:
            self._lade_aus_einstellungen()

    def _lade_aus_einstellungen(self) -> None:
        self._lade_laeuft = True
        einstellungen = self._datenbestand.einstellungen
        self._standard.setPlainText(einstellungen.standard_anschreibentext)
        self._waehle_sprache(einstellungen.ui_sprache)
        self._lade_waehrungen(einstellungen.waehrungsliste, einstellungen.standardwaehrung)
        self._ausgabe.setText(einstellungen.ausgabe_verzeichnis)
        self._debitor.setText(str(einstellungen.naechste_debitornummer))
        self._lade_jahres_tabelle(einstellungen.naechste_rechnungsnummer)
        self._loesche_fehler()
        self._lade_laeuft = False
        self._setze_geaendert(False)

    # --- Währungen ----------------------------------------------------------

    def _lade_waehrungen(self, liste: list[str], standard: str) -> None:
        self._waehrungen.setRowCount(0)
        for code in liste:
            zeile = self._waehrungen.rowCount()
            self._waehrungen.insertRow(zeile)
            self._waehrungen.setItem(zeile, 0, QTableWidgetItem(code))
        self._fuelle_standardwaehrung(standard)

    def _lese_waehrungen(self) -> list[str]:
        """Die Codes der Tabelle in ihrer Reihenfolge; leere Zeilen bleiben außen vor."""
        codes = []
        for zeile in range(self._waehrungen.rowCount()):
            item = self._waehrungen.item(zeile, 0)
            code = item.text().strip() if item is not None else ""
            if code:
                codes.append(code)
        return codes

    def _fuelle_standardwaehrung(self, wunsch: str | None = None) -> None:
        """Füllt die Auswahl aus der Tabelle und hält die bisherige Wahl, wenn es sie noch gibt.

        `wunsch` gewinnt (beim Laden aus den Einstellungen); sonst bleibt die aktuelle
        Auswahl bestehen. Steht der Wert nicht mehr in der Liste, wird nichts gewählt: Das
        ist ehrlicher als eine stille Ersatzwahl, und `pruefe_einstellungen` benennt es beim
        Bestätigen.
        """
        ziel = wunsch if wunsch is not None else self._standardwaehrung.currentText()
        gesperrt = self._lade_laeuft
        self._lade_laeuft = True  # das Neu-Füllen ist keine Anwender-Änderung
        self._standardwaehrung.clear()
        self._standardwaehrung.addItems(self._lese_waehrungen())
        index = self._standardwaehrung.findText(ziel)
        self._standardwaehrung.setCurrentIndex(index)  # -1 = keine Wahl, wenn nicht gefunden
        self._lade_laeuft = gesperrt

    def _waehrungen_geaendert(self, *args) -> None:
        """Tabellen-Änderung: Auswahl nachziehen und den Bestätigen-Knopf hervorheben."""
        if self._lade_laeuft:
            return
        self._fuelle_standardwaehrung()
        self._markiere_geaendert()

    def _waehrung_hinzufuegen(self) -> None:
        """Hängt eine leere, editierbare Zeile an und springt zum Bearbeiten hinein."""
        zeile = self._waehrungen.rowCount()
        self._waehrungen.insertRow(zeile)
        item = QTableWidgetItem("")
        self._waehrungen.setItem(zeile, 0, item)
        self._waehrungen.setCurrentItem(item)
        self._waehrungen.editItem(item)
        self._markiere_geaendert()

    def _waehrung_entfernen(self) -> None:
        """Entfernt die gewählte Währung, sofern sie nirgends in Gebrauch ist (S-0062).

        Der Löschschutz prüft den **gespeicherten** Bestand (wie `artikel_referenziert`).
        Wer die Standardwährung gerade erst umgestellt, aber noch nicht bestätigt hat, muss
        deshalb erst bestätigen; die Meldung nennt die Fundstelle und macht das erklärbar.
        """
        zeile = self._waehrungen.currentRow()
        if zeile < 0:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("einstellungen.waehrung_bitte_auswaehlen"),
            )
            return
        item = self._waehrungen.item(zeile, 0)
        code = item.text().strip() if item is not None else ""
        befund = waehrung_referenziert(self._datenbestand, code) if code else None
        if befund is not None:
            QMessageBox.warning(
                self,
                ui_text("einstellungen.waehrung_in_gebrauch_titel"),
                ui_text(
                    "einstellungen.waehrung_in_gebrauch_text",
                    code=code,
                    fundstelle=befund_text(befund),
                ),
            )
            return
        self._waehrungen.removeRow(zeile)
        self._fuelle_standardwaehrung()
        self._markiere_geaendert()

    def _lade_jahres_tabelle(self, zaehler: dict[str, int]) -> None:
        self._jahre.setRowCount(0)
        for jahr in sorted(zaehler):
            self._fuege_jahr_zeile(jahr, zaehler[jahr], jahr_editierbar=False)

    def _fuege_jahr_zeile(self, jahr: str, nummer: int, *, jahr_editierbar: bool) -> None:
        """Eine Tabellenzeile. Bestehende Jahre haben ein schreibgeschütztes Jahr, neue nicht."""
        zeile = self._jahre.rowCount()
        self._jahre.insertRow(zeile)
        jahr_item = QTableWidgetItem(str(jahr))
        if not jahr_editierbar:
            jahr_item.setFlags(jahr_item.flags() & ~Qt.ItemIsEditable)
        self._jahre.setItem(zeile, 0, jahr_item)
        self._jahre.setItem(zeile, 1, QTableWidgetItem(str(nummer)))

    def _jahr_hinzufuegen(self) -> None:
        """Fügt eine leere, editierbare Zeile für ein neues Jahr mit Startwert an (S-0044 AK2)."""
        self._fuege_jahr_zeile("", 10001, jahr_editierbar=True)

    # --- Bestätigen ---------------------------------------------------------

    def _zellen_text(self, zeile: int, spalte: int) -> str:
        item = self._jahre.item(zeile, spalte)
        return item.text().strip() if item is not None else ""

    @staticmethod
    def _parse_positive_zahl(text: str) -> int | None:
        """Positive ganze Zahl aus einer Eingabe; None bei leer, Vorzeichen, Komma oder Text."""
        text = text.strip()
        if not text.isdigit():
            return None
        wert = int(text)
        return wert if wert >= 1 else None

    def _lese_jahres_zaehler(self) -> tuple[dict[str, int], str | None]:
        """Liest die Jahres-Tabelle als dict. `(dict, None)` bei Erfolg, `({}, fehlertext)` sonst.

        Fängt hier nur ab, was das typisierte `Einstellungen`-Objekt nicht mehr abbilden kann:
        nicht-ganzzahlige Nummern und doppelte Jahre (die im dict verloren gingen). Wertebereich
        und Jahr-Format prüft anschließend `pruefe_einstellungen`.
        """
        zaehler: dict[str, int] = {}
        for zeile in range(self._jahre.rowCount()):
            jahr = self._zellen_text(zeile, 0)
            nummer_text = self._zellen_text(zeile, 1)
            if not jahr and not nummer_text:
                continue  # vollständig leere Zeile überspringen
            nummer = self._parse_positive_zahl(nummer_text)
            if nummer is None:
                return {}, ui_text(
                    "einstellungen.fehler_zaehler",
                    jahr=jahr or ui_text("einstellungen.jahr_leer"),
                )
            if jahr in zaehler:
                return {}, ui_text("einstellungen.fehler_jahr_doppelt", jahr=jahr)
            zaehler[jahr] = nummer
        return zaehler, None

    def _bestaetigen(self) -> None:
        self._loesche_fehler()
        text = self._standard.toPlainText().strip()
        debitor = self._parse_positive_zahl(self._debitor.text())
        zaehler, zaehler_fehler = self._lese_jahres_zaehler()

        fehler = False
        if debitor is None:
            self._zeige_feld_fehler(
                "debitornummer", ui_text("einstellungen.fehler_debitor")
            )
            fehler = True
        if zaehler_fehler is not None:
            self._zeige_feld_fehler("rechnungsnummer", zaehler_fehler)
            fehler = True
        if fehler:
            return

        sprache = self._sprache.currentData()

        # Erst einen Kandidaten prüfen; das echte Objekt wird nie mit ungültigen Werten
        # überschrieben, damit Verwerfen den gespeicherten Stand zuverlässig zurückholt.
        kandidat = replace(
            self._datenbestand.einstellungen,
            standard_anschreibentext=text,
            ui_sprache=sprache,
            waehrungsliste=self._lese_waehrungen(),
            standardwaehrung=self._standardwaehrung.currentText(),
            ausgabe_verzeichnis=self._ausgabe.text().strip(),
            naechste_debitornummer=debitor,
            naechste_rechnungsnummer=zaehler,
        )
        befunde = pruefe_einstellungen(kandidat)
        if befunde:
            for befund in befunde:
                self._zeige_feld_fehler(befund.feld, befund_text(befund))
            return

        einstellungen = self._datenbestand.einstellungen
        sprache_geaendert = sprache != einstellungen.ui_sprache
        einstellungen.standard_anschreibentext = text
        einstellungen.ui_sprache = sprache
        einstellungen.waehrungsliste = kandidat.waehrungsliste
        einstellungen.standardwaehrung = kandidat.standardwaehrung
        einstellungen.ausgabe_verzeichnis = self._ausgabe.text().strip()
        einstellungen.naechste_debitornummer = debitor
        einstellungen.naechste_rechnungsnummer = zaehler
        if self._auto.speichere_jetzt(self):
            self._setze_geaendert(False)
            self._lade_aus_einstellungen()  # Tabelle neu sortiert und neue Jahre schreibgeschützt
            if sprache_geaendert:
                self._weise_auf_neustart_hin()

    def _weise_auf_neustart_hin(self) -> None:
        """Meldet, dass die neue UI-Sprache erst beim nächsten Start greift (S-0059 AK2).

        Die Story verlangt die Wirkung „spätestens nach einem Neustart". Ein sofortiges
        Umschalten müsste alle Reiter neu bauen, ausgelöst aus diesem Reiter heraus, der
        dabei selbst verworfen würde, und offene Änderungen anderer Reiter gingen verloren
        (Architekturentscheidung 3E-0031). Der Hinweis steht noch in der bisherigen
        Sprache, weil die Oberfläche es auch tut.
        """
        QMessageBox.information(
            self,
            ui_text("einstellungen.sprache_neustart_titel"),
            ui_text("einstellungen.sprache_neustart_text"),
        )
