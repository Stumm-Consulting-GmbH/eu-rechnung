"""Rechnungs-Detailmaske als eingebetteter Maskenbereich (S-0024).

Master-Detail-Maske rechts neben der Rechnungs-Liste, einheitlich zum Firma-/Artikel-/
Kunden-/Bestellungs-Muster: kein modales Popup mehr, sondern ein `QWidget`, das der
Rechnungen-Reiter einbettet. Die Maske arbeitet auf einer „aktuellen" Rechnung, die der
Reiter über `zeige` setzt (vorbelegte neue Rechnung beim Anlegen, bestehende beim Ändern),
und meldet ihre Aktionen über die Signale `bestaetigt`, `verworfen` und (nur im Ändern-Modus)
`erstellen_angefordert` zurück; die CRUD- und Erstellungs-Steuerung bleibt beim Reiter.

Sie trägt den Bestellungs-Bezug (Anzeige), die Kopf-Felder, die Positionsliste mit dem
bestellungsgebundenen Positions-Prozess aus 3E-0022 (Vorbelegung mit Menge 0, inline
Menge/Einzelpreis, „Position aus Bestellung", „Freie Position", Warnungen aus
`warne_rechnung`) und die editierbaren Verkäufer-/Käufer-Kopien. Pflichtbefunde
(`pruefe_rechnung`) erscheinen feld-nah über den geteilten `FeldFehlerMixin`; die
Warnhinweise verhindern das Speichern nicht. Alle Datumsfelder nutzen das programmweite
Kalender-Popup (`DatumsFeld`, S-0075).
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.domain import (
    Artikel,
    ArtikelTyp,
    Bestellung,
    IndividuellesFeld,
    Leistungszeitraum,
    Position,
    Rechnung,
)
from eu_rechnung.services import (
    STANDARD_RECHNUNGSSPRACHE,
    berechne_gesamtpreis,
    pruefe_rechnung,
    warne_rechnung,
)
from eu_rechnung.texte import SPRACH_NAMEN, SPRACHEN, Sprachkontext
from eu_rechnung.ui.betrag import format_betrag, parse_betrag
from eu_rechnung.ui.datums_feld import DatumsFeld
from eu_rechnung.ui.aenderung import AenderungsKnopfMixin
from eu_rechnung.ui.feld_fehler import FeldFehlerMixin
from eu_rechnung.ui.rechnungs_anzeige import erzeugt_text, status_text
from eu_rechnung.ui.skonto_felder import SkontoFelderMixin
from eu_rechnung.ui.sprache import befund_text, ui_sprache, ui_text
from eu_rechnung.ui.vererbungs_auswahl import VererbungsAuswahl

# Kernfelder der Verkäufer-/Käufer-Bereiche: (Feldname, Katalog-Schlüssel).
#
# Schlüssel statt Texte: Ein `ui_text()` hier liefe beim Import des Moduls, also vor
# dem Setzen der UI-Sprache, und fröre die Beschriftungen auf Deutsch ein (wie in
# `firma_reiter`). Aufgelöst wird erst im Aufbau.
_PARTEI_FELDER = [
    ("name", "allgemein.feld_name"),
    ("strasse", "allgemein.feld_strasse"),
    # Eigenes Feld wie in Firma- und Kunden-Maske; der Katalog-Schlüssel ist derselbe und
    # steht bereits in allen fünf Sprachdateien.
    ("hausnummer", "firma.feld_hausnummer"),
    ("plz", "firma.feld_plz"),
    ("ort", "allgemein.feld_ort"),
    ("land", "firma.feld_land"),
    ("steuer_id", "rechnung.feld_steuer_id"),
]


def _zahl(wert: Decimal) -> str:
    """Menge als Dezimalzahl der UI-Sprache, ohne unnötige Nullen: 3.50 -> '3,5'.

    Bewusst nicht `Sprachkontext.menge`: Das rundet auf zwei Nachkommastellen und
    verlöre eine Menge wie 0,125. Hier zählt die verlustfreie Anzeige des erfassten
    Werts.
    """
    trenner = Sprachkontext(ui_sprache()).dezimaltrenner
    return format(wert.normalize(), "f").replace(".", trenner)


class PositionDialog(QDialog):
    """Dialog für eine freie, bestellungsfremde Position (Freitext-Bezeichnung, S-0024)."""

    def __init__(self, waehrung: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ui_text("position.freie_titel"))
        self._bezeichnung = QLineEdit()
        self._menge = QLineEdit()
        self._einzelpreis = QLineEdit()

        form = QFormLayout(self)
        form.addRow(ui_text("rechnung.spalte_bezeichnung"), self._bezeichnung)
        form.addRow(ui_text("rechnung.spalte_menge"), self._menge)
        form.addRow(
            ui_text("position.feld_einzelpreis_waehrung", waehrung=waehrung),
            self._einzelpreis,
        )
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._pruefe_und_akzeptiere)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def _pruefe_und_akzeptiere(self) -> None:
        if not self._bezeichnung.text().strip():
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("position.fehlt_bezeichnung"),
            )
            return
        menge = parse_betrag(self._menge.text())
        einzelpreis = parse_betrag(self._einzelpreis.text())
        if menge is None or menge < 0:
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("position.fehler_menge"),
            )
            return
        if einzelpreis is None or einzelpreis < 0:
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("position.fehler_einzelpreis"),
            )
            return
        self.accept()

    def position(self) -> Position:
        """Die erfasste freie Position mit berechnetem Gesamtpreis (nach `exec`)."""
        menge = parse_betrag(self._menge.text())
        einzelpreis = parse_betrag(self._einzelpreis.text())
        return Position(
            artikel_id="",  # freie Position: kein Bezug zur Bestellung
            bezeichnung=self._bezeichnung.text().strip(),
            menge=menge,
            einzelpreis=einzelpreis,
            gesamtpreis=berechne_gesamtpreis(menge, einzelpreis),
        )


class BestellPositionDialog(QDialog):
    """Dialog zum Wieder-Hinzufügen einer gültigen Artikel-Position der Bestellung (S-0024)."""

    def __init__(
        self,
        verfuegbar: list[tuple[str, str, Decimal]],
        waehrung: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(ui_text("position.aus_bestellung_titel"))
        self.setMinimumWidth(420)
        self._auswahl = QComboBox()
        for artikel_id, name, einzelpreis in verfuegbar:
            self._auswahl.addItem(
                ui_text(
                    "position.auswahl_eintrag",
                    name=name,
                    preis=f"{format_betrag(einzelpreis)} {waehrung}",
                ),
                (artikel_id, name, einzelpreis),
            )

        form = QFormLayout(self)
        form.addRow(ui_text("gueltiger_artikel.feld_artikel"), self._auswahl)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def position(self) -> Position:
        """Die gewählte Position mit Menge 0 und Einzelpreis aus der Bestellung (nach `exec`)."""
        artikel_id, name, einzelpreis = self._auswahl.currentData()
        return Position(
            artikel_id=artikel_id,
            bezeichnung=name,
            menge=Decimal("0"),
            einzelpreis=einzelpreis,
            gesamtpreis=Decimal("0.00"),
        )


class ArtikelPositionDialog(QDialog):
    """Dialog zum Hinzufügen einer Position aus einem aktiven Stammdaten-Artikel (S-0024).

    Bietet die übergebenen aktiven Artikel zur Wahl und erzeugt eine `Position` mit
    Artikel-Bezug, Artikelname als Bezeichnung und Menge 0. Der Vorschlagspreis wird nur
    als Einzelpreis übernommen, wenn seine Währung der Belegwährung entspricht; bei
    abweichender Währung bleibt der Einzelpreis 0 und wird in der Positionszeile selbst
    gepflegt (Product-Owner-Entscheidung 2026-07-16). Der Auswahl-Eintrag zeigt den
    Vorschlagspreis in der Artikel-eigenen Währung, damit eine Abweichung sichtbar ist.
    """

    def __init__(
        self,
        artikel: list[Artikel],
        waehrung: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(ui_text("position.aus_artikel_titel"))
        self.setMinimumWidth(420)
        self._belegwaehrung = waehrung
        self._auswahl = QComboBox()
        for a in artikel:
            self._auswahl.addItem(
                ui_text(
                    "position.auswahl_eintrag",
                    name=a.artikelname,
                    preis=f"{format_betrag(a.vorschlagspreis.betrag)} {a.vorschlagspreis.waehrung}",
                ),
                a,
            )

        form = QFormLayout(self)
        form.addRow(ui_text("gueltiger_artikel.feld_artikel"), self._auswahl)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def position(self) -> Position:
        """Die gewählte Position mit Menge 0 (nach `exec`).

        Der Vorschlagspreis wird nur bei währungsgleichem Artikel als Einzelpreis
        übernommen; sonst bleibt er 0 und wird in der Positionszeile selbst erfasst.
        """
        artikel = self._auswahl.currentData()
        preis = artikel.vorschlagspreis
        einzelpreis = preis.betrag if preis.waehrung == self._belegwaehrung else Decimal("0")
        return Position(
            artikel_id=artikel.id,
            bezeichnung=artikel.artikelname,
            menge=Decimal("0"),
            einzelpreis=einzelpreis,
            gesamtpreis=Decimal("0.00"),
        )


class LeistungszeitraumDialog(QDialog):
    """Dialog zum Setzen oder Löschen des Positions-Leistungszeitraums (S-0069).

    Eine Checkbox schaltet den Zeitraum ganz ab (Position ohne Zeitraum); ist sie an, gelten
    die beiden Datumsfelder mit `von ≤ bis`. Vorbelegt wird der bestehende Positions-Zeitraum,
    sonst der übergebene Kopf-Zeitraum (BG-14).
    """

    def __init__(
        self,
        zeitraum: Leistungszeitraum | None,
        vorbelegung: Leistungszeitraum,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(ui_text("position.zeitraum_titel"))
        # Die Vorbelegung ist der Kopf-Zeitraum (BG-14); er dient hier zugleich als Grenze,
        # weil der Positions-Zeitraum (BG-26) innerhalb liegen muss (S-0069).
        self._kopf = vorbelegung
        self._aktiv = QCheckBox(ui_text("position.zeitraum_angeben"))
        self._aktiv.setChecked(zeitraum is not None)
        self._aktiv.toggled.connect(self._aktualisiere_aktiv)
        self._von = DatumsFeld()
        self._bis = DatumsFeld()
        start = zeitraum or vorbelegung
        self._von.setze_datum(start.von)
        self._bis.setze_datum(start.bis)

        zeile = QHBoxLayout()
        zeile.addWidget(self._von)
        zeile.addWidget(QLabel(ui_text("rechnung.zeitraum_bis")))
        zeile.addWidget(self._bis)
        zeile_w = QWidget()
        zeile_w.setLayout(zeile)

        form = QFormLayout(self)
        form.addRow(self._aktiv)
        form.addRow(ui_text("sichtteil.leistungszeitraum"), zeile_w)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._pruefe_und_akzeptiere)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)
        self._aktualisiere_aktiv()

    def _aktualisiere_aktiv(self) -> None:
        an = self._aktiv.isChecked()
        self._von.setEnabled(an)
        self._bis.setEnabled(an)

    def _pruefe_und_akzeptiere(self) -> None:
        if self._aktiv.isChecked() and self._von.datum() > self._bis.datum():
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("position.zeitraum_reihenfolge"),
            )
            return
        # Der Positions-Zeitraum muss innerhalb des Kopf-Zeitraums liegen (BG-26 ⊆ BG-14,
        # sonst KoSIT-invalide; S-0069). Frühe Rückmeldung, bevor der Wert gesetzt wird.
        if self._aktiv.isChecked() and (
            self._von.datum() < self._kopf.von or self._bis.datum() > self._kopf.bis
        ):
            QMessageBox.warning(
                self,
                ui_text("allgemein.eingabe_titel"),
                ui_text("position.zeitraum_ausserhalb"),
            )
            return
        self.accept()

    def zeitraum(self) -> Leistungszeitraum | None:
        """Der erfasste Zeitraum, oder None wenn abgeschaltet (nach `exec`)."""
        if not self._aktiv.isChecked():
            return None
        return Leistungszeitraum(von=self._von.datum(), bis=self._bis.datum())


class RechnungsMaske(FeldFehlerMixin, SkontoFelderMixin, AenderungsKnopfMixin, QWidget):
    """Eingebettete Detailmaske zum Anlegen und Ändern einer Rechnung.

    Arbeitet auf der über `zeige` gesetzten `rechnung`. `bestaetigt` meldet dem Reiter
    eine geprüfte und (mit bestätigten Warnungen) übernommene Rechnung; `verworfen` meldet
    den Abbruch. Ohne gesetzte Rechnung ist die Maske leer und gesperrt.
    """

    #: Bestätigen geklickt, Pflichtprüfung bestanden und Werte übernommen.
    bestaetigt = Signal()
    #: Verwerfen geklickt.
    verworfen = Signal()
    #: „Rechnung erstellen" geklickt (nur im Ändern-Modus aktiv); der Reiter orchestriert.
    erstellen_angefordert = Signal()

    def __init__(self, artikel: list[Artikel], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._artikel = list(artikel)
        self._rechnung: Rechnung | None = None
        self._bestellung: Bestellung | None = None
        self._ist_neu = True
        self._lade_laeuft = False  # unterdrückt Änderungs-Markierung und itemChanged beim Laden
        self._geaendert = False
        self._fehler: dict[str, QLabel] = {}
        self._verkaeufer_edits: dict[str, QLineEdit] = {}
        self._kaeufer_edits: dict[str, QLineEdit] = {}
        self._baue_ui()
        self.zeige(None, None, ist_neu=True)

    # --- Zugriff für den Reiter --------------------------------------------

    @property
    def rechnung(self) -> Rechnung | None:
        """Die aktuell bearbeitete Rechnung (nach `bestaetigt` mit übernommenen Werten)."""
        return self._rechnung

    @property
    def bestellung(self) -> Bestellung | None:
        """Die Bestellung, auf der die aktuelle Rechnung fußt."""
        return self._bestellung

    @property
    def ist_neu(self) -> bool:
        """True im Anlegen-Modus, False beim Ändern einer bestehenden Rechnung."""
        return self._ist_neu

    @property
    def geaendert(self) -> bool:
        """True, wenn seit dem Laden Felder verändert wurden."""
        return self._geaendert

    def setze_artikel(self, artikel: list[Artikel]) -> None:
        """Aktualisiert den Artikel-Stamm für die Positions-Auswahl (S-0024 AK7).

        Die Maske hält die Artikelliste, um in „Position aus Artikel" die aktiven Artikel
        anzubieten und Artikelnamen sowie -typen aufzulösen. Der Reiter ruft dies beim
        Anzeigen auf, damit im Artikel-Reiter neu angelegte oder gelöschte Artikel ohne
        Neustart wirken. Sonst hielte die Maske dauerhaft den Stand ihres Aufbauzeitpunkts,
        also den Bestand von vor der ersten Rechnungserfassung (Fund aus der Abnahme,
        Cluster 4). Eine eigene Kopie der Liste bleibt bewusst: Das Auffrischen geschieht
        kontrolliert beim Anzeigen, nicht mitten in einer offenen Bearbeitung.
        """
        self._artikel = list(artikel)

    # --- Aufbau -------------------------------------------------------------

    def _baue_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._bezug = QLabel("")
        self._bezug.setStyleSheet("font-weight: bold;")
        self._bezug.setWordWrap(True)
        layout.addWidget(self._bezug)

        layout.addWidget(self._baue_kopf())
        layout.addWidget(self._baue_positionen(), 1)
        layout.addWidget(
            self._baue_partei_box("rechnung.gruppe_verkaeufer", self._verkaeufer_edits, "verkaeufer")
        )
        layout.addWidget(
            self._baue_partei_box("rechnung.gruppe_kaeufer", self._kaeufer_edits, "kaeufer")
        )
        layout.addWidget(self._baue_individuelle_felder())

        leiste = QHBoxLayout()
        # „Rechnung erstellen" links, sichtbar getrennt von Verwerfen/Bestätigen (S-0032 AK1).
        self._erstellen_knopf = QPushButton(ui_text("erstellen.titel"))
        self._erstellen_knopf.clicked.connect(self._erstellen_angefordert)
        leiste.addWidget(self._erstellen_knopf)
        leiste.addStretch(1)
        verwerfen = QPushButton(ui_text("allgemein.knopf_verwerfen"))
        verwerfen.clicked.connect(self._verwerfen)
        self._bestaetigen_knopf = QPushButton(ui_text("allgemein.knopf_bestaetigen"))
        self._bestaetigen_knopf.setDefault(True)
        self._bestaetigen_knopf.clicked.connect(self._bestaetigen)
        leiste.addWidget(verwerfen)
        leiste.addWidget(self._bestaetigen_knopf)
        layout.addLayout(leiste)

    def _baue_kopf(self) -> QGroupBox:
        box = QGroupBox(ui_text("rechnung.gruppe_kopfdaten"))
        form = QFormLayout(box)
        self._nummer = QLineEdit()
        self._nummer.textChanged.connect(self._markiere_geaendert)
        self._datum = DatumsFeld()
        self._datum.dateChanged.connect(self._markiere_geaendert)
        # Der Kopf-Zeitraum (BG-14) zieht die ihm folgenden Positions-Zeiträume mit (S-0085);
        # deshalb hängt an beiden Feldern neben der Änderungs-Markierung der Nachzug.
        self._lz_von = DatumsFeld()
        self._lz_von.dateChanged.connect(self._markiere_geaendert)
        self._lz_von.dateChanged.connect(self._ziehe_positions_zeitraeume_nach)
        self._lz_bis = DatumsFeld()
        self._lz_bis.dateChanged.connect(self._markiere_geaendert)
        self._lz_bis.dateChanged.connect(self._ziehe_positions_zeitraeume_nach)
        self._reverse = QCheckBox(ui_text("kunde.schalter_reverse_charge"))
        self._reverse.toggled.connect(self._markiere_geaendert)
        # Der Steuersatz (Kategorie S) ist bei Reverse-Charge gegenstandslos (Satz 0); der
        # Schalter deaktiviert das Feld live (S-0079).
        self._steuersatz = QLineEdit()
        self._steuersatz.textChanged.connect(self._markiere_geaendert)
        self._reverse.toggled.connect(self._aktualisiere_steuersatz_feld)
        self._zahlung = QLineEdit()
        self._zahlung.textChanged.connect(self._markiere_geaendert)
        # Zahlungsfrist und Skonto sind aus der Bestellung vorbelegt und hier änderbar
        # (S-0080); das Skonto steht strukturiert neben der Zahlungsbedingung, nicht in
        # deren freiem Text, weil es nur so maschinell auswertbar ist (S-0051).
        self._zahlungsfrist = QSpinBox()
        self._zahlungsfrist.setRange(0, 3650)
        self._zahlungsfrist.setSuffix(" Tage")
        self._zahlungsfrist.valueChanged.connect(self._markiere_geaendert)
        skonto_w = self._baue_skonto_zeile(self._markiere_geaendert)
        # Bankverbindung der Ausgabe (BG-16/17), aus den Konten der Verkäufer-Kopie gewählt und
        # nach Belegwährung vorbelegt (S-0065). Erst beim Laden gefüllt.
        self._bankverbindung = QComboBox()
        self._bankverbindung.currentIndexChanged.connect(self._markiere_geaendert)
        # Die Rechnung erbt ihre Sprache nicht: Sie trägt den beim Anlegen aufgelösten Wert
        # als eigenen (S-0058 AK3) und bleibt änderbar wie jedes andere Feld, auch im Status
        # „Erzeugt" (S-0026: eingefroren ist die Ausgabedatei, nicht die Rechnung).
        self._sprache = VererbungsAuswahl(erbt_moeglich=False)
        self._sprache.geaendert.connect(self._markiere_geaendert)
        self._anschreiben = QPlainTextEdit()
        self._anschreiben.setFixedHeight(90)
        self._anschreiben.textChanged.connect(self._markiere_geaendert)
        # Ausgabestand als reine Anzeige (S-0024 AK2, S-0032 AK4): Er entsteht beim Erzeugen,
        # nicht beim Erfassen, und ist deshalb kein Eingabefeld. Beide Werte stehen auch in
        # der Liste; hier, weil man die Rechnung in der Maske bearbeitet und dabei wissen
        # muss, ob und wann sie schon ausgegeben wurde.
        self._status_anzeige = QLabel("")
        self._erzeugt_anzeige = QLabel("")

        zeitraum = QHBoxLayout()
        zeitraum.addWidget(self._lz_von)
        zeitraum.addWidget(QLabel(ui_text("rechnung.zeitraum_bis")))
        zeitraum.addWidget(self._lz_bis)
        zeitraum_w = QWidget()
        zeitraum_w.setLayout(zeitraum)

        form.addRow(ui_text("uebersicht.spalte_rechnungsnummer"), self._nummer)
        form.addRow(self._fehler_label("rechnungsnummer"))
        form.addRow(ui_text("uebersicht.spalte_rechnungsdatum"), self._datum)
        form.addRow(self._fehler_label("rechnungsdatum"))
        form.addRow(ui_text("sichtteil.leistungszeitraum"), zeitraum_w)
        form.addRow("", self._reverse)
        form.addRow(ui_text("rechnung.feld_steuersatz"), self._steuersatz)
        form.addRow(self._fehler_label("steuersatz"))
        # Reihenfolge der Zahlungsangaben wie in der Bestellungsmaske: Frist, Bedingung,
        # Skonto. Die Rechnung übernimmt sie von dort, also lesen sie sich hier gleich.
        form.addRow(ui_text("bestellung.feld_zahlungsfrist"), self._zahlungsfrist)
        form.addRow(ui_text("bestellung.feld_zahlungsbedingung"), self._zahlung)
        form.addRow(ui_text("bestellung.feld_skonto"), skonto_w)
        form.addRow(self._fehler_label("skonto_tage"))
        form.addRow(self._fehler_label("skonto_prozent"))
        form.addRow(ui_text("rechnung.feld_bankverbindung"), self._bankverbindung)
        form.addRow(self._fehler_label("bankverbindung"))
        form.addRow(ui_text("allgemein.feld_rechnungssprache"), self._sprache)
        form.addRow(ui_text("rechnung.feld_anschreibentext"), self._anschreiben)
        form.addRow(ui_text("uebersicht.spalte_status"), self._status_anzeige)
        form.addRow(ui_text("uebersicht.spalte_erzeugt_am"), self._erzeugt_anzeige)
        return box

    def _baue_positionen(self) -> QGroupBox:
        box = QGroupBox(ui_text("rechnung.gruppe_positionen"))
        layout = QVBoxLayout(box)
        self._pos_tabelle = QTableWidget(0, 5)
        self._pos_tabelle.setHorizontalHeaderLabels(
            [
                ui_text("rechnung.spalte_bezeichnung"),
                ui_text("rechnung.spalte_menge"),
                ui_text("gueltiger_artikel.feld_einzelpreis"),
                ui_text("rechnung.spalte_gesamtpreis"),
                ui_text("rechnung.spalte_leistungszeitraum"),
            ]
        )
        kopf = self._pos_tabelle.horizontalHeader()
        kopf.setSectionResizeMode(0, QHeaderView.Stretch)
        # Menge und Einzelpreis werden direkt in der Zelle bearbeitet; Bezeichnung und
        # Gesamtpreis sind je Zeile schreibgeschuetzt (Flags in `_lade_positionen`).
        self._pos_tabelle.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self._pos_tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        kopf_h = self._pos_tabelle.horizontalHeader().sizeHint().height()
        zeile_h = self._pos_tabelle.verticalHeader().defaultSectionSize()
        self._pos_tabelle.setMinimumHeight(
            kopf_h + 5 * zeile_h + 2 * self._pos_tabelle.frameWidth()
        )
        self._pos_tabelle.itemChanged.connect(self._zelle_geaendert)
        layout.addWidget(self._pos_tabelle)
        layout.addWidget(self._fehler_label("positionen"))

        leiste = QHBoxLayout()
        aus_best = QPushButton(ui_text("rechnung.knopf_position_aus_bestellung"))
        aus_best.clicked.connect(self._position_aus_bestellung)
        aus_artikel = QPushButton(ui_text("rechnung.knopf_position_aus_artikel"))
        aus_artikel.clicked.connect(self._position_aus_artikel)
        frei = QPushButton(ui_text("rechnung.knopf_freie_position"))
        frei.clicked.connect(self._freie_position)
        zeitraum = QPushButton(ui_text("rechnung.knopf_leistungszeitraum"))
        zeitraum.clicked.connect(self._position_zeitraum)
        entf = QPushButton(ui_text("rechnung.knopf_position_entfernen"))
        entf.clicked.connect(self._position_entfernen)
        leiste.addWidget(aus_best)
        leiste.addWidget(aus_artikel)
        leiste.addWidget(frei)
        leiste.addWidget(zeitraum)
        leiste.addWidget(entf)
        leiste.addStretch(1)
        self._summe_label = QLabel(self._netto_text(Decimal("0.00")))
        self._summe_label.setStyleSheet("font-weight: bold;")
        leiste.addWidget(self._summe_label)
        layout.addLayout(leiste)
        # Verbrauchsstand des Gesamt-Höchstbetrags, nur sichtbar wenn die Bestellung einen
        # trägt (S-0024 AK6). Er steht unter den Positionen, weil er sich mit jeder Menge
        # ändert; die Überschreitung selbst meldet die Warnung beim Bestätigen.
        self._obergrenzen_label = QLabel("")
        self._obergrenzen_label.setEnabled(False)  # dezent, als Hinweis erkennbar
        self._obergrenzen_label.setVisible(False)
        layout.addWidget(self._obergrenzen_label)
        return box

    def _baue_partei_box(
        self, titel_schluessel: str, edits: dict[str, QLineEdit], praefix: str
    ) -> QGroupBox:
        box = QGroupBox(ui_text(titel_schluessel))
        form = QFormLayout(box)
        for schluessel, text_schluessel in _PARTEI_FELDER:
            feld = QLineEdit()
            feld.textChanged.connect(self._markiere_geaendert)
            edits[schluessel] = feld
            form.addRow(ui_text(text_schluessel), feld)
            if schluessel == "name":
                form.addRow(self._fehler_label(f"{praefix}_name"))
        return box

    def _baue_individuelle_felder(self) -> QGroupBox:
        """Die beim Anlegen übernommenen Felder als editierbare Name-Wert-Liste (S-0040 AK2)."""
        box = QGroupBox(ui_text("individuelle_felder.gruppe"))
        layout = QVBoxLayout(box)
        self._felder_tabelle = QTableWidget(0, 2)
        self._felder_tabelle.setHorizontalHeaderLabels(
            [ui_text("allgemein.feld_name"), ui_text("individuelle_felder.spalte_wert")]
        )
        self._felder_tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._felder_tabelle.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        kopf_h = self._felder_tabelle.horizontalHeader().sizeHint().height()
        zeile_h = self._felder_tabelle.verticalHeader().defaultSectionSize()
        self._felder_tabelle.setMinimumHeight(
            kopf_h + 3 * zeile_h + 2 * self._felder_tabelle.frameWidth()
        )
        self._felder_tabelle.itemChanged.connect(self._markiere_geaendert)
        layout.addWidget(self._felder_tabelle)
        return box

    # --- Hilfen -------------------------------------------------------------

    def _belegwaehrung(self) -> str:
        """Die Belegwährung der geladenen Bestellung; leer, solange keine gesetzt ist (S-0064)."""
        return self._bestellung.waehrung if self._bestellung is not None else ""

    def _netto_text(self, netto: Decimal) -> str:
        """Die Nettosumme unter der Positionstabelle, in der UI-Sprache mit Belegwährung."""
        betrag = f"{format_betrag(netto)} {self._belegwaehrung()}".rstrip()
        return ui_text("rechnung.summe_netto", betrag=betrag)

    def _artikelname(self, artikel_id: str) -> str:
        artikel = next((a for a in self._artikel if a.id == artikel_id), None)
        return artikel.artikelname if artikel is not None else artikel_id

    def _verfuegbare_bestell_positionen(self) -> list[tuple[str, str, Decimal]]:
        """Gültige Artikel der Bestellung, die noch nicht als Position vorhanden sind."""
        if self._rechnung is None or self._bestellung is None:
            return []
        vorhanden = {p.artikel_id for p in self._rechnung.positionen if p.artikel_id}
        return [
            (g.artikel_id, self._artikelname(g.artikel_id), g.einzelpreis)
            for g in self._bestellung.gueltige_artikel
            if g.artikel_id not in vorhanden
        ]

    def _aktive_artikel(self) -> list[Artikel]:
        """Die aktiven Stammdaten-Artikel für den Positions-Weg aus dem Artikel-Stamm (S-0024)."""
        return [a for a in self._artikel if a.aktiv]

    # --- Laden und Zurückschreiben -----------------------------------------

    def zeige(self, rechnung: Rechnung | None, bestellung: Bestellung | None, *, ist_neu: bool) -> None:
        """Zeigt eine Rechnung (Anlegen oder Ändern) oder sperrt die leere Maske.

        Ohne Rechnung oder Bestellung ist die Maske leer und deaktiviert; der Reiter
        nutzt das für den Zustand ohne gewählte Bestellung. Mit Rechnung wird die Maske
        aus deren Werten befüllt und der Bestellungs-Bezug angezeigt.
        """
        self._lade_laeuft = True
        # Auf einer tiefen Kopie arbeiten, damit Positions- und Feld-Edits das Original
        # (beim Ändern die Rechnung in der Bestellung) erst beim Bestätigen erreichen und
        # ein Verwerfen sie folgenlos lässt. Der Reiter übernimmt die Kopie beim Bestätigen.
        self._rechnung = deepcopy(rechnung) if rechnung is not None else None
        self._bestellung = bestellung
        self._ist_neu = ist_neu
        self._loesche_fehler()
        if self._rechnung is None or bestellung is None:
            self._leere_felder()
            self.setEnabled(False)
        else:
            self.setEnabled(True)
            # „Rechnung erstellen" nur für eine bereits gespeicherte Rechnung (nicht im Anlegen).
            self._erstellen_knopf.setEnabled(not ist_neu)
            self._bezug.setText(
                ui_text(
                    "rechnung.bezug",
                    bestellnummer=bestellung.bestellnummer,
                    kunde=self._rechnung.kaeufer.name,
                    waehrung=bestellung.waehrung,
                )
            )
            self._lade_aus_rechnung()
        self._lade_laeuft = False
        self._setze_geaendert(False)

    def _aktualisiere_steuersatz_feld(self) -> None:
        """Setzt den Steuersatz bei Reverse-Charge auf 0 und sperrt das Feld (S-0023 AK6).

        Das Sperren allein genügte nicht: Es ließ einen vorher erfassten Satz stehen, der
        gespeichert wurde und dort etwas behauptete, was für diese Rechnung nicht gilt. Die
        Ausgabe erzwingt die 0 ohnehin; die Anzeige sagt jetzt dasselbe.
        """
        rc = self._reverse.isChecked()
        self._steuersatz.setEnabled(not rc)
        if rc:
            self._steuersatz.setText(format_betrag(Decimal("0")))

    def _fuelle_bankverbindungen(self) -> None:
        """Füllt die Bankverbindungs-Auswahl aus der Verkäufer-Kopie und stellt sie auf die Wahl.

        Erster Eintrag ist „(keine)", danach je Konto „Währung — Bank — IBAN"; vorbelegt wird
        die an der Rechnung gespeicherte Bankverbindung (S-0065 AK1/AK3).
        """
        self._bankverbindung.clear()
        self._bankverbindung.addItem(ui_text("rechnung.bankverbindung_keine"), None)
        gewaehlt = 0
        for b in self._rechnung.verkaeufer.bankverbindungen:
            self._bankverbindung.addItem(f"{b.waehrung} — {b.bank} — {b.iban}", b)
            if b == self._rechnung.bankverbindung:
                gewaehlt = self._bankverbindung.count() - 1
        self._bankverbindung.setCurrentIndex(gewaehlt)

    def _leere_felder(self) -> None:
        heute = date.today()
        self._bezug.setText("")
        self._nummer.setText("")
        self._datum.setze_datum(heute)
        self._lz_von.setze_datum(heute)
        self._lz_bis.setze_datum(heute)
        self._reverse.setChecked(False)
        self._steuersatz.setText("")
        self._aktualisiere_steuersatz_feld()
        self._zahlung.setText("")
        self._zahlungsfrist.setValue(0)
        self._setze_skonto(None)
        self._bankverbindung.clear()
        self._sprache.setze_optionen([(k, SPRACH_NAMEN[k]) for k in SPRACHEN])
        self._sprache.setze_wert(STANDARD_RECHNUNGSSPRACHE)
        self._anschreiben.setPlainText("")
        self._status_anzeige.setText("")
        self._erzeugt_anzeige.setText("")
        for edits in (self._verkaeufer_edits, self._kaeufer_edits):
            for feld in edits.values():
                feld.setText("")
        self._pos_tabelle.setRowCount(0)
        self._felder_tabelle.setRowCount(0)
        self._summe_label.setText(self._netto_text(Decimal("0.00")))

    def _lade_aus_rechnung(self) -> None:
        r = self._rechnung
        self._nummer.setText(r.rechnungsnummer)
        self._datum.setze_datum(r.rechnungsdatum)
        self._lz_von.setze_datum(r.leistungszeitraum.von)
        self._lz_bis.setze_datum(r.leistungszeitraum.bis)
        self._reverse.setChecked(r.reverse_charge)
        self._steuersatz.setText(format_betrag(r.steuersatz))
        self._aktualisiere_steuersatz_feld()
        self._zahlung.setText(r.zahlungsbedingung)
        self._zahlungsfrist.setValue(r.zahlungsfrist)
        self._setze_skonto(r.skonto)
        self._fuelle_bankverbindungen()
        self._sprache.setze_optionen([(k, SPRACH_NAMEN[k]) for k in SPRACHEN])
        self._sprache.setze_wert(r.rechnungssprache)
        self._anschreiben.setPlainText(r.anschreibentext)
        self._status_anzeige.setText(status_text(r.status))
        self._erzeugt_anzeige.setText(erzeugt_text(r.zuletzt_erzeugt_am, leer="—"))
        self._lade_partei(self._verkaeufer_edits, r.verkaeufer.name, r.verkaeufer.adresse,
                          r.verkaeufer.mehrwertsteuer_id)
        self._lade_partei(self._kaeufer_edits, r.kaeufer.name, r.kaeufer.adresse,
                          r.kaeufer.umsatzsteuer_id)
        self._lade_positionen()
        self._lade_individuelle_felder()

    def _lade_partei(self, edits, name, adresse, steuer_id) -> None:
        edits["name"].setText(name)
        edits["strasse"].setText(adresse.strasse)
        edits["hausnummer"].setText(adresse.hausnummer)
        edits["plz"].setText(adresse.plz)
        edits["ort"].setText(adresse.ort)
        edits["land"].setText(adresse.land)
        edits["steuer_id"].setText(steuer_id)

    def _lade_positionen(self) -> None:
        vorher = self._lade_laeuft
        self._lade_laeuft = True
        self._pos_tabelle.setRowCount(0)
        for pos in self._rechnung.positionen:
            zeile = self._pos_tabelle.rowCount()
            self._pos_tabelle.insertRow(zeile)
            werte = [
                pos.bezeichnung,
                _zahl(pos.menge),
                format_betrag(pos.einzelpreis),
                format_betrag(pos.gesamtpreis),
                self._zeitraum_anzeige(pos),
            ]
            for spalte, text in enumerate(werte):
                item = QTableWidgetItem(text)
                if spalte in (0, 3, 4):  # Bezeichnung, Gesamtpreis und Zeitraum schreibgeschützt
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._pos_tabelle.setItem(zeile, spalte, item)
        self._lade_laeuft = vorher
        self._aktualisiere_summe()

    def _zelle_geaendert(self, item: QTableWidgetItem) -> None:
        """Übernimmt eine editierte Menge oder einen Einzelpreis und rechnet neu (S-0024)."""
        if self._lade_laeuft or self._rechnung is None:
            return
        zeile, spalte = item.row(), item.column()
        if not 0 <= zeile < len(self._rechnung.positionen):
            return
        pos = self._rechnung.positionen[zeile]
        wert = parse_betrag(item.text())
        if spalte == 1 and wert is not None and wert >= 0:
            pos.menge = wert
        elif spalte == 2 and wert is not None and wert >= 0:
            pos.einzelpreis = wert
        pos.gesamtpreis = berechne_gesamtpreis(pos.menge, pos.einzelpreis)
        self._lade_laeuft = True
        self._pos_tabelle.item(zeile, 1).setText(_zahl(pos.menge))
        self._pos_tabelle.item(zeile, 2).setText(format_betrag(pos.einzelpreis))
        self._pos_tabelle.item(zeile, 3).setText(format_betrag(pos.gesamtpreis))
        self._lade_laeuft = False
        self._aktualisiere_summe()
        self._markiere_geaendert()

    def _aktualisiere_summe(self) -> None:
        positionen = self._rechnung.positionen if self._rechnung is not None else []
        netto = sum((p.gesamtpreis for p in positionen), Decimal("0.00"))
        self._summe_label.setText(self._netto_text(netto))
        self._aktualisiere_obergrenzen_stand()

    def _aktualisiere_obergrenzen_stand(self) -> None:
        """Zeigt den Verbrauch am Gesamt-Höchstbetrag der Bestellung (S-0024 AK6).

        Gezählt wird der Verbrauch der übrigen Rechnungen plus dieser, damit der Stand die
        offene Erfassung schon einschließt; beim Ändern zählt die eigene Fassung aus der
        Bestellung nicht doppelt. Ohne Höchstbetrag bleibt die Zeile unsichtbar, statt eine
        Grenze zu behaupten, die es nicht gibt.
        """
        grenze = self._bestellung.gesamt_hoechstbetrag if self._bestellung else None
        if grenze is None or self._rechnung is None:
            self._obergrenzen_label.setVisible(False)
            return
        andere = [
            pos
            for r in self._bestellung.rechnungen
            if r.id != self._rechnung.id
            for pos in r.positionen
        ]
        verbraucht = sum(
            (p.gesamtpreis for p in andere + self._rechnung.positionen), Decimal("0.00")
        )
        self._obergrenzen_label.setText(
            ui_text(
                "rechnung.obergrenzen_stand",
                verbraucht=format_betrag(verbraucht),
                grenze=format_betrag(grenze),
                rest=format_betrag(grenze - verbraucht),
            )
        )
        self._obergrenzen_label.setVisible(True)

    def _lade_individuelle_felder(self) -> None:
        self._felder_tabelle.setRowCount(0)
        for feld in self._rechnung.individuelle_felder:
            zeile = self._felder_tabelle.rowCount()
            self._felder_tabelle.insertRow(zeile)
            self._felder_tabelle.setItem(zeile, 0, QTableWidgetItem(feld.name))
            self._felder_tabelle.setItem(zeile, 1, QTableWidgetItem(feld.wert))

    def _lese_individuelle_felder(self) -> list[IndividuellesFeld]:
        """Die editierten Felder als Kopien; Zeilen ohne Namen werden übersprungen."""
        felder: list[IndividuellesFeld] = []
        for zeile in range(self._felder_tabelle.rowCount()):
            name_item = self._felder_tabelle.item(zeile, 0)
            name = name_item.text().strip() if name_item is not None else ""
            if not name:
                continue
            wert_item = self._felder_tabelle.item(zeile, 1)
            wert = wert_item.text().strip() if wert_item is not None else ""
            felder.append(IndividuellesFeld(name=name, aktiv=True, wert=wert))
        return felder

    def _uebernehme_in_rechnung(self) -> None:
        r = self._rechnung
        r.rechnungsnummer = self._nummer.text().strip()
        r.rechnungsdatum = self._datum.datum()
        r.leistungszeitraum.von = self._lz_von.datum()
        r.leistungszeitraum.bis = self._lz_bis.datum()
        r.reverse_charge = self._reverse.isChecked()
        # Bei Reverse-Charge hart 0, unabhängig vom Feld (S-0023 AK6): Die Anzeige führt es
        # zwar nach, aber die Invariante gehört nicht an ein Eingabefeld gehängt.
        r.steuersatz = (
            Decimal("0")
            if r.reverse_charge
            else parse_betrag(self._steuersatz.text()) or Decimal("0")
        )
        r.zahlungsbedingung = self._zahlung.text().strip()
        r.zahlungsfrist = self._zahlungsfrist.value()
        r.skonto, _ = self._lese_skonto()  # Eingabe-Befunde fängt `_bestaetigen` vorab ab
        r.bankverbindung = deepcopy(self._bankverbindung.currentData())
        r.rechnungssprache = self._sprache.wert()
        r.anschreibentext = self._anschreiben.toPlainText()
        self._uebernehme_partei(self._verkaeufer_edits, r.verkaeufer, "mehrwertsteuer_id")
        self._uebernehme_partei(self._kaeufer_edits, r.kaeufer, "umsatzsteuer_id")
        r.individuelle_felder = self._lese_individuelle_felder()

    def _uebernehme_partei(self, edits, obj, steuer_attr) -> None:
        obj.name = edits["name"].text().strip()
        obj.adresse.strasse = edits["strasse"].text().strip()
        obj.adresse.hausnummer = edits["hausnummer"].text().strip()
        obj.adresse.plz = edits["plz"].text().strip()
        obj.adresse.ort = edits["ort"].text().strip()
        obj.adresse.land = edits["land"].text().strip()
        setattr(obj, steuer_attr, edits["steuer_id"].text().strip())

    # --- Positions-Aktionen -------------------------------------------------

    def _position_aus_bestellung(self) -> None:
        if self._rechnung is None:
            return
        verfuegbar = self._verfuegbare_bestell_positionen()
        if not verfuegbar:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("rechnung.alle_positionen_vorhanden"),
            )
            return
        dialog = BestellPositionDialog(verfuegbar, self._belegwaehrung(), self)
        if dialog.exec():
            self._fuege_position_hinzu(dialog.position())

    def _position_aus_artikel(self) -> None:
        if self._rechnung is None:
            return
        aktive = self._aktive_artikel()
        if not aktive:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("rechnung.keine_aktiven_artikel"),
            )
            return
        dialog = ArtikelPositionDialog(aktive, self._belegwaehrung(), self)
        if dialog.exec():
            self._fuege_position_hinzu(dialog.position())

    def _freie_position(self) -> None:
        if self._rechnung is None:
            return
        dialog = PositionDialog(self._belegwaehrung(), self)
        if dialog.exec():
            self._fuege_position_hinzu(dialog.position())

    def _position_entfernen(self) -> None:
        if self._rechnung is None:
            return
        zeile = self._pos_tabelle.currentRow()
        if 0 <= zeile < len(self._rechnung.positionen):
            del self._rechnung.positionen[zeile]
            self._lade_positionen()
            self._markiere_geaendert()

    # --- Positions-Leistungszeitraum (S-0067/S-0068/S-0069) ------------------

    def _kopf_zeitraum(self) -> Leistungszeitraum:
        """Der in der Maske erfasste Rechnungskopf-Zeitraum (BG-14) als neues Objekt."""
        return Leistungszeitraum(von=self._lz_von.datum(), bis=self._lz_bis.datum())

    def _ziehe_positions_zeitraeume_nach(self) -> None:
        """Zieht den geänderten Kopf-Zeitraum auf die ihm folgenden Positionen nach (S-0085).

        **Erkennungsregel: Wertgleichheit mit dem bisherigen Kopf-Zeitraum.** Eine Position,
        deren Zeitraum dem alten Kopf entspricht, hat ihn von dort und folgt ihm weiter; eine
        abweichende trägt einen eigens erfassten Wert und bleibt, ebenso eine ohne Zeitraum.
        Ein zusätzliches Kennzeichen an der Position braucht es dafür nicht: Es müsste für
        bestehende Rechnungen geraten werden und hielte dieselbe Aussage ein zweites Mal.

        Ohne diesen Nachzug blieben die vorbelegten Positions-Zeiträume beim Verschieben des
        Kopfs stehen, fielen aus dem Kopf-Zeitraum heraus (BG-26 ⊆ BG-14) und mussten einzeln
        korrigiert werden, obwohl der Anwender sie nie angefasst hatte.

        Jede nachgezogene Position erhält ein **eigenes** Zeitraum-Objekt; ein geteiltes würde
        eine spätere Einzeländerung auf alle übrigen durchschlagen lassen.
        """
        if self._lade_laeuft or self._rechnung is None:
            return
        # Den alten Kopf-Wert als eigenes Objekt sichern, bevor er überschrieben wird.
        bisher = Leistungszeitraum(
            von=self._rechnung.leistungszeitraum.von,
            bis=self._rechnung.leistungszeitraum.bis,
        )
        neu = self._kopf_zeitraum()
        if neu == bisher:
            return
        for pos in self._rechnung.positionen:
            if pos.leistungszeitraum == bisher:
                pos.leistungszeitraum = Leistungszeitraum(von=neu.von, bis=neu.bis)
        # Den Kopf mitführen: Beide Datumsfelder melden einzeln, der nächste Vergleich liefe
        # sonst gegen einen veralteten Stand und zöge die Positionen nicht mehr mit.
        self._rechnung.leistungszeitraum = neu
        self._lade_positionen()

    def _darf_zeitraum(self, pos: Position) -> bool:
        """True, wenn die Position einen Leistungszeitraum tragen darf.

        Ein Produkt-Artikel schließt ihn aus (S-0067); Leistungs-Artikel und freie Positionen
        (ohne Artikel-Bezug, Product-Owner-Entscheidung 2026-07-16) dürfen einen tragen.
        """
        if not pos.artikel_id:
            return True
        artikel = next((a for a in self._artikel if a.id == pos.artikel_id), None)
        return artikel is None or artikel.typ is not ArtikelTyp.PRODUKT

    def _zeitraum_anzeige(self, pos: Position) -> str:
        """Der Positions-Zeitraum als „von – bis" für die Tabelle; leer ohne Zeitraum."""
        lz = pos.leistungszeitraum
        return "" if lz is None else f"{lz.von.isoformat()} – {lz.bis.isoformat()}"

    def _fuege_position_hinzu(self, pos: Position) -> None:
        """Hängt eine Position an und belegt bei erlaubtem Typ ihren Zeitraum aus dem Kopf vor (S-0069)."""
        if self._darf_zeitraum(pos):
            pos.leistungszeitraum = self._kopf_zeitraum()
        self._rechnung.positionen.append(pos)
        self._lade_positionen()
        self._markiere_geaendert()

    def _position_zeitraum(self) -> None:
        """Öffnet den Zeitraum-Dialog für die markierte Position (Knopf; S-0069)."""
        if self._rechnung is None:
            return
        zeile = self._pos_tabelle.currentRow()
        if not 0 <= zeile < len(self._rechnung.positionen):
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("rechnung.bitte_position_waehlen"),
            )
            return
        pos = self._rechnung.positionen[zeile]
        # Produkt-Positionen tragen keinen Zeitraum; ein bereits gesetzter (aus der Zeit als
        # Leistung, Kopie-Prinzip) bleibt aber bearbeitbar.
        if not self._darf_zeitraum(pos) and pos.leistungszeitraum is None:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("position.zeitraum_nur_leistung"),
            )
            return
        dialog = LeistungszeitraumDialog(pos.leistungszeitraum, self._kopf_zeitraum(), self)
        if dialog.exec():
            pos.leistungszeitraum = dialog.zeitraum()
            self._lade_positionen()
            self._markiere_geaendert()

    # --- Bestätigen und Verwerfen ------------------------------------------

    def _melde_befunde(self, befunde: list) -> None:
        """Zeigt Prüfbefunde feld-nah; Befunde ohne eigenes Feld-Label als Sammelmeldung.

        Ohne diesen Rückfall verschwände ein Befund für ein Feld ohne Label spurlos, und das
        Bestätigen bräche ohne jede Rückmeldung ab (der „passiert nichts"-Fall aus 4T-0138).
        """
        ohne_label = []
        for befund in befunde:
            if befund.feld in self._fehler:
                self._zeige_feld_fehler(befund.feld, befund_text(befund))
            else:
                ohne_label.append(befund_text(befund))
        if ohne_label:
            QMessageBox.warning(
                self,
                ui_text("rechnungen.unvollstaendig_titel"),
                "\n".join(f"• {t}" for t in ohne_label),
            )

    def _bestaetigen(self) -> None:
        if self._rechnung is None or self._bestellung is None:
            return
        self._loesche_fehler()
        # Eingabe-Ebene vor der Übernahme: Ein halb gefülltes Skonto liesse sich sonst nicht
        # ins Wertobjekt übernehmen und ginge still verloren.
        _, eingabe_befunde = self._lese_skonto()
        if eingabe_befunde:
            for feld, text in eingabe_befunde:
                self._zeige_feld_fehler(feld, text)
            return
        self._uebernehme_in_rechnung()
        befunde = pruefe_rechnung(self._rechnung)
        if befunde:
            self._melde_befunde(befunde)
            return
        warnungen = warne_rechnung(self._rechnung, self._bestellung)
        if warnungen:
            antwort = QMessageBox.warning(
                self,
                ui_text("allgemein.warnung_titel"),
                ui_text(
                    "rechnung.warnung_frage",
                    warnungen="\n".join(f"• {befund_text(w)}" for w in warnungen),
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if antwort != QMessageBox.Yes:
                return
        self.bestaetigt.emit()

    def _verwerfen(self) -> None:
        self.verworfen.emit()

    # --- Erstellung (S-0032) ------------------------------------------------

    def _erstellen_angefordert(self) -> None:
        """Meldet dem Reiter die Erstellungs-Anforderung für die geladene Rechnung (S-0032 AK1)."""
        self.erstellen_angefordert.emit()

    def versuche_speichern(self) -> bool:
        """Speichert offene Änderungen über den Bestätigungsweg; True, wenn nichts mehr offen ist.

        Dient dem Reiter, ungespeicherte Änderungen vor der Erstellung festzuschreiben
        (S-0032 AK5). Ohne offene Änderungen ist nichts zu tun. Scheitert die Bestätigung
        (Pflichtfehler oder abgelehnte Warnung), bleibt die Maske geändert und liefert False.
        """
        if not self._geaendert:
            return True
        self._bestaetigen()
        return not self._geaendert
