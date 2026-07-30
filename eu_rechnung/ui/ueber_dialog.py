"""Über-Dialog mit den Kerninformationen zur Anwendung (S-0077).

Zeigt Produktname, Zweck, Version, Herausgeber, Copyright und die verwendeten
Open-Source-Komponenten mit ihren Lizenzen. Der Hinweis auf die Komponenten erfüllt deren
Namensnennungspflichten, etwa die Attributionspflicht der Apache-2.0-Lizenz von drafthorse;
diese Pflicht besteht unabhängig von der Lizenz der Anwendung selbst, die erst mit der
Paketierung festgelegt wird.

Produktname, Herausgeber und Copyright-Jahr stammen aus der Paket-Identität
(`eu_rechnung/__init__.py`), die Version ebenfalls; sie ist dort die einzige Quelle, aus der
auch `pyproject.toml` liest.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from eu_rechnung import COPYRIGHT_JAHR, HERAUSGEBER, PRODUKTNAME, __version__
from eu_rechnung.ui.sprache import ui_text

# Die eingebundenen Fremdkomponenten mit ihren Lizenzen. Die Angaben sind aus den
# Paket-Metadaten der installierten Distributionen erhoben und in Architektur.md verankert;
# sie stehen hier fest, statt zur Laufzeit über `importlib.metadata` gelesen zu werden. Zwei
# Gründe: Die Metadaten liegen in der späteren `.exe` nicht verlässlich vor, und die
# Lizenzangabe steckt je Paket in einem anderen Feld (`License`, `License-Expression` oder
# Classifier), teils als Volltext. Bei einer Änderung der Abhängigkeiten in `pyproject.toml`
# ist diese Liste mitzuziehen.
_KOMPONENTEN: tuple[tuple[str, str], ...] = (
    ("factur-x", "BSD-3-Clause"),
    ("drafthorse", "Apache-2.0"),
    ("ReportLab", "BSD-3-Clause"),
    ("pypdf", "BSD-3-Clause"),
    ("jsonschema", "MIT"),
    ("PySide6 (Qt)", "LGPL-3.0"),
)


class UeberDialog(QDialog):
    """Modaler Info-Dialog zur Anwendung, erreichbar über „Hilfe → Über…"."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Texte beim Aufbau holen, nicht in Modul-Konstanten: Die UI-Sprache steht erst
        # nach dem Anwendungsstart fest (siehe ui/sprache.py).
        self.setWindowTitle(ui_text("ueber.titel"))
        # Der Zweck ist ein ganzer Satz. Ein QLabel meldet ohne Umbruch die volle Satzbreite
        # als Wunschgröße und zöge den Dialog entsprechend in die Breite; deshalb unten
        # Wortumbruch und hier eine Obergrenze, an der der Satz bricht. Die Grenze gilt für
        # alle fünf Sprachen, deren Sätze unterschiedlich lang sind.
        self.setMaximumWidth(520)
        layout = QVBoxLayout(self)

        name = QLabel(PRODUKTNAME)  # Eigenname, unübersetzt
        schrift = name.font()
        schrift.setBold(True)
        name.setFont(schrift)
        layout.addWidget(name)
        zweck = QLabel(ui_text("ueber.zweck"))
        zweck.setWordWrap(True)
        layout.addWidget(zweck)

        layout.addSpacing(8)
        layout.addWidget(QLabel(ui_text("ueber.version", version=__version__)))
        layout.addWidget(QLabel(ui_text("ueber.herausgeber", herausgeber=HERAUSGEBER)))
        layout.addWidget(
            QLabel(
                ui_text("ueber.copyright", jahr=COPYRIGHT_JAHR, herausgeber=HERAUSGEBER)
            )
        )

        layout.addSpacing(8)
        layout.addWidget(QLabel(ui_text("ueber.komponenten")))
        # Namen und Lizenzbezeichnungen sind Eigennamen und bleiben in jeder Sprache gleich.
        layout.addWidget(
            QLabel("\n".join(f"{name} — {lizenz}" for name, lizenz in _KOMPONENTEN))
        )

        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        layout.addWidget(knoepfe)
