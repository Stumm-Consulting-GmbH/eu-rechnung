"""Kunde-Reiter: Liste und eingebettete Detailmaske zur Kunden-Pflege (S-0012 bis S-0016).

Master-Detail wie der Artikel-Reiter, aber mit einer gegliederten Maske nach dem
Firma-Muster: links die Kunden-Liste (`ObjektListe` mit Filter/Sortier über Kundennummer,
Name und Ort, „inaktive anzeigen"), rechts die Detailmaske in den Gruppen Kunde, Adresse
sowie Kontakt und Steuer. Die Pflicht-Markierung spiegelt den dokumentweiten Schalter
`xrechnung_aktiv` der eigenen Firma (kein eigener Schalter in dieser Maske) und die
bedingte USt-ID-Pflicht bei Reverse-Charge; sie wird beim Laden und beim Umschalten von
Reverse-Charge aktualisiert. Anlegen und Ändern über dieselbe Maske; die Kundennummer wird
beim Anlegen aus dem Debitor-Zähler vorbelegt (Präfix D) und der Zähler bei Erfolg nur
fortgeschrieben, wenn die Vorbelegung unverändert übernommen wurde (S-0043 AK3). Validierungshinweise
erscheinen am betroffenen Feld; der Bestätigen-Knopf hebt offene Änderungen hervor (blau).
Hartes Löschen nur bei einem Kunden ohne Bestellungen und nach Sicherheitsabfrage, sonst
über das Deaktivieren.
"""

from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung.domain import Adresse, Datenbestand, Kunde
from eu_rechnung.services import (
    effektive_rechnungssprache,
    effektive_waehrung,
    effektiver_anschreibentext,
    pruefe_kunde,
)
from eu_rechnung.texte import SPRACH_NAMEN, SPRACHEN
from eu_rechnung.ui.anschreiben_feld import AnschreibenFeld
from eu_rechnung.ui.auto_speicher import AutoSpeicher
from eu_rechnung.ui.aenderung import AenderungsKnopfMixin
from eu_rechnung.ui.feld_fehler import FeldFehlerMixin
from eu_rechnung.ui.individuelle_felder_feld import IndividuelleFelderFeld
from eu_rechnung.ui.liste import ObjektListe, Spalte
from eu_rechnung.ui.sprache import befund_text, ui_text
from eu_rechnung.ui.vererbungs_auswahl import VererbungsAuswahl

# Feldgruppen der Maske: (Gruppen-Schlüssel, [(Feldname, Text-Schlüssel, Pflichtstufe), ...]).
# Pflichtstufe: "immer" (EN-Pflicht), "xr" (nur bei aktiver XRechnung), "rc" (nur bei
# gesetztem Reverse-Charge), "opt" (nie).
#
# Katalog-Schlüssel statt Texte: Ein `ui_text()` hier liefe beim Import, also vor dem
# Setzen der UI-Sprache, und fröre die Beschriftungen auf Deutsch ein (wie in
# `firma_reiter`). Aufgelöst wird erst im Aufbau.
_GRUPPEN = [
    (
        "kunde.gruppe_kunde",
        [
            ("kundennummer", "kunde.feld_kundennummer", "immer"),
            ("name", "allgemein.feld_name", "immer"),
            ("namenszusatz1", "firma.feld_namenszusatz1", "opt"),
            ("namenszusatz2", "firma.feld_namenszusatz2", "opt"),
        ],
    ),
    (
        "kunde.gruppe_adresse",
        [
            ("strasse", "firma.feld_strasse", "xr"),
            ("hausnummer", "firma.feld_hausnummer", "opt"),
            ("plz", "firma.feld_plz", "xr"),
            ("ort", "firma.feld_ort", "xr"),
            ("land", "firma.feld_land", "immer"),
        ],
    ),
    (
        "kunde.gruppe_kontakt_steuer",
        [
            ("email", "firma.feld_email", "xr"),
            ("umsatzsteuer_id", "kunde.feld_umsatzsteuer_id", "rc"),
        ],
    ),
]


class KundeReiter(FeldFehlerMixin, AenderungsKnopfMixin, QWidget):
    """Reiter mit Kunden-Liste und eingebetteter Anlege-/Änderungsmaske."""

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
        self._aktueller: Kunde | None = None  # in der Maske bearbeitet; None = Anlegen
        self._geaendert = False
        self._lade_laeuft = False
        self._edits: dict[str, QLineEdit] = {}
        # schlüssel -> (Label, Basistext, Pflichtstufe) für die Live-Markierung
        self._pflicht: dict[str, tuple[QLabel, str, str]] = {}
        self._fehler: dict[str, QLabel] = {}
        self._baue_ui()
        self._fuelle_liste()
        self._neuer_kunde()

    # --- Aufbau -------------------------------------------------------------

    def _baue_ui(self) -> None:
        layout = QHBoxLayout(self)

        links = QVBoxLayout()
        self._liste = ObjektListe(
            [
                Spalte(ui_text("kunde.feld_kundennummer"), lambda k: k.kundennummer),
                Spalte(ui_text("allgemein.feld_name"), lambda k: k.name),
                Spalte(ui_text("allgemein.feld_ort"), lambda k: k.adresse.ort),
                Spalte(
                    ui_text("allgemein.spalte_aktiv"),
                    lambda k: ui_text("allgemein.ja" if k.aktiv else "allgemein.nein"),
                ),
            ],
            aktiv_attribut="aktiv",
            standard_sortierspalte=1,  # alphabetisch nach Name (S-0016)
        )
        self._liste.auswahl_geaendert.connect(self._auf_auswahl)
        links.addWidget(self._liste, 1)

        knoepfe = QHBoxLayout()
        neu = QPushButton(ui_text("kunde.knopf_neu"))
        neu.clicked.connect(self._neuer_kunde)
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
        for gruppen_schluessel, felder in _GRUPPEN:
            aussen.addWidget(self._baue_gruppe(gruppen_schluessel, felder))

        aussen.addWidget(self._baue_vorgaben())

        self._felder = IndividuelleFelderFeld()
        self._felder.geaendert.connect(self._markiere_geaendert)
        aussen.addWidget(self._felder)

        self._anschreiben = AnschreibenFeld()
        self._anschreiben.geaendert.connect(self._markiere_geaendert)
        aussen.addWidget(self._anschreiben)

        schalter = QHBoxLayout()
        self._reverse_charge = QCheckBox(ui_text("kunde.schalter_reverse_charge"))
        self._reverse_charge.toggled.connect(self._aktualisiere_pflicht)
        self._reverse_charge.toggled.connect(self._markiere_geaendert)
        self._aktiv = QCheckBox(ui_text("allgemein.aktiv"))
        self._aktiv.toggled.connect(self._markiere_geaendert)
        schalter.addWidget(self._reverse_charge)
        schalter.addWidget(self._aktiv)
        schalter.addStretch(1)
        aussen.addLayout(schalter)
        aussen.addStretch(1)

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

    def _baue_vorgaben(self) -> QGroupBox:
        """Gruppe „Vorgaben für Belege": was der Kunde an Bestellung und Rechnung vererbt.

        Währung (S-0062 AK3) und Rechnungssprache (S-0082 AK1) teilen sich denselben
        Baustein und damit dieselbe Bedienung. Die Währung erbt allein von der
        Standardwährung, deshalb bleibt ihre Herkunfts-Zeile weg; die Sprache nennt sie,
        weil ihr Rückfall keine Ebene ist, die der Anwender irgendwo sähe.
        """
        box = QGroupBox(ui_text("kunde.gruppe_vorgaben"))
        form = QFormLayout(box)
        self._waehrung = VererbungsAuswahl()
        self._waehrung.geaendert.connect(self._markiere_geaendert)
        form.addRow(ui_text("kunde.feld_waehrung"), self._waehrung)
        self._sprache = VererbungsAuswahl()
        self._sprache.geaendert.connect(self._markiere_geaendert)
        form.addRow(ui_text("allgemein.feld_rechnungssprache"), self._sprache)
        return box

    def _fuelle_vorgaben(self, kunde: Kunde | None) -> None:
        """Füllt Währungs- und Sprach-Auswahl und stellt sie auf die Werte des Kunden."""
        einstellungen = self._datenbestand.einstellungen
        self._waehrung.setze_optionen([(c, c) for c in einstellungen.waehrungsliste])
        # Der Kunde ist die oberste Währungs-Ebene: Er erbt allein von der Standardwährung,
        # die `services.waehrung` ohne Kunde liefert (einheitlich zu Anschreiben und Sprache).
        self._waehrung.setze_wert(
            kunde.waehrung if kunde is not None else None,
            geerbt_anzeige=effektive_waehrung(einstellungen),
        )
        self._sprache.setze_optionen([(k, SPRACH_NAMEN[k]) for k in SPRACHEN])
        # Der Kunde ist die oberste Sprach-Ebene: Er erbt allein vom Rückfall Deutsch, den
        # `services.sprache` fest setzt (die UI-Sprache darf hier nicht einfließen, sonst
        # veränderte ein Wechsel der Arbeitssprache die Belege).
        self._sprache.setze_wert(
            kunde.rechnungssprache if kunde is not None else None,
            geerbt_anzeige=SPRACH_NAMEN[effektive_rechnungssprache()],
            herkunft="allgemein.herkunft_rueckfall",
        )

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

    # --- Pflicht-Markierung (spiegelt den Firma-Schalter) -------------------

    def _aktualisiere_pflicht(self) -> None:
        """Setzt die Pflicht-Sterne nach dem Firma-Schalter und Reverse-Charge (live)."""
        xr = self._datenbestand.eigene_firma.xrechnung_aktiv
        rc = self._reverse_charge.isChecked()
        for label, basis, stufe in self._pflicht.values():
            pflicht = (
                stufe == "immer"
                or (stufe == "xr" and xr)
                or (stufe == "rc" and rc)
            )
            label.setText(f"{basis} *" if pflicht else basis)

    # --- Liste --------------------------------------------------------------

    def _fuelle_liste(self) -> None:
        self._liste.setze_objekte(self._datenbestand.kunden)

    def _auf_auswahl(self, kunde: object) -> None:
        if isinstance(kunde, Kunde):
            self._lade_in_maske(kunde)

    # --- Laden und Zurückschreiben ------------------------------------------

    def _vorbelegte_kundennummer(self) -> str:
        """Kundennummer-Vorbelegung aus dem Debitor-Zähler (Präfix D, S-0043)."""
        return f"D{self._datenbestand.einstellungen.naechste_debitornummer}"

    def _lade_in_maske(self, kunde: Kunde | None) -> None:
        """Zeigt einen Kunden (Ändern) oder leert die Maske mit vorbelegter Nummer (Anlegen)."""
        self._lade_laeuft = True
        self._aktueller = kunde
        if kunde is None:
            nummer = self._vorbelegte_kundennummer()
            werte = {schluessel: "" for schluessel in self._edits}
            werte["kundennummer"] = nummer
            self._reverse_charge.setChecked(False)
            self._aktiv.setChecked(True)
        else:
            zusatz = list(kunde.namenszusatz) + ["", ""]
            werte = {
                "kundennummer": kunde.kundennummer,
                "name": kunde.name,
                "namenszusatz1": zusatz[0],
                "namenszusatz2": zusatz[1],
                "strasse": kunde.adresse.strasse,
                "hausnummer": kunde.adresse.hausnummer,
                "plz": kunde.adresse.plz,
                "ort": kunde.adresse.ort,
                "land": kunde.adresse.land,
                "email": kunde.email,
                "umsatzsteuer_id": kunde.umsatzsteuer_id,
            }
            self._reverse_charge.setChecked(kunde.reverse_charge)
            self._aktiv.setChecked(kunde.aktiv)
        for schluessel, wert in werte.items():
            self._edits[schluessel].setText(wert)
        self._fuelle_vorgaben(kunde)
        self._felder.setze_felder(kunde.individuelle_felder if kunde is not None else [])
        # Der Kunde erbt allein vom globalen Standard (keine höhere Ebene dazwischen).
        geerbt = effektiver_anschreibentext(self._datenbestand.einstellungen)
        self._anschreiben.setze_wert(
            kunde.anschreibentext if kunde is not None else None,
            geerbt_text=geerbt,
            herkunft="allgemein.herkunft_standard",
        )
        self._aktualisiere_pflicht()
        self._loesche_fehler()
        self._lade_laeuft = False
        self._setze_geaendert(False)

    def _neuer_kunde(self) -> None:
        self._lade_in_maske(None)

    def _verwerfen(self) -> None:
        self._lade_in_maske(self._aktueller)

    def _leerer_kunde(self) -> Kunde:
        return Kunde(
            id="",
            kundennummer="",
            name="",
            adresse=Adresse(strasse="", plz="", ort="", land=""),
            email="",
            umsatzsteuer_id="",
            reverse_charge=False,
        )

    def _uebernehme_in_kunde(self, kunde: Kunde) -> None:
        """Schreibt die Maske-Eingaben in ein Kunde-Objekt (erfasste Felder)."""
        kunde.kundennummer = self._edits["kundennummer"].text().strip()
        kunde.name = self._edits["name"].text().strip()
        kunde.namenszusatz = [
            self._edits["namenszusatz1"].text().strip(),
            self._edits["namenszusatz2"].text().strip(),
        ]
        kunde.adresse.strasse = self._edits["strasse"].text().strip()
        kunde.adresse.hausnummer = self._edits["hausnummer"].text().strip()
        kunde.adresse.plz = self._edits["plz"].text().strip()
        kunde.adresse.ort = self._edits["ort"].text().strip()
        kunde.adresse.land = self._edits["land"].text().strip()
        kunde.email = self._edits["email"].text().strip()
        kunde.umsatzsteuer_id = self._edits["umsatzsteuer_id"].text().strip()
        kunde.reverse_charge = self._reverse_charge.isChecked()
        kunde.aktiv = self._aktiv.isChecked()
        kunde.waehrung = self._waehrung.wert()  # None = erbt
        kunde.rechnungssprache = self._sprache.wert()  # None = erbt
        kunde.individuelle_felder = self._felder.felder()
        kunde.anschreibentext = self._anschreiben.wert()

    # --- Aktionen -----------------------------------------------------------

    def _bestaetigen(self) -> None:
        self._loesche_fehler()
        kandidat = self._leerer_kunde()
        self._uebernehme_in_kunde(kandidat)
        ignoriere = self._aktueller.id if self._aktueller else None
        befunde = pruefe_kunde(kandidat, self._datenbestand, ignoriere_id=ignoriere)
        if befunde:
            for befund in befunde:
                self._zeige_feld_fehler(befund.feld, befund_text(befund))
            return

        if self._aktueller is None:
            kandidat.id = str(uuid.uuid4())
            self._datenbestand.kunden.append(kandidat)
            # Zähler nur fortschreiben, wenn die Vorbelegung unverändert übernommen wurde:
            # ein manuell vergebener Wert verbraucht keine automatische Nummer (S-0043 AK3).
            if kandidat.kundennummer == self._vorbelegte_kundennummer():
                self._datenbestand.einstellungen.naechste_debitornummer += 1
            self._aktueller = kandidat
        else:
            self._uebernehme_in_kunde(self._aktueller)

        if self._auto.speichere_jetzt(self):
            self._setze_geaendert(False)
        self._fuelle_liste()

    def _loeschen(self) -> None:
        kunde = self._liste.aktuelles_objekt()
        if not isinstance(kunde, Kunde):
            QMessageBox.information(
                self,
                ui_text("allgemein.hinweis_titel"),
                ui_text("kunde.bitte_auswaehlen"),
            )
            return
        if kunde.bestellungen:
            QMessageBox.information(
                self,
                ui_text("kunde.loeschen_gesperrt_titel"),
                ui_text("kunde.loeschen_gesperrt_text"),
            )
            return
        antwort = QMessageBox.question(
            self,
            ui_text("kunde.loeschen_titel"),
            ui_text("kunde.loeschen_frage", name=kunde.name, nummer=kunde.kundennummer),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if antwort != QMessageBox.Yes:
            return
        self._datenbestand.kunden.remove(kunde)
        self._auto.speichere_jetzt(self)
        self._fuelle_liste()
        self._neuer_kunde()
