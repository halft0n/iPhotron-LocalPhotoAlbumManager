"""Screenshot management gallery tab widget."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


class ScreenshotFilterBar(QWidget):
    filterChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        for label, key in [
            (self.tr("All"), "all"),
            (self.tr("Today"), "today"),
            (self.tr("This Week"), "week"),
            (self.tr("This Month"), "month"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            if key == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, k=key: self.filterChanged.emit(k))
            layout.addWidget(btn)
        layout.addStretch()

        self._sort_label = QLabel(self.tr("Sort:"))
        layout.addWidget(self._sort_label)

        self._sort_date = QPushButton(self.tr("By Date"))
        self._sort_date.setCheckable(True)
        self._sort_date.setChecked(True)
        self._sort_date.setAutoExclusive(True)
        layout.addWidget(self._sort_date)

        self._sort_size = QPushButton(self.tr("By Size"))
        self._sort_size.setCheckable(True)
        self._sort_size.setAutoExclusive(True)
        layout.addWidget(self._sort_size)


class ScreenshotGalleryWidget(QWidget):
    """Grid display of screenshot thumbnails with batch selection."""

    selectionChanged = Signal(int, int)
    deleteRequested = Signal(list)
    markNonScreenshot = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        self._count_label = QLabel()
        header_layout.addWidget(self._count_label)
        header_layout.addStretch()

        self._select_all = QPushButton(self.tr("Select All"))
        self._select_all.clicked.connect(self._on_select_all)
        header_layout.addWidget(self._select_all)

        self._invert = QPushButton(self.tr("Invert"))
        self._invert.clicked.connect(self._on_invert)
        header_layout.addWidget(self._invert)

        layout.addLayout(header_layout)

        self._filter_bar = ScreenshotFilterBar()
        self._filter_bar.filterChanged.connect(self._on_filter_changed)
        layout.addWidget(self._filter_bar)

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(QSize(160, 120))
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setWrapping(True)
        self._list.setSpacing(8)
        self._list.itemSelectionChanged.connect(self._emit_selection)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._list, 1)

        self._all_rows: List[Dict[str, Any]] = []
        self._current_filter = "all"

    def set_screenshots(self, rows: List[Dict[str, Any]]) -> None:
        self._all_rows = list(rows)
        self._apply_filter()

    def _apply_filter(self) -> None:
        self._list.clear()
        now = datetime.now()
        filtered = self._all_rows

        if self._current_filter == "today":
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            filtered = [r for r in self._all_rows if self._row_after(r, today)]
        elif self._current_filter == "week":
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            filtered = [r for r in self._all_rows if self._row_after(r, week_start)]
        elif self._current_filter == "month":
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            filtered = [r for r in self._all_rows if self._row_after(r, month_start)]

        total_bytes = sum(int(r.get("bytes") or 0) for r in filtered)
        self._count_label.setText(
            self.tr("{0} screenshots, {1}").format(len(filtered), _format_bytes(total_bytes))
        )

        for row in filtered:
            from pathlib import PurePosixPath

            rel = str(row.get("rel", ""))
            fname = PurePosixPath(rel).name
            folder = str(row.get("parent_album_path") or PurePosixPath(rel).parent.as_posix())

            item = QListWidgetItem()
            item.setText(f"{fname}\n\U0001f4c1 {folder}")
            item.setToolTip(rel)
            item.setData(Qt.ItemDataRole.UserRole, row)

            micro = row.get("micro_thumbnail")
            if isinstance(micro, (bytes, bytearray)):
                img = QImage()
                if img.loadFromData(micro):
                    item.setIcon(QPixmap.fromImage(img))

            self._list.addItem(item)

    def selected_rels(self) -> List[str]:
        result = []
        for item in self._list.selectedItems():
            row = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(row, dict):
                result.append(str(row.get("rel", "")))
        return result

    def selected_total_bytes(self) -> int:
        total = 0
        for item in self._list.selectedItems():
            row = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(row, dict):
                total += int(row.get("bytes") or 0)
        return total

    def _emit_selection(self) -> None:
        rels = self.selected_rels()
        total = self.selected_total_bytes()
        self.selectionChanged.emit(len(rels), total)

    def _on_select_all(self) -> None:
        self._list.selectAll()

    def _on_invert(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setSelected(not item.isSelected())

    def _on_filter_changed(self, key: str) -> None:
        self._current_filter = key
        self._apply_filter()

    def _show_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        item = self._list.itemAt(pos)
        if item is None:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(row, dict):
            return
        menu = QMenu(self)
        action = menu.addAction(self.tr("Mark as Not Screenshot"))
        action.triggered.connect(lambda: self.markNonScreenshot.emit(str(row.get("rel", ""))))
        menu.exec(self._list.viewport().mapToGlobal(pos))

    @staticmethod
    def _row_after(row: Dict[str, Any], threshold: datetime) -> bool:
        dt_str = row.get("dt")
        if not isinstance(dt_str, str):
            return False
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None) >= threshold
        except (ValueError, TypeError):
            return False
