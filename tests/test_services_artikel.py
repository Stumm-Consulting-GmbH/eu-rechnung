"""Tests der Artikel-Validierung und Referenzprüfung (services/artikel.py)."""

from decimal import Decimal

from eu_rechnung.domain import Artikel, Preis
from eu_rechnung.services import artikel_referenziert, erzeuge_seed, pruefe_artikel


def _artikel(name: str, *, betrag: str = "100.00", waehrung: str = "EUR", id: str = "") -> Artikel:
    return Artikel(
        id=id, artikelname=name, vorschlagspreis=Preis(Decimal(betrag), waehrung)
    )


def test_pruefe_artikel_gueltig_ist_leer():
    befunde = pruefe_artikel(_artikel("Ganz neuer Artikel"), erzeuge_seed())
    assert befunde == []


def test_pruefe_artikel_name_ist_pflicht():
    befunde = pruefe_artikel(_artikel("   "), erzeuge_seed())
    assert any(b.feld == "name" for b in befunde)


def test_pruefe_artikel_waehrung_ist_pflicht():
    befunde = pruefe_artikel(_artikel("Neu", waehrung="  "), erzeuge_seed())
    assert any(b.feld == "waehrung" for b in befunde)


def test_pruefe_artikel_betrag_nicht_negativ():
    befunde = pruefe_artikel(_artikel("Neu", betrag="-5.00"), erzeuge_seed())
    assert any(b.feld == "betrag" for b in befunde)


def test_pruefe_artikel_name_eindeutig_ohne_gross_klein_und_getrimmt():
    bestand = erzeuge_seed()
    name = bestand.artikel[0].artikelname
    befunde = pruefe_artikel(_artikel(f"  {name.upper()} "), bestand)
    assert any(b.feld == "name" for b in befunde)


def test_pruefe_artikel_selbst_ist_von_dublette_ausgenommen():
    bestand = erzeuge_seed()
    vorhanden = bestand.artikel[0]
    befunde = pruefe_artikel(
        _artikel(vorhanden.artikelname, id=vorhanden.id),
        bestand,
        ignoriere_id=vorhanden.id,
    )
    assert all(b.feld != "name" for b in befunde)


def test_artikel_referenziert_erkennt_bestell_referenz():
    bestand = erzeuge_seed()  # Seed: art-1 und art-2 hängen in der Bestellung
    assert artikel_referenziert(bestand, "art-1") is True
    assert artikel_referenziert(bestand, "gibt-es-nicht") is False


# --- Währung stammt aus der Währungstabelle (S-0005 AK4, 4T-0159) -----------


def test_pruefe_artikel_waehrung_muss_in_der_waehrungsliste_stehen():
    """AK4: „Pflicht" allein genügt nicht, die Währung muss aus der Tabelle stammen."""
    bestand = erzeuge_seed()
    assert "XYZ" not in bestand.einstellungen.waehrungsliste
    befunde = pruefe_artikel(_artikel("Neu", waehrung="XYZ"), bestand)
    assert [b.schluessel for b in befunde] == ["artikel.waehrung_nicht_in_liste"]
    assert befunde[0].feld == "waehrung"
    assert befunde[0].werte == {"code": "XYZ"}


def test_pruefe_artikel_waehrung_aus_der_liste_ist_gueltig():
    bestand = erzeuge_seed()
    waehrung = bestand.einstellungen.waehrungsliste[0]
    assert pruefe_artikel(_artikel("Neu", waehrung=waehrung), bestand) == []


def test_pruefe_artikel_leere_waehrung_meldet_nur_das_fehlen():
    """Eine leere Währung fehlt, sie steht nicht „nicht in der Liste": ein Befund, nicht zwei."""
    befunde = pruefe_artikel(_artikel("Neu", waehrung="  "), erzeuge_seed())
    assert [b.schluessel for b in befunde] == ["allgemein.fehlt_waehrung"]
