"""Prüfbefund der Fachlogik: Feldbezug plus Katalog-Schlüssel statt fertigem Text (S-0061).

Die `pruefe_*`-Funktionen liefern ihre Meldungen als `Befund`. Der Befund nennt das
betroffene Feld und den Schlüssel des Textes, nicht den Text selbst; aufgelöst wird er erst
dort, wo er angezeigt wird (`ui.sprache.befund_text`). So bleibt `services` UI-frei und
kennt die eingestellte Sprache nicht: Dieselbe Prüfung bedient eine deutsche und eine
spanische Oberfläche, ohne etwas von beiden zu wissen.

Werte gehören als Platzhalter in `werte` und werden nie in den Schlüssel hineinformatiert.
Ein vorformatiertes „Position 3: …" bände die Satzstellung an die deutsche Grammatik; als
Platzhalter kann jede Sprachdatei die Stellung selbst wählen.
"""

from __future__ import annotations

from typing import NamedTuple


class Befund(NamedTuple):
    """Ein Prüfbefund: betroffenes Feld, Katalog-Schlüssel und Platzhalter-Werte.

    `feld` deckt sich mit dem Feldschlüssel der Maske (``"name"``, ``"bank"``, ``"positionen"``
    ...), damit die Oberfläche den Hinweis feld-nah darstellen kann. Meldungen ohne
    Feldbezug (die Warnungen aus `warne_rechnung`, die Erzeugungsfehler in
    `services.erstellung`) tragen ``""``; sie erscheinen im Dialog, nicht am Feld.

    `werte` wird ausschließlich gelesen (`str.format`), nie mutiert; das geteilte
    Vorgabe-Wörterbuch ist deshalb unkritisch.
    """

    feld: str
    schluessel: str
    werte: dict[str, object] = {}
