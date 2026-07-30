"""JSON-Schema des Datenbestands für die Strukturprüfung beim Laden.

Bewusst strukturell gehalten: Top-Level, schema_version, Haupt-Entitäten und
deren Kern-required-Felder. Wertebereiche prüfen Domäne und Services, nicht
dieses Schema. Zusätzliche Felder bleiben erlaubt, damit künftige Erweiterungen
die Validierung bestehender Dateien nicht brechen.
"""

_ADRESSE = {
    "type": "object",
    "required": ["strasse", "plz", "ort", "land"],
}

DATENBESTAND_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schema_version", "eigene_firma", "einstellungen", "artikel", "kunden"],
    "properties": {
        "schema_version": {"type": "integer", "const": 3},
        "eigene_firma": {
            "type": "object",
            "required": ["name", "adresse", "mehrwertsteuer_id", "bankverbindungen"],
            "properties": {"adresse": _ADRESSE},
        },
        "einstellungen": {
            "type": "object",
            "required": [
                "standard_anschreibentext",
                "naechste_rechnungsnummer",
                "naechste_debitornummer",
            ],
        },
        "artikel": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "artikelname", "vorschlagspreis"],
            },
        },
        "kunden": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "kundennummer",
                    "name",
                    "adresse",
                    "reverse_charge",
                    "bestellungen",
                ],
                "properties": {
                    "adresse": _ADRESSE,
                    "bestellungen": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "bestellnummer", "rechnungen"],
                            "properties": {
                                "rechnungen": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": [
                                            "id",
                                            "rechnungsnummer",
                                            "rechnungsdatum",
                                            "verkaeufer",
                                            "kaeufer",
                                            "reverse_charge",
                                            "summen",
                                        ],
                                    },
                                }
                            },
                        },
                    },
                },
            },
        },
    },
}
