"""Skonto-Erfassungsfelder als gemeinsamer UI-Baustein (S-0051, S-0080).

Kapselt die beiden Felder (Tage, Prozent), ihr Füllen und ihr Einlesen samt der Regel
„beide oder keines" für die Masken, die eine Skonto-Angabe erfassen: die Rechnung und die
Bestellung, in der das Skonto vertraglich vereinbart wird. Das Muster ist in 4T-0116 an der
Rechnungsmaske entstanden und hier zusammengeführt (4T-0119), damit beide Masken dieselbe
Bedienung und dieselben Meldungen tragen, analog zu `feld_fehler` und `betrag`.

Nutzung: die Maske erbt `SkontoFelderMixin` vor der Qt-Basis, baut die Zeile über
`self._baue_skonto_zeile(self._markiere_geaendert)` ins Formular, legt darunter die
Fehler-Labels `skonto_tage` und `skonto_prozent` an (`FeldFehlerMixin`), füllt die Felder
über `_setze_skonto` und liest sie beim Bestätigen über `_lese_skonto`. Das Einlesen gehört
vor die Übernahme: Meldet es Befunde, darf nichts übernommen werden, sonst ginge ein halb
gefülltes Skonto still verloren.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from eu_rechnung.domain import Skonto
from eu_rechnung.texte import Sprachkontext
from eu_rechnung.ui.betrag import parse_betrag
from eu_rechnung.ui.sprache import ui_sprache, ui_text

# Breite der beiden schmalen Zahlenfelder.
_FELD_BREITE = 60


def parse_ganzzahl(text: str) -> int | None:
    """Parst eine ganze Zahl; None bei leerer oder ungültiger Eingabe.

    Bewusst strikt statt über `parse_betrag`: „14,5" soll als Skonto-Tage einen Fehler
    ergeben, nicht still zu 14 werden.
    """
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _prozent_text(wert: Decimal) -> str:
    """Prozentsatz für das Erfassungsfeld, ohne unnötige Nullen: 2.00 -> '2', 2.50 -> '2,5'.

    Der Dezimaltrenner folgt der UI-Sprache, damit `parse_betrag` die eigene Anzeige
    zurücklesen kann (englisch '2.5' statt '2,5').
    """
    trenner = Sprachkontext(ui_sprache()).dezimaltrenner
    return format(wert.normalize(), "f").replace(".", trenner)


class SkontoFelderMixin:
    """Zwei Erfassungsfelder für die optionale Skonto-Angabe (Tage, Prozent).

    Erwartet von der erbenden Maske die Fehler-Labels `skonto_tage` und `skonto_prozent`
    (über `FeldFehlerMixin`). Der Baustein bringt keine eigene Qt-Basis und keinen
    Konstruktor mit, damit er sich als Mixin mit `QWidget` verträgt.
    """

    _skonto_tage: QLineEdit
    _skonto_prozent: QLineEdit

    def _baue_skonto_zeile(self, bei_aenderung: Callable[[], None]) -> QWidget:
        """Erzeugt die Felder und liefert die Zeile `[Tage] Tage [Prozent] %` als Widget.

        `bei_aenderung` wird an beide Felder gehängt und meldet der Maske die Änderung.
        """
        self._skonto_tage = QLineEdit()
        self._skonto_tage.setMaximumWidth(_FELD_BREITE)
        self._skonto_tage.textChanged.connect(bei_aenderung)
        self._skonto_prozent = QLineEdit()
        self._skonto_prozent.setMaximumWidth(_FELD_BREITE)
        self._skonto_prozent.textChanged.connect(bei_aenderung)

        zeile = QHBoxLayout()
        zeile.addWidget(self._skonto_tage)
        zeile.addWidget(QLabel(ui_text("skonto.einheit_tage")))
        zeile.addWidget(self._skonto_prozent)
        zeile.addWidget(QLabel("%"))
        zeile.addStretch(1)
        widget = QWidget()
        widget.setLayout(zeile)
        return widget

    def _setze_skonto(self, skonto: Skonto | None) -> None:
        """Füllt die Felder aus einer Skonto-Angabe; ohne Angabe bleiben beide leer."""
        self._skonto_tage.setText(str(skonto.tage) if skonto else "")
        self._skonto_prozent.setText(_prozent_text(skonto.prozent) if skonto else "")

    def _lese_skonto(self) -> tuple[Skonto | None, list[tuple[str, str]]]:
        """Liest die Felder als `(Skonto oder None, Eingabe-Befunde)`.

        Prüft, was nur die Maske sehen kann: „beide oder keines" und die Eingabe-Form. Das
        Wertobjekt `Skonto` bildet den Zustand „nur ein Wert gefüllt" nicht ab, deshalb
        erreicht er die Service-Prüfung nie; der Wertebereich dagegen bleibt dort
        (`pruefe_rechnung`, `pruefe_bestellung`). Bei Befunden ist der erste Rückgabewert
        `None`.
        """
        tage_text = self._skonto_tage.text().strip()
        prozent_text = self._skonto_prozent.text().strip()
        if not tage_text and not prozent_text:
            return None, []  # kein Skonto

        befunde: list[tuple[str, str]] = []
        tage = parse_ganzzahl(tage_text)
        prozent = parse_betrag(prozent_text)
        if not tage_text:
            befunde.append(("skonto_tage", ui_text("skonto.fehlt_tage")))
        elif tage is None:
            befunde.append(("skonto_tage", ui_text("skonto.fehler_tage")))
        if not prozent_text:
            befunde.append(("skonto_prozent", ui_text("skonto.fehlt_prozent")))
        elif prozent is None:
            befunde.append(("skonto_prozent", ui_text("skonto.fehler_prozent")))
        if befunde:
            return None, befunde
        return Skonto(tage=tage, prozent=prozent), []
