"""Bestellungs-Validierung und Verbrauchsrechnung (UI-frei) für die Bestellungs-Pflege.

Trägt die semantische Prüfung einer Bestellung (Pflicht-Kopffelder, Datums- und
Betragsplausibilität; S-0018) und die Verbrauchsrechnung zu den Obergrenzen (S-0018 AK6).
Die Oberfläche prüft über ``pruefe_bestellung`` vor dem Speichern und zeigt die Befunde am
betroffenen Feld; das Einhängen der Bestellung am Kunden und das Persistieren übernimmt die
Maske über das automatische Speichern.

Die Verbrauchsrechnung summiert den bereits über die Rechnungen der Bestellung abgerufenen
Anteil (Menge bzw. Betrag je gültigem Artikel, netto gesamt). Solange die
Rechnungserfassung (F-0005) noch keine Rechnungen erzeugt, ist der Verbrauch 0; die
Rechnung ist bewusst schon vollständig, damit die Rest-Anzeige mit F-0005 ohne weitere
Änderung lebendig wird.
"""

from __future__ import annotations

from decimal import Decimal

from eu_rechnung.domain import Bestellung, ObergrenzeArt
from eu_rechnung.services.befund import Befund

# Wertebereich des vereinbarten Skontos, wortgleich zur Rechnungsprüfung
# (services.rechnung), damit die Bestellung nichts durchlässt, was die Rechnung später
# ablehnt (S-0080).
_SKONTO_PROZENT_MAX = Decimal("100")


def pruefe_bestellung(bestellung: Bestellung) -> list[Befund]:
    """Prüft eine Bestellung feldweise. Leere Liste bedeutet gültig.

    Die Feldschlüssel der Befunde sind ``bestellnummer``, ``waehrung``, ``ende``,
    ``zahlungsbedingung``, ``zahlungsfrist``, ``gesamt_hoechstbetrag``, ``gueltige_artikel``,
    ``skonto_tage`` oder ``skonto_prozent``.
    Pflicht sind Bestellnummer, Währung, Zahlungsbedingung und mindestens ein gültiger
    Artikel; die Bestellnummer darf sich über Bestellungen wiederholen (BT-13), daher keine
    Eindeutigkeitsprüfung. Das Ende-Datum darf nicht vor dem Beginn liegen; Zahlungsfrist und
    ein gesetzter Gesamt-Höchstbetrag dürfen nicht negativ sein (S-0019, S-0020). Ein
    vereinbartes Skonto muss im Wertebereich liegen (S-0080); die beiden Skonto-Schlüssel
    teilt sich die Prüfung mit `services.rechnung`, weil dort derselbe Wertebereich gilt.
    """
    befunde: list[Befund] = []

    if not bestellung.bestellnummer.strip():
        befunde.append(Befund("bestellnummer", "bestellung.fehlt_bestellnummer"))
    if not bestellung.waehrung.strip():
        befunde.append(Befund("waehrung", "allgemein.fehlt_waehrung"))
    if not bestellung.zahlungsbedingung.strip():
        befunde.append(Befund("zahlungsbedingung", "bestellung.fehlt_zahlungsbedingung"))
    if bestellung.ende_datum < bestellung.beginn_datum:
        befunde.append(Befund("ende", "bestellung.ende_vor_beginn"))
    if bestellung.zahlungsfrist < 0:
        befunde.append(Befund("zahlungsfrist", "bestellung.zahlungsfrist_negativ"))
    if bestellung.gesamt_hoechstbetrag is not None and bestellung.gesamt_hoechstbetrag < 0:
        befunde.append(Befund("gesamt_hoechstbetrag", "bestellung.hoechstbetrag_negativ"))
    if not bestellung.gueltige_artikel:
        befunde.append(Befund("gueltige_artikel", "bestellung.kein_gueltiger_artikel"))
    if bestellung.skonto is not None:
        if bestellung.skonto.tage <= 0:
            befunde.append(Befund("skonto_tage", "skonto.tage_zu_klein"))
        if not Decimal("0") < bestellung.skonto.prozent <= _SKONTO_PROZENT_MAX:
            befunde.append(Befund("skonto_prozent", "skonto.prozent_bereich"))

    return befunde


def verbrauch_gesamt(bestellung: Bestellung) -> Decimal:
    """Netto abgerufener Gesamtbetrag: Summe der Positions-Gesamtpreise aller Rechnungen.

    Grundlage der Rest-Anzeige zum Gesamt-Höchstbetrag (S-0018 AK6). Ohne erfasste
    Rechnungen (F-0005) ist das Ergebnis 0.
    """
    return sum(
        (
            pos.gesamtpreis
            for rechnung in bestellung.rechnungen
            for pos in rechnung.positionen
        ),
        Decimal("0"),
    )


def verbrauch_artikel(
    bestellung: Bestellung, artikel_id: str, art: ObergrenzeArt
) -> Decimal:
    """Abgerufener Anteil eines gültigen Artikels je Obergrenze-Art.

    Für eine Mengen-Obergrenze die Summe der Positionsmengen, für eine Betrags-Obergrenze
    die Summe der Positions-Gesamtpreise, jeweils über die Positionen aller Rechnungen der
    Bestellung mit passender ``artikel_id`` (S-0018 AK6). Ohne erfasste Rechnungen 0.
    """
    posten = [
        pos
        for rechnung in bestellung.rechnungen
        for pos in rechnung.positionen
        if pos.artikel_id == artikel_id
    ]
    if art is ObergrenzeArt.MENGE:
        return sum((p.menge for p in posten), Decimal("0"))
    return sum((p.gesamtpreis for p in posten), Decimal("0"))
