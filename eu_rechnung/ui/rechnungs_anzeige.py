"""Anzeige-Formatierung des Ausgabestands einer Rechnung (gemeinsamer UI-Baustein).

Status und Erzeugungs-Zeitstempel erscheinen an drei Stellen: in der Rechnungs-Liste, in der
Rechnungsübersicht und seit 4T-0160 auch in der Detailmaske (S-0024 AK2, S-0032 AK4). Die
Formatierung liegt deshalb hier, nach dem Muster von `betrag.py`, statt ein drittes Mal
abgeschrieben zu werden.

**Der Zeitstempel folgt der UI-Sprache.** Er wird UTC gehalten und nur für die Anzeige in die
lokale Zeitzone umgerechnet (Zeitstempel-Konvention: lokale Zeit nur in der UI); das Muster
kommt aus den Sprachdateien (`format.zeitstempel`), nicht aus dem Code. Die Rechnungs-Liste
hatte es bis 4T-0160 fest verdrahtet und zeigte deshalb auch in einer englischen Oberfläche
das deutsche Format; die Übersicht machte es bereits richtig.
"""

from __future__ import annotations

from datetime import datetime

from eu_rechnung.domain import RechnungsStatus
from eu_rechnung.ui.sprache import ui_text


def status_text(status: RechnungsStatus) -> str:
    """Der Rechnungsstatus in der UI-Sprache."""
    return ui_text(f"rechnung.status_{status.name.lower()}")


def erzeugt_text(stempel: datetime | None, *, leer: str = "") -> str:
    """Der Erzeugungs-Zeitstempel in lokaler Zeit und UI-Sprache.

    `leer` ist die Darstellung einer nie erzeugten Rechnung: In der Liste und der Maske ein
    Gedankenstrich, in der Übersicht eine leere Zelle.
    """
    if not stempel:
        return leer
    return stempel.astimezone().strftime(ui_text("format.zeitstempel"))
