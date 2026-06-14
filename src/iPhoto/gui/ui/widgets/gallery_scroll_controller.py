"""Low-latency wheel handling and viewport state for the Gallery grid."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True, slots=True)
class GalleryViewportState:
    """One immutable description of the Gallery viewport."""

    generation: int
    visible_first: int
    visible_last: int
    direction: int
    velocity: float
    actively_scrolling: bool


class GalleryScrollController(QObject):
    """Keep wheel input responsive and publish at most one viewport state per event-loop turn."""

    _IDLE_TIMEOUT_MS = 90
    _FAST_WHEEL_INTERVAL_SEC = 0.085
    _MAX_ACCELERATION = 4

    def __init__(self, view, publish: Callable[[], None]) -> None:
        super().__init__(view)
        self._view = view
        self._publish = publish
        self._pending_pixel_delta = 0.0
        self._generation = 0
        self._last_value = int(self._view.verticalScrollBar().value())
        self._last_value_at = time.monotonic()
        self._direction = 0
        self._velocity = 0.0
        self._last_wheel_at = 0.0
        self._wheel_streak = 0

        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(0)
        self._apply_timer.timeout.connect(self._apply_pending_scroll)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(self._IDLE_TIMEOUT_MS)
        self._idle_timer.timeout.connect(self._publish_idle_state)

        self._view.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

    def handle_wheel(self, event) -> bool:
        """Accumulate one wheel event without introducing inertial drag."""

        pixel_delta = event.pixelDelta()
        pixel_y = pixel_delta.y() if not pixel_delta.isNull() else 0
        if pixel_y:
            # Trackpads already provide a precise physical-pixel stream.
            delta = -float(pixel_y)
            self._wheel_streak = 0
        else:
            angle_delta = event.angleDelta()
            angle = angle_delta.y() or angle_delta.x()
            if not angle:
                return False
            now = time.monotonic()
            if now - self._last_wheel_at <= self._FAST_WHEEL_INTERVAL_SEC:
                self._wheel_streak = min(self._MAX_ACCELERATION - 1, self._wheel_streak + 1)
            else:
                self._wheel_streak = 0
            self._last_wheel_at = now

            steps = float(angle) / 120.0
            wheel_lines = max(1, QApplication.wheelScrollLines())
            row_height = max(1, self._view.gridSize().height() or self._view.iconSize().height())
            acceleration = 1 + self._wheel_streak
            delta = -steps * row_height * wheel_lines * acceleration

        self._pending_pixel_delta += delta
        if not self._apply_timer.isActive():
            self._apply_timer.start()
        event.accept()
        return True

    def schedule_publish(self) -> None:
        self._publish()

    def viewport_state(self, row_count: int) -> GalleryViewportState | None:
        if row_count <= 0:
            return None
        cell_height = max(1, self._view.gridSize().height() or self._view.iconSize().height())
        cell_width = max(1, self._view.gridSize().width() or self._view.iconSize().width())
        viewport = self._view.viewport()
        columns = max(1, viewport.width() // cell_width)
        scroll_y = max(0, self._view.verticalScrollBar().value())
        first_grid_row = scroll_y // cell_height
        visible_grid_rows = max(1, math.ceil(viewport.height() / cell_height) + 1)
        first = min(row_count - 1, first_grid_row * columns)
        last = min(row_count - 1, (first_grid_row + visible_grid_rows) * columns - 1)
        self._generation += 1
        return GalleryViewportState(
            generation=self._generation,
            visible_first=first,
            visible_last=max(first, last),
            direction=self._direction,
            velocity=self._velocity,
            actively_scrolling=self._idle_timer.isActive(),
        )

    def _apply_pending_scroll(self) -> None:
        delta = self._pending_pixel_delta
        self._pending_pixel_delta = 0.0
        if not delta:
            return
        scrollbar = self._view.verticalScrollBar()
        target = max(
            scrollbar.minimum(),
            min(scrollbar.maximum(), scrollbar.value() + round(delta)),
        )
        scrollbar.setValue(target)
        self._idle_timer.start()
        self.schedule_publish()

    def _on_scroll_value_changed(self, value: int) -> None:
        now = time.monotonic()
        elapsed = max(1e-6, now - self._last_value_at)
        distance = int(value) - self._last_value
        self._direction = 1 if distance > 0 else (-1 if distance < 0 else self._direction)
        self._velocity = abs(float(distance)) / elapsed
        self._last_value = int(value)
        self._last_value_at = now
        self._idle_timer.start()
        self.schedule_publish()

    def _publish_idle_state(self) -> None:
        self._velocity = 0.0
        self.schedule_publish()


__all__ = ["GalleryScrollController", "GalleryViewportState"]
