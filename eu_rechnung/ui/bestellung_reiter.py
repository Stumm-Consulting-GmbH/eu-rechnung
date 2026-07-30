"""Bestellung-Reiter: globale Liste und eingebettete Detailmaske zur Bestellungs-Pflege (S-0018).

Master-Detail im selben Reiter, einheitlich zum Firma-/Artikel-/Kunden-Muster: links die
globale Bestellungs-Liste über alle Kunden (`ObjektListe` mit Filter/Sortier und
„inaktive anzeigen"), rechts die scrollbare Detailmaske. Die Bestellung hängt strukturell
am Kunden (`kunde.bestellungen`); beim Anlegen wird der Kunde gewählt und die Bestellung
dort eingehängt, beim Ändern ist er fest. Die Maske trägt die Kopffelder (Bestellnummer,
Währung, Beginn/Ende über das programmweite Datums-Widget, Zahlungsfrist,
Zahlungsbedingung, optionales Skonto über den geteilten `SkontoFelderMixin`,
optionaler Gesamt-Höchstbetrag, aktiv), die Unterliste der gültigen
Artikel (Popup-Erfassung mit Einzelpreis-Vorbelegung und optionaler Obergrenze), die
individuellen Felder als Fünf-Plätze-Baustein und den Anschreibentext. Wo eine Obergrenze gesetzt ist,
zeigt die Maske den verbrauchten Anteil und den Rest (Berechnung `services.bestellung`,
mit F-0005 lebendig). Validierungshinweise erscheinen am betroffenen Feld; geprüft wird ein
Kandidat, das echte Objekt wird erst nach bestandener Prüfung geschrieben. Jede bestätigte
Operation speichert automatisch. Das Löschen und die Auflisten-Feinheiten folgen in 4T-0085.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.domain import (
    Bestellung,
    Datenbestand,
    GueltigerArtikel,
    Kunde,
    ObergrenzeArt,
)
from eu_rechnung.services import (
    effektive_rechnungssprache,
    effektive_waehrung,
    effektiver_anschreibentext,
    pruefe_bestellung,
    verbrauch_artikel,
    verbrauch_gesamt,
)
from eu_rechnung.texte import SPRACH_NAMEN, SPRACHEN
from eu_rechnung.ui.anschreiben_feld import AnschreibenFeld
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.betrag import format_betrag, parse_betrag
from eu_rechnung.ui.datums_feld import DatumsFeld
from eu_rechnung.ui.aenderung import AenderungsKnopfMixin
from eu_rechnung.ui.feld_fehler import FeldFehlerMixin
from eu_rechnung.ui.gueltiger_artikel_dialog import GueltigerArtikelDialog
from eu_rechnung.ui.individuelle_felder_feld import IndividuelleFelderFeld
from eu_rechnung.ui.liste import ObjektListe, Spalte
from eu_rechnung.ui.skonto_felder import SkontoFelderMixin
from eu_rechnung.ui.sprache import befund_text, ui_text
from eu_rechnung.ui.vererbungs_auswahl import VererbungsAuswahl


class _BestellZeile:
    """Verbindet eine Bestellung mit ihrem Eltern-Kunden für die globale Liste.

    Die Bestellung hängt strukturell am Kunden (`kunde.bestellungen`) und trägt selbst
    keinen Kunde-Bezug. Für die entitätsunabhängige `ObjektListe` bündelt dieser Wrapper
    beide und reicht das `aktiv`-Flag der Bestellung durch, sodass der aktiv-Filter greift.
    """

    def __init__(self, kunde: Kunde, bestellung: Bestellung) -> None:
        self.kunde = kunde
        self.bestellung = bestellung

    @property
    def aktiv(self) -> bool:
        return self.bestellung.aktiv


class BestellungReiter(FeldFehlerMixin, SkontoFelderMixin, AenderungsKnopfMixin, QWidget):
    """Reiter mit globaler Bestellungs-Liste und eingebetteter Anlege-/Änderungsmaske."""

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
        self._aktuelle: Bestellung | None = None  # bearbeitet; None = Anlegen
        self._aktueller_kunde: Kunde | None = None  # Eltern-Kunde beim Ändern
        self._geaendert = False
        self._lade_laeuft = False
        self._fehler: dict[str, QLabel] = {}
        self._gueltige_artikel: list[GueltigerArtikel] = []
        self._baue_ui()
        self._fuelle_liste()
        self._neue_bestellung()

    # --- Aufbau -------------------------------------------------------------

    def _baue_ui(self) -> None:
        layout = QHBoxLayout(self)

        links = QVBoxLayout()
        self._liste = ObjektListe(
            [
                Spalte(ui_text("bestellung.feld_kunde"), lambda z: z.kunde.name),
                Spalte(
                    ui_text("bestellung.feld_bestellnummer"),
                    lambda z: z.bestellung.bestellnummer,
                ),
                Spalte(
                    ui_text("bestellung.spalte_zeitraum"),
                    lambda z: self._zeitraum_text(z.bestellung),
                    sortierwert=lambda z: z.bestellung.beginn_datum,
                ),
                Spalte(
                    ui_text("allgemein.feld_waehrung"), lambda z: z.bestellung.waehrung
                ),
                Spalte(
                    ui_text("allgemein.spalte_aktiv"),
                    lambda z: ui_text(
                        "allgemein.ja" if z.bestellung.aktiv else "allgemein.nein"
                    ),
                ),
            ],
            aktiv_attribut="aktiv",
            standard_sortierspalte=0,  # alphabetisch nach Kunde (S-0022)
        )
        self._liste.auswahl_geaendert.connect(self._auf_auswahl)
        links.addWidget(self._liste, 1)

        knoepfe = QHBoxLayout()
        neu = QPushButton(ui_text("bestellung.knopf_neu"))
        neu.clicked.connect(self._neue_bestellung)
        loeschen = QPushButton(ui_text("allgemein.knopf_loeschen"))
        loeschen.clicked.connect(self._loeschen)
        knoepfe.addWidget(neu)
        knoepfe.addWidget(loeschen)
        knoepfe.addStretch(1)
        links.addLayout(knoepfe)
        layout.addLayout(links, 3)

        bereich = QScrollArea()
        bereich.setWidgetResizable(True)
        bereich.setWidget(self._baue_maske())
        layout.addWidget(bereich, 2)

    def _baue_maske(self) -> QWidget:
        container = QWidget()
        aussen = QVBoxLayout(container)
        aussen.addWidget(self._baue_kopf_gruppe())
        aussen.addWidget(self._baue_gueltige_gruppe())
        self._felder = IndividuelleFelderFeld()
        self._felder.geaendert.connect(self._markiere_geaendert)
        aussen.addWidget(self._felder)
        self._anschreiben = AnschreibenFeld()
        self._anschreiben.geaendert.connect(self._markiere_geaendert)
        aussen.addWidget(self._anschreiben)

        leiste = QHBoxLayout()
        leiste.addStretch(1)
        verwerfen = QPushButton(ui_text("allgemein.knopf_verwerfen"))
        verwerfen.clicked.connect(self._verwerfen)
        self._bestaetigen_knopf = QPushButton(ui_text("allgemein.knopf_bestaetigen"))
        self._bestaetigen_knopf.setDefault(True)
        self._bestaetigen_knopf.clicked.connect(self._bestaetigen)
        leiste.addWidget(verwerfen)
        leiste.addWidget(self._bestaetigen_knopf)
        aussen.addLayout(leiste)
        return container

    def _baue_kopf_gruppe(self) -> QGroupBox:
        box = QGroupBox(ui_text("bestellung.gruppe"))
        form = QFormLayout(box)

        self._kunde_combo = QComboBox()
        self._kunde_combo.currentIndexChanged.connect(self._markiere_geaendert)
        self._kunde_combo.currentIndexChanged.connect(self._aktualisiere_anschreiben_vererbung)
        self._kunde_combo.currentIndexChanged.connect(self._aktualisiere_sprach_vererbung)
        self._kunde_combo.currentIndexChanged.connect(self._aktualisiere_waehrung_vorbelegung)
        form.addRow(ui_text("bestellung.feld_kunde"), self._kunde_combo)
        form.addRow(self._fehler_label("kunde"))

        self._bestellnummer = QLineEdit()
        self._bestellnummer.textChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("bestellung.feld_bestellnummer"), self._bestellnummer)
        form.addRow(self._fehler_label("bestellnummer"))

        # Die Belegwährung ist ein eigener Pflichtwert der Bestellung, kein Erb-Feld: Sie
        # wird aus der Kaskade nur vorbelegt und ist danach der feste Wert des Belegs
        # (S-0017, S-0063). Deshalb hier eine schlichte Auswahl statt VererbungsAuswahl.
        self._waehrung = QComboBox()
        self._waehrung.setEditable(True)
        self._waehrung.currentTextChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("allgemein.feld_waehrung"), self._waehrung)
        form.addRow(self._fehler_label("waehrung"))

        # Die Rechnungssprache erbt dagegen vom Kunden (S-0082 AK2).
        self._sprache = VererbungsAuswahl()
        self._sprache.geaendert.connect(self._markiere_geaendert)
        form.addRow(ui_text("allgemein.feld_rechnungssprache"), self._sprache)

        self._beginn = DatumsFeld()
        self._beginn.dateChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("bestellung.feld_beginn"), self._beginn)
        self._ende = DatumsFeld()
        self._ende.dateChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("bestellung.feld_ende"), self._ende)
        form.addRow(self._fehler_label("ende"))

        self._zahlungsfrist = QSpinBox()
        self._zahlungsfrist.setRange(0, 3650)
        self._zahlungsfrist.setSuffix(" " + ui_text("skonto.einheit_tage"))
        self._zahlungsfrist.valueChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("bestellung.feld_zahlungsfrist"), self._zahlungsfrist)
        form.addRow(self._fehler_label("zahlungsfrist"))

        self._zahlungsbedingung = QLineEdit()
        self._zahlungsbedingung.textChanged.connect(self._markiere_geaendert)
        form.addRow(ui_text("bestellung.feld_zahlungsbedingung"), self._zahlungsbedingung)
        form.addRow(self._fehler_label("zahlungsbedingung"))

        # Vertraglich vereinbartes Skonto; die Rechnung übernimmt es beim Anlegen (S-0080).
        form.addRow(
            ui_text("bestellung.feld_skonto"),
            self._baue_skonto_zeile(self._markiere_geaendert),
        )
        form.addRow(self._fehler_label("skonto_tage"))
        form.addRow(self._fehler_label("skonto_prozent"))

        self._gesamt = QLineEdit()
        self._gesamt.setPlaceholderText(ui_text("bestellung.gesamt_platzhalter"))
        self._gesamt.textChanged.connect(self._markiere_geaendert)
        self._gesamt.textChanged.connect(self._aktualisiere_gesamt_rest)
        form.addRow(ui_text("bestellung.feld_gesamt_hoechstbetrag"), self._gesamt)
        form.addRow(self._fehler_label("gesamt_hoechstbetrag"))
        self._gesamt_rest = QLabel("")
        self._gesamt_rest.setVisible(False)
        form.addRow("", self._gesamt_rest)

        self._aktiv = QCheckBox(ui_text("allgemein.aktiv"))
        self._aktiv.toggled.connect(self._markiere_geaendert)
        form.addRow("", self._aktiv)
        return box

    def _baue_gueltige_gruppe(self) -> QGroupBox:
        box = QGroupBox(ui_text("bestellung.gruppe_gueltige_artikel"))
        layout = QVBoxLayout(box)
        self._gueltige_tabelle = QTableWidget(0, 5)
        self._gueltige_tabelle.setHorizontalHeaderLabels(
            [
                ui_text("gueltiger_artikel.feld_artikel"),
                ui_text("gueltiger_artikel.feld_einzelpreis"),
                ui_text("bestellung.spalte_obergrenze"),
                ui_text("bestellung.spalte_verbraucht"),
                ui_text("bestellung.spalte_rest"),
            ]
        )
        self._gueltige_tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._gueltige_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._gueltige_tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._gueltige_tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self._gueltige_tabelle)
        layout.addWidget(self._fehler_label("gueltige_artikel"))

        leiste = QHBoxLayout()
        hinzu = QPushButton(ui_text("allgemein.knopf_hinzufuegen"))
        hinzu.clicked.connect(self._gueltigen_hinzufuegen)
        aendern = QPushButton(ui_text("allgemein.knopf_aendern"))
        aendern.clicked.connect(self._gueltigen_aendern)
        entf = QPushButton(ui_text("allgemein.knopf_entfernen"))
        entf.clicked.connect(self._gueltigen_entfernen)
        leiste.addWidget(hinzu)
        leiste.addWidget(aendern)
        leiste.addWidget(entf)
        leiste.addStretch(1)
        layout.addLayout(leiste)
        return box

    # --- Hilfen -------------------------------------------------------------

    @staticmethod
    def _zeitraum_text(bestellung: Bestellung) -> str:
        return f"{bestellung.beginn_datum:%d.%m.%Y}–{bestellung.ende_datum:%d.%m.%Y}"

    def _artikel_name(self, artikel_id: str) -> str:
        artikel = next((a for a in self._datenbestand.artikel if a.id == artikel_id), None)
        return artikel.artikelname if artikel is not None else "(unbekannt)"

    def _aktive_artikel(self) -> list:
        return [a for a in self._datenbestand.artikel if a.aktiv]

    def _fuelle_kunden_combo(self, aktueller: Kunde | None) -> None:
        """Füllt die Kunden-Auswahl mit aktiven Kunden; beim Ändern fest auf den Eltern-Kunden."""
        self._kunde_combo.clear()
        kunden = [k for k in self._datenbestand.kunden if k.aktiv]
        if aktueller is not None and aktueller not in kunden:
            kunden = [aktueller] + kunden  # inaktiver Eltern-Kunde bleibt sichtbar
        for kunde in kunden:
            self._kunde_combo.addItem(f"{kunde.kundennummer} — {kunde.name}", kunde)
        if aktueller is not None:
            index = self._kunde_combo.findData(aktueller)
            if index >= 0:
                self._kunde_combo.setCurrentIndex(index)
        self._kunde_combo.setEnabled(aktueller is None)  # fest beim Ändern

    def _fuelle_waehrungen(self, aktuell: str | None) -> None:
        """Füllt die Währungs-Auswahl; beim Ändern auf den festen Belegwert, beim Anlegen vor.

        `aktuell` ist der gespeicherte Belegwert der Bestellung (Ändern) und bleibt maßgeblich.
        Beim Anlegen (`aktuell is None`) belegt die Kaskade Kunde → Standardwährung vor (S-0063).
        """
        einst = self._datenbestand.einstellungen
        self._waehrung.clear()
        self._waehrung.addItems(einst.waehrungsliste)
        self._waehrung.setCurrentText(aktuell or self._vorbelegte_waehrung())

    def _vorbelegte_waehrung(self) -> str:
        """Die für die neue Bestellung vorzubelegende Währung aus der Kaskade (S-0063).

        Wie `_geerbte_sprache`, aber mit Wurzelwert: Ein Kunde vererbt seine Währung, sonst
        greift die Standardwährung (`services.waehrung`). Gelesen wird der in der Auswahl
        stehende Kunde, denn `_aktueller_kunde` ist beim Anlegen noch nicht gesetzt.
        """
        kunde = self._kunde_combo.currentData()
        return effektive_waehrung(
            self._datenbestand.einstellungen,
            kunde=kunde if isinstance(kunde, Kunde) else None,
        )

    def _aktualisiere_waehrung_vorbelegung(self, *args) -> None:
        """Zieht die Währungs-Vorbelegung nach, wenn der Anwender beim Anlegen den Kunden wechselt.

        Nur im Anlege-Modus: Beim Ändern ist die Belegwährung der feste, eigene Wert der
        Bestellung (S-0017) und darf einem Kundenwechsel nicht folgen (dort ist der Kunde
        ohnehin fest). Sie überschreibt dabei eine zuvor gewählte Währung bewusst, weil die
        Vorbelegung dem gewählten Kunden folgt.
        """
        if self._lade_laeuft or self._aktuelle is not None:
            return
        self._waehrung.setCurrentText(self._vorbelegte_waehrung())

    def _geerbter_anschreiben(self) -> tuple[str, str]:
        """Der für die Bestellung geerbte Anschreibentext und seine Herkunft (S-0036).

        Die Herkunft ist ein Katalog-Schlüssel, kein fertiger Text; übersetzt wird sie
        erst im Anschreiben-Baustein.
        """
        kunde = self._kunde_combo.currentData()
        einst = self._datenbestand.einstellungen
        if isinstance(kunde, Kunde):
            text = effektiver_anschreibentext(einst, kunde=kunde)
            herkunft = (
                "allgemein.herkunft_kunde"
                if kunde.anschreibentext is not None
                else "allgemein.herkunft_standard"
            )
        else:
            text = einst.standard_anschreibentext
            herkunft = "allgemein.herkunft_standard"
        return text, herkunft

    def _aktualisiere_anschreiben_vererbung(self, *args) -> None:
        """Frischt die geerbte Vorschau auf, wenn der Anwender den Kunden wechselt."""
        if self._lade_laeuft:
            return
        text, herkunft = self._geerbter_anschreiben()
        self._anschreiben.aktualisiere_vererbung(geerbt_text=text, herkunft=herkunft)

    def _geerbte_sprache(self) -> tuple[str, str]:
        """Die für die Bestellung geerbte Rechnungssprache und ihre Herkunft (S-0082).

        Wie `_geerbter_anschreiben`, aber ohne Wurzelwert in den Einstellungen: Die
        Sprach-Kaskade fällt fest auf Deutsch zurück, weil dort die UI-Sprache steht und ein
        Wechsel der Arbeitssprache die Belege nicht verändern darf (`services.sprache`).
        """
        kunde = self._kunde_combo.currentData()
        if isinstance(kunde, Kunde):
            return (
                effektive_rechnungssprache(kunde=kunde),
                "allgemein.herkunft_kunde"
                if kunde.rechnungssprache is not None
                else "allgemein.herkunft_rueckfall",
            )
        return effektive_rechnungssprache(), "allgemein.herkunft_rueckfall"

    def _aktualisiere_sprach_vererbung(self, *args) -> None:
        """Frischt die geerbte Sprache auf, wenn der Anwender den Kunden wechselt."""
        if self._lade_laeuft:
            return
        code, herkunft = self._geerbte_sprache()
        self._sprache.aktualisiere_vererbung(
            geerbt_anzeige=SPRACH_NAMEN[code], herkunft=herkunft
        )

    # --- Liste --------------------------------------------------------------

    def _fuelle_liste(self) -> None:
        zeilen = [
            _BestellZeile(kunde, bestellung)
            for kunde in self._datenbestand.kunden
            for bestellung in kunde.bestellungen
        ]
        self._liste.setze_objekte(zeilen)

    def _auf_auswahl(self, zeile: object) -> None:
        if isinstance(zeile, _BestellZeile):
            self._lade_in_maske(zeile)

    # --- Laden und Zurückschreiben ------------------------------------------

    def _lade_in_maske(self, zeile: _BestellZeile | None) -> None:
        """Zeigt eine Bestellung (Ändern) oder leert die Maske (Anlegen)."""
        self._lade_laeuft = True
        if zeile is None:
            self._aktuelle = None
            self._aktueller_kunde = None
            heute = date.today()
            self._fuelle_kunden_combo(None)
            self._bestellnummer.setText("")
            self._fuelle_waehrungen(None)
            self._beginn.setze_datum(heute)
            self._ende.setze_datum(heute)
            self._zahlungsfrist.setValue(0)
            self._zahlungsbedingung.setText("")
            self._setze_skonto(None)
            self._gesamt.setText("")
            self._aktiv.setChecked(True)
            self._gueltige_artikel = []
        else:
            b = zeile.bestellung
            self._aktuelle = b
            self._aktueller_kunde = zeile.kunde
            self._fuelle_kunden_combo(zeile.kunde)
            self._bestellnummer.setText(b.bestellnummer)
            self._fuelle_waehrungen(b.waehrung)
            self._beginn.setze_datum(b.beginn_datum)
            self._ende.setze_datum(b.ende_datum)
            self._zahlungsfrist.setValue(b.zahlungsfrist)
            self._zahlungsbedingung.setText(b.zahlungsbedingung)
            self._setze_skonto(b.skonto)
            self._gesamt.setText(
                "" if b.gesamt_hoechstbetrag is None else format_betrag(b.gesamt_hoechstbetrag)
            )
            self._aktiv.setChecked(b.aktiv)
            self._gueltige_artikel = [
                GueltigerArtikel(g.artikel_id, g.einzelpreis, g.obergrenze)
                for g in b.gueltige_artikel
            ]
        self._felder.setze_felder(
            self._aktuelle.individuelle_felder if self._aktuelle is not None else []
        )
        text, herkunft = self._geerbter_anschreiben()
        self._anschreiben.setze_wert(
            self._aktuelle.anschreibentext if self._aktuelle is not None else None,
            geerbt_text=text,
            herkunft=herkunft,
        )
        code, sprach_herkunft = self._geerbte_sprache()
        self._sprache.setze_optionen([(k, SPRACH_NAMEN[k]) for k in SPRACHEN])
        self._sprache.setze_wert(
            self._aktuelle.rechnungssprache if self._aktuelle is not None else None,
            geerbt_anzeige=SPRACH_NAMEN[code],
            herkunft=sprach_herkunft,
        )
        self._fuelle_gueltige_tabelle()
        self._aktualisiere_gesamt_rest()
        self._loesche_fehler()
        self._lade_laeuft = False
        self._setze_geaendert(False)

    def _neue_bestellung(self) -> None:
        self._lade_in_maske(None)

    def _verwerfen(self) -> None:
        if self._aktuelle is None:
            self._lade_in_maske(None)
        else:
            self._lade_in_maske(_BestellZeile(self._aktueller_kunde, self._aktuelle))

    # --- Unterlisten-Tabellen -----------------------------------------------

    def _fuelle_gueltige_tabelle(self) -> None:
        self._gueltige_tabelle.setRowCount(0)
        for g in self._gueltige_artikel:
            zeile = self._gueltige_tabelle.rowCount()
            self._gueltige_tabelle.insertRow(zeile)
            if g.obergrenze is not None:
                art_text = ui_text(
                    "gueltiger_artikel.art_menge"
                    if g.obergrenze.art is ObergrenzeArt.MENGE
                    else "gueltiger_artikel.art_betrag"
                )
                grenze = f"{art_text}: {format_betrag(g.obergrenze.wert)}"
                verbraucht = (
                    verbrauch_artikel(self._aktuelle, g.artikel_id, g.obergrenze.art)
                    if self._aktuelle is not None
                    else Decimal("0")
                )
                verbraucht_text = format_betrag(verbraucht)
                rest_text = format_betrag(g.obergrenze.wert - verbraucht)
            else:
                grenze = verbraucht_text = rest_text = "–"
            werte = [
                self._artikel_name(g.artikel_id),
                format_betrag(g.einzelpreis),
                grenze,
                verbraucht_text,
                rest_text,
            ]
            for spalte, text in enumerate(werte):
                self._gueltige_tabelle.setItem(zeile, spalte, QTableWidgetItem(text))

    def _aktualisiere_gesamt_rest(self) -> None:
        """Zeigt Verbrauch und Rest zum Gesamt-Höchstbetrag, sobald einer gesetzt ist (AK6)."""
        betrag = parse_betrag(self._gesamt.text())
        if betrag is None:
            self._gesamt_rest.setText("")
            self._gesamt_rest.setVisible(False)
            return
        verbraucht = (
            verbrauch_gesamt(self._aktuelle) if self._aktuelle is not None else Decimal("0")
        )
        self._gesamt_rest.setText(
            ui_text(
                "bestellung.gesamt_rest_anzeige",
                verbraucht=format_betrag(verbraucht),
                rest=format_betrag(betrag - verbraucht),
            )
        )
        self._gesamt_rest.setVisible(True)

    # --- Gültige-Artikel-Aktionen -------------------------------------------

    def _markierte_gueltige(self) -> int:
        zeile = self._gueltige_tabelle.currentRow()
        return zeile if 0 <= zeile < len(self._gueltige_artikel) else -1

    def _gueltigen_hinzufuegen(self) -> None:
        aktive = self._aktive_artikel()
        if not aktive:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("rechnung.keine_aktiven_artikel"),
            )
            return
        dialog = GueltigerArtikelDialog(
            aktive, self._waehrung.currentText().strip(), parent=self
        )
        if dialog.exec() == QDialog.Accepted:
            self._gueltige_artikel.append(dialog.gueltiger_artikel())
            self._fuelle_gueltige_tabelle()
            self._markiere_geaendert()

    def _gueltigen_aendern(self) -> None:
        zeile = self._markierte_gueltige()
        if zeile < 0:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("bestellung.gueltiger_bitte_auswaehlen"),
            )
            return
        dialog = GueltigerArtikelDialog(
            self._aktive_artikel(),
            self._waehrung.currentText().strip(),
            self._gueltige_artikel[zeile],
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            self._gueltige_artikel[zeile] = dialog.gueltiger_artikel()
            self._fuelle_gueltige_tabelle()
            self._markiere_geaendert()

    def _gueltigen_entfernen(self) -> None:
        zeile = self._markierte_gueltige()
        if zeile < 0:
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("bestellung.gueltiger_bitte_auswaehlen"),
            )
            return
        del self._gueltige_artikel[zeile]
        self._fuelle_gueltige_tabelle()
        self._markiere_geaendert()

    # --- Kandidat und Bestätigen --------------------------------------------

    def _leere_bestellung(self) -> Bestellung:
        """Baut eine leere Bestellung als Prüf-Kandidat (vor der Übernahme ins echte Objekt)."""
        heute = date.today()
        return Bestellung(
            id="",
            bestellnummer="",
            beginn_datum=heute,
            ende_datum=heute,
            zahlungsfrist=0,
            zahlungsbedingung="",
        )

    def _uebernehme_in_bestellung(self, b: Bestellung) -> None:
        """Schreibt die Maske-Eingaben in das übergebene Bestellungs-Objekt."""
        b.bestellnummer = self._bestellnummer.text().strip()
        b.waehrung = self._waehrung.currentText().strip()
        b.beginn_datum = self._beginn.datum()
        b.ende_datum = self._ende.datum()
        b.zahlungsfrist = self._zahlungsfrist.value()
        b.zahlungsbedingung = self._zahlungsbedingung.text().strip()
        b.skonto, _ = self._lese_skonto()  # Eingabe-Befunde fängt `_bestaetigen` vorab ab
        b.gesamt_hoechstbetrag = parse_betrag(self._gesamt.text())
        b.aktiv = self._aktiv.isChecked()
        b.gueltige_artikel = list(self._gueltige_artikel)
        b.individuelle_felder = self._felder.felder()
        b.anschreibentext = self._anschreiben.wert()
        b.rechnungssprache = self._sprache.wert()  # None = erbt

    def _bestaetigen(self) -> None:
        self._loesche_fehler()
        if self._aktuelle is None:
            kunde = self._kunde_combo.currentData()
            if not isinstance(kunde, Kunde):
                self._zeige_feld_fehler("kunde", ui_text("bestellung.bitte_kunde_waehlen"))
                return
        else:
            kunde = self._aktueller_kunde

        # Eingabe-Ebene vor der Übernahme: Ein halb gefülltes Skonto liesse sich nicht ins
        # Wertobjekt übernehmen und ginge still verloren (S-0080).
        _, eingabe_befunde = self._lese_skonto()
        if eingabe_befunde:
            for feld, text in eingabe_befunde:
                self._zeige_feld_fehler(feld, text)
            return

        kandidat = self._leere_bestellung()
        self._uebernehme_in_bestellung(kandidat)
        befunde = pruefe_bestellung(kandidat)
        if befunde:
            for befund in befunde:
                self._zeige_feld_fehler(befund.feld, befund_text(befund))
            return

        if self._aktuelle is None:
            kandidat.id = str(uuid.uuid4())
            kunde.bestellungen.append(kandidat)
            self._auto.speichere_jetzt(self)
            self._fuelle_liste()
            self._lade_in_maske(_BestellZeile(kunde, kandidat))  # in den Ändern-Modus
            return

        self._uebernehme_in_bestellung(self._aktuelle)
        if self._auto.speichere_jetzt(self):
            self._setze_geaendert(False)
        self._fuelle_liste()

    def _loeschen(self) -> None:
        """Hartes Löschen nur bei einer Bestellung ohne Rechnungen und nach Rückfrage (S-0021)."""
        zeile = self._liste.aktuelles_objekt()
        if not isinstance(zeile, _BestellZeile):
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("bestellung.bitte_auswaehlen"),
            )
            return
        bestellung = zeile.bestellung
        if bestellung.rechnungen:
            QMessageBox.information(
                self,
                ui_text("bestellung.loeschen_gesperrt_titel"),
                ui_text("bestellung.loeschen_gesperrt_text"),
            )
            return
        antwort = QMessageBox.question(
            self,
            ui_text("bestellung.loeschen_titel"),
            ui_text(
                "bestellung.loeschen_frage",
                nummer=bestellung.bestellnummer,
                kunde=zeile.kunde.name,
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if antwort != QMessageBox.Yes:
            return
        zeile.kunde.bestellungen.remove(bestellung)
        self._auto.speichere_jetzt(self)
        self._fuelle_liste()
        self._neue_bestellung()
