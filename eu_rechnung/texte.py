"""Sprachkatalog: feste Texte je Sprache aus pflegbaren Sprachdateien (S-0061).

Zentrale Quelle aller festen Texte des Programms. Oberfläche und Ausgabe nutzen dieselbe
Mechanik, aber getrennte Sprachen: die Oberfläche die UI-Sprache aus den Einstellungen
(S-0059), der PDF-Sichtteil die aufgelöste Rechnungssprache der jeweiligen Rechnung
(S-0060). Die Sprache wird deshalb immer explizit übergeben und nie aus globalem Zustand
gezogen; nur so lässt sich aus einer deutschen Oberfläche heraus eine englische Rechnung
erzeugen.

Bewusst kein Qt-`tr()` mit `.ts`-Dateien (Architekturentscheidung 3E-0031): Erstens stünden
die deutschen Texte dann als `tr("Rechnungsnummer")` fest im Code, was S-0061 AK2
ausschließt. Zweitens ist ein `QTranslator` prozessweit installiert und kennt nur eine
Sprache, während der Sichtteil (ReportLab, kein Qt) dieselben Texte in einer anderen Sprache
braucht als die gerade laufende Oberfläche.

Die Sprachdateien liegen als flache JSON-Wörterbücher unter `ressourcen/sprachen/`. Sie
sind das Arbeitsmaterial des DoD-Kriteriums D5 und bewusst ohne Werkzeugkette pflegbar
(kein `lupdate`/`lrelease`-Schritt, kein Binärformat).
"""

from __future__ import annotations

import functools
import importlib.resources
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

#: Die fünf unterstützten Sprachen (F-0016). Reihenfolge ist zugleich die Anzeigereihenfolge.
SPRACHEN: tuple[str, ...] = ("de", "en", "it", "fr", "es")

#: Rückfall, wenn eine Übersetzung fehlt oder die Sprache unbekannt ist (S-0061 AK3).
RUECKFALL: str = "de"

#: Sprachname in der jeweils eigenen Sprache. Bewusst nicht übersetzt: Ein Anwender muss
#: seine Sprache auch dann finden, wenn die Oberfläche gerade in einer steht, die er nicht
#: liest.
SPRACH_NAMEN: dict[str, str] = {
    "de": "Deutsch",
    "en": "English",
    "it": "Italiano",
    "fr": "Français",
    "es": "Español",
}


@functools.lru_cache(maxsize=len(SPRACHEN))
def katalog(sprache: str) -> dict[str, str]:
    """Die Sprachdatei einer Sprache als Wörterbuch; zwischengespeichert.

    Die Dateien ändern sich zur Laufzeit nicht, deshalb wird jede nur einmal gelesen
    (dasselbe Muster wie beim ICC-Profil in `export/pdf_sicht.py`).
    """
    roh = (
        importlib.resources.files("eu_rechnung")
        .joinpath("ressourcen", "sprachen", f"{sprache}.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(roh)


def normierte_sprache(sprache: str | None) -> str:
    """Eine unterstützte Sprache; unbekannte oder fehlende Werte ergeben Deutsch.

    Die Sprache stammt aus gespeicherten Daten (Einstellungen, Rechnung) und kann in einer
    von Hand verfremdeten Datei jeden Wert tragen. Ein harter Fehler wäre hier
    unverhältnismäßig: Ein unbekannter Wert darf die Anwendung nicht daran hindern, zu
    starten oder eine Rechnung zu erzeugen.
    """
    if sprache is None:
        return RUECKFALL
    kurz = sprache.strip().lower()[:2]
    return kurz if kurz in SPRACHEN else RUECKFALL


def text(schluessel: str, sprache: str, **platzhalter: object) -> str:
    """Den Text zu einem Schlüssel in der gewünschten Sprache, mit deutschem Rückfall.

    Fehlt der Schlüssel in der Zielsprache, wird der deutsche Text geliefert und die
    Oberfläche bleibt funktionsfähig (S-0061 AK3). Fehlt er auch dort, ist das ein
    Programmierfehler und kein Datenproblem: Dann wirft die Funktion, damit ein vergessener
    Eintrag in der Entwicklung auffällt statt beim Anwender.

    Platzhalter werden über `str.format` eingesetzt. Werte werden immer als Platzhalter
    übergeben und nie in den Text hineinformatiert, damit die Satzstellung je Sprache frei
    bleibt.
    """
    ziel = normierte_sprache(sprache)
    wert = katalog(ziel).get(schluessel)
    if wert is None:
        wert = katalog(RUECKFALL).get(schluessel)
    if wert is None:
        raise KeyError(f"Unbekannter Text-Schlüssel: {schluessel!r}")
    return wert.format(**platzhalter) if platzhalter else wert


# --- Sprachgebundene Texte und Formate ---------------------------------------

# Rundungseinheit Cent (BR-CO-17), konsistent zu services.berechne_summen.
_CENT = Decimal("0.01")

# Platzhalter beim Trennerwechsel: ein Zeichen, das in formatierten Zahlen nie vorkommt.
_MARKE = "\x00"


class Sprachkontext:
    """Texte und Zahlenformate einer Sprache, gebündelt.

    Bündelt, was sonst als Sprach-Parameter durch jede Layout- und Ausgabefunktion zu
    reichen wäre. Die Formatmuster (Trennzeichen, Datumsmuster) stehen wie die Texte in den
    Sprachdateien und nicht im Code: Sie sind Teil dessen, was je Sprache gepflegt wird, und
    unterscheiden sich real (deutsch `1.234,56`, englisch `1,234.56`, französisch `1 234,56`).

    Verwender sind der PDF-Sichtteil und die ZUGFeRD-Metadaten mit der Rechnungssprache
    (S-0060); die Oberfläche nutzt denselben Kontext mit der UI-Sprache (S-0059).
    """

    def __init__(self, sprache: str) -> None:
        self.sprache = normierte_sprache(sprache)
        #: Trennzeichen der Sprache. Öffentlich, weil nicht nur die Ausgabe sie braucht:
        #: Die Betrags-Eingabe der Oberfläche muss ihre eigene Anzeige zurücklesen können
        #: (`ui.betrag.parse_betrag`).
        self.tausendertrenner = text("format.tausendertrenner", self.sprache)
        self.dezimaltrenner = text("format.dezimaltrenner", self.sprache)
        self._datumsmuster = text("format.datum", self.sprache)

    def t(self, schluessel: str, **platzhalter: object) -> str:
        """Fester Text aus der Sprachdatei."""
        return text(schluessel, self.sprache, **platzhalter)

    def _trenner(self, englisch: str) -> str:
        """Setzt in einer englisch formatierten Zahl die Trenner der Zielsprache ein.

        Der Umweg über eine Marke ist nötig, weil sich Tausender- und Dezimaltrenner je
        nach Sprache gegenseitig ersetzen (deutsch `.`/`,` gegen englisch `,`/`.`).
        """
        return (
            englisch.replace(",", _MARKE)
            .replace(".", self.dezimaltrenner)
            .replace(_MARKE, self.tausendertrenner)
        )

    def geld(self, betrag: Decimal) -> str:
        """Geldbetrag in der Zielsprache: 12345.6 -> '12.345,60' bzw. '12,345.60'."""
        return self._trenner(f"{betrag:,.2f}")

    def menge(self, menge: Decimal) -> str:
        """Menge in der Zielsprache, ganzzahlig ohne Nachkommastellen."""
        ganz, _, frac = f"{menge:.2f}".partition(".")
        if frac == "00":
            return ganz
        return f"{ganz}{self.dezimaltrenner}{frac.rstrip('0')}"

    def prozent(self, satz: Decimal) -> str:
        """Prozentsatz mit zwei Nachkommastellen: 2 -> '2,00' bzw. '2.00'."""
        gerundet = f"{satz.quantize(_CENT, rounding=ROUND_HALF_UP):f}"
        return gerundet.replace(".", self.dezimaltrenner)

    def datum(self, d: date) -> str:
        """Datum im Muster der Zielsprache."""
        return d.strftime(self._datumsmuster)

    def land(self, code: str) -> str:
        """Ausgeschriebener Ländername; Rückfall ist der ISO-Code selbst."""
        try:
            return self.t(f"land.{code}")
        except KeyError:
            return code  # Land ohne Eintrag: der Code ist die ehrlichste Anzeige
