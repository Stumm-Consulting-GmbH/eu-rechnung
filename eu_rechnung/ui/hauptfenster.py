"""Hauptfenster: Anwendungsrahmen mit Reiterleiste und Firma-Datei-Verwaltung.

Träger der v1-Oberfläche (4T-0075): ein `QTabWidget` mit genau einem, nicht
schließbaren Reiter je Tätigkeit (Firma, Artikel, Kunden, Bestellungen, Rechnungen,
Rechnungsübersicht, Einstellungen). Der Rechnungen-Reiter trägt die bestehende
Rechnungsansicht (`RechnungenReiter`); die übrigen Reiter tragen zunächst einen
Platzhalter, bis ihre Masken in den Arbeitspaketen 2A-0007 bis 2A-0009 folgen.

Beim Start ohne aktive Firma zeigt das Fenster statt der Reiterleiste eine zentrale
Leerfläche (`LeerHinweis`); alle fachlichen Reiter sind dann nicht zugänglich, nur
das Menü „Datei" (und die Schaltflächen der Leerfläche) führt zum Anlegen oder Öffnen
einer Firma (4T-0080, S-0003). Sobald eine Firma angelegt oder geladen ist, tritt die
Reiterleiste an ihre Stelle. Central-Widget ist dazu ein `QStackedWidget` mit den
beiden Seiten Leerfläche und Reiterleiste.

Über das Menü „Datei" werden die dokument-basierten Firma-Operationen bedient
(4T-0079, S-0071): eine neue Firma anlegen (Speichern-Dialog, Endung `.scgr`),
eine bestehende öffnen (Öffnen-Dialog), über eine Liste zuletzt geöffneter
Firmen schnell laden und die aktive Firma wieder schließen (S-0083). Je Instanz ist
genau eine Firma aktiv; ein Wechsel ersetzt Datenbestand, Zielpfad und automatisches
Speichern und baut die Reiter frisch auf, das Schließen räumt sie ab und führt zurück
in den Leerzustand. Der Fenstertitel nennt die aktive Firma bei ihrem Dateinamen, damit
mehrere gleichzeitig laufende Instanzen unterscheidbar bleiben (S-0084).
Der Zustand eines Reiters bleibt über den Reiterwechsel erhalten (die Widgets
bestehen dauerhaft); nur der Firma-Wechsel baut sie neu. Für Absprünge aktiviert
`zeige_reiter` einen Ziel-Reiter und zeigt dort optional ein übergebenes Objekt an.

Das Menü „Hilfe" führt zur Prozesshilfe (Taste F1) und zum Über-Dialog (4T-0149,
S-0076). Beide sind wie „Datei" auch ohne aktive Firma erreichbar.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung import PRODUKTNAME
from eu_rechnung.domain import Datenbestand
from eu_rechnung.persistence import STANDARD_PFAD, sperre
from eu_rechnung.persistence.konfiguration import (
    AppKonfiguration,
    existierende_zuletzt_geoeffnet,
    lade_konfiguration,
    merke_zuletzt_geoeffnet,
    speichere_konfiguration,
    vergiss_aktive_firma,
)
from eu_rechnung.ui import firma_dialoge
from eu_rechnung.ui.artikel_reiter import ArtikelReiter
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.bestellung_reiter import BestellungReiter
from eu_rechnung.ui.einstellungen_reiter import EinstellungenReiter
from eu_rechnung.ui.firma_reiter import FirmaReiter
from eu_rechnung.ui.hilfe_dialog import HilfeDialog
from eu_rechnung.ui.kunde_reiter import KundeReiter
from eu_rechnung.ui.rechnungen_reiter import RechnungenReiter
from eu_rechnung.ui.rechnungsuebersicht_reiter import RechnungsuebersichtReiter
from eu_rechnung.ui.sprache import ui_text
from eu_rechnung.ui.ueber_dialog import UeberDialog


class Reiter(Enum):
    """Die sieben Tätigkeits-Reiter in ihrer festen Reihenfolge (S-0074).

    Die Reihenfolge der Enum-Werte ist zugleich die Reihenfolge in der Reiterleiste. Der
    Wert ist ein technischer Schlüssel und **nicht** die Beschriftung: Die holt
    `anzeigename` aus dem Sprachkatalog (S-0061). Der Wert bleibt bewusst stabil, weil
    `zeige_reiter` und die Tests ihn referenzieren.
    """

    FIRMA = "firma"
    ARTIKEL = "artikel"
    KUNDEN = "kunden"
    BESTELLUNGEN = "bestellungen"
    RECHNUNGEN = "rechnungen"
    RECHNUNGSUEBERSICHT = "rechnungsuebersicht"
    EINSTELLUNGEN = "einstellungen"

    @property
    def anzeigename(self) -> str:
        """Beschriftung des Reiters in der Reiterleiste, in der aktiven UI-Sprache."""
        return ui_text(f"hauptfenster.reiter_{self.value}")


class PlatzhalterReiter(QWidget):
    """Vorläufiger Reiter-Inhalt für die in v1 folgenden Tätigkeiten.

    Zeigt zentriert den Tätigkeitsnamen mit dem Hinweis, dass der Inhalt in v1
    folgt, dezent (ausgegraut), damit der Platzhalter klar erkennbar ist, ohne zu
    stören. Die echte Maske je Tätigkeit kommt mit den Arbeitspaketen 2A-0007 bis
    2A-0009.
    """

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        layout = QVBoxLayout(self)
        hinweis = QLabel(ui_text("hauptfenster.platzhalter", name=name))
        hinweis.setAlignment(Qt.AlignCenter)
        hinweis.setEnabled(False)  # dezent, als noch nicht aktive Tätigkeit erkennbar
        layout.addWidget(hinweis)


class LeerHinweis(QWidget):
    """Zentrale Fläche des Leerzustands ohne aktive Firma (S-0003, AK1/AK3).

    Ohne aktive Firma zeigt das Fenster statt der Reiterleiste diese Fläche. Sie
    erklärt den Leerzustand und bietet die einzigen verfügbaren Aktionen an: eine
    neue Firma anlegen oder eine bestehende öffnen (dieselben Aktionen wie im Menü
    „Datei"). Die beiden Rückrufe lösen genau die Menü-Aktionen des Hauptfensters
    aus; sobald eine Firma aktiv ist, tritt die Reiterleiste an diese Stelle.
    """

    def __init__(
        self,
        bei_neuer_firma,
        bei_firma_oeffnen,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch(1)

        titel = QLabel(ui_text("hauptfenster.leer_titel"))
        titel.setAlignment(Qt.AlignCenter)
        schrift = titel.font()
        schrift.setPointSize(schrift.pointSize() + 4)
        schrift.setBold(True)
        titel.setFont(schrift)
        layout.addWidget(titel)

        hinweis = QLabel(ui_text("hauptfenster.leer_hinweis"))
        hinweis.setAlignment(Qt.AlignCenter)
        layout.addWidget(hinweis)

        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        neu = QPushButton(ui_text("hauptfenster.menue_neue_firma"))
        neu.clicked.connect(bei_neuer_firma)
        oeffnen = QPushButton(ui_text("hauptfenster.menue_firma_oeffnen"))
        oeffnen.clicked.connect(bei_firma_oeffnen)
        knoepfe.addWidget(neu)
        knoepfe.addWidget(oeffnen)
        knoepfe.addStretch(1)
        layout.addLayout(knoepfe)

        layout.addStretch(1)


class HauptFenster(QMainWindow):
    """Anwendungsrahmen: `QTabWidget` mit den Reitern und Firma-Datei-Verwaltung."""

    # Produktname aus der Paket-Identität (`eu_rechnung/__init__.py`); ein Eigenname wird
    # nicht übersetzt und steht deshalb nicht im Sprachkatalog.
    _BASIS_TITEL = PRODUKTNAME

    def __init__(
        self,
        datenbestand: Datenbestand | None = None,
        *,
        daten_pfad: Path | str = STANDARD_PFAD,
        konfig_pfad: Path | str | None = None,
    ) -> None:
        super().__init__()
        # Ohne aktive Firma bleiben Datenbestand und automatisches Speichern None;
        # der Leerzustand baut keine Reiter auf (S-0003). Eine übergebene Firma wird
        # unten über _setze_aktive_firma aktiviert.
        self._datenbestand: Datenbestand | None = None
        self._daten_pfad = Path(daten_pfad)
        # Konfig-Pfad optional: ohne ihn wird die Zuletzt-geöffnet-Liste nur im
        # Speicher geführt (kein Schreiben) – bequem für Tests.
        self._konfig_pfad = Path(konfig_pfad) if konfig_pfad is not None else None
        self._konfig = (
            lade_konfiguration(self._konfig_pfad)
            if self._konfig_pfad is not None
            else AppKonfiguration()
        )
        self._auto_speicher: AutoSpeicher | None = None
        # Pfad, dessen Datei-Sperre diese Instanz hält (None im Leerzustand, S-0073).
        self._gesperrter_pfad: Path | None = None
        self.resize(1600, 560)
        # Central-Widget als Stapel: Leerfläche (ohne aktive Firma) und Reiterleiste.
        self._stapel = QStackedWidget()
        self._leer_hinweis = LeerHinweis(self._neue_firma, self._firma_oeffnen)
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)  # Reiter sind nicht schließbar (AK1)
        self._stapel.addWidget(self._leer_hinweis)
        self._stapel.addWidget(self._tabs)
        self.setCentralWidget(self._stapel)
        self._reiter_widgets: dict[Reiter, QWidget] = {}
        self._baue_menue()
        self._aktualisiere_zuletzt_menue()
        # Mit übergebener Firma direkt in den aktiven Zustand, sonst leer starten.
        if datenbestand is not None:
            self._setze_aktive_firma(datenbestand, self._daten_pfad)
        else:
            self._zeige_leerzustand()

    # --- Menü und Firma-Datei-Verwaltung ------------------------------------

    def _baue_menue(self) -> None:
        """Legt die Menüs „Datei" (S-0071) und „Hilfe" (S-0076) an.

        Läuft in `__init__` **vor** der Fallunterscheidung auf eine aktive Firma. Beide
        Menüs sind damit auch im Leerzustand vorhanden und bedienbar, wie es S-0003 für
        „Datei" und S-0076 (AK5) für „Hilfe" verlangt: Die Prozesshilfe erklärt gerade den
        ersten Schritt, das Anlegen einer Firma, und muss vor der ersten Firma erreichbar
        sein.
        """
        menue = self.menuBar().addMenu(ui_text("hauptfenster.menue_datei"))
        neu = QAction(ui_text("hauptfenster.menue_neue_firma"), self)
        neu.triggered.connect(self._neue_firma)
        menue.addAction(neu)
        oeffnen = QAction(ui_text("hauptfenster.menue_firma_oeffnen"), self)
        oeffnen.triggered.connect(self._firma_oeffnen)
        menue.addAction(oeffnen)
        self._zuletzt_menue = QMenu(ui_text("hauptfenster.menue_zuletzt"), self)
        menue.addMenu(self._zuletzt_menue)
        # Das Schließen steht bei den übrigen Firma-Operationen. Ohne aktive Firma gibt es
        # nichts zu schließen, deshalb startet die Aktion inaktiv (S-0083 AK1); aktiviert
        # wird sie in `_setze_aktive_firma`, deaktiviert im Leerzustand.
        self._schliessen_aktion = QAction(
            ui_text("hauptfenster.menue_firma_schliessen"), self
        )
        self._schliessen_aktion.triggered.connect(self._firma_schliessen)
        self._schliessen_aktion.setEnabled(False)
        menue.addAction(self._schliessen_aktion)
        menue.addSeparator()
        beenden = QAction(ui_text("hauptfenster.menue_beenden"), self)
        beenden.triggered.connect(self.close)
        menue.addAction(beenden)

        # Das Menü als Attribut halten, wie schon `_zuletzt_menue`: PySide6 gibt die
        # Ownership des von `addMenu` erzeugten QMenu an Python. Ohne Referenz kann der
        # Garbage Collector das C++-Objekt einziehen, sobald irgendwo ein Wrapper darauf
        # entsteht und wieder fällt; Zugriffe darauf brechen dann mit „already deleted".
        self._hilfe_menue = self.menuBar().addMenu(ui_text("hauptfenster.menue_hilfe"))
        self._hilfe_aktion = QAction(ui_text("hauptfenster.menue_hilfe_anzeigen"), self)
        # F1 ist unter Windows die etablierte Hilfe-Taste (S-0076 AK3). Der Kontext
        # `WindowShortcut` lässt sie im ganzen Fenster greifen, unabhängig davon, welcher
        # Reiter oder welches Feld gerade den Fokus hat; an ein Widget gebundene Kürzel
        # täten das nicht. Das Kürzel steht zugleich sichtbar im Menü (AK2).
        self._hilfe_aktion.setShortcut(QKeySequence(Qt.Key_F1))
        self._hilfe_aktion.setShortcutContext(Qt.WindowShortcut)
        self._hilfe_aktion.triggered.connect(self._zeige_hilfe)
        self._hilfe_menue.addAction(self._hilfe_aktion)
        # Die Aktion zusätzlich am Fenster registrieren: Ein Kürzel einer Menü-Aktion
        # greift sonst nicht, solange das Menü nie geöffnet wurde.
        self.addAction(self._hilfe_aktion)
        self._ueber_aktion = QAction(ui_text("hauptfenster.menue_ueber"), self)
        self._ueber_aktion.triggered.connect(self._zeige_ueber)
        self._hilfe_menue.addAction(self._ueber_aktion)

    def _zeige_hilfe(self) -> None:
        """Öffnet die Prozesshilfe (S-0076 AK4; Inhalt folgt mit 4T-0151)."""
        HilfeDialog(self).exec()

    def _zeige_ueber(self) -> None:
        """Öffnet den Über-Dialog (S-0076 AK4; Inhalt folgt mit 4T-0150)."""
        UeberDialog(self).exec()

    def _neue_firma(self) -> None:
        """Legt über den Speichern-Dialog eine neue, leere Firma-Datei an (AK1)."""
        ergebnis = firma_dialoge.lege_neue_firma_an(self)
        if ergebnis is None:
            return
        bestand, pfad = ergebnis
        self._setze_aktive_firma(bestand, pfad)
        self.zeige_reiter(Reiter.FIRMA)  # direkt zur Erfassung der neuen Firma

    def _firma_oeffnen(self) -> None:
        """Lädt über den Öffnen-Dialog eine bestehende Firma-Datei (AK2)."""
        ergebnis = firma_dialoge.oeffne_firma(self)
        if ergebnis is None:
            return
        self._setze_aktive_firma(*ergebnis)

    def _lade_firma_aus_pfad(self, pfad: Path) -> None:
        """Lädt eine bekannte Firma-Datei (Zuletzt-geöffnet) und aktiviert sie (AK4)."""
        ergebnis = firma_dialoge.lade_firma(pfad, self)
        if ergebnis is None:
            return
        self._setze_aktive_firma(*ergebnis)

    def oeffne_uebergebene_firma(self, pfad: Path) -> None:
        """Öffnet eine beim Programmstart übergebene Firma-Datei (S-0054).

        Öffentlich, weil der Aufruf von außen kommt: Ein Doppelklick auf eine
        `.scgr`-Datei startet die Anwendung mit deren Pfad als Argument, und `app.py`
        reicht ihn hierher. Geladen wird über **denselben** Weg wie beim Öffnen aus
        „Zuletzt geöffnet", also mit Sperre, Übernahme einer verwaisten Sperre,
        Fehlermeldung bei defekter Datei, Zuletzt-Liste und Autostart-Vermerk. So
        verhält sich der Doppelklick identisch zum Öffnen von Hand, und es entsteht kein
        zweiter Ladepfad mit eigenen Randfällen.

        Trägt der Pfad nicht die Firma-Endung, wird er abgewiesen: Windows kann jede
        Datei an ein Programm übergeben, und eine fremde Datei soll nicht am Schema
        scheitern, sondern verständlich abgelehnt werden. Das Fenster bleibt dann im
        Leerzustand. Eine fehlende oder defekte Firma-Datei meldet der gemeinsame
        Ladeweg selbst.
        """
        if pfad.suffix.lower() != firma_dialoge.DATEI_ENDUNG:
            QMessageBox.warning(
                self,
                ui_text("firma_dialog.uebergabe_endung_titel"),
                ui_text("firma_dialog.uebergabe_endung_text", name=pfad.name),
            )
            return
        self._lade_firma_aus_pfad(pfad)

    def _firma_schliessen(self) -> None:
        """Schließt die aktive Firma und kehrt in den Leerzustand zurück (S-0083).

        Im Regelfall ohne Rückfrage, denn jede bestätigte Operation ist bereits gespeichert
        (S-0072); eine Bestätigung ohne Risiko wäre nur lästig (AK5). Nur wenn ein
        automatisches Speichern fehlschlug und abgebrochen wurde, steht ein ungespeicherter
        Stand im Raum, den das Schließen verwerfen würde; dann wird gewarnt (AK6).

        Die Datei-Sperre wird freigegeben, damit dieselbe Firma unmittelbar wieder geöffnet
        werden kann (AK3); die Datei selbst bleibt unberührt und weiterhin in der
        Zuletzt-geöffnet-Liste (AK4).
        """
        if self._datenbestand is None:
            return
        if self._auto_speicher is not None and self._auto_speicher.ungespeichert:
            if not self._frage_ungespeichert_schliessen():
                return
        if self._gesperrter_pfad is not None:
            sperre.gib_sperre_frei(self._gesperrter_pfad)
            self._gesperrter_pfad = None
        # Den Autostart-Vermerk löschen, sonst zöge der nächste Programmstart die Firma
        # sofort wieder herein und das Schließen wäre über das Programm-Ende hinaus
        # wirkungslos (AK8). Die Zuletzt-geöffnet-Liste bleibt davon unberührt (AK4).
        self._konfig = vergiss_aktive_firma(self._konfig)
        if self._konfig_pfad is not None:
            speichere_konfiguration(self._konfig, self._konfig_pfad)
        if self._auto_speicher is not None:
            self._auto_speicher.ungespeichert_geaendert.disconnect(self._aktualisiere_titel)
            self._auto_speicher.deleteLater()
            self._auto_speicher = None
        self._datenbestand = None
        self._raeume_reiter_ab()
        self._zeige_leerzustand()

    def _frage_ungespeichert_schliessen(self) -> bool:
        """Warnt vor dem Verwerfen eines ungespeicherten Stands; True heißt schließen (AK6)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(ui_text("hauptfenster.schliessen_ungespeichert_titel"))
        box.setText(ui_text("hauptfenster.schliessen_ungespeichert_text"))
        trotzdem = box.addButton(
            ui_text("hauptfenster.schliessen_trotzdem"), QMessageBox.AcceptRole
        )
        box.addButton(
            ui_text("hauptfenster.schliessen_abbrechen"), QMessageBox.RejectRole
        )
        box.exec()
        return box.clickedButton() is trotzdem

    def _setze_aktive_firma(self, datenbestand: Datenbestand, pfad: Path | str) -> None:
        """Macht einen geladenen oder angelegten Datenbestand zur aktiven Firma (AK3).

        Ersetzt Datenbestand, Zielpfad und automatisches Speichern, baut die Reiter
        frisch auf, schaltet von der Leerfläche auf die Reiterleiste (AK4) und vermerkt
        die Firma als zuletzt geöffnet. Je Instanz bleibt so genau eine Firma aktiv.
        Dient auch dem Übergang aus dem Leerzustand; dann gibt es noch kein vorheriges
        automatisches Speichern, das abzuhängen wäre. Die Datei-Sperre des neuen Pfads
        hat der Aufrufer (firma_dialoge bzw. app) bereits erworben; die Sperre der
        bisherigen Firma wird hier freigegeben (S-0073).
        """
        neuer_pfad = Path(pfad)
        if self._gesperrter_pfad is not None and self._gesperrter_pfad != neuer_pfad:
            sperre.gib_sperre_frei(self._gesperrter_pfad)
        self._gesperrter_pfad = neuer_pfad
        self._datenbestand = datenbestand
        self._daten_pfad = neuer_pfad
        alt = self._auto_speicher
        if alt is not None:
            alt.ungespeichert_geaendert.disconnect(self._aktualisiere_titel)
        self._auto_speicher = AutoSpeicher(datenbestand, self._daten_pfad, self)
        self._auto_speicher.ungespeichert_geaendert.connect(self._aktualisiere_titel)
        self._aktualisiere_titel(False)
        self._baue_reiter()
        if alt is not None:
            alt.deleteLater()
        self._stapel.setCurrentWidget(self._tabs)
        self._schliessen_aktion.setEnabled(True)  # ab jetzt gibt es etwas zu schließen
        self._merke_firma_in_konfig(self._daten_pfad)

    def _merke_firma_in_konfig(self, pfad: Path) -> None:
        """Setzt eine Firma an die Spitze der Zuletzt-geöffnet-Liste und speichert sie."""
        self._konfig = merke_zuletzt_geoeffnet(self._konfig, pfad)
        if self._konfig_pfad is not None:
            speichere_konfiguration(self._konfig, self._konfig_pfad)
        self._aktualisiere_zuletzt_menue()

    def _aktualisiere_zuletzt_menue(self) -> None:
        """Baut das Untermenü „Zuletzt geöffnet" aus den noch existierenden Dateien."""
        self._zuletzt_menue.clear()
        eintraege = existierende_zuletzt_geoeffnet(self._konfig)
        self._zuletzt_menue.setEnabled(bool(eintraege))
        for pfad in eintraege:
            aktion = QAction(pfad.name, self)
            aktion.setToolTip(str(pfad))
            aktion.setStatusTip(str(pfad))
            aktion.triggered.connect(
                lambda _checked=False, p=pfad: self._lade_firma_aus_pfad(p)
            )
            self._zuletzt_menue.addAction(aktion)

    # --- Reiter -------------------------------------------------------------

    def _raeume_reiter_ab(self) -> None:
        """Entfernt alle Reiter und gibt ihre Widgets frei.

        Gemeinsam genutzt vom Firma-Wechsel (der die Reiter danach neu aufbaut) und vom
        Schließen (S-0083). In beiden Fällen darf keine Maske auf dem alten Datenbestand
        weiterleben.
        """
        while self._tabs.count():
            widget = self._tabs.widget(0)
            self._tabs.removeTab(0)
            widget.deleteLater()
        self._reiter_widgets = {}

    def _baue_reiter(self) -> None:
        """Baut die Reiter frisch auf; Firma und Rechnungen echt, Rest Platzhalter.

        Beim Firma-Wechsel werden bestehende Reiter zunächst entfernt und verworfen,
        damit die neuen Reiter auf dem aktiven Datenbestand aufsetzen.
        """
        self._raeume_reiter_ab()
        for reiter in Reiter:
            if reiter is Reiter.FIRMA:
                widget: QWidget = FirmaReiter(
                    self._datenbestand, auto_speicher=self._auto_speicher
                )
            elif reiter is Reiter.RECHNUNGEN:
                widget = RechnungenReiter(
                    self._datenbestand,
                    daten_pfad=self._daten_pfad,
                    auto_speicher=self._auto_speicher,
                )
            elif reiter is Reiter.ARTIKEL:
                widget = ArtikelReiter(
                    self._datenbestand, auto_speicher=self._auto_speicher
                )
            elif reiter is Reiter.KUNDEN:
                widget = KundeReiter(
                    self._datenbestand, auto_speicher=self._auto_speicher
                )
            elif reiter is Reiter.BESTELLUNGEN:
                widget = BestellungReiter(
                    self._datenbestand, auto_speicher=self._auto_speicher
                )
            elif reiter is Reiter.RECHNUNGSUEBERSICHT:
                widget = RechnungsuebersichtReiter(self._datenbestand)
                # Doppelklick in der Übersicht führt in die Erfassung: Die Übersicht kennt
                # den Rechnungen-Reiter nicht, das Fenster orchestriert (S-0056 AK2).
                widget.rechnung_geoeffnet.connect(
                    lambda rechnung: self.zeige_reiter(Reiter.RECHNUNGEN, rechnung)
                )
            elif reiter is Reiter.EINSTELLUNGEN:
                widget = EinstellungenReiter(
                    self._datenbestand, auto_speicher=self._auto_speicher
                )
            else:
                widget = PlatzhalterReiter(reiter.anzeigename)
            self._reiter_widgets[reiter] = widget
            self._tabs.addTab(widget, reiter.anzeigename)

    def zeige_reiter(self, reiter: Reiter, objekt: object | None = None) -> None:
        """Aktiviert den Ziel-Reiter und zeigt dort optional ein Objekt an.

        Grundgerüst für Absprünge (AK4): wechselt zum Reiter und ruft, falls ein
        Objekt übergeben wird und das Ziel-Widget es unterstützt, dessen
        `zeige_objekt` auf (etwa eine Rechnung im Rechnungen-Reiter).
        """
        widget = self._reiter_widgets[reiter]
        self._tabs.setCurrentWidget(widget)
        if objekt is not None:
            zeige = getattr(widget, "zeige_objekt", None)
            if callable(zeige):
                zeige(objekt)

    def _zeige_leerzustand(self) -> None:
        """Zeigt die Leerfläche ohne aktive Firma; nur das Menü „Datei" führt weiter."""
        self._stapel.setCurrentWidget(self._leer_hinweis)
        self._schliessen_aktion.setEnabled(False)
        self._aktualisiere_titel(False)

    def _aktualisiere_titel(self, ungespeichert: bool) -> None:
        """Setzt den Fenstertitel aus Firma-Datei und Zustand (S-0084, S-0072 AK4).

        Mit aktiver Firma beginnt der Titel mit dem Dateinamen ohne Endung, gefolgt vom
        Produktnamen; ist der Stand nicht gespeichert, hängt der bisherige Zusatz hinten an.
        Der Dateiname steht **vorn**, weil Taskleiste und Fensterwechsel lange Titel hinten
        abschneiden: Nur so bleibt bei mehreren Instanzen erkennbar, welches Fenster welche
        Firma führt (S-0073). Ohne aktive Firma gibt es keinen Dateinamen; dort bleibt der
        Titel unverändert.
        """
        if self._datenbestand is None:
            self.setWindowTitle(
                ui_text("hauptfenster.titel_keine_firma", titel=self._BASIS_TITEL)
            )
            return
        schluessel = (
            "hauptfenster.titel_nicht_gespeichert"
            if ungespeichert
            else "hauptfenster.titel_mit_firma"
        )
        self.setWindowTitle(
            ui_text(schluessel, datei=self._daten_pfad.stem, titel=self._BASIS_TITEL)
        )

    def closeEvent(self, event) -> None:
        """Gibt beim Schließen die Datei-Sperre der aktiven Firma frei (S-0073).

        Bei einem regulären Beenden wird die Sperre freigegeben, sodass die Firma-Datei
        wieder geöffnet werden kann. Ein Absturz hinterlässt eine verwaiste Sperre, die
        beim nächsten Öffnen nach Bestätigung übernehmbar ist.
        """
        if self._gesperrter_pfad is not None:
            sperre.gib_sperre_frei(self._gesperrter_pfad)
        super().closeEvent(event)
