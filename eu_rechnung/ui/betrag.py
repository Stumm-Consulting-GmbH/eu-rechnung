"""Geldbetrags-Formatierung und -Eingabe in der UI-Sprache (gemeinsamer UI-Baustein).

Kapselt die Umwandlung zwischen ``Decimal`` und der Anzeige für alle Masken mit
Betragsfeldern (Artikel-Vorschlagspreis, Bestellungs-Einzelpreise und -Obergrenzen,
Gesamt-Höchstbetrag, Steuersatz, Skonto). Das Muster ist in 4T-0082 entstanden und hier
zusammengeführt, damit die Betragsdarstellung über die Masken einheitlich ist.

**Sprache (S-0059).** Anzeige **und** Eingabe folgen der UI-Sprache. Beides muss
zusammenpassen: Läse eine englische Oberfläche `1,200.00` mit deutschen Trennregeln,
käme 1,2 heraus statt 1.200 (in 4T-0129 gemessen). Die Trennzeichen kommen aus dem
Sprachkontext, also aus den Sprachdateien.

Nicht zu verwechseln mit der Ausgabe-Formatierung des Sichtteils: Die folgt der
**Rechnungssprache** und nutzt `Sprachkontext.geld` direkt (S-0060).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from eu_rechnung.texte import Sprachkontext
from eu_rechnung.ui.sprache import ui_sprache


def format_betrag(betrag: Decimal, sprache: str | None = None) -> str:
    """Betragsdarstellung in der UI-Sprache: 1200 -> '1.200,00' bzw. '1,200.00'.

    Ohne `sprache` gilt die aktive UI-Sprache; der Parameter dient Tests und Aufrufern,
    die eine bestimmte Sprache brauchen.
    """
    return Sprachkontext(sprache or ui_sprache()).geld(betrag)


def parse_betrag(text: str, sprache: str | None = None) -> Decimal | None:
    """Liest eine Betragseingabe in der UI-Sprache; None bei leer oder ungültig.

    Kommt der Dezimaltrenner der Sprache vor, gilt das volle Format: Tausendertrenner
    werden entfernt, der Dezimaltrenner wird zum Punkt (deutsch `1.200,00`, englisch
    `1,200.00`, französisch `1 200,00`). Fehlt er, gilt eine einfache Eingabe wie `1200.00`
    oder `1200`; der Tausendertrenner wird nur dann entfernt, wenn er nicht selbst der
    Punkt ist. So bleibt die von `format_betrag` erzeugte Anzeige verlustfrei rücklesbar,
    und das bisherige deutsche Verhalten ändert sich nicht.
    """
    kontext = Sprachkontext(sprache or ui_sprache())
    text = text.strip()
    if not text:
        return None
    # Gewöhnliche Leerzeichen mit entfernen: Der französische Tausendertrenner ist ein
    # geschütztes Leerzeichen, das ein Anwender beim Tippen kaum trifft.
    text = text.replace(" ", "").replace(" ", "")
    if kontext.dezimaltrenner in text:
        text = text.replace(kontext.tausendertrenner, "").replace(kontext.dezimaltrenner, ".")
    elif kontext.tausendertrenner != ".":
        # Einfache Eingabe ohne Dezimaltrenner. Den Tausendertrenner zu entfernen ist nur
        # sicher, solange er nicht der Punkt ist: Aus deutschem „1200.00" würde sonst
        # 120000 statt 1200.
        text = text.replace(kontext.tausendertrenner, "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None
