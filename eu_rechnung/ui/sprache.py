"""Aktive Sprache der Bedienoberfläche als Prozess-Zustand (S-0059).

Die Oberfläche zieht ihre Texte aus demselben Katalog wie die Ausgabe
(`eu_rechnung.texte`), aber in einer anderen Sprache: der UI-Sprache aus den
Einstellungen statt der Rechnungssprache des jeweiligen Belegs. Weil jedes Widget diese
Sprache braucht, hält sie dieses Modul einmal je Prozess, statt sie durch jede Maske,
jeden Dialog und jedes Feld zu reichen.

**Warum der globale Zustand hier liegt und nicht in `texte.py`.** Der Katalog bekommt seine
Sprache bewusst immer explizit; nur so kann er aus einer deutschen Oberfläche heraus eine
englische Rechnung setzen. Dieses Modul ist die Ausnahme für genau einen Verwender, die
Oberfläche, und lebt deshalb in der UI-Schicht. `export` und `services` greifen nicht
darauf zu.

**Wann die Sprache gesetzt wird.** Einmal beim Anwendungsstart (`app.main`) aus der
Startfirma. Ein Firma-Wechsel zur Laufzeit zieht sie bewusst **nicht** nach: Die Reiter
sind dann bereits gebaut und würden mitten in der Sitzung teils in der alten, teils in der
neuen Sprache stehen. Eine geänderte Sprache greift beim nächsten Start (S-0059 AK2, das
verlangt „spätestens nach einem Neustart").
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from eu_rechnung.texte import RUECKFALL, Sprachkontext, normierte_sprache, text

if TYPE_CHECKING:  # nur für die Typangabe; zur Laufzeit kennt dieses Modul services nicht
    from eu_rechnung.services.befund import Befund

# Aktive UI-Sprache des Prozesses. Vor dem ersten Setzen (und in Tests, die den Start nicht
# durchlaufen) gilt Deutsch, wie im Leerzustand ohne Firma.
_aktive_sprache: str = RUECKFALL


def setze_ui_sprache(sprache: str | None) -> str:
    """Setzt die aktive UI-Sprache und gibt den tatsächlich gesetzten Wert zurück.

    Unbekannte Werte werden auf Deutsch normiert (`normierte_sprache`), damit ein von Hand
    verfremdeter Eintrag in der Firma-Datei die Oberfläche nicht unbenutzbar macht.
    """
    global _aktive_sprache
    _aktive_sprache = normierte_sprache(sprache)
    return _aktive_sprache


def ui_sprache() -> str:
    """Die aktive UI-Sprache."""
    return _aktive_sprache


def ui_text(schluessel: str, **platzhalter: object) -> str:
    """Ein Oberflächen-Text in der aktiven UI-Sprache.

    Die Kurzform, die alle Masken nutzen, statt jedes Mal `text(…, ui_sprache())` zu
    schreiben. Rückfall auf Deutsch bei fehlender Übersetzung regelt der Katalog
    (S-0061 AK3).
    """
    return text(schluessel, _aktive_sprache, **platzhalter)


def ui_kontext() -> Sprachkontext:
    """Sprachkontext der aktiven UI-Sprache, für Zahlen- und Datumsformate der Masken."""
    return Sprachkontext(_aktive_sprache)


def befund_text(befund: Befund) -> str:
    """Der Text eines Prüfbefunds in der aktiven UI-Sprache.

    Die Gegenstelle zu `services.befund.Befund`: Die Fachlogik nennt Schlüssel und Werte,
    hier werden sie zum Satz. Damit bleibt die Auflösung an der einzigen Stelle, die die
    eingestellte Sprache kennt, und die Prüfung selbst bleibt UI-frei.

    Zahlwerte werden dabei in der UI-Sprache dargestellt (4T-0160): Ein `Decimal` käme sonst
    als „1200.00" in den Satz, während die Maske daneben „1.200,00" zeigt. Die Fachlogik
    nennt den Wert, die Darstellung kennt nur die Oberfläche.
    """
    kontext = ui_kontext()
    werte = {
        schluessel: kontext.geld(wert) if isinstance(wert, Decimal) else wert
        for schluessel, wert in befund.werte.items()
    }
    return ui_text(befund.schluessel, **werte)
