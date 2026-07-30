"""Wächter gegen hart verdrahtete Oberflächentexte (4T-0171).

Meldungs- und Dialogtexte müssen aus dem Sprachkatalog kommen (`ui_text`/`befund_text`),
sonst bleiben sie in den vier nicht-deutschen Oberflächensprachen deutsch. Genau dieser Bruch
war der Anlass: zehn Stellen in `rechnungen_reiter.py` und `bestellung_reiter.py`, die den
Katalog umgingen. Dieser Quelltext-Scan hält ihn fern, indem er QMessageBox-, QFileDialog-
und `setWindowTitle`-Aufrufe daraufhin prüft, dass ihr Titel- und Text-Argument kein
deutschsprachiges String-Literal ist.

Der Scan liest den AST, nicht den laufenden Code: Er erfasst auch Zweige, die kein Test je
auslöst, und meldet eine Rückkehr des Bruchs sofort statt erst beim fremdsprachigen Anwender.
"""

from __future__ import annotations

import ast
import pathlib

_UI = pathlib.Path(__file__).resolve().parent.parent / "eu_rechnung" / "ui"

# Aufrufe, deren Titel-/Text-Argumente aus dem Katalog kommen müssen:
# Attribut-Name -> Indizes der zu prüfenden Positionsargumente.
_MELDUNGEN = {"information": (1, 2), "warning": (1, 2), "question": (1, 2), "critical": (1, 2)}
_DATEIDIALOGE = {"getExistingDirectory": (1,), "getOpenFileName": (1,), "getSaveFileName": (1,)}


def _ist_wort_literal(knoten: ast.AST) -> bool:
    """Ein String-Literal mit Buchstaben; erlaubt bleiben reine Format-/Steuerzeichen.

    Geprüft wird nur das Argument selbst und einfache Zusammensetzungen (`a + b`,
    `x if c else y`), nicht der Inhalt von Funktionsaufrufen: `ui_text("schluessel")` trägt
    zwar ein Literal, aber der Schlüssel ist kein Anzeigetext. `"\\n\\n" + ui_text(...)` bleibt
    erlaubt, weil das Literal keinen Buchstaben trägt.
    """
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
        return any(z.isalpha() for z in knoten.value)
    if isinstance(knoten, ast.JoinedStr):  # f-String: nur die festen Textteile zählen
        return any(
            isinstance(teil, ast.Constant)
            and isinstance(teil.value, str)
            and any(z.isalpha() for z in teil.value)
            for teil in knoten.values
        )
    if isinstance(knoten, ast.BinOp):
        return _ist_wort_literal(knoten.left) or _ist_wort_literal(knoten.right)
    if isinstance(knoten, ast.IfExp):
        return _ist_wort_literal(knoten.body) or _ist_wort_literal(knoten.orelse)
    return False


def _gepruefte_aufrufe() -> list[tuple[str, int, str, tuple[int, ...]]]:
    """Alle relevanten Aufrufe als (modul, zeile, art, zu prüfende Argument-Indizes)."""
    treffer = []
    for pfad in sorted(_UI.glob("*.py")):
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)):
                continue
            attr = knoten.func.attr
            ziel = getattr(knoten.func.value, "id", None)
            if ziel == "QMessageBox" and attr in _MELDUNGEN:
                treffer.append((pfad.name, knoten.lineno, f"QMessageBox.{attr}", _MELDUNGEN[attr]))
            elif ziel == "QFileDialog" and attr in _DATEIDIALOGE:
                treffer.append((pfad.name, knoten.lineno, f"QFileDialog.{attr}", _DATEIDIALOGE[attr]))
            elif attr == "setWindowTitle":
                treffer.append((pfad.name, knoten.lineno, "setWindowTitle", (0,)))
    return treffer


def _verstoesse() -> list[str]:
    verstoesse = []
    for pfad in sorted(_UI.glob("*.py")):
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)):
                continue
            attr = knoten.func.attr
            ziel = getattr(knoten.func.value, "id", None)
            if ziel == "QMessageBox" and attr in _MELDUNGEN:
                indizes = _MELDUNGEN[attr]
            elif ziel == "QFileDialog" and attr in _DATEIDIALOGE:
                indizes = _DATEIDIALOGE[attr]
            elif attr == "setWindowTitle":
                indizes = (0,)
            else:
                continue
            for idx in indizes:
                if len(knoten.args) > idx and _ist_wort_literal(knoten.args[idx]):
                    verstoesse.append(f"{pfad.name}:{knoten.lineno} {ziel or ''}.{attr} Argument {idx}")
    return verstoesse


def test_der_scan_findet_aufrufe():
    """Absicherung des Scans selbst: Ein leerer Scan bestünde den Test darunter blind."""
    assert len(_gepruefte_aufrufe()) > 30


def test_keine_hartkodierten_meldungs_und_dialogtexte():
    """AK4: Titel- und Textargumente kommen aus dem Katalog, nicht als deutsches Literal."""
    verstoesse = _verstoesse()
    assert not verstoesse, "Hart verdrahtete Oberflächentexte:\n" + "\n".join(verstoesse)


def test_der_scan_schlaegt_bei_einem_literal_an():
    """Belegt statt behauptet: Gegen einen synthetischen Verstoß meldet der Scan an."""
    quelle = 'QMessageBox.information(self, "Hinweis", "Bitte eine Rechnung wählen.")'
    aufruf = ast.parse(quelle).body[0].value
    assert _ist_wort_literal(aufruf.args[1])  # Titel-Literal
    assert _ist_wort_literal(aufruf.args[2])  # Text-Literal
    # Der Katalog-Weg dagegen ist sauber:
    sauber = ast.parse('QMessageBox.information(self, ui_text("a.b"), ui_text("c.d"))').body[0].value
    assert not _ist_wort_literal(sauber.args[1])
    assert not _ist_wort_literal(sauber.args[2])
    # Zusammensetzung aus Katalogtext und reinem Trennzeichen bleibt erlaubt:
    kombi = ast.parse('QMessageBox.question(self, ui_text("t"), ui_text("f", n=x) + "\\n\\n")').body[0].value
    assert not _ist_wort_literal(kombi.args[2])
