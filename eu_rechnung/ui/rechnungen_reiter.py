"""Rechnungen-Reiter: Master-Detail mit Bestellungs-Bezug, Liste und eingebetteter Maske.

Träger der Rechnungsansicht, seit 4T-0100 auf das einheitliche Master-Detail-Muster der
übrigen Reiter gehoben: links der Bestellungs-Bezug (Kunde, dann Bestellung) über der
`ObjektListe` der Rechnungen der gewählten Bestellung (Filter und Sortierung, Standard
Rechnungsdatum absteigend; S-0028), darunter die Aktionsknöpfe; rechts die eingebettete
`RechnungsMaske` (S-0024). Über „Neue Rechnung" wird eine aus den Stammdaten vorbelegte
Rechnung angelegt (S-0025/S-0029); die Auswahl einer Zeile lädt sie zum Ändern (S-0026);
„Löschen" entfernt sie nach Sicherheitsabfrage (S-0027); „Rechnung erstellen" speichert offene
Maskenänderungen, prüft die Rechnung zweistufig gegen die Pflichtfelder der aktiven Stufe,
weist bei inaktiver XRechnung auf die fehlende CIUS-Garantie hin und erzeugt dann die
Ausgabedateien (F-0006, S-0047/S-0049). Die Aktion steht am Listen-Knopf und in der Maske.

Die Maske arbeitet auf einer Kopie; beim Ändern hält der Reiter das Original und ersetzt es
beim Bestätigen. Zwei Wächter halten die Signal-Kaskaden auseinander: `_programmatisch`
unterdrückt das Laden der Maske beim programmatischen Befüllen/Markieren der Liste,
`_auffrischen_laeuft` das Leeren der Maske beim Auffrischen der Stammdaten-Auswahl
(`showEvent`, `zeige_objekt`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.domain import Bestellung, Datenbestand, Kunde, Rechnung, RechnungsStatus
from eu_rechnung.persistence import STANDARD_PFAD, PersistenzFehler
from eu_rechnung.services import (
    Befund,
    ValidierungsFehler,
    berechne_summen,
    erstelle_ausgaben,
    finde_rechnungsnummer_dublette,
    lege_rechnung_an,
    pruefe_rechnung_fuer_ausgabe,
    vorbelege_rechnung,
)
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.erstellen_dialog import FormatDialog
from eu_rechnung.ui.liste import ObjektListe, Spalte
from eu_rechnung.ui.rechnungs_anzeige import erzeugt_text, status_text
from eu_rechnung.ui.rechnungsmaske import RechnungsMaske
from eu_rechnung.ui.sprache import befund_text, ui_kontext, ui_text

# Aware-UTC-Frühwert als Sortier-Rückfall für noch nie erzeugte Rechnungen
# (zuletzt_erzeugt_am ist UTC-aware; ein naiver Rückfall würde beim Vergleich brechen).
_FRUEH = datetime.min.replace(tzinfo=timezone.utc)

# Vorgeschlagener Ordnername unter „Dokumente", wenn noch kein Ausgabe-Verzeichnis
# gepflegt ist (S-0057 AK1).
_STANDARD_AUSGABE_ORDNER = "EU-Rechnung Ausgabe"


class RechnungenReiter(QWidget):
    """Reiter mit Bestellungs-Bezug, Rechnungs-Liste und eingebetteter Detailmaske."""

    def __init__(
        self,
        datenbestand: Datenbestand,
        *,
        daten_pfad: Path | str = STANDARD_PFAD,
        auto_speicher: AutoSpeicher | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._datenbestand = datenbestand
        self._daten_pfad = daten_pfad
        self._auto = auto_speicher or AutoSpeicher(datenbestand, daten_pfad)
        # Beim Ändern die Original-Rechnung in der Bestellung (die Maske arbeitet auf einer
        # Kopie); None im Anlegen- und Leerzustand.
        self._bearbeitete_original: Rechnung | None = None
        # Wächter: unterdrückt das Laden der Maske aus programmatischen Auswahl-Signalen.
        self._programmatisch = False
        # Wächter: unterdrückt das Leeren der Maske beim Auffrischen der Auswahl.
        self._auffrischen_laeuft = False
        self._baue_ui()
        self._fuelle_kunden()

    # --- Aufbau -------------------------------------------------------------

    def _baue_ui(self) -> None:
        layout = QHBoxLayout(self)

        links = QVBoxLayout()

        auswahl = QHBoxLayout()
        auswahl.addWidget(QLabel(ui_text("rechnungen.label_kunde")))
        self._kunde_box = QComboBox()
        self._kunde_box.currentIndexChanged.connect(self._kunde_gewechselt)
        auswahl.addWidget(self._kunde_box, 1)
        auswahl.addWidget(QLabel(ui_text("rechnungen.label_bestellung")))
        self._bestellung_box = QComboBox()
        self._bestellung_box.currentIndexChanged.connect(self._bestellung_gewechselt)
        auswahl.addWidget(self._bestellung_box, 1)
        links.addLayout(auswahl)

        self._hinweis = QLabel("")
        self._hinweis.setWordWrap(True)
        self._hinweis.setVisible(False)
        links.addWidget(self._hinweis)

        self._liste = ObjektListe(
            [
                Spalte(ui_text("uebersicht.spalte_rechnungsnummer"), lambda r: r.rechnungsnummer),
                Spalte(
                    ui_text("uebersicht.spalte_rechnungsdatum"),
                    lambda r: r.rechnungsdatum.strftime("%d.%m.%Y"),
                    sortierwert=lambda r: r.rechnungsdatum,
                ),
                Spalte(
                    ui_text("sichtteil.leistungszeitraum"),
                    lambda r: self._zeitraum_text(r),
                    sortierwert=lambda r: r.leistungszeitraum.von,
                ),
                Spalte(ui_text("uebersicht.spalte_status"), lambda r: status_text(r.status)),
                Spalte(
                    ui_text("uebersicht.spalte_erzeugt_am"),
                    lambda r: self._erzeugt_text(r),
                    sortierwert=lambda r: r.zuletzt_erzeugt_am or _FRUEH,
                ),
            ],
            standard_sortierspalte=1,  # Rechnungsdatum
            standard_absteigend=True,  # neueste zuerst (S-0028)
        )
        self._liste.auswahl_geaendert.connect(self._auf_auswahl)
        links.addWidget(self._liste, 1)

        knoepfe = QHBoxLayout()
        self._neu_knopf = QPushButton(ui_text("rechnungen.knopf_neu"))
        self._neu_knopf.clicked.connect(self._neue_rechnung)
        self._loeschen_knopf = QPushButton(ui_text("allgemein.knopf_loeschen"))
        self._loeschen_knopf.clicked.connect(self._loeschen)
        self._erstellen_knopf = QPushButton(ui_text("erstellen.titel"))
        self._erstellen_knopf.clicked.connect(self._rechnung_erstellen)
        knoepfe.addWidget(self._neu_knopf)
        knoepfe.addWidget(self._loeschen_knopf)
        knoepfe.addWidget(self._erstellen_knopf)
        knoepfe.addStretch(1)
        links.addLayout(knoepfe)

        layout.addLayout(links, 3)

        bereich = QScrollArea()
        bereich.setWidgetResizable(True)
        self._maske = RechnungsMaske(self._datenbestand.artikel)
        self._maske.bestaetigt.connect(self._auf_bestaetigt)
        self._maske.verworfen.connect(self._auf_verworfen)
        self._maske.erstellen_angefordert.connect(self._rechnung_erstellen)
        bereich.setWidget(self._maske)
        layout.addWidget(bereich, 2)

    # --- Hilfen -------------------------------------------------------------

    @staticmethod
    def _zeitraum_text(rechnung: Rechnung) -> str:
        lz = rechnung.leistungszeitraum
        return f"{lz.von:%d.%m.%Y}–{lz.bis:%d.%m.%Y}"

    @staticmethod
    def _erzeugt_text(rechnung: Rechnung) -> str:
        return erzeugt_text(rechnung.zuletzt_erzeugt_am, leer="—")

    # --- Datenzugriff -------------------------------------------------------

    def _aktueller_kunde(self) -> Kunde | None:
        return self._kunde_box.currentData()

    def _aktuelle_bestellung(self) -> Bestellung | None:
        return self._bestellung_box.currentData()

    def _markierte_rechnung(self) -> Rechnung | None:
        objekt = self._liste.aktuelles_objekt()
        return objekt if isinstance(objekt, Rechnung) else None

    # --- Bestellungs-Bezug und Liste ---------------------------------------

    def _fuelle_kunden(self, zusatz: Kunde | None = None) -> None:
        """Füllt die Kunden-Auswahl mit den aktiven Kunden (S-0015 AK1).

        Ein deaktivierter Kunde wird nicht mehr angeboten, denn genau das ist der Zweck des
        Deaktivierens. `zusatz` nimmt einen darüber hinaus aufzunehmenden Kunden auf: Die Box
        wählt nicht nur den Kunden einer neuen Rechnung, sie steuert über `_kunde_gewechselt`
        auch, welche Rechnungen die Liste zeigt. Ohne diesen Weg wären die Rechnungen eines
        deaktivierten Kunden hier unerreichbar, was S-0015 AK1 („bleibt aber mit Bestellungen
        und Rechnungen erhalten") gerade ausschließt.
        """
        self._kunde_box.clear()
        for kunde in self._datenbestand.kunden:
            if kunde.aktiv or kunde is zusatz:
                self._kunde_box.addItem(f"{kunde.name} ({kunde.kundennummer})", kunde)
        self._aktualisiere_leerzustand()

    def _kunde_gewechselt(self) -> None:
        self._fuelle_bestellungen()
        self._fuelle_liste()
        self._aktualisiere_leerzustand()

    def _fuelle_bestellungen(self, zusatz: Bestellung | None = None) -> None:
        """Füllt die Bestellungs-Auswahl mit den aktiven Bestellungen des Kunden (S-0024).

        `zusatz` wirkt wie bei `_fuelle_kunden`: Der Sprung auf eine Rechnung einer
        deaktivierten Bestellung muss sie erreichbar machen.
        """
        self._bestellung_box.clear()
        kunde = self._aktueller_kunde()
        if kunde is not None:
            for bestellung in kunde.bestellungen:
                if bestellung.aktiv or bestellung is zusatz:
                    self._bestellung_box.addItem(bestellung.bestellnummer, bestellung)

    def _bestellung_gewechselt(self) -> None:
        self._fuelle_liste()
        self._aktualisiere_leerzustand()
        if not self._auffrischen_laeuft:
            # Echter Wechsel durch den Anwender: einen offenen Anlege-/Ändern-Kontext verwerfen.
            self._bearbeitete_original = None
            self._maske.zeige(None, None, ist_neu=True)

    def _fuelle_liste(self) -> None:
        self._programmatisch = True
        try:
            bestellung = self._aktuelle_bestellung()
            rechnungen = list(bestellung.rechnungen) if bestellung is not None else []
            self._liste.setze_objekte(rechnungen)
        finally:
            self._programmatisch = False

    def _waehle_in_liste(self, rechnung: Rechnung) -> None:
        """Markiert eine Rechnung in der Liste, ohne das Auswahl-Laden auszulösen."""
        self._programmatisch = True
        try:
            self._liste.waehle_objekt(rechnung)
        finally:
            self._programmatisch = False

    def _aktualisiere_leerzustand(self) -> None:
        """Zeigt bei fehlenden Stammdaten einen Hinweis und sperrt „Neue Rechnung" (AK2)."""
        if not self._datenbestand.kunden:
            self._hinweis.setText(ui_text("rechnungen.leer_keine_kunden"))
            self._hinweis.setVisible(True)
        elif self._aktuelle_bestellung() is None:
            self._hinweis.setText(ui_text("rechnungen.leer_keine_bestellung"))
            self._hinweis.setVisible(True)
        else:
            self._hinweis.setVisible(False)
        self._neu_knopf.setEnabled(self._aktuelle_bestellung() is not None)

    def _aktualisiere_stammdaten(self) -> None:
        """Füllt Kunde- und Bestellung-Auswahl neu und stellt Auswahl und Markierung her (AK1).

        Der `zusatz`-Weg gilt **allein einer offenen Rechnung**: Nur dann darf ein inzwischen
        deaktivierter Kunde in seiner Box bleiben, damit das Auffrischen dem Anwender nicht
        wegzieht, woran er gerade arbeitet. Ohne offene Rechnung verschwindet er, und die
        Auswahl fällt auf den ersten aktiven Kunden.

        **Nicht an der bloßen Auswahl festmachen:** Die Box zeigt nach dem Aufbau auf ihren
        ersten Eintrag, ohne dass jemand ihn gewählt hätte. Hinge der Zusatz daran, hielte
        sich ein deaktivierter Kunde selbst in der Liste, solange niemand umschaltet, und
        S-0015 AK1 wäre genau dort verletzt, wo es zählt: beim Anlegen einer neuen Rechnung.

        Die Bestellungen werden nach dem Setzen des Kunden erneut gefüllt, weil
        `_kunde_gewechselt` sie zwischendurch ohne `zusatz` aufbaut.
        """
        # Den Artikel-Stamm der Maske mitziehen: „Position aus Artikel" und die
        # Typ-Auflösung sollen im Artikel-Reiter neu angelegte oder gelöschte Artikel ohne
        # Neustart sehen (S-0024 AK7; Fund aus der Abnahme, Cluster 4). Berührt keine der
        # Auswahl-Boxen und braucht deshalb den Auffrischen-Wächter nicht.
        self._maske.setze_artikel(self._datenbestand.artikel)
        self._auffrischen_laeuft = True
        try:
            offen = self._bearbeitete_original is not None
            kunde = self._aktueller_kunde()
            bestellung = self._aktuelle_bestellung()
            markierte = self._markierte_rechnung()
            self._fuelle_kunden(zusatz=kunde if offen else None)
            if kunde is not None:
                self._waehle_in_box(self._kunde_box, kunde)
            self._fuelle_bestellungen(zusatz=bestellung if offen else None)
            if bestellung is not None:
                self._waehle_in_box(self._bestellung_box, bestellung)
            self._fuelle_liste()
            if markierte is not None:
                self._waehle_in_liste(markierte)
        finally:
            self._auffrischen_laeuft = False

    def showEvent(self, event) -> None:
        """Beim Anzeigen des Reiters die Stammdaten-Auswahl auffrischen (AK1)."""
        super().showEvent(event)
        self._aktualisiere_stammdaten()

    # --- Navigation ---------------------------------------------------------

    def zeige_objekt(self, rechnung: Rechnung) -> None:
        """Springt zu einer Rechnung: wählt Kunde und Bestellung, markiert und lädt sie.

        Kunde und Bestellung werden als `zusatz` neu aufgenommen, weil beide deaktiviert sein
        können und dann nicht in ihrer Box stünden. `_waehle_in_box` fände sie nicht und ließe
        die Auswahl stumm stehen, während die Maske die Rechnung lädt: Die Liste zeigte dann
        eine andere Rechnung als die Maske.
        """
        for kunde in self._datenbestand.kunden:
            for bestellung in kunde.bestellungen:
                if rechnung in bestellung.rechnungen:
                    self._auffrischen_laeuft = True
                    try:
                        self._fuelle_kunden(zusatz=kunde)
                        self._waehle_in_box(self._kunde_box, kunde)
                        self._fuelle_bestellungen(zusatz=bestellung)
                        self._waehle_in_box(self._bestellung_box, bestellung)
                        self._fuelle_liste()
                        self._waehle_in_liste(rechnung)
                    finally:
                        self._auffrischen_laeuft = False
                    self._bearbeitete_original = rechnung
                    self._maske.zeige(rechnung, bestellung, ist_neu=False)
                    return

    @staticmethod
    def _waehle_in_box(box: QComboBox, objekt: object) -> None:
        """Setzt die Auswahl der Combobox auf den Eintrag mit diesem Objekt."""
        for i in range(box.count()):
            if box.itemData(i) is objekt:
                box.setCurrentIndex(i)
                return

    # --- Auswahl, Anlegen, Ändern ------------------------------------------

    def _auf_auswahl(self, objekt: object) -> None:
        """Lädt die vom Anwender gewählte Rechnung zum Ändern in die Maske (S-0026)."""
        if self._programmatisch:
            return
        if isinstance(objekt, Rechnung):
            self._bearbeitete_original = objekt
            self._maske.zeige(objekt, self._aktuelle_bestellung(), ist_neu=False)

    def _neue_rechnung(self) -> None:
        kunde = self._aktueller_kunde()
        bestellung = self._aktuelle_bestellung()
        if kunde is None or bestellung is None:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("rechnungen.bitte_kunde_bestellung"),
            )
            return
        self._hebe_auswahl_auf()
        self._bearbeitete_original = None
        rechnung = vorbelege_rechnung(self._datenbestand, kunde, bestellung)
        self._maske.zeige(rechnung, bestellung, ist_neu=True)

    def _bestaetige_bei_dublette(self, rechnung: Rechnung) -> bool:
        """Warnt bei einer bestandsweiten Rechnungsnummer-Dublette (S-0045); True = fortfahren.

        Prüft über den gesamten Datenbestand (die Maske kennt ihn bewusst nicht) und gilt für
        Anlegen und Ändern; die bearbeitete Rechnung selbst ist über ihre `id` ausgenommen. Die
        Warnung benennt die andere Rechnung und lässt das Speichern zu (Warn-statt-Sperr).
        """
        treffer = finde_rechnungsnummer_dublette(self._datenbestand, rechnung)
        if treffer is None:
            return True
        antwort = QMessageBox.warning(
            self,
            ui_text("rechnungen.dublette_titel"),
            ui_text(
                "rechnungen.dublette_text",
                nummer=rechnung.rechnungsnummer,
                kunde=treffer.kunde.name,
                kundennummer=treffer.kunde.kundennummer,
                bestellnummer=treffer.bestellung.bestellnummer,
                datum=ui_kontext().datum(treffer.rechnung.rechnungsdatum),
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return antwort == QMessageBox.Yes

    def _auf_bestaetigt(self) -> None:
        """Reaktion auf die geprüfte Maske: Anlegen (S-0025) oder Ändern (S-0026)."""
        rechnung = self._maske.rechnung
        bestellung = self._maske.bestellung
        if rechnung is None or bestellung is None:
            return
        if not self._bestaetige_bei_dublette(rechnung):
            return
        if self._maske.ist_neu:
            try:
                lege_rechnung_an(
                    self._datenbestand, bestellung, rechnung, pfad=self._daten_pfad
                )
            except ValidierungsFehler as fehler:
                QMessageBox.warning(
                    self,
                    ui_text("rechnungen.anlegen_fehler_titel"),
                    "\n".join(befund_text(b) for b in fehler.befunde),
                )
                return
            except PersistenzFehler:
                # Rechnung ist angelegt, aber noch nicht geschrieben: Wiederholen anbieten.
                self._auto.speichere_jetzt(self)
            else:
                self._auto.melde_gespeichert()
        else:
            original = self._bearbeitete_original
            index = next(
                (i for i, r in enumerate(bestellung.rechnungen) if r is original), -1
            )
            if index < 0:
                return
            rechnung.summen = berechne_summen(
                rechnung.positionen, rechnung.reverse_charge, rechnung.steuersatz
            )
            bestellung.rechnungen[index] = rechnung  # bearbeitete Kopie ersetzt das Original
            self._auto.speichere_jetzt(self)
        # In beiden Fällen die bestätigte Rechnung im Ändern-Modus weiterführen.
        self._bearbeitete_original = rechnung
        self._fuelle_liste()
        self._waehle_in_liste(rechnung)
        self._maske.zeige(rechnung, bestellung, ist_neu=False)

    def _auf_verworfen(self) -> None:
        if not self._maske.ist_neu and self._bearbeitete_original is not None:
            # Änderung verwerfen: bestehende Rechnung neu (aus dem Original) laden.
            self._maske.zeige(self._bearbeitete_original, self._aktuelle_bestellung(), ist_neu=False)
        else:
            self._bearbeitete_original = None
            self._hebe_auswahl_auf()
            self._maske.zeige(None, None, ist_neu=True)

    def _hebe_auswahl_auf(self) -> None:
        self._programmatisch = True
        try:
            self._liste.auswahl_aufheben()
        finally:
            self._programmatisch = False

    # --- Löschen (S-0027) ---------------------------------------------------

    def _loeschen(self) -> None:
        """Hartes Löschen der markierten Rechnung nach Sicherheitsabfrage (S-0027)."""
        rechnung = self._markierte_rechnung()
        bestellung = self._aktuelle_bestellung()
        if rechnung is None or bestellung is None:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("rechnungen.bitte_auswaehlen"),
            )
            return
        zusatz = ""
        if rechnung.status is RechnungsStatus.ERZEUGT:
            zusatz = "\n\n" + ui_text("rechnungen.loeschen_zusatz_erzeugt")
        antwort = QMessageBox.question(
            self,
            ui_text("rechnungen.loeschen_titel"),
            ui_text("rechnungen.loeschen_frage", nummer=rechnung.rechnungsnummer) + zusatz,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if antwort != QMessageBox.Yes:
            return
        bestellung.rechnungen.remove(rechnung)
        self._auto.speichere_jetzt(self)
        self._bearbeitete_original = None
        self._fuelle_liste()
        self._maske.zeige(None, None, ist_neu=True)

    # --- Rechnung erstellen (F-0006) ---------------------------------------

    def _frage_ueberschreiben(self, pfad: Path) -> bool:
        antwort = QMessageBox.question(
            self,
            ui_text("rechnungen.ueberschreiben_titel"),
            ui_text("rechnungen.ueberschreiben_text", name=pfad.name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return antwort == QMessageBox.Yes

    def _rechnung_erstellen(self) -> None:
        bestellung = self._aktuelle_bestellung()
        rechnung = self._markierte_rechnung()
        if bestellung is None or rechnung is None:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("rechnungen.bitte_auswaehlen"),
            )
            return
        # AK5: offene Änderungen der in der Maske geladenen Rechnung erst festschreiben; die
        # Erstellung arbeitet immer auf dem gespeicherten Stand.
        if self._bearbeitete_original is rechnung and self._maske.geaendert:
            if not self._maske.versuche_speichern():
                return  # Pflichtfehler oder abgelehnte Warnung: Erstellung abbrechen
            rechnung = self._markierte_rechnung()
            if rechnung is None:
                return
        dialog = FormatDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        # AK2: Pflichtprüfung vor der Ausgabe; fehlende Pflichtangaben verhindern die Erzeugung.
        befunde = pruefe_rechnung_fuer_ausgabe(rechnung)
        if befunde:
            self._zeige_pflicht_meldung(befunde)
            return
        # AK3: Schalter-Hinweis bei inaktiver XRechnung (Erzeugung nach Bestätigung möglich).
        if not rechnung.verkaeufer.xrechnung_aktiv and not self._bestaetige_schalter_hinweis():
            return
        # Ohne gepflegtes Ausgabe-Verzeichnis zuerst eines festlegen (S-0057 AK1).
        verzeichnis = self._sichere_ausgabe_verzeichnis()
        if verzeichnis is None:
            return
        ergebnis = erstelle_ausgaben(
            rechnung,
            bestellung.bestellnummer,
            bestellung.waehrung,
            dialog.formate(),
            ausgabe_verzeichnis=verzeichnis,
            ueberschreiben=self._frage_ueberschreiben,
        )
        if ergebnis.pflicht_befunde:  # defensiv: die Vorprüfung sollte das bereits abfangen
            self._zeige_pflicht_meldung(ergebnis.pflicht_befunde)
            return
        if ergebnis.fehler:
            QMessageBox.warning(
                self,
                ui_text("rechnungen.erstellung_fehler_titel"),
                befund_text(ergebnis.fehler),
            )
            return
        if not ergebnis.erzeugte_dateien:
            QMessageBox.information(
                self,
                ui_text("rechnungen.abgebrochen_titel"),
                ui_text("rechnungen.abgebrochen_text"),
            )
            return
        # Status und Zeitstempel der Erstellung automatisch speichern (bei Schreibfehler
        # mit Wiederholen-Dialog), dann Liste auffrischen und die Rechnung wieder markieren.
        self._auto.speichere_jetzt(self)
        self._fuelle_liste()
        self._waehle_in_liste(rechnung)
        # Auch die Maske zeigt den Ausgabestand (S-0032 AK4). `_waehle_in_liste` lädt sie
        # bewusst nicht neu, sonst ginge ein offener Bearbeitungsstand verloren; hier ist
        # nichts offen (oben gespeichert), und ohne diesen Aufruf stünde in der Maske
        # weiterhin „Entwurf".
        self._maske.zeige(rechnung, bestellung, ist_neu=False)
        self._bearbeitete_original = rechnung
        orte = "\n".join(str(p) for p in ergebnis.erzeugte_dateien)
        QMessageBox.information(
            self,
            ui_text("rechnungen.erstellt_titel"),
            ui_text("rechnungen.erstellt_text", orte=orte),
        )

    def _sichere_ausgabe_verzeichnis(self) -> str | None:
        """Das Ausgabe-Verzeichnis der Einstellungen; schlägt beim ersten Mal eines vor.

        Ist keines gepflegt, wird `<Dokumente>/<Standardordner>` angeboten (Startort wie
        beim Anlegen einer Firma-Datei, S-0073). Der Anwender übernimmt den Vorschlag,
        wählt einen anderen Ordner oder bricht ab; bei Übernahme wird das Verzeichnis
        gespeichert, sodass die Frage nur einmal kommt (S-0057 AK1). Rückgabe ist das
        Verzeichnis oder `None` bei Abbruch.
        """
        einstellungen = self._datenbestand.einstellungen
        if einstellungen.ausgabe_verzeichnis.strip():
            return einstellungen.ausgabe_verzeichnis.strip()

        dokumente = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        vorschlag = str(Path(dokumente or ".") / _STANDARD_AUSGABE_ORDNER)
        antwort = QMessageBox.question(
            self,
            ui_text("rechnungen.ausgabe_festlegen_titel"),
            ui_text("rechnungen.ausgabe_festlegen_text", vorschlag=vorschlag),
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if antwort == QMessageBox.Cancel:
            return None
        if antwort == QMessageBox.Yes:
            gewaehlt = vorschlag
        else:
            gewaehlt = QFileDialog.getExistingDirectory(
                self, ui_text("einstellungen.ordner_dialog_titel"), dokumente or ""
            )
            if not gewaehlt:
                return None

        einstellungen.ausgabe_verzeichnis = gewaehlt
        self._auto.speichere_jetzt(self)
        return gewaehlt

    def _zeige_pflicht_meldung(self, befunde: list[Befund]) -> None:
        """Zeigt fehlende Pflichtangaben als verständliche Liste ohne Technik-Auszug (S-0047 AK2)."""
        texte = "\n".join(f"• {befund_text(b)}" for b in befunde)
        QMessageBox.warning(
            self,
            ui_text("rechnungen.unvollstaendig_titel"),
            ui_text("rechnungen.unvollstaendig_text", befunde=texte),
        )

    def _bestaetige_schalter_hinweis(self) -> bool:
        """Weist auf die inaktive XRechnung hin; True, wenn trotzdem erstellt werden soll (S-0047 AK3)."""
        antwort = QMessageBox.question(
            self,
            ui_text("rechnungen.schalter_hinweis_titel"),
            ui_text("rechnungen.schalter_hinweis_text"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return antwort == QMessageBox.Yes
