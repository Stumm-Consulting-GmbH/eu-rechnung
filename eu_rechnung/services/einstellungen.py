"""Prüfung der globalen Einstellungen (UI-frei).

Der Pflicht-Standard-Anschreibentext (S-0035, Wurzelwert der Anschreiben-Vererbung), die
Währungsliste mit ihrer Standardwährung (S-0062) und die Nummernkreise (nächste Kundennummer
und die Jahres-Zähler der Rechnungsnummer, S-0044): zulässig sind nur positive ganze Zahlen,
die Jahres-Schlüssel müssen vierstellige Jahre sein.
Liefert `Befund`-Einträge für die feld-nahe Anzeige, analog `pruefe_firma`/`pruefe_artikel`.
Der Sammel-Schlüssel `rechnungsnummer` trägt die Jahres-Zähler-Befunde (Anzeige unter der
Jahres-Tabelle, analog `positionen`), `waehrungsliste` die der Währungstabelle.

Die Katalog-Schlüssel `einstellungen.fehler_debitor` und `einstellungen.fehler_zaehler`
teilt sich diese Prüfung mit der Eingabe-Prüfung der Maske (`ui.einstellungen_reiter`): Dort
fällt derselbe Befund an, wenn der Wert schon nicht als Zahl lesbar ist, hier, wenn er lesbar,
aber fachlich unzulässig ist. Ein Text, zwei Anlässe.

Die Referenzprüfung `waehrung_referenziert` wohnt hier und nicht bei der Währungs-Kaskade,
weil sie die Liste schützt, und die Liste ist eine Einstellung.
"""

from __future__ import annotations

import re

from eu_rechnung.domain import Datenbestand, Einstellungen
from eu_rechnung.services.befund import Befund

# Währungscode nach ISO 4217: genau drei Großbuchstaben. Bewusst nur die Form, nicht die
# echte Codeliste: Die brächte eine zu pflegende Tabelle ins Programm, während die
# Formprüfung den realen Tippfehler („EU", „eur", „EURO") bereits abfängt (4T-0132).
_WAEHRUNG_MUSTER = re.compile(r"^[A-Z]{3}$")


def pruefe_einstellungen(einstellungen: Einstellungen) -> list[Befund]:
    """Prüft die Einstellungen feldweise. Leere Liste bedeutet valide."""
    befunde: list[Befund] = []
    if not einstellungen.standard_anschreibentext.strip():
        befunde.append(
            Befund("standard_anschreibentext", "einstellungen.fehlt_standardtext")
        )
    befunde += _pruefe_waehrungen(einstellungen)
    if einstellungen.naechste_debitornummer < 1:
        befunde.append(Befund("debitornummer", "einstellungen.fehler_debitor"))
    for jahr, stand in einstellungen.naechste_rechnungsnummer.items():
        if not (jahr.isdigit() and len(jahr) == 4):
            befunde.append(
                Befund("rechnungsnummer", "einstellungen.jahr_format", {"jahr": jahr})
            )
        elif stand < 1:
            befunde.append(
                Befund("rechnungsnummer", "einstellungen.fehler_zaehler", {"jahr": jahr})
            )
    return befunde


def _pruefe_waehrungen(einstellungen: Einstellungen) -> list[Befund]:
    """Währungsliste und Standardwährung (S-0062 AK1/AK2).

    Alle Befunde tragen den Sammel-Schlüssel ``waehrungsliste`` beziehungsweise
    ``standardwaehrung``, passend zu den beiden Bedienelementen der Maske.
    """
    befunde: list[Befund] = []
    liste = einstellungen.waehrungsliste

    if not liste:
        befunde.append(Befund("waehrungsliste", "einstellungen.fehlt_waehrungsliste"))
    gesehen: set[str] = set()
    for code in liste:
        # Bewusst ohne strip(): Ein gespeichertes „ EUR" wäre die Belegwährung einer
        # Bestellung und landete so in BT-5. Die Maske trimmt beim Lesen, diese Prüfung
        # deckt den Rest (von Hand bearbeitete Dateien).
        if not _WAEHRUNG_MUSTER.match(code):
            befunde.append(
                Befund("waehrungsliste", "einstellungen.waehrung_format", {"code": code})
            )
        elif code in gesehen:
            befunde.append(
                Befund("waehrungsliste", "einstellungen.waehrung_doppelt", {"code": code})
            )
        else:
            gesehen.add(code)

    # Die Standardwährung muss in der Liste stehen, sonst erbte der Kunde einen Wert, den
    # die Auswahl gar nicht anbietet. Bei leerer Liste bleibt der Befund aus: Dann ist die
    # Liste selbst der Befund, und zwei Meldungen für eine Ursache verwirren nur.
    standard = einstellungen.standardwaehrung
    if liste and standard not in liste:
        befunde.append(
            Befund(
                "standardwaehrung",
                "einstellungen.standardwaehrung_nicht_in_liste",
                {"code": standard},
            )
        )
    return befunde


def waehrung_referenziert(datenbestand: Datenbestand, code: str) -> Befund | None:
    """Die erste Fundstelle einer benutzten Währung, sonst None (S-0062, Löschschutz).

    Eine Währung, die irgendwo in Gebrauch ist, darf nicht aus der Liste verschwinden: Sonst
    zeigte eine Bestellung eine Belegwährung, die es nicht mehr gibt, und die Auswahl könnte
    sie nicht wiederherstellen. Geprüft werden alle Stellen, an denen eine Währung stehen
    kann: Standardwährung, Kunde, Bestellung, Artikel-Preis und Bankverbindung.

    Rückgabe ist ein `Befund` **ohne Feldbezug**, dessen Schlüssel die Fundstelle benennt;
    die Oberfläche setzt ihn in ihre Meldung ein. Der erste Treffer genügt, weil er die
    Frage „darf ich löschen?" bereits beantwortet.
    """
    if datenbestand.einstellungen.standardwaehrung == code:
        return Befund("", "einstellungen.fundstelle_standardwaehrung")
    for artikel in datenbestand.artikel:
        if artikel.vorschlagspreis.waehrung == code:
            return Befund(
                "", "einstellungen.fundstelle_artikel", {"name": artikel.artikelname}
            )
    for bank in datenbestand.eigene_firma.bankverbindungen:
        if bank.waehrung == code:
            return Befund("", "einstellungen.fundstelle_bankverbindung")
    for kunde in datenbestand.kunden:
        if kunde.waehrung == code:
            return Befund("", "einstellungen.fundstelle_kunde", {"name": kunde.name})
        for bestellung in kunde.bestellungen:
            if bestellung.waehrung == code:
                return Befund(
                    "",
                    "einstellungen.fundstelle_bestellung",
                    {"nummer": bestellung.bestellnummer},
                )
    return None
