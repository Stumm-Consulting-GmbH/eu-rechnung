"""Erfassungslogik der Rechnung: Vorbelegung, Prüfung und Anlegen (UI-frei).

Baut aus einer gewählten Bestellung eine vorbelegte Rechnung (S-0029), prüft die
Pflichtangaben und legt sie mit berechneten Summen an (S-0025). Die Werte werden
beim Anlegen aus den Stammdaten übernommen und bleiben editierbar; die Rechnung
hält eigene Kopien (Designentscheidung 2), damit spätere Stammdaten-Änderungen
nicht zurückwirken.

Der Kopf-Leistungszeitraum wird aus dem Bestellzeitraum vorbelegt und als Pflicht geführt,
weil sein Ende das Lieferdatum BT-72 speist (S-0023, S-0029); die Überschreitungs-Warnung
der Bestell-Obergrenzen liefert `obergrenzen_warnungen` (S-0024). Die Eindeutigkeits-Warnung
bei doppelter Rechnungsnummer liefert `finde_rechnungsnummer_dublette` (S-0045); die Auflösung
des effektiven Anschreibentexts liegt in `services.anschreiben` (S-0034).
"""

from __future__ import annotations

import copy
import re
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import NamedTuple

from eu_rechnung.domain import (
    ArtikelTyp,
    Bankverbindung,
    Bestellung,
    Datenbestand,
    EigeneFirma,
    Einstellungen,
    IndividuellesFeld,
    Kaeufer,
    Kunde,
    Leistungszeitraum,
    ObergrenzeArt,
    Position,
    Rechnung,
    RechnungsStatus,
    Summen,
)
from eu_rechnung.persistence import STANDARD_PFAD, speichere
from eu_rechnung.services.anschreiben import effektiver_anschreibentext
from eu_rechnung.services.befund import Befund
from eu_rechnung.services.firma import pruefe_firma
from eu_rechnung.services.sprache import effektive_rechnungssprache

_CENT = Decimal("0.01")
_START_NUMMER = 10001  # Startwert des Jahres-Zaehlers der Rechnungsnummer (S-0041/S-0042)
# E-Mail-Grundmuster fuer die Kaeuferpruefung, gespiegelt aus services.firma/services.kunde
# (bewusste modul-lokale Kopie je Pruefmodul, wie im Projekt etabliert).
_EMAIL_MUSTER = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidierungsFehler(Exception):
    """Fehlende oder ungültige Pflichtangaben beim Anlegen.

    Trägt die Einzelbefunde als Liste, damit die Oberfläche sie am jeweiligen
    Feld anzeigen und in der eingestellten Sprache auflösen kann.

    Die Ausnahmen-Nachricht listet bewusst die Katalog-Schlüssel und nicht die aufgelösten
    Texte: Sie landet in Stacktraces und Protokollen, ist also Entwickler-Material und kein
    Oberflächen-Text. Die Sprache kennt diese Schicht ohnehin nicht.
    """

    def __init__(self, befunde: list[Befund]) -> None:
        self.befunde = befunde
        super().__init__("; ".join(b.schluessel for b in befunde))


def berechne_gesamtpreis(menge: Decimal, einzelpreis: Decimal) -> Decimal:
    """Positions-Gesamtpreis = Menge × Einzelpreis, auf Cent gerundet."""
    return (menge * einzelpreis).quantize(_CENT)


def berechne_summen(
    positionen: list[Position], reverse_charge: bool, steuersatz: Decimal = Decimal("0")
) -> Summen:
    """Rechnungssummen aus den Positionen.

    Reverse-Charge: netto = brutto = Zahlbetrag, Steuer 0 (Kategorie AE). Normalfall
    (kein Reverse-Charge): Steuer = netto × Steuersatz, kaufmännisch auf Cent gerundet
    (BR-CO-17), brutto = netto + Steuer (Kategorie S, S-0079).
    """
    netto = sum((p.gesamtpreis for p in positionen), Decimal("0.00")).quantize(_CENT)
    if reverse_charge:
        steuer = Decimal("0.00")
    else:
        steuer = (netto * steuersatz / Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP)
    brutto = netto + steuer
    return Summen(netto=netto, steuer=steuer, brutto=brutto)


def _uebernommene_felder(kunde: Kunde, bestellung: Bestellung) -> list[IndividuellesFeld]:
    """Aktive individuelle Felder aus Kunde und Bestellung als eigene Kopien."""
    felder: list[IndividuellesFeld] = []
    for quelle in (kunde.individuelle_felder, bestellung.individuelle_felder):
        felder.extend(copy.deepcopy(f) for f in quelle if f.aktiv)
    return felder


def _artikelname(datenbestand: Datenbestand, artikel_id: str) -> str:
    """Artikelname zur Artikelnummer aus den Stammdaten; die Nummer selbst als Rückfall."""
    artikel = next((a for a in datenbestand.artikel if a.id == artikel_id), None)
    return artikel.artikelname if artikel is not None else artikel_id


def _ist_produkt(datenbestand: Datenbestand, artikel_id: str) -> bool:
    """True, wenn der Artikel ein Produkt ist; ein Produkt trägt keinen Leistungszeitraum (S-0067)."""
    artikel = next((a for a in datenbestand.artikel if a.id == artikel_id), None)
    return artikel is not None and artikel.typ is ArtikelTyp.PRODUKT


def _vorbelegte_positionen(datenbestand: Datenbestand, bestellung: Bestellung) -> list[Position]:
    """Je gültigem Artikel der Bestellung eine Position mit Menge 0 (S-0029).

    Artikelnummer, Bezeichnung (Artikelname) und Einzelpreis stammen aus der Bestellung;
    Menge und Gesamtpreis starten bei 0. Der Anwender trägt in der Maske die abzurechnende
    Menge ein. Leistungs-Artikel-Positionen tragen den Kopf-Leistungszeitraum (BG-14) vorbelegt
    (S-0069), Produkt-Positionen keinen (S-0067).
    """
    kopf_zeitraum = Leistungszeitraum(von=bestellung.beginn_datum, bis=bestellung.ende_datum)
    return [
        Position(
            artikel_id=gueltiger.artikel_id,
            bezeichnung=_artikelname(datenbestand, gueltiger.artikel_id),
            menge=Decimal("0"),
            einzelpreis=gueltiger.einzelpreis,
            gesamtpreis=Decimal("0.00"),
            leistungszeitraum=(
                None
                if _ist_produkt(datenbestand, gueltiger.artikel_id)
                else copy.deepcopy(kopf_zeitraum)
            ),
        )
        for gueltiger in bestellung.gueltige_artikel
    ]


def _vorbelegte_rechnungsnummer(einstellungen: Einstellungen, jahr: str) -> str:
    """Die aus dem Jahres-Zaehler gebildete Vorbelegung im Format `JJJJ-NNNNN` (S-0042).

    Existiert fuer das Jahr noch kein Zaehler, startet er bei `_START_NUMMER`.
    """
    stand = einstellungen.naechste_rechnungsnummer.get(jahr, _START_NUMMER)
    return f"{jahr}-{stand}"


def _schreibe_jahres_zaehler_fort(einstellungen: Einstellungen, rechnung: Rechnung) -> None:
    """Erhoeht den Jahres-Zaehler nur bei unveraenderter Vorbelegung (S-0042 AK3).

    Der Zaehler zaehlt die automatisch vergebenen Nummern: Entspricht die gespeicherte
    Rechnungsnummer exakt der aus dem aktuellen Stand gebildeten Vorbelegung, wird er um eins
    erhoeht. Ein manuell ueberschriebener Wert verbraucht keine automatische Nummer (ein
    verworfenes Anlegen ohnehin nicht, es ruft diese Funktion nicht auf).
    """
    jahr = str(rechnung.rechnungsdatum.year)
    if rechnung.rechnungsnummer == _vorbelegte_rechnungsnummer(einstellungen, jahr):
        stand = einstellungen.naechste_rechnungsnummer.get(jahr, _START_NUMMER)
        einstellungen.naechste_rechnungsnummer[jahr] = stand + 1


def _vorbelegte_bankverbindung(firma: EigeneFirma, waehrung: str) -> Bankverbindung | None:
    """Die erste Bankverbindung der Firma mit passender Belegwährung als eingefrorene Kopie.

    Ohne passende Währung bleibt die Wahl leer (`None`); der Anwender wählt sie dann in der
    Rechnungsmaske (S-0065 AK2). Die Kopie entkoppelt die Wahl von späteren Änderungen an der
    Bankverbindungs-Liste der Firma (Designentscheidung 2).
    """
    passend = next((b for b in firma.bankverbindungen if b.waehrung == waehrung), None)
    return copy.deepcopy(passend) if passend is not None else None


def vorbelege_rechnung(
    datenbestand: Datenbestand,
    kunde: Kunde,
    bestellung: Bestellung,
    *,
    heute: date | None = None,
) -> Rechnung:
    """Baut eine neue, aus den Stammdaten vorbelegte Rechnung (noch ohne `id`).

    Alle Werte sind editierbar; die Rechnung hält eigene Kopien von Verkäufer,
    Käufer und den aktiven individuellen Feldern. Die Positionen werden aus den gültigen
    Artikeln der Bestellung mit Menge 0 vorbelegt (S-0029). Anschreibentext und
    Rechnungssprache werden entlang ihrer Kaskaden aufgelöst (S-0034, S-0060). `heute` ist
    injizierbar (Testbarkeit), sonst das aktuelle Tagesdatum.
    """
    heute = heute or date.today()
    jahr = str(heute.year)
    kaeufer = Kaeufer(
        name=kunde.name,
        adresse=copy.deepcopy(kunde.adresse),
        umsatzsteuer_id=kunde.umsatzsteuer_id,
        kundennummer=kunde.kundennummer,
        email=kunde.email,
        namenszusatz=list(kunde.namenszusatz),
    )
    return Rechnung(
        id="",  # wird beim Anlegen vergeben
        rechnungsnummer=_vorbelegte_rechnungsnummer(datenbestand.einstellungen, jahr),
        rechnungsdatum=heute,
        leistungszeitraum=Leistungszeitraum(
            von=bestellung.beginn_datum, bis=bestellung.ende_datum
        ),
        verkaeufer=copy.deepcopy(datenbestand.eigene_firma),
        kaeufer=kaeufer,
        reverse_charge=kunde.reverse_charge,
        zahlungsbedingung=bestellung.zahlungsbedingung,
        # Vertraglich in der Bestellung vereinbart, hier als eigene Kopie übernommen und an
        # der Rechnung änderbar (S-0080).
        zahlungsfrist=bestellung.zahlungsfrist,
        skonto=copy.deepcopy(bestellung.skonto),
        anschreibentext=effektiver_anschreibentext(
            datenbestand.einstellungen, kunde=kunde, bestellung=bestellung
        ),
        # Entlang der Kaskade aufgelöst und als eigene Kopie übernommen; an der Rechnung
        # änderbar (S-0058 AK3, S-0060 AK1). Steuert die Sprache der Ausgabe, nicht die der
        # Oberfläche.
        rechnungssprache=effektive_rechnungssprache(kunde=kunde, bestellung=bestellung),
        summen=Summen(netto=Decimal("0.00"), steuer=Decimal("0.00"), brutto=Decimal("0.00")),
        # Bei Reverse-Charge ist der Satz 0 (S-0023 AK6): Die Steuer schuldet der Empfänger,
        # ein Firmen-Standardsatz gilt für diese Rechnung nicht. Die Ausgabe erzwingt die 0
        # ohnehin (`cii_xml`, `berechne_summen`); ohne diese Zeile trüge das gespeicherte Feld
        # einen Wert, den die Rechnung selbst nirgends verwendet.
        steuersatz=(
            Decimal("0")
            if kunde.reverse_charge
            else datenbestand.eigene_firma.standard_steuersatz
        ),
        bankverbindung=_vorbelegte_bankverbindung(
            datenbestand.eigene_firma, bestellung.waehrung
        ),
        status=RechnungsStatus.ENTWURF,
        positionen=_vorbelegte_positionen(datenbestand, bestellung),
        individuelle_felder=_uebernommene_felder(kunde, bestellung),
    )


def _pruefe_rechnungsrumpf(rechnung: Rechnung) -> list[Befund]:
    """Pflichtprüfung der Rechnungs-Kopffelder ohne Verkäufer-/Käuferangaben.

    Deckt die auf Rechnungsebene stufenunabhängigen Pflichten ab (Rechnungsnummer,
    Rechnungsdatum, mindestens eine Position mit nicht-negativen Werten, Steuersatz im
    Normalfall, Wertebereich eines gesetzten Skontos). Die Verkäufer- und Käuferpflichten
    sind zweistufig und liegen in
    `pruefe_firma`/`pruefe_kaeufer`; sie werden hier bewusst nicht geprüft, damit die
    Basis- und die Ausgabeprüfung denselben Rumpf ohne Doppelbefunde teilen.
    """
    befunde: list[Befund] = []
    if not rechnung.rechnungsnummer.strip():
        befunde.append(Befund("rechnungsnummer", "rechnung.fehlt_rechnungsnummer"))
    if rechnung.rechnungsdatum is None:
        befunde.append(Befund("rechnungsdatum", "rechnung.fehlt_rechnungsdatum"))
    if not rechnung.positionen:
        befunde.append(Befund("positionen", "rechnung.keine_position"))
    for i, pos in enumerate(rechnung.positionen, start=1):
        if pos.menge < 0:
            befunde.append(Befund("positionen", "rechnung.position_menge_negativ", {"nr": i}))
        if pos.einzelpreis < 0:
            befunde.append(Befund("positionen", "rechnung.position_preis_negativ", {"nr": i}))
        # Der Positions-Leistungszeitraum (BG-26) muss innerhalb des Kopf-Zeitraums (BG-14)
        # liegen; sonst ist die Ausgabe KoSIT-invalide (BR-CO, S-0069). Greift auch, wenn der
        # Kopf-Zeitraum nachträglich verengt wird.
        lz = pos.leistungszeitraum
        if lz is not None and (
            lz.von < rechnung.leistungszeitraum.von or lz.bis > rechnung.leistungszeitraum.bis
        ):
            befunde.append(
                Befund("positionen", "rechnung.position_zeitraum_ausserhalb", {"nr": i})
            )
    if not rechnung.reverse_charge and rechnung.steuersatz <= Decimal("0"):
        befunde.append(Befund("steuersatz", "rechnung.steuersatz_fehlt"))
    # Wertebereich eines gesetzten Skontos (S-0051). Die BR-DE-18-Zeile lässt nur
    # nicht-negative Tage und einen vorzeichenlosen Prozentsatz zu; die Obergrenze von
    # 100 % ist darüber hinaus fachlich gesetzt (4T-0116).
    if rechnung.skonto is not None:
        if rechnung.skonto.tage <= 0:
            befunde.append(Befund("skonto_tage", "skonto.tage_zu_klein"))
        if not Decimal("0") < rechnung.skonto.prozent <= Decimal("100"):
            befunde.append(Befund("skonto_prozent", "skonto.prozent_bereich"))
    return befunde


def pruefe_rechnung(rechnung: Rechnung) -> list[Befund]:
    """Basis-Pflichtprüfung des MVP (Erfassung). Leere Liste bedeutet valide.

    Liefert `Befund`-Einträge für die feld-nahe Anzeige in der Rechnungsmaske, analog
    `pruefe_bestellung`/`pruefe_artikel`. Prüft den Rechnungsrumpf (Positions-Befunde unter
    dem Sammel-Schlüssel `positionen`) und das Vorhandensein von Verkäufer- und
    Käufernamen; die vollständige zweistufige Verkäufer-/Käuferpflicht setzt erst die
    Ausgabeprüfung durch (`pruefe_rechnung_fuer_ausgabe`, S-0047/S-0049).
    """
    befunde = _pruefe_rechnungsrumpf(rechnung)
    if not rechnung.verkaeufer.name.strip():
        befunde.append(Befund("verkaeufer_name", "rechnung.fehlt_verkaeufer_name"))
    if not rechnung.kaeufer.name.strip():
        befunde.append(Befund("kaeufer_name", "rechnung.fehlt_kaeufer_name"))
    return befunde


def pruefe_kaeufer(
    kaeufer: Kaeufer, *, xrechnung_aktiv: bool, reverse_charge: bool
) -> list[Befund]:
    """Prüft den Rechnungs-Käufer stufenabhängig. Leere Liste bedeutet gültig.

    Spiegelt `services.kunde.pruefe_kunde` für die eingefrorene Käufer-Kopie, ohne die
    Kundennummer-Eindeutigkeit (die gehört zur Stammdatenpflege). EN-Pflicht: Name, Land,
    Kundennummer; die USt-ID zusätzlich bei Reverse-Charge (BR-AE). Bei aktiver XRechnung
    zusätzlich vollständige Adresse und E-Mail (S-0011). Die Befunde tragen `kaeufer_`-
    Feldschlüssel, passend zu `pruefe_rechnung`.
    """
    befunde: list[Befund] = []
    if not kaeufer.name.strip():
        befunde.append(Befund("kaeufer_name", "rechnung.fehlt_kaeufer_name"))
    if not kaeufer.adresse.land.strip():
        befunde.append(Befund("kaeufer_land", "rechnung.fehlt_kaeufer_land"))
    if not kaeufer.kundennummer.strip():
        befunde.append(Befund("kaeufer_kundennummer", "allgemein.fehlt_kundennummer"))
    if reverse_charge and not kaeufer.umsatzsteuer_id.strip():
        befunde.append(Befund("kaeufer_umsatzsteuer_id", "rechnung.rc_pflicht_kaeufer_ustid"))
    if xrechnung_aktiv:
        if not kaeufer.adresse.strasse.strip():
            befunde.append(Befund("kaeufer_strasse", "rechnung.xr_pflicht_kaeufer_strasse"))
        if not kaeufer.adresse.plz.strip():
            befunde.append(Befund("kaeufer_plz", "rechnung.xr_pflicht_kaeufer_plz"))
        if not kaeufer.adresse.ort.strip():
            befunde.append(Befund("kaeufer_ort", "rechnung.xr_pflicht_kaeufer_ort"))
        if not kaeufer.email.strip():
            befunde.append(Befund("kaeufer_email", "rechnung.xr_pflicht_kaeufer_email"))
    if kaeufer.email.strip() and not _EMAIL_MUSTER.match(kaeufer.email.strip()):
        befunde.append(Befund("kaeufer_email", "rechnung.kaeufer_email_format"))
    return befunde


def pruefe_rechnung_fuer_ausgabe(rechnung: Rechnung) -> list[Befund]:
    """Zweistufige Pflichtprüfung vor der Ausgabe (S-0047/S-0049). Leer bedeutet valide.

    Prüft die Rechnung gegen die Pflichtfelder der aktiven Stufe. Maßgeblich ist der
    eingefrorene Verkäufer-Schalter `rechnung.verkaeufer.xrechnung_aktiv`
    (Designentscheidung 2), damit die Ausgabe den zum Rechnungszeitpunkt festgeschriebenen
    Stand prüft. Der Verkäufer wird über `pruefe_firma` geprüft (Befunde mit
    `verkaeufer_`-Präfix), der Käufer über `pruefe_kaeufer`; der Rumpf über
    `_pruefe_rechnungsrumpf`. So decken sich die geprüften Felder mit den EN- und
    XRechnung-CIUS-Pflichten der Datenmodell-Stories (S-0001, S-0011, S-0023).
    """
    xr = rechnung.verkaeufer.xrechnung_aktiv
    befunde = _pruefe_rechnungsrumpf(rechnung)
    # Bei aktiver XRechnung ist die Wahl einer Bankverbindung Pflicht (S-0065 AK4). Ohne sie
    # verließe sich die Ausgabe auf den stummen Rückfall auf die erste, der bei mehreren
    # Konten das falsche nennen könnte.
    if xr and rechnung.bankverbindung is None:
        befunde.append(Befund("bankverbindung", "rechnung.fehlt_bankverbindung"))
    befunde += [
        b._replace(feld=f"verkaeufer_{b.feld}") for b in pruefe_firma(rechnung.verkaeufer)
    ]
    befunde += pruefe_kaeufer(
        rechnung.kaeufer, xrechnung_aktiv=xr, reverse_charge=rechnung.reverse_charge
    )
    return befunde


def warne_rechnung(rechnung: Rechnung, bestellung: Bestellung) -> list[Befund]:
    """Warnhinweise beim Anlegen (kein Speicher-Hindernis; S-0025).

    Warnt, wenn der Einzelpreis einer Position vom Wert des zugehörigen gültigen Artikels
    in der Bestellung abweicht oder eine Position keinem gültigen Artikel der Bestellung
    entspricht (freie Position). Die Rechnung fußt auf der Bestellung, daher sind beide
    Fälle nur Hinweise, keine Fehler.

    Die Warnungen tragen kein Feld (``""``): Sie erscheinen gesammelt im Dialog vor dem
    Speichern und nicht an einem einzelnen Eingabefeld.
    """
    bestell_preise = {g.artikel_id: g.einzelpreis for g in bestellung.gueltige_artikel}
    warnungen: list[Befund] = []
    for i, pos in enumerate(rechnung.positionen, start=1):
        if pos.artikel_id in bestell_preise:
            if pos.einzelpreis != bestell_preise[pos.artikel_id]:
                warnungen.append(
                    Befund(
                        "",
                        "rechnung.warnung_preis_abweichung",
                        {"nr": i, "bezeichnung": pos.bezeichnung},
                    )
                )
        else:
            warnungen.append(
                Befund(
                    "",
                    "rechnung.warnung_freie_position",
                    {"nr": i, "bezeichnung": pos.bezeichnung},
                )
            )
    warnungen += obergrenzen_warnungen(rechnung, bestellung)
    return warnungen


def _verbrauch_der_anderen(
    rechnung: Rechnung, bestellung: Bestellung
) -> list[Position]:
    """Die Positionen aller Rechnungen der Bestellung außer dieser.

    Beim Ändern liegt die eigene Fassung bereits in `bestellung.rechnungen`; zählte man sie
    mit, wäre jede Änderung sofort eine Überschreitung. Verglichen wird über die `id`, denn
    die Maske arbeitet auf einer Kopie und ist nicht identisch mit dem Original. Beim
    Anlegen ist die `id` leer und trifft keine bestehende Rechnung.
    """
    return [
        pos
        for andere in bestellung.rechnungen
        if andere.id != rechnung.id
        for pos in andere.positionen
    ]


def obergrenzen_warnungen(rechnung: Rechnung, bestellung: Bestellung) -> list[Befund]:
    """Warnt, wenn diese Rechnung eine Obergrenze der Bestellung überschreitet (S-0024 AK6).

    Zwei Ebenen, beide optional und frei kombinierbar (S-0017 AK7): der Gesamt-Höchstbetrag
    der Bestellung und je gültigem Artikel eine Obergrenze als Menge oder Betrag. Gezählt
    wird der Verbrauch der übrigen Rechnungen plus dieser.

    Warnung, kein Fehler: Die Obergrenze ist eine kaufmännische Vereinbarung, keine
    Normvorgabe. Ob im Einzelfall darüber hinaus abgerechnet wird, entscheidet der Anwender;
    das Werkzeug sagt ihm nur, dass er es tut.
    """
    andere = _verbrauch_der_anderen(rechnung, bestellung)
    warnungen: list[Befund] = []

    if bestellung.gesamt_hoechstbetrag is not None:
        verbraucht = sum((p.gesamtpreis for p in andere), Decimal("0"))
        summe = verbraucht + sum((p.gesamtpreis for p in rechnung.positionen), Decimal("0"))
        if summe > bestellung.gesamt_hoechstbetrag:
            warnungen.append(
                Befund(
                    "",
                    "rechnung.warnung_gesamt_hoechstbetrag",
                    {"summe": summe, "grenze": bestellung.gesamt_hoechstbetrag},
                )
            )

    for gueltiger in bestellung.gueltige_artikel:
        grenze = gueltiger.obergrenze
        if grenze is None:
            continue
        eigene = [p for p in rechnung.positionen if p.artikel_id == gueltiger.artikel_id]
        fremde = [p for p in andere if p.artikel_id == gueltiger.artikel_id]
        if grenze.art is ObergrenzeArt.MENGE:
            summe = sum((p.menge for p in eigene + fremde), Decimal("0"))
        else:
            summe = sum((p.gesamtpreis for p in eigene + fremde), Decimal("0"))
        if summe > grenze.wert:
            bezeichnung = eigene[0].bezeichnung if eigene else gueltiger.artikel_id
            warnungen.append(
                Befund(
                    "",
                    "rechnung.warnung_obergrenze_artikel",
                    {"bezeichnung": bezeichnung, "summe": summe, "grenze": grenze.wert},
                )
            )
    return warnungen


def lege_rechnung_an(
    datenbestand: Datenbestand,
    bestellung: Bestellung,
    rechnung: Rechnung,
    *,
    pfad: Path | str = STANDARD_PFAD,
) -> Rechnung:
    """Prüft und legt die Rechnung an: Summen, `id`, Status, Einhängen, Speichern.

    Wirft `ValidierungsFehler`, wenn Pflichtangaben fehlen. Bei Erfolg erhält die
    Rechnung eine eindeutige `id` und Status „Entwurf", wird in die Bestellung
    eingehängt, der Jahres-Zähler bei unveränderter Vorbelegung fortgeschrieben (S-0042
    AK3) und der Datenbestand persistiert. Die übergebene `bestellung` muss die im
    `datenbestand` hängende Instanz sein.
    """
    befunde = pruefe_rechnung(rechnung)
    if befunde:
        raise ValidierungsFehler(befunde)
    rechnung.summen = berechne_summen(
        rechnung.positionen, rechnung.reverse_charge, rechnung.steuersatz
    )
    rechnung.id = str(uuid.uuid4())
    rechnung.status = RechnungsStatus.ENTWURF
    bestellung.rechnungen.append(rechnung)
    _schreibe_jahres_zaehler_fort(datenbestand.einstellungen, rechnung)
    speichere(datenbestand, pfad)
    return rechnung


class RechnungsnummerDublette(NamedTuple):
    """Fundstelle einer anderen Rechnung mit derselben Rechnungsnummer, mit Kontext (S-0045)."""

    kunde: Kunde
    bestellung: Bestellung
    rechnung: Rechnung


def finde_rechnungsnummer_dublette(
    datenbestand: Datenbestand, rechnung: Rechnung
) -> RechnungsnummerDublette | None:
    """Sucht eine andere Rechnung mit derselben Rechnungsnummer im gesamten Bestand (S-0045).

    Vergleicht die getrimmte Rechnungsnummer über alle Kunden, Bestellungen und Rechnungen
    hinweg; die geprüfte Rechnung selbst ist über ihre `id` ausgenommen (Selbst-Ausnahme beim
    Ändern). Liefert den ersten Treffer mit Kontext (Kunde, Bestellung, andere Rechnung) oder
    None. Eine leere Rechnungsnummer löst keine Warnung aus (das fängt die Pflichtprüfung ab).
    """
    nummer = rechnung.rechnungsnummer.strip()
    if not nummer:
        return None
    for kunde in datenbestand.kunden:
        for bestellung in kunde.bestellungen:
            for andere in bestellung.rechnungen:
                if rechnung.id and andere.id == rechnung.id:
                    continue  # dieselbe Rechnung (Selbst-Ausnahme beim Ändern)
                if andere.rechnungsnummer.strip() == nummer:
                    return RechnungsnummerDublette(kunde, bestellung, andere)
    return None
