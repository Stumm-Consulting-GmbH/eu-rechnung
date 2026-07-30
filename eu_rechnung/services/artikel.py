"""Artikel-Validierung und Referenzprüfung (UI-frei) für die Artikel-Pflege.

Trägt die semantische Prüfung eines Artikels (Pflichtfelder, Namens-Eindeutigkeit,
nicht-negativer Preis; S-0007/S-0008) und die Referenzprüfung für das harte Löschen
(S-0009). Wie bei der Firma prüft die Oberfläche über `pruefe_artikel` vor dem Speichern
und zeigt die Befunde am betroffenen Feld an; das Einhängen und Persistieren übernimmt die
Maske über das automatische Speichern.

Die Befunde tragen je einen Feldschlüssel (``"name"``, ``"betrag"``, ``"waehrung"``),
damit die Maske den Hinweis feld-nah darstellen kann. Die Betrags-Formatprüfung
(Dezimaleingabe) liegt in der Maske, weil sie das Parsen der Eingabe betrifft.
"""

from __future__ import annotations

from eu_rechnung.domain import Artikel, Datenbestand
from eu_rechnung.services.befund import Befund


def _name_schluessel(name: str) -> str:
    """Vergleichsform des Artikelnamens: getrimmt und ohne Groß-/Kleinschreibung (S-0007)."""
    return name.strip().casefold()


def pruefe_artikel(
    artikel: Artikel,
    datenbestand: Datenbestand,
    *,
    ignoriere_id: str | None = None,
) -> list[Befund]:
    """Prüft einen Artikel feldweise. Leere Liste bedeutet gültig.

    Jeder Befund trägt den Feldschlüssel ``"name"``, ``"betrag"`` oder ``"waehrung"`` und
    den Katalog-Schlüssel seines Textes. Der Namensvergleich für die Eindeutigkeit erfolgt
    ohne Groß-/Kleinschreibung und getrimmt; ``ignoriere_id`` nimmt beim Ändern den
    Artikel selbst von der Dubletten-Prüfung aus (S-0008).
    """
    befunde: list[Befund] = []

    name = artikel.artikelname.strip()
    if not name:
        befunde.append(Befund("name", "artikel.fehlt_name"))
    else:
        schluessel = _name_schluessel(name)
        for anderer in datenbestand.artikel:
            if anderer.id == ignoriere_id:
                continue
            if _name_schluessel(anderer.artikelname) == schluessel:
                befunde.append(Befund("name", "artikel.name_doppelt"))
                break

    if artikel.vorschlagspreis.betrag < 0:
        befunde.append(Befund("betrag", "artikel.preis_negativ"))

    waehrung = artikel.vorschlagspreis.waehrung.strip()
    if not waehrung:
        befunde.append(Befund("waehrung", "allgemein.fehlt_waehrung"))
    elif waehrung not in datenbestand.einstellungen.waehrungsliste:
        # Die Währung stammt aus der Währungstabelle (S-0005 AK4). Die Maske bietet nur
        # deren Einträge an; erreichbar ist der Fall über eine fremd bearbeitete Datei,
        # denn `waehrung_referenziert` verhindert das Löschen einer benutzten Währung.
        befunde.append(Befund("waehrung", "artikel.waehrung_nicht_in_liste", {"code": waehrung}))

    return befunde


def artikel_referenziert(datenbestand: Datenbestand, artikel_id: str) -> bool:
    """True, wenn der Artikel in mindestens einer Bestellung als gültiger Artikel hängt.

    Grundlage für das harte Löschen (S-0009): referenzierte Artikel dürfen nicht
    entfernt, sondern nur deaktiviert werden. Ausgegebene Rechnungen sind kein Hindernis,
    da ihre Positionen Bezeichnung und Preis kopiert haben.
    """
    for kunde in datenbestand.kunden:
        for bestellung in kunde.bestellungen:
            for gueltiger in bestellung.gueltige_artikel:
                if gueltiger.artikel_id == artikel_id:
                    return True
    return False
