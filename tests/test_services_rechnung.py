"""Tests der Rechnungs-Erfassungslogik (Vorbelegung, Prüfung, Anlegen), Java-frei."""

from datetime import date
from decimal import Decimal

import pytest

from eu_rechnung.domain import (
    Adresse,
    ArtikelTyp,
    IndividuellesFeld,
    Kaeufer,
    Leistungszeitraum,
    Position,
    RechnungsStatus,
    Skonto,
)
from eu_rechnung.persistence import lade
from eu_rechnung.services import (
    ValidierungsFehler,
    berechne_gesamtpreis,
    berechne_summen,
    erzeuge_seed,
    finde_rechnungsnummer_dublette,
    lege_rechnung_an,
    obergrenzen_warnungen,
    pruefe_kaeufer,
    pruefe_rechnung,
    pruefe_rechnung_fuer_ausgabe,
    vorbelege_rechnung,
    warne_rechnung,
)


def _seed_kunde_bestellung():
    bestand = erzeuge_seed()
    kunde = bestand.kunden[0]
    bestellung = kunde.bestellungen[0]
    return bestand, kunde, bestellung


def test_vorbelegung_uebernimmt_stammdaten():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.rechnungsnummer == "2026-10001"
    assert rechnung.rechnungsdatum == date(2026, 7, 10)
    assert rechnung.verkaeufer.name == "Muster Consulting GmbH"
    assert rechnung.kaeufer.name == kunde.name
    assert rechnung.kaeufer.kundennummer == "D10002"
    assert rechnung.reverse_charge is True
    assert rechnung.zahlungsbedingung == bestellung.zahlungsbedingung
    # None-Kaskade: Bestellung und Kunde erben -> Standardtext
    assert rechnung.anschreibentext == bestand.einstellungen.standard_anschreibentext
    # Kopf-Leistungszeitraum aus dem Bestellzeitraum (MVP-Delta D4)
    assert rechnung.leistungszeitraum.von == bestellung.beginn_datum
    assert rechnung.leistungszeitraum.bis == bestellung.ende_datum
    # nur aktive individuelle Felder, noch keine id
    assert len(rechnung.individuelle_felder) == 2
    assert all(f.aktiv for f in rechnung.individuelle_felder)
    # Positionen aus den gültigen Artikeln der Bestellung mit Menge 0 vorbelegt (S-0029)
    assert [p.artikel_id for p in rechnung.positionen] == ["art-1", "art-2"]
    assert all(p.menge == Decimal("0") for p in rechnung.positionen)
    assert rechnung.positionen[0].bezeichnung == "IT-Beratung Senior Projektleitung"
    assert rechnung.positionen[0].einzelpreis == Decimal("1200.00")
    assert rechnung.id == ""


def test_vorbelegung_positions_zeitraum_typabhaengig():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    # Der zweite gültige Artikel wird zum Produkt; es trägt keinen Positions-Zeitraum (S-0067),
    # der Leistungs-Artikel dagegen den Kopf-Zeitraum vorbelegt (S-0069).
    produkt_id = bestellung.gueltige_artikel[1].artikel_id
    next(a for a in bestand.artikel if a.id == produkt_id).typ = ArtikelTyp.PRODUKT
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    leistung, produkt = rechnung.positionen[0], rechnung.positionen[1]
    assert leistung.leistungszeitraum is not None
    assert leistung.leistungszeitraum.von == bestellung.beginn_datum
    assert leistung.leistungszeitraum.bis == bestellung.ende_datum
    assert produkt.leistungszeitraum is None


def test_vorbelegte_kopien_sind_unabhaengig():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    kunde.name = "Geändert AG"
    kunde.adresse.ort = "Berlin"
    bestand.eigene_firma.name = "Andere GmbH"
    # Die Rechnung hält eigene Kopien; spätere Stammdaten-Änderungen wirken nicht zurück.
    assert rechnung.kaeufer.name == "Beispiel Kunde GmbH"
    assert rechnung.kaeufer.adresse.ort == "München"
    assert rechnung.verkaeufer.name == "Muster Consulting GmbH"


def test_berechne_gesamtpreis_und_summen():
    assert berechne_gesamtpreis(Decimal("3.5"), Decimal("1400.00")) == Decimal("4900.00")
    positionen = [
        Position("art-1", "A", Decimal("10"), Decimal("1200.00"), Decimal("12000.00")),
        Position("art-2", "B", Decimal("3.5"), Decimal("1400.00"), Decimal("4900.00")),
    ]
    summen = berechne_summen(positionen, reverse_charge=True)
    assert summen.netto == Decimal("16900.00")
    assert summen.steuer == Decimal("0.00")
    assert summen.brutto == Decimal("16900.00")


def test_summen_normalfall_mit_steuersatz():
    """Normalfall (kein Reverse-Charge): Steuer = netto × Satz auf Cent, brutto = netto + Steuer."""
    positionen = [
        Position("art-1", "A", Decimal("10"), Decimal("1200.00"), Decimal("12000.00")),
        Position("art-2", "B", Decimal("3.5"), Decimal("1400.00"), Decimal("4900.00")),
    ]
    summen = berechne_summen(positionen, reverse_charge=False, steuersatz=Decimal("19"))
    assert summen.netto == Decimal("16900.00")
    assert summen.steuer == Decimal("3211.00")  # 16900.00 × 19 %
    assert summen.brutto == Decimal("20111.00")


def test_summen_steuer_kaufmaennisch_gerundet():
    """Der Steuerbetrag wird kaufmännisch auf Cent gerundet (BR-CO-17)."""
    positionen = [Position("art-1", "A", Decimal("1"), Decimal("100.10"), Decimal("100.10"))]
    # 100.10 × 19 % = 19.019 -> kaufmännisch 19.02
    summen = berechne_summen(positionen, reverse_charge=False, steuersatz=Decimal("19"))
    assert summen.steuer == Decimal("19.02")
    assert summen.brutto == Decimal("119.12")


def test_pruefung_meldet_fehlende_position():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = []  # alle Positionen entfernt
    befunde = pruefe_rechnung(rechnung)
    # Befunde sind (feld, text)-Paare für die feld-nahe Anzeige (S-0024)
    assert any(b.feld == "positionen" for b in befunde)


def test_menge_null_ist_zulaessig():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    # alle Positionen mit Menge 0 (Vorbelegung) sind zulässig -> kein harter Befund
    assert pruefe_rechnung(rechnung) == []


# --- Positions-Zeitraum gegen den Kopf-Zeitraum (S-0069 AK5, 4T-0147) -------


def test_pruefung_meldet_positions_zeitraum_ausserhalb_des_kopfes():
    """S-0069 AK5: Ein Positions-Zeitraum außerhalb des Kopf-Zeitraums (BG-26 nicht in BG-14) ist
    ein Pflichtbefund; sonst waere die Ausgabe KoSIT-invalide."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    # Kopf ist der Bestellzeitraum (Mai); ein April-Zeitraum liegt davor.
    rechnung.positionen[0].leistungszeitraum = Leistungszeitraum(date(2026, 4, 1), date(2026, 4, 30))
    befunde = pruefe_rechnung(rechnung)
    assert any(b.schluessel == "rechnung.position_zeitraum_ausserhalb" for b in befunde)


def test_positions_zeitraum_innerhalb_des_kopfes_ist_zulaessig():
    """Gegenprobe: ein Positions-Zeitraum innerhalb des Kopf-Zeitraums loest keinen Befund aus."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen[0].leistungszeitraum = Leistungszeitraum(date(2026, 5, 10), date(2026, 5, 20))
    assert not any(
        b.schluessel == "rechnung.position_zeitraum_ausserhalb" for b in pruefe_rechnung(rechnung)
    )


def test_ausgabepruefung_meldet_positions_zeitraum_ausserhalb():
    """AK5: Auch die Ausgabe-Pflichtpruefung faengt den ungueltigen Positions-Zeitraum ab und
    verhindert damit eine KoSIT-invalide Ausgabe."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen[0].leistungszeitraum = Leistungszeitraum(date(2026, 4, 1), date(2026, 4, 30))
    befunde = pruefe_rechnung_fuer_ausgabe(rechnung)
    assert any(b.schluessel == "rechnung.position_zeitraum_ausserhalb" for b in befunde)


def test_warnung_bei_geaendertem_einzelpreis():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen[0].einzelpreis = Decimal("999.00")  # weicht vom Bestellwert ab
    assert any(
        w.schluessel == "rechnung.warnung_preis_abweichung"
        for w in warne_rechnung(rechnung, bestellung)
    )


def test_warnung_bei_bestellungsfremder_position():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen.append(
        Position("", "Sonderleistung", Decimal("1"), Decimal("100.00"), Decimal("100.00"))
    )
    assert any(
        w.schluessel == "rechnung.warnung_freie_position"
        for w in warne_rechnung(rechnung, bestellung)
    )


def test_keine_warnung_bei_unveraenderter_vorbelegung():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert warne_rechnung(rechnung, bestellung) == []


def test_anlegen_berechnet_summen_vergibt_id_und_persistiert(tmp_path):
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    pfad = tmp_path / "daten.json"
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = [
        Position("art-1", "IT-Beratung", Decimal("10"), Decimal("1200.00"), Decimal("12000.00")),
        Position("art-2", "Cutover", Decimal("3.5"), Decimal("1400.00"), Decimal("4900.00")),
    ]
    angelegt = lege_rechnung_an(bestand, bestellung, rechnung, pfad=pfad)
    assert angelegt.id  # nicht mehr leer
    assert angelegt.status is RechnungsStatus.ENTWURF
    assert angelegt.summen.netto == Decimal("16900.00")
    assert bestellung.rechnungen == [angelegt]
    # Jahres-Zähler fortgeschrieben
    assert bestand.einstellungen.naechste_rechnungsnummer["2026"] == 10002
    # persistiert und wieder ladbar
    wieder = lade(pfad)
    assert wieder.kunden[0].bestellungen[0].rechnungen[0].rechnungsnummer == "2026-10001"


def test_ueberschriebene_rechnungsnummer_laesst_zaehler_unveraendert(tmp_path):
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = [
        Position("art-1", "IT-Beratung", Decimal("10"), Decimal("1200.00"), Decimal("12000.00")),
    ]
    rechnung.rechnungsnummer = "2026-88888"  # Vorbelegung manuell überschrieben
    lege_rechnung_an(bestand, bestellung, rechnung, pfad=tmp_path / "d.json")
    # Überschreiben verbraucht keine automatische Nummer; der Zähler bleibt unangetastet (S-0042 AK3)
    assert bestand.einstellungen.naechste_rechnungsnummer.get("2026", 10001) == 10001


def test_anlegen_wirft_bei_pflichtverletzung(tmp_path):
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen = []  # keine Positionen
    with pytest.raises(ValidierungsFehler):
        lege_rechnung_an(bestand, bestellung, rechnung, pfad=tmp_path / "d.json")


def test_uebernahme_kunde_vor_bestellung_ohne_zusammenfuehrung():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    kunde.individuelle_felder = [
        IndividuellesFeld("Ref", True, "K"),
        IndividuellesFeld("Inaktiv", False, "x"),
    ]
    bestellung.individuelle_felder = [IndividuellesFeld("Ref", True, "B")]  # gleichnamig, aktiv
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    # aktive Kunde-Felder zuerst, dann Bestellung; inaktive nicht; gleichnamige beide (S-0039)
    assert [(f.name, f.wert) for f in rechnung.individuelle_felder] == [("Ref", "K"), ("Ref", "B")]


def test_uebernommene_felder_ohne_ruckwirkung():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    vorher = [(f.name, f.wert) for f in rechnung.individuelle_felder]
    for feld in kunde.individuelle_felder + bestellung.individuelle_felder:
        feld.name = "GEAENDERT"
        feld.wert = "GEAENDERT"
    # Kopie-Prinzip: spätere Stammdaten-Änderungen wirken nicht auf die Rechnung zurück (S-0039)
    assert [(f.name, f.wert) for f in rechnung.individuelle_felder] == vorher


# --- Eindeutigkeits-Warnung bei doppelter Rechnungsnummer (S-0045) ----------


def _lege_rechnung(bestand, kunde, bestellung, pfad):
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung)
    rechnung.positionen = [
        Position("art-1", "A", Decimal("1"), Decimal("1200.00"), Decimal("1200.00"))
    ]
    return lege_rechnung_an(bestand, bestellung, rechnung, pfad=pfad)


def test_dublette_wird_ueber_den_bestand_gefunden(tmp_path):
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    r1 = _lege_rechnung(bestand, kunde, bestellung, tmp_path / "d.json")  # "2026-..."
    # zweite, noch nicht angelegte Rechnung manuell auf dieselbe Nummer
    r2 = vorbelege_rechnung(bestand, kunde, bestellung)
    r2.rechnungsnummer = r1.rechnungsnummer
    treffer = finde_rechnungsnummer_dublette(bestand, r2)
    assert treffer is not None
    assert treffer.rechnung is r1
    assert treffer.kunde is kunde
    assert treffer.bestellung is bestellung


def test_keine_dublette_bei_eindeutiger_nummer(tmp_path):
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    _lege_rechnung(bestand, kunde, bestellung, tmp_path / "d.json")
    # nächste Vorbelegung trägt eine fortgeschriebene, eindeutige Nummer
    r2 = vorbelege_rechnung(bestand, kunde, bestellung)
    assert finde_rechnungsnummer_dublette(bestand, r2) is None


def test_dublette_selbst_ausnahme_ueber_id(tmp_path):
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    r1 = _lege_rechnung(bestand, kunde, bestellung, tmp_path / "d.json")
    # dieselbe angelegte Rechnung gegen den Bestand: sie ist über ihre id ausgenommen
    assert finde_rechnungsnummer_dublette(bestand, r1) is None


def test_dublette_beim_aendern_gegen_andere_rechnung(tmp_path):
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    pfad = tmp_path / "d.json"
    r1 = _lege_rechnung(bestand, kunde, bestellung, pfad)
    r2 = _lege_rechnung(bestand, kunde, bestellung, pfad)  # eindeutige, fortgeschriebene Nummer
    r2.rechnungsnummer = r1.rechnungsnummer  # auf die Nummer von r1 geändert -> Dublette
    treffer = finde_rechnungsnummer_dublette(bestand, r2)
    assert treffer is not None
    assert treffer.rechnung is r1  # r2 selbst bleibt ausgenommen


# --- Steuersatz und Normalsteuerfall (S-0079) -------------------------------


def test_vorbelegung_uebernimmt_steuersatz_aus_firma():
    """Im Normalsteuerfall belegt der Firmen-Standardsatz die Rechnung vor (S-0079).

    Der Seed-Kunde ist Reverse-Charge; für diese Aussage muss er es hier nicht sein. Bis
    4T-0160 prüfte der Test den Firmensatz an einem RC-Kunden und schrieb damit fest, was
    S-0023 AK6 gerade ausschließt.
    """
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    kunde.reverse_charge = False
    bestand.eigene_firma.standard_steuersatz = Decimal("19")
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.steuersatz == Decimal("19")


def test_vorbelegung_setzt_steuersatz_bei_reverse_charge_auf_null():
    """S-0023 AK6: Bei Reverse-Charge ist der Satz 0, auch wenn die Firma einen führt.

    Die Ausgabe erzwingt die 0 ohnehin; ohne diese Regel trüge das gespeicherte Feld einen
    Wert, den die Rechnung selbst nirgends verwendet.
    """
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    assert kunde.reverse_charge is True
    bestand.eigene_firma.standard_steuersatz = Decimal("19")
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.steuersatz == Decimal("0")


def test_pruefung_verlangt_steuersatz_im_normalfall():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.reverse_charge = False  # Normalfall
    rechnung.steuersatz = Decimal("0")  # aber kein Satz gesetzt
    rechnung.positionen[0].menge = Decimal("1")  # eine gültige Position
    assert any(b.feld == "steuersatz" for b in pruefe_rechnung(rechnung))


def test_reverse_charge_ohne_steuersatz_ist_zulaessig():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    # Seed-Kunde ist Reverse-Charge: Satz 0 löst keinen Steuersatz-Befund aus
    assert rechnung.reverse_charge is True
    assert not any(b.feld == "steuersatz" for b in pruefe_rechnung(rechnung))


# --- Vorbelegung der Zahlungsmodalitäten aus der Bestellung (S-0080) --------


def test_vorbelegung_uebernimmt_skonto_und_zahlungsfrist():
    """AK3: Die Rechnung holt sich die vertraglich vereinbarten Zahlungsmodalitäten aus der
    Bestellung, so wie sie es mit der Zahlungsbedingung bereits tut."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    bestellung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    bestellung.zahlungsfrist = 30
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.skonto == Skonto(tage=14, prozent=Decimal("2"))
    assert rechnung.zahlungsfrist == 30


def test_vorbelegung_ohne_skonto_an_der_bestellung():
    """AK3: Ohne Vereinbarung entsteht die Rechnung ohne Skonto."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    assert bestellung.skonto is None
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.skonto is None


def test_vorbelegtes_skonto_ist_eigene_kopie():
    """AK4: Die Rechnung hält eine eigene Kopie; eine spätere Änderung an der Bestellung
    wirkt nicht auf die bereits angelegte Rechnung zurück, und umgekehrt."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    bestellung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    bestellung.skonto.prozent = Decimal("3")  # Vertrag ändert sich später
    assert rechnung.skonto.prozent == Decimal("2")
    rechnung.skonto.tage = 7  # an der Rechnung angepasst
    assert bestellung.skonto.tage == 14


# --- Skonto (S-0051) --------------------------------------------------------


def test_skonto_wertebereich_wird_geprueft():
    """Tage und Prozent müssen größer 0 sein; die Befunde tragen eigene Feldschlüssel für
    die feld-nahe Anzeige."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.skonto = Skonto(tage=0, prozent=Decimal("0"))
    felder = [b.feld for b in pruefe_rechnung(rechnung)]
    assert "skonto_tage" in felder
    assert "skonto_prozent" in felder


def test_skonto_prozent_hat_obergrenze_hundert():
    """Der Prozentsatz ist fachlich auf 100 begrenzt (4T-0116); BR-DE-18 selbst ließe
    jeden vorzeichenlosen Satz zu. Die Grenze selbst ist noch zulässig."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("100"))
    assert pruefe_rechnung(rechnung) == []
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("100.01"))
    assert any(b.feld == "skonto_prozent" for b in pruefe_rechnung(rechnung))


def test_gueltiges_skonto_ohne_befund():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    assert pruefe_rechnung(rechnung) == []


def test_ohne_skonto_kein_befund():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.skonto is None  # Default: kein Skonto
    assert pruefe_rechnung(rechnung) == []


def test_skonto_wertebereich_auch_in_der_ausgabepruefung(beispiel_rechnung):
    """Auch die Ausgabeprüfung fängt ein ungültiges Skonto ab: Negative Tage brächen sonst
    die Regel BR-DE-18, die KoSIT als fatal wertet."""
    rechnung, _, _ = beispiel_rechnung
    rechnung.skonto = Skonto(tage=-1, prozent=Decimal("2"))
    assert any(b.feld == "skonto_tage" for b in pruefe_rechnung_fuer_ausgabe(rechnung))


def test_skonto_veraendert_summen_nicht(tmp_path):
    """Kein Vorab-Abzug: Das Skonto kürzt weder Positionen noch Summen oder Zahlbetrag
    (S-0051 AK3)."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.positionen[0].menge = Decimal("10")
    rechnung.positionen[0].gesamtpreis = Decimal("12000.00")
    rechnung.skonto = Skonto(tage=14, prozent=Decimal("2"))
    lege_rechnung_an(bestand, bestellung, rechnung, pfad=tmp_path / "daten.json")
    # Reverse-Charge-Fall: netto = brutto = Zahlbetrag, ungekürzt trotz Skonto
    assert rechnung.summen.netto == Decimal("12000.00")
    assert rechnung.summen.brutto == Decimal("12000.00")
    assert rechnung.positionen[0].gesamtpreis == Decimal("12000.00")


# --- Kaeuferpruefung und zweistufige Ausgabepruefung (S-0047/S-0049) --------


def _kaeufer(**abweichungen) -> Kaeufer:
    """Vollständiger CIUS-Käufer als Prüf-Kandidat; einzelne Felder überschreibbar."""
    daten = dict(
        name="Beispiel Kunde GmbH",
        adresse=Adresse(strasse="Musterstraße 5", plz="80331", ort="München", land="DE"),
        umsatzsteuer_id="DE123456789",
        kundennummer="D10002",
        email="rechnungseingang@example.org",
    )
    daten.update(abweichungen)
    return Kaeufer(**daten)


def test_pruefe_kaeufer_en_stufe_genuegt_bei_inaktiver_xrechnung():
    # Ohne Straße/PLZ/Ort/E-Mail, aber mit Name, Land und Kundennummer genügt die EN-Stufe
    kaeufer = _kaeufer(adresse=Adresse(strasse="", plz="", ort="", land="DE"), email="")
    assert pruefe_kaeufer(kaeufer, xrechnung_aktiv=False, reverse_charge=False) == []


def test_pruefe_kaeufer_cius_verlangt_adresse_und_email():
    kaeufer = _kaeufer(adresse=Adresse(strasse="", plz="", ort="", land="DE"), email="")
    felder = {b.feld for b in pruefe_kaeufer(kaeufer, xrechnung_aktiv=True, reverse_charge=False)}
    assert {"kaeufer_strasse", "kaeufer_plz", "kaeufer_ort", "kaeufer_email"} <= felder


def test_pruefe_kaeufer_reverse_charge_verlangt_ust_id():
    kaeufer = _kaeufer(umsatzsteuer_id="")
    felder = {b.feld for b in pruefe_kaeufer(kaeufer, xrechnung_aktiv=True, reverse_charge=True)}
    assert "kaeufer_umsatzsteuer_id" in felder


def test_pruefe_kaeufer_ungueltige_email_wird_gemeldet():
    kaeufer = _kaeufer(email="kein-email")
    felder = {b.feld for b in pruefe_kaeufer(kaeufer, xrechnung_aktiv=True, reverse_charge=False)}
    assert "kaeufer_email" in felder


def test_ausgabepruefung_vollstaendiger_fall_ist_leer(beispiel_rechnung):
    rechnung, _, _ = beispiel_rechnung  # vollständiger CIUS-Reverse-Charge-Fall
    assert pruefe_rechnung_fuer_ausgabe(rechnung) == []


def test_ausgabepruefung_inaktiver_schalter_ignoriert_cius(beispiel_rechnung):
    rechnung, _, _ = beispiel_rechnung
    rechnung.verkaeufer.xrechnung_aktiv = False
    # CIUS-Felder von Verkäufer und Käufer leeren: bei inaktivem Schalter kein Befund
    rechnung.verkaeufer.adresse.strasse = ""
    rechnung.verkaeufer.email = ""
    rechnung.verkaeufer.telefon = ""
    rechnung.verkaeufer.kontakt_name = ""
    rechnung.verkaeufer.bankverbindungen = []
    rechnung.kaeufer.adresse.strasse = ""
    rechnung.kaeufer.email = ""
    assert pruefe_rechnung_fuer_ausgabe(rechnung) == []


def test_ausgabepruefung_aktiver_schalter_meldet_verkaeufer_und_kaeufer(beispiel_rechnung):
    rechnung, _, _ = beispiel_rechnung
    rechnung.verkaeufer.xrechnung_aktiv = True
    rechnung.verkaeufer.email = ""  # Verkäufer-CIUS-Pflicht (BT-34)
    rechnung.kaeufer.email = ""  # Käufer-CIUS-Pflicht (BT-49)
    felder = {b.feld for b in pruefe_rechnung_fuer_ausgabe(rechnung)}
    assert "verkaeufer_email" in felder
    assert "kaeufer_email" in felder


# --- Bankverbindung nach Rechnungswährung (S-0065, 4T-0135) ----------------


def test_ausgabepruefung_meldet_fehlende_bankverbindung_bei_xrechnung(beispiel_rechnung):
    """AK4: Bei aktiver XRechnung ist eine gewählte Bankverbindung Pflicht für die Ausgabe."""
    rechnung, _, _ = beispiel_rechnung
    rechnung.bankverbindung = None  # keine Wahl
    assert any(b.feld == "bankverbindung" for b in pruefe_rechnung_fuer_ausgabe(rechnung))


def test_ausgabepruefung_ohne_xrechnung_erlaubt_fehlende_bankverbindung(beispiel_rechnung):
    """AK5: Bei inaktiver XRechnung ist die Bankverbindung nicht Pflicht; der Export fällt
    auf die erste zurück."""
    rechnung, _, _ = beispiel_rechnung
    rechnung.verkaeufer.xrechnung_aktiv = False
    rechnung.bankverbindung = None
    assert not any(b.feld == "bankverbindung" for b in pruefe_rechnung_fuer_ausgabe(rechnung))


# --- Rechnungssprache aus der Kaskade (S-0060 AK1, S-0058 AK3) --------------


def test_vorbelegung_ohne_gesetzte_sprache_ist_deutsch():
    """Beide Ebenen erben (None): Rückfall Deutsch."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    assert kunde.rechnungssprache is None and bestellung.rechnungssprache is None
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.rechnungssprache == "de"


def test_vorbelegung_uebernimmt_die_aufgeloeste_sprache():
    """Die Rechnung erhält die Sprache der speziellsten gesetzten Ebene."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    kunde.rechnungssprache = "en"
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.rechnungssprache == "en"

    bestellung.rechnungssprache = "fr"  # speziellere Ebene gewinnt
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    assert rechnung.rechnungssprache == "fr"


def test_vorbelegte_sprache_ist_eine_eigene_kopie():
    """Kopie-Prinzip: Eine Änderung an der Rechnung wirkt nicht auf die Stammdaten zurück."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    kunde.rechnungssprache = "en"
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.rechnungssprache = "it"
    assert kunde.rechnungssprache == "en"
    assert bestellung.rechnungssprache is None


# --- Obergrenzen-Warnung (S-0024 AK6, 4T-0160) ------------------------------


def _rechnung_mit(bestand, kunde, bestellung, positionen, *, id: str = ""):
    """Eine vorbelegte Rechnung mit gesetzten Positionen; `id` markiert eine bestehende."""
    rechnung = vorbelege_rechnung(bestand, kunde, bestellung, heute=date(2026, 7, 10))
    rechnung.id = id
    rechnung.positionen = positionen
    return rechnung


def _position(artikel_id: str, menge: str, einzelpreis: str = "100.00") -> Position:
    gesamt = Decimal(menge) * Decimal(einzelpreis)
    return Position(artikel_id, "A", Decimal(menge), Decimal(einzelpreis), gesamt)


def test_ohne_obergrenzen_keine_warnung():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    for gueltiger in bestellung.gueltige_artikel:
        gueltiger.obergrenze = None
    bestellung.gesamt_hoechstbetrag = None
    rechnung = _rechnung_mit(bestand, kunde, bestellung, [_position("art-1", "999")])
    assert obergrenzen_warnungen(rechnung, bestellung) == []


def test_mengen_obergrenze_wird_gemeldet():
    """Der Seed führt bei art-1 eine Mengen-Obergrenze von 20."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = _rechnung_mit(bestand, kunde, bestellung, [_position("art-1", "21")])
    befunde = obergrenzen_warnungen(rechnung, bestellung)
    assert [b.schluessel for b in befunde] == ["rechnung.warnung_obergrenze_artikel"]
    assert befunde[0].werte["summe"] == Decimal("21")
    assert befunde[0].werte["grenze"] == Decimal("20")


def test_mengen_obergrenze_genau_erreicht_ist_keine_ueberschreitung():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = _rechnung_mit(bestand, kunde, bestellung, [_position("art-1", "20")])
    assert obergrenzen_warnungen(rechnung, bestellung) == []


def test_verbrauch_frueherer_rechnungen_zaehlt_mit():
    """Zwei Rechnungen à 15 überschreiten die Grenze von 20, jede für sich nicht."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    frueher = _rechnung_mit(bestand, kunde, bestellung, [_position("art-1", "15")], id="r-1")
    bestellung.rechnungen.append(frueher)
    neu = _rechnung_mit(bestand, kunde, bestellung, [_position("art-1", "15")])
    befunde = obergrenzen_warnungen(neu, bestellung)
    assert [b.schluessel for b in befunde] == ["rechnung.warnung_obergrenze_artikel"]
    assert befunde[0].werte["summe"] == Decimal("30")


def test_eigene_fassung_zaehlt_beim_aendern_nicht_doppelt():
    """Die zu ändernde Rechnung liegt schon in der Bestellung; sonst wäre jede Änderung
    einer Rechnung mit Grenzwert sofort eine Überschreitung."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    bestehend = _rechnung_mit(bestand, kunde, bestellung, [_position("art-1", "20")], id="r-1")
    bestellung.rechnungen.append(bestehend)
    # Dieselbe Rechnung erneut geöffnet (die Maske arbeitet auf einer Kopie, gleiche id).
    kopie = _rechnung_mit(bestand, kunde, bestellung, [_position("art-1", "20")], id="r-1")
    assert obergrenzen_warnungen(kopie, bestellung) == []


def test_gesamt_hoechstbetrag_wird_gemeldet():
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    for gueltiger in bestellung.gueltige_artikel:
        gueltiger.obergrenze = None
    bestellung.gesamt_hoechstbetrag = Decimal("1000.00")
    rechnung = _rechnung_mit(
        bestand, kunde, bestellung, [_position("art-1", "11", "100.00")]
    )
    befunde = obergrenzen_warnungen(rechnung, bestellung)
    assert [b.schluessel for b in befunde] == ["rechnung.warnung_gesamt_hoechstbetrag"]
    assert befunde[0].werte["summe"] == Decimal("1100.00")


def test_beide_ebenen_melden_gemeinsam():
    """Gesamt-Höchstbetrag und Artikel-Obergrenze sind frei kombinierbar (S-0017 AK7)."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    bestellung.gesamt_hoechstbetrag = Decimal("1000.00")
    rechnung = _rechnung_mit(
        bestand, kunde, bestellung, [_position("art-1", "21", "100.00")]
    )
    schluessel = [b.schluessel for b in obergrenzen_warnungen(rechnung, bestellung)]
    assert schluessel == [
        "rechnung.warnung_gesamt_hoechstbetrag",
        "rechnung.warnung_obergrenze_artikel",
    ]


def test_warne_rechnung_traegt_die_obergrenzen_warnung_mit():
    """Die Warnung erscheint auf demselben Weg wie die übrigen (Dialog vor dem Speichern)."""
    bestand, kunde, bestellung = _seed_kunde_bestellung()
    rechnung = _rechnung_mit(
        bestand, kunde, bestellung, [_position("art-1", "21", "1200.00")]
    )
    schluessel = [b.schluessel for b in warne_rechnung(rechnung, bestellung)]
    assert "rechnung.warnung_obergrenze_artikel" in schluessel


# --- Grenzbeträge in der Summenbildung (4T-0168) ----------------------------


def test_summen_sehr_grosser_betrag_mit_steuer():
    """Ein sehr großer Betrag bleibt in Steuer und Brutto exakt (Decimal statt Gleitkomma)."""
    positionen = [
        Position("art-1", "A", Decimal("1000000"), Decimal("9999.99"), Decimal("9999990000.00"))
    ]
    summen = berechne_summen(positionen, reverse_charge=False, steuersatz=Decimal("19"))
    assert summen.netto == Decimal("9999990000.00")
    assert summen.steuer == Decimal("1899998100.00")  # 9999990000.00 × 19 %
    assert summen.brutto == Decimal("11899988100.00")
