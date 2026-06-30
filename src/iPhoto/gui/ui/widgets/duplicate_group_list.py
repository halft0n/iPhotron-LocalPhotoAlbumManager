"""Scrollable list of duplicate groups."""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


class DuplicateGroupListWidget(QScrollArea):
    """Vertical scroll area holding DuplicateGroupCard instances."""

    selectionChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setObjectName("duplicateGroupList")

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(16)

        self._empty_label = QLabel(self.tr("No duplicate photos found."))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._empty_label)
        self._layout.addStretch()

        self.setWidget(self._container)
        self._cards: list = []

    def clear_groups(self) -> None:
        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._empty_label.setVisible(True)

    def add_group_card(self, card: QWidget) -> None:
        self._empty_label.setVisible(False)
        idx = self._layout.count() - 1
        self._layout.insertWidget(idx, card)
        self._cards.append(card)

    def group_cards(self) -> list:
        return list(self._cards)
