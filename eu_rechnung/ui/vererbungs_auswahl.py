"""Auswahlfeld für Werte einer Vererbungskaskade (4T-0132, 4T-0137).

Wiederverwendbarer Baustein für die Felder, deren Wert entweder geerbt oder eigen ist: die
Währung am Kunden (S-0062) und die Rechnungssprache an Kunde, Bestellung und Rechnung
(S-0082). Der Ebenen-Wert ist `None` (erbt) oder der eigene Wert.

**Warum eine Auswahl und kein Schalter samt Feld**, wie ihn `AnschreibenFeld` für denselben
Zweck zeigt: Ein Textfeld kann nicht zwischen „leer" und „erbt" unterscheiden und braucht
den Schalter deshalb. Eine Auswahl trägt ihren Zustand selbst; der erste Eintrag lautet
„erbt (Deutsch)" und nennt den geerbten Wert gleich mit. Ein zweites Bedienelement für
dieselbe Aussage wäre Zeremonie.

Die Herkunft steht darunter als dezenter Hinweis („Erbt von: Kunde"), sichtbar nur, solange
geerbt wird. Sie ist optional: Wo es nur eine mögliche Quelle gibt (die Währung erbt allein
von der Standardwährung), wäre die Zeile Rauschen.

Die Beschriftungen entstehen erst beim Setzen der Werte und nicht beim Import, sonst fröre
die Sprache auf Deutsch ein (`test_ui_uebersetzung.py` fängt den Fall).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from eu_rechnung.ui.sprache import ui_text


class VererbungsAuswahl(QWidget):
    """Auswahl mit „erbt"-Eintrag und optionaler Herkunfts-Anzeige.

    Ohne `erbt_moeglich` entfällt der Erb-Eintrag: Die Rechnung trägt ihre Sprache als
    eigenen, beim Anlegen aufgelösten Wert und erbt nicht (S-0082 AK4).
    """

    #: Meldet eine Änderung durch den Anwender an den umgebenden Reiter.
    geaendert = Signal()

    def __init__(self, *, erbt_moeglich: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._erbt_moeglich = erbt_moeglich
        self._lade_laeuft = False
        self._optionen: list[tuple[str, str]] = []  # (wert, anzeige)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.setSpacing(2)
        self._auswahl = QComboBox()
        self._auswahl.currentIndexChanged.connect(self._auf_wechsel)
        aussen.addWidget(self._auswahl)
        self._hinweis = QLabel("")
        self._hinweis.setEnabled(False)  # dezent, als erläuternder Hinweis erkennbar
        self._hinweis.setVisible(False)
        aussen.addWidget(self._hinweis)

    def _auf_wechsel(self, *args) -> None:
        if self._lade_laeuft:
            return
        self._aktualisiere_hinweis()
        self.geaendert.emit()

    def setze_optionen(self, optionen: list[tuple[str, str]]) -> None:
        """Die wählbaren Werte als (wert, anzeige); zu rufen vor `setze_wert`."""
        self._optionen = list(optionen)

    def setze_wert(
        self,
        wert: str | None,
        *,
        geerbt_anzeige: str = "",
        herkunft: str | None = None,
    ) -> None:
        """Lädt den Ebenen-Wert (None = erbt) samt geerbter Vorschau und ihrer Herkunft.

        `geerbt_anzeige` ist der fertige Anzeigetext des geerbten Werts (etwa „Deutsch"),
        `herkunft` ein Katalog-Schlüssel (`allgemein.herkunft_*`) und kein fertiger Text:
        Sonst käme die Herkunft in der Sprache des aufrufenden Reiters herein und bliebe
        beim Sprachwechsel stehen. Ohne `herkunft` entfällt die Hinweiszeile.

        Ein Wert außerhalb der Optionen erscheint zusätzlich am Ende: Ein gespeicherter
        Stand darf beim Öffnen der Maske nicht still auf „erbt" fallen und beim nächsten
        Bestätigen verloren gehen.
        """
        self._lade_laeuft = True
        self._herkunft = herkunft
        self._auswahl.clear()
        if self._erbt_moeglich:
            self._auswahl.addItem(ui_text("allgemein.erbt_wert", wert=geerbt_anzeige), None)
        for opt_wert, anzeige in self._optionen:
            self._auswahl.addItem(anzeige, opt_wert)
        if wert is not None and self._auswahl.findData(wert) < 0:
            self._auswahl.addItem(wert, wert)  # unbekannter Bestandswert, sichtbar halten
        index = self._auswahl.findData(wert)
        self._auswahl.setCurrentIndex(index if index >= 0 else 0)
        self._aktualisiere_hinweis()
        self._lade_laeuft = False

    def aktualisiere_vererbung(
        self, *, geerbt_anzeige: str, herkunft: str | None = None
    ) -> None:
        """Frischt die geerbte Vorschau auf, ohne die getroffene Wahl zu verwerfen.

        Nötig, wenn sich die höhere Ebene unter der Maske ändert: In der Bestellungs-Maske
        wechselt der Anwender den Kunden, und mit ihm die geerbte Sprache.
        """
        self._lade_laeuft = True
        self._herkunft = herkunft
        if self._erbt_moeglich:
            self._auswahl.setItemText(
                0, ui_text("allgemein.erbt_wert", wert=geerbt_anzeige)
            )
        self._aktualisiere_hinweis()
        self._lade_laeuft = False

    def _aktualisiere_hinweis(self) -> None:
        """Die Herkunft gilt nur beim Erben; ein eigener Wert stammt von nirgends."""
        erbt = self._auswahl.currentData() is None and self._erbt_moeglich
        zeigen = erbt and self._herkunft is not None
        if zeigen:
            self._hinweis.setText(
                ui_text("allgemein.erbt_von", herkunft=ui_text(self._herkunft))
            )
        self._hinweis.setVisible(zeigen)

    def wert(self) -> str | None:
        """Der Ebenen-Wert: `None`, wenn geerbt wird, sonst der gewählte Wert."""
        return self._auswahl.currentData()
