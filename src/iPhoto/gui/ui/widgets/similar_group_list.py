"""Scrollable list of similar photo groups."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class PhashProgressWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        self._label = QLabel(self.tr("Computing perceptual hashes..."))
        layout.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setMinimum(0)
        layout.addWidget(self._bar, 1)

    def set_progress(self, completed: int, total: int) -> None:
        self._bar.setMaximum(max(total, 1))
        self._bar.setValue(completed)
        self._label.setText(
            self.tr("Perceptual hash: {0} / {1}").format(completed, total)
        )
        self.setVisible(completed < total)


class SimilarityThresholdWidget(QWidget):
    thresholdChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        layout.addWidget(QLabel(self.tr("Similarity threshold:")))
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(2)
        self._slider.setMaximum(16)
        self._slider.setValue(8)
        self._slider.setTickInterval(1)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.valueChanged.connect(self._on_changed)
        layout.addWidget(self._slider, 1)

        self._pct_label = QLabel("87%")
        layout.addWidget(self._pct_label)

    def _on_changed(self, value: int) -> None:
        pct = max(0, round((1 - value / 64) * 100))
        self._pct_label.setText(f"{pct}%")
        self.thresholdChanged.emit(value)


class SimilarGroupListWidget(QScrollArea):
    selectionChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(16)

        self._empty_label = QLabel(self.tr("No similar photos found."))
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


class SimilarGroupCard(QFrame):
    assetToggled = Signal(str, bool)

    def __init__(
        self,
        group_id: str,
        assets: list,
        recommended_rel: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("similarGroupCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._group_id = group_id
        self._marked_for_delete: set[str] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)

        header = QLabel(
            self.tr("Similar group ({0} photos)").format(len(assets))
        )
        hf = header.font()
        hf.setBold(True)
        header.setFont(hf)
        root.addWidget(header)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(12)
        from .duplicate_group_card import DuplicateAssetCard

        self._asset_cards: list[DuplicateAssetCard] = []
        for asset in assets:
            card = DuplicateAssetCard(
                asset,
                is_recommended=(asset.rel == recommended_rel),
            )
            card.toggled.connect(self._on_toggled)
            row_layout.addWidget(card)
            self._asset_cards.append(card)
        row_layout.addStretch()
        root.addLayout(row_layout)

        self.setStyleSheet(
            "#similarGroupCard { border: 1px solid palette(mid); border-radius: 6px; background: palette(base); }"
        )

    @property
    def marked_for_delete(self) -> set[str]:
        return set(self._marked_for_delete)

    def _on_toggled(self, rel: str, marked: bool) -> None:
        if marked:
            self._marked_for_delete.add(rel)
        else:
            self._marked_for_delete.discard(rel)
        self.assetToggled.emit(rel, marked)
