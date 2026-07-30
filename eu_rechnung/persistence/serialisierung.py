"""Generische, typgesteuerte (De)serialisierung zwischen Domänen-dataclasses
und JSON-kompatiblen Strukturen.

Statt to_dict/from_dict je Klasse arbeitet diese Schicht rekursiv über
`dataclasses.fields` und die aufgelösten Typhints. Sondertypen werden bewusst
formatiert: Decimal als String (exakte Geldbeträge), date/datetime als ISO-
String (datetime in UTC mit Z-Suffix, project-standards Abschnitt H), Enum
über den Wert.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum


def zu_json(obj):
    """Wandelt ein Domänenobjekt rekursiv in JSON-kompatible Strukturen."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: zu_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Decimal):
        return str(obj)
    # datetime vor date prüfen, da datetime eine Subklasse von date ist.
    if isinstance(obj, datetime):
        dt = obj.astimezone(timezone.utc) if obj.tzinfo else obj
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [zu_json(x) for x in obj]
    if isinstance(obj, dict):
        return {k: zu_json(v) for k, v in obj.items()}
    return obj  # str, int, float, bool, None


def von_json(typ, daten):
    """Baut aus JSON-Daten rekursiv eine Instanz des erwarteten Typs `typ`."""
    origin = typing.get_origin(typ)

    # Optional[X] bzw. X | None
    if origin is typing.Union or origin is types.UnionType:
        if daten is None:
            return None
        nicht_none = [a for a in typing.get_args(typ) if a is not type(None)]
        return von_json(nicht_none[0], daten)

    # list[X]
    if origin is list:
        (inner,) = typing.get_args(typ)
        return [von_json(inner, x) for x in daten]

    # dict[K, V]
    if origin is dict:
        _, v_typ = typing.get_args(typ)
        return {k: von_json(v_typ, v) for k, v in daten.items()}

    # Verschachtelte dataclass
    if dataclasses.is_dataclass(typ):
        hints = typing.get_type_hints(typ)
        werte = {
            f.name: von_json(hints[f.name], daten[f.name])
            for f in dataclasses.fields(typ)
            if f.name in daten
        }
        return typ(**werte)

    # Sondertypen
    if typ is Decimal:
        return Decimal(str(daten))
    if typ is datetime:
        return datetime.fromisoformat(daten)
    if typ is date:
        return date.fromisoformat(daten)
    if isinstance(typ, type) and issubclass(typ, Enum):
        return typ(daten)

    return daten  # primitive (str, int, float, bool)
