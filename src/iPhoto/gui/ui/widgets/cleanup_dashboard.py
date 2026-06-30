"""Cleanup dashboard -- top-level page with summary cards and tabbed content."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ...viewmodels.cleanup_viewmodel import CleanupViewModel


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


class _SummaryCard(QWidget):
    clicked = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cleanupSummaryCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self._title = QLabel(title)
        self._title.setObjectName("summaryCardTitle")
        font = self._title.font()
        font.setPointSize(font.pointSize() + 1)
        font.setBold(True)
        self._title.setFont(font)
        layout.addWidget(self._title)

        self._detail = QLabel("")
        self._detail.setObjectName("summaryCardDetail")
        layout.addWidget(self._detail)

        self._sub = QLabel("")
        self._sub.setObjectName("summaryCardSub")
        layout.addWidget(self._sub)

        self.setStyleSheet(
            """
            #cleanupSummaryCard {
                border: 1px solid palette(mid);
                border-radius: 8px;
                background: palette(base);
            }
            #cleanupSummaryCard:hover {
                border-color: palette(highlight);
            }
            """
        )

    def set_detail(self, text: str) -> None:
        self._detail.setText(text)

    def set_sub(self, text: str) -> None:
        self._sub.setText(text)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class CleanupDashboardWidget(QWidget):
    """Main cleanup page with summary cards and tabbed sections."""

    deleteRequested = Signal(list)
    tabChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cleanupDashboard")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 0)
        root.setSpacing(12)

        header = QLabel(self.tr("Cleanup"))
        header.setObjectName("cleanupHeader")
        hfont = header.font()
        hfont.setPointSize(hfont.pointSize() + 4)
        hfont.setBold(True)
        header.setFont(hfont)
        root.addWidget(header)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self._dup_card = _SummaryCard(self.tr("Exact Duplicates"))
        self._sim_card = _SummaryCard(self.tr("Similar Photos"))
        self._ss_card = _SummaryCard(self.tr("Screenshots"))
        cards_layout.addWidget(self._dup_card)
        cards_layout.addWidget(self._sim_card)
        cards_layout.addWidget(self._ss_card)
        cards_layout.addStretch()
        root.addLayout(cards_layout)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.currentChanged.connect(self.tabChanged.emit)
        root.addWidget(self._tabs, 1)

        self._dup_card.clicked.connect(lambda: self._tabs.setCurrentIndex(0))
        self._sim_card.clicked.connect(lambda: self._tabs.setCurrentIndex(1))
        self._ss_card.clicked.connect(lambda: self._tabs.setCurrentIndex(2))

        self._batch_bar = _BatchActionBar()
        self._batch_bar.deleteClicked.connect(lambda: self.deleteRequested.emit([]))
        root.addWidget(self._batch_bar)

        self._dup_tab_widget: QWidget | None = None
        self._sim_tab_widget: QWidget | None = None
        self._ss_tab_widget: QWidget | None = None

    @property
    def tabs(self) -> QTabWidget:
        return self._tabs

    @property
    def batch_bar(self) -> "_BatchActionBar":
        return self._batch_bar

    def set_duplicate_tab(self, widget: QWidget) -> None:
        if self._dup_tab_widget is not None:
            self._tabs.removeTab(0)
        self._dup_tab_widget = widget
        self._tabs.insertTab(0, widget, self.tr("Exact Duplicates"))

    def set_similar_tab(self, widget: QWidget) -> None:
        idx = 1 if self._dup_tab_widget is not None else 0
        if self._sim_tab_widget is not None:
            self._tabs.removeTab(idx)
        self._sim_tab_widget = widget
        self._tabs.insertTab(idx, widget, self.tr("Similar Photos"))

    def set_screenshot_tab(self, widget: QWidget) -> None:
        idx = self._tabs.count()
        if self._ss_tab_widget is not None:
            self._tabs.removeTab(idx - 1)
        self._ss_tab_widget = widget
        self._tabs.addTab(widget, self.tr("Screenshots"))

    def update_summary(
        self,
        dup_groups: int,
        dup_assets: int,
        dup_wasted: int,
        sim_groups: int,
        sim_assets: int,
        ss_count: int,
        ss_bytes: int,
    ) -> None:
        self._dup_card.set_detail(
            self.tr("{0} groups / {1} photos").format(dup_groups, dup_assets)
        )
        self._dup_card.set_sub(
            self.tr("Free up {0}").format(_format_bytes(dup_wasted))
        )

        self._sim_card.set_detail(
            self.tr("{0} groups / {1} photos").format(sim_groups, sim_assets)
        )
        self._sim_card.set_sub(self.tr("View details"))

        self._ss_card.set_detail(self.tr("{0} photos").format(ss_count))
        self._ss_card.set_sub(_format_bytes(ss_bytes))


class _BatchActionBar(QWidget):
    deleteClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cleanupBatchBar")
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)

        self._label = QLabel("")
        layout.addWidget(self._label, 1)

        self._delete_btn = QPushButton(self.tr("Delete Marked Items"))
        self._delete_btn.setObjectName("cleanupDeleteBtn")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self.deleteClicked.emit)
        layout.addWidget(self._delete_btn)

    def update_selection(self, count: int, total_bytes: int) -> None:
        if count == 0:
            self._label.setText("")
            self._delete_btn.setEnabled(False)
            self._delete_btn.setText(self.tr("Delete Marked Items"))
        else:
            self._label.setText(
                self.tr("Selected {0} items ({1})").format(count, _format_bytes(total_bytes))
            )
            self._delete_btn.setEnabled(True)
            self._delete_btn.setText(
                self.tr("Delete Marked Items ({0}, free {1})").format(
                    count, _format_bytes(total_bytes)
                )
            )
