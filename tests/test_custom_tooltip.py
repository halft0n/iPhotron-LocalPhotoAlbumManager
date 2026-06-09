from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6", reason="PySide6 is required for tooltip tests", exc_type=ImportError)

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from iPhoto.gui.ui.widgets.custom_tooltip import _TEXT_FLAGS, FloatingToolTip


@pytest.fixture
def qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.parametrize(
    "text",
    [
        "Rotate counter-clockwise",
        "Perspektive zuruecksetzen",
        "返回网格视图",
        "选择要调整的透视参考点",
    ],
)
def test_floating_tooltip_size_hint_matches_painted_text(qapp: QApplication, text: str) -> None:
    del qapp
    tooltip = FloatingToolTip()
    tooltip.setText(text)
    tooltip.resize(tooltip.sizeHint())

    measured = _painted_text_bounds(tooltip, text)
    text_rect = tooltip._text_rect()

    assert measured.width() <= text_rect.width() + 0.5
    assert measured.height() <= text_rect.height() + 0.5
    assert text_rect.width() - measured.width() <= 1.0


@pytest.mark.parametrize(
    "text",
    [
        "Donaudampfschifffahrtsgesellschaftskapitaen",
        "这是一个没有空格但仍然应该完整换行显示的中文悬浮提示文案",
    ],
)
def test_floating_tooltip_wraps_unbroken_text_within_max_width(
    qapp: QApplication, text: str
) -> None:
    del qapp
    tooltip = FloatingToolTip()
    tooltip.setText(text)
    tooltip.resize(tooltip.sizeHint())

    measured = _painted_text_bounds(tooltip, text)
    text_rect = tooltip._text_rect()

    assert tooltip.sizeHint().width() <= tooltip._MAX_WIDTH
    assert measured.width() <= text_rect.width() + 0.5
    assert measured.height() <= text_rect.height() + 0.5


def _painted_text_bounds(tooltip: FloatingToolTip, text: str):
    image = QImage(tooltip.width(), tooltip.height(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setFont(tooltip._font)
    try:
        return painter.boundingRect(tooltip._text_rect(), _TEXT_FLAGS, text)
    finally:
        painter.end()
