"""Rechnungsübersicht-Reiter: lesende Gesamt-Sicht auf alle Rechnungen (S-0055, S-0056).

Eigene Tätigkeit (Reiter, S-0074) mit einer flachen Tabelle über alle Kunden und
Bestellungen hinweg: Kunde, Bestellnummer, Rechnungsnummer, Rechnungsdatum, Status und
zuletzt erzeugt am. Ausgangszustand ist Rechnungsdatum absteigend; Filtern und Sortieren
über alle Spalten bringt der geteilte `ObjektListe`-Baustein mit (Konvention K2), sodass
die Bedienung der übrigen Listen gleicht. Der Status ist farblich abgesetzt, damit offene
Entwürfe auf einen Blick auffallen.

Die Übersicht ist rein lesend und ändert nichts; bearbeitet wird in der
Rechnungserfassung. Zwei Wege führen von hier nach außen (S-0056 AK2/AK3): Ein Doppelklick
meldet die Rechnung über das Signal `rechnung_geoeffnet`, worauf das Hauptfenster in den
Rechnungen-Reiter wechselt und sie dort lädt; „Ablageort öffnen" öffnet den Zielordner der
erzeugten Dateien. Die Übersicht kennt den Rechnungen-Reiter dabei nicht selbst.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.domain import Datenbestand, Rechnung, RechnungsStatus
from eu_rechnung.services import (
    STANDARD_AUSGABE,
    RechnungsZeile,
    alle_rechnungen,
    zielordner_der_rechnung,
)
from eu_rechnung.texte import Sprachkontext
from eu_rechnung.ui.liste import ObjektListe, Spalte
from eu_rechnung.ui.rechnungs_anzeige import erzeugt_text, status_text
from eu_rechnung.ui.sprache import ui_kontext, ui_text

# Aware-UTC-Frühwert als Sortier-Rückfall für noch nie erzeugte Rechnungen (wie im
# Rechnungen-Reiter; ein naiver Rückfall würde beim Vergleich mit UTC-aware brechen).
_FRUEH = datetime.min.replace(tzinfo=timezone.utc)

# Status-Farben: Entwürfe fallen auf (offene Arbeit), Erzeugtes ist ruhig abgehakt.
_FARBE_ENTWURF = QColor("#a04000")
_FARBE_ERZEUGT = QColor("#107c10")

#: Spaltenindex des Rechnungsdatums (Ausgangs-Sortierung, S-0055 AK2).
_SPALTE_RECHNUNGSDATUM = 3


def _ist_erzeugt(zeile: object) -> bool:
    """True, wenn die Zeile eine erzeugte Rechnung trägt (Ablageort verfügbar)."""
    return (
        isinstance(zeile, RechnungsZeile)
        and zeile.rechnung.status is RechnungsStatus.ERZEUGT
    )


def _status_farbe(zeile: RechnungsZeile) -> QColor:
    """Farbe des Status-Textes: Entwurf abgesetzt gegenüber Erzeugt (S-0056 AK1)."""
    if zeile.rechnung.status is RechnungsStatus.ENTWURF:
        return _FARBE_ENTWURF
    return _FARBE_ERZEUGT


def _status_text(zeile: RechnungsZeile) -> str:
    """Status in der UI-Sprache.

    Übersetzt wird nur die Anzeige: Der Enum-Wert („Entwurf", „Erzeugt") steht so in
    der Firma-Datei und bleibt unangetastet, sonst bräuchte jede Bestandsdatei eine
    Migration.
    """
    return status_text(zeile.rechnung.status)


def _erzeugt_text(zeile: RechnungsZeile) -> str:
    """Erzeugungs-Zeitstempel in lokaler Anzeige und UI-Sprache; leer, wenn nie erzeugt."""
    return erzeugt_text(zeile.rechnung.zuletzt_erzeugt_am)


class RechnungsuebersichtReiter(QWidget):
    """Lesende Übersicht aller Rechnungen der Firma-Datei."""

    #: Doppelklick auf einen Eintrag: Die Rechnung soll in der Erfassung geöffnet werden.
    #: Das Hauptfenster wechselt den Reiter; die Übersicht kennt ihn nicht (S-0056 AK2).
    rechnung_geoeffnet = Signal(object)

    def __init__(self, datenbestand: Datenbestand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._datenbestand = datenbestand
        self._baue_ui()
        self.aktualisiere()

    def _baue_ui(self) -> None:
        layout = QVBoxLayout(self)
        kontext = ui_kontext()  # Datumsformat der Spalte, in der UI-Sprache

        hinweis = QLabel(ui_text("uebersicht.hinweis"))
        hinweis.setWordWrap(True)
        layout.addWidget(hinweis)

        self._liste = ObjektListe(
            [
                Spalte(ui_text("bestellung.feld_kunde"), lambda z: z.kunde.name),
                Spalte(
                    ui_text("bestellung.feld_bestellnummer"),
                    lambda z: z.bestellung.bestellnummer,
                ),
                Spalte(
                    ui_text("uebersicht.spalte_rechnungsnummer"),
                    lambda z: z.rechnung.rechnungsnummer,
                ),
                Spalte(
                    ui_text("uebersicht.spalte_rechnungsdatum"),
                    lambda z: kontext.datum(z.rechnung.rechnungsdatum),
                    sortierwert=lambda z: z.rechnung.rechnungsdatum,
                ),
                Spalte(
                    ui_text("uebersicht.spalte_status"),
                    _status_text,
                    vordergrund=_status_farbe,
                ),
                Spalte(
                    ui_text("uebersicht.spalte_erzeugt_am"),
                    _erzeugt_text,
                    sortierwert=lambda z: z.rechnung.zuletzt_erzeugt_am or _FRUEH,
                ),
            ],
            standard_sortierspalte=_SPALTE_RECHNUNGSDATUM,
            standard_absteigend=True,  # neueste zuerst (S-0055 AK2)
        )
        self._liste.auswahl_geaendert.connect(self._auf_auswahl)
        self._liste.objekt_aktiviert.connect(self._auf_doppelklick)
        layout.addWidget(self._liste, 1)

        leiste = QHBoxLayout()
        leiste.addStretch(1)
        self._ablage_knopf = QPushButton(ui_text("uebersicht.knopf_ablageort"))
        self._ablage_knopf.clicked.connect(self._oeffne_ablageort)
        self._ablage_knopf.setEnabled(False)  # erst mit einer erzeugten Rechnung
        leiste.addWidget(self._ablage_knopf)
        layout.addLayout(leiste)

    def aktualisiere(self) -> None:
        """Liest den Bestand neu ein; nach Änderungen in der Erfassung aufzurufen."""
        self._liste.setze_objekte(alle_rechnungen(self._datenbestand))

    def showEvent(self, event) -> None:
        """Beim Anzeigen des Reiters den Bestand neu einlesen (S-0055 AK1).

        Die Reiter entstehen einmal beim Aktivieren der Firma, in aller Regel bevor die
        erste Rechnung erfasst ist; erfasst und gelöscht wird danach im Rechnungen-Reiter.
        Ohne dieses Auffrischen zeigte die Übersicht dauerhaft den Stand des
        Aufbauzeitpunkts und blieb im Regelfall leer, obwohl Rechnungen vorhanden sind.
        Gleiches Muster wie im Rechnungen-Reiter, der so seine Stammdaten-Auswahl
        nachzieht.
        """
        super().showEvent(event)
        self.aktualisiere()

    # --- Wege nach außen ----------------------------------------------------

    def _auf_auswahl(self, zeile: object) -> None:
        """„Ablageort öffnen" gilt nur für erzeugte Rechnungen (S-0056 AK3)."""
        self._ablage_knopf.setEnabled(_ist_erzeugt(zeile))

    def _auf_doppelklick(self, zeile: object) -> None:
        """Meldet die Rechnung zum Öffnen in der Erfassung (S-0055 AK3, S-0056 AK2)."""
        if isinstance(zeile, RechnungsZeile):
            self.rechnung_geoeffnet.emit(zeile.rechnung)

    def ablageort(self, rechnung: Rechnung) -> Path:
        """Zielordner der erzeugten Dateien nach dem Ablageschema (S-0057).

        Leitet den Pfad aus Ausgabe-Verzeichnis und Kundennummer her; ein Pfad je Rechnung
        wird nicht gespeichert. Ohne gepflegtes Verzeichnis greift der Rückfall des
        Erstellungs-Service, mit dem dann auch erzeugt worden wäre.
        """
        verzeichnis = self._datenbestand.einstellungen.ausgabe_verzeichnis.strip()
        return zielordner_der_rechnung(rechnung, verzeichnis or STANDARD_AUSGABE)

    def _oeffne_ablageort(self) -> None:
        """Öffnet den Zielordner der markierten Rechnung im Datei-Explorer (S-0057 AK3).

        Fehlt der Ordner, etwa weil der Anwender die Dateien verschoben hat, erscheint ein
        lesbarer Hinweis; das Werkzeug verwaltet die Dateien nicht (S-0057, Abgrenzung).
        """
        zeile = self._liste.aktuelles_objekt()
        if not _ist_erzeugt(zeile):
            return
        ordner = self.ablageort(zeile.rechnung)
        if not ordner.is_dir():
            QMessageBox.information(
                self,
                ui_text("uebersicht.ablage_fehlt_titel"),
                ui_text("uebersicht.ablage_fehlt_text", ordner=ordner),
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ordner)))
