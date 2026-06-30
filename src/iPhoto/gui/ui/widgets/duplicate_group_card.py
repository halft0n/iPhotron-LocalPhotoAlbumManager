"""Card widget representing a single group of duplicate photos."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....domain.models.cleanup import DuplicateAsset, DuplicateGroup


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


class DuplicateGroupCard(QFrame):
    """Displays one group of exact-duplicate photos side by side."""

    keepRecommended = Signal(str)
    assetToggled = Signal(str, bool)

    def __init__(
        self,
        group: DuplicateGroup,
        recommended_rel: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("duplicateGroupCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._group = group
        self._recommended_rel = recommended_rel
        self._marked_for_delete: set[str] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)

        header = QHBoxLayout()
        count = len(group.assets)
        self._header_label = QLabel(
            self.tr("Group ({0} photos, identical)").format(count)
        )
        hf = self._header_label.font()
        hf.setBold(True)
        self._header_label.setFont(hf)
        header.addWidget(self._header_label)
        header.addStretch()

        keep_btn = QPushButton(self.tr("Keep Recommended"))
        keep_btn.clicked.connect(self._apply_recommendation)
        header.addWidget(keep_btn)

        root.addLayout(header)

        assets_row = QHBoxLayout()
        assets_row.setSpacing(12)
        self._asset_cards: list[DuplicateAssetCard] = []

        for asset in group.assets:
            card = DuplicateAssetCard(
                asset,
                is_recommended=(asset.rel == recommended_rel),
            )
            card.toggled.connect(self._on_asset_toggled)
            assets_row.addWidget(card)
            self._asset_cards.append(card)

        assets_row.addStretch()
        root.addLayout(assets_row)

        self.setStyleSheet(
            """
            #duplicateGroupCard {
                border: 1px solid palette(mid);
                border-radius: 6px;
                background: palette(base);
            }
            """
        )

    @property
    def group(self) -> DuplicateGroup:
        return self._group

    @property
    def marked_for_delete(self) -> set[str]:
        return set(self._marked_for_delete)

    def _apply_recommendation(self) -> None:
        for card in self._asset_cards:
            should_delete = card.asset.rel != self._recommended_rel
            card.set_marked(should_delete)
            if should_delete:
                self._marked_for_delete.add(card.asset.rel)
            else:
                self._marked_for_delete.discard(card.asset.rel)
        self.keepRecommended.emit(self._recommended_rel)
        self.assetToggled.emit("", False)

    def _on_asset_toggled(self, rel: str, marked: bool) -> None:
        if marked:
            self._marked_for_delete.add(rel)
        else:
            self._marked_for_delete.discard(rel)
        self.assetToggled.emit(rel, marked)


class DuplicateAssetCard(QFrame):
    """Single asset tile inside a duplicate group."""

    toggled = Signal(str, bool)

    def __init__(
        self,
        asset: DuplicateAsset,
        is_recommended: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("duplicateAssetCard")
        self._asset = asset
        self._is_recommended = is_recommended
        self._marked = False

        self.setFixedWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        self._status_label = QLabel()
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_status_label()
        layout.addWidget(self._status_label)

        self._thumb = QLabel()
        self._thumb.setFixedSize(180, 135)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setScaledContents(True)
        self._thumb.setStyleSheet("background: palette(dark); border-radius: 4px;")

        if asset.micro_thumbnail:
            from PySide6.QtGui import QImage, QPixmap

            img = QImage()
            if img.loadFromData(asset.micro_thumbnail):
                self._thumb.setPixmap(QPixmap.fromImage(img))

        layout.addWidget(self._thumb)

        from pathlib import PurePosixPath

        fname = PurePosixPath(asset.rel).name
        name_label = QLabel(fname)
        name_label.setToolTip(asset.rel)
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        folder = asset.parent_album_path or PurePosixPath(asset.rel).parent.as_posix()
        folder_label = QLabel(f"\U0001f4c1 {folder}")
        folder_label.setObjectName("assetFolderLabel")
        folder_label.setToolTip(self.tr("Located in: {0}").format(folder))
        folder_label.setWordWrap(True)
        layout.addWidget(folder_label)

        info_parts = []
        info_parts.append(_format_bytes(asset.size_bytes))
        if asset.width and asset.height:
            info_parts.append(f"{asset.width}\u00d7{asset.height}")
        info_label = QLabel(" | ".join(info_parts))
        layout.addWidget(info_label)

        if asset.created_at:
            dt_label = QLabel(asset.created_at.strftime("%Y-%m-%d %H:%M"))
            layout.addWidget(dt_label)

        camera = " ".join(filter(None, [asset.make, asset.model])) or self.tr("No camera info")
        camera_label = QLabel(camera)
        layout.addWidget(camera_label)

        badges: list[str] = []
        if asset.is_favorite:
            badges.append("\u2605 " + self.tr("Favorite"))
        if asset.has_gps:
            badges.append("GPS")
        if badges:
            badge_label = QLabel(" | ".join(badges))
            layout.addWidget(badge_label)

        self._apply_border()

    @property
    def asset(self) -> DuplicateAsset:
        return self._asset

    def set_marked(self, marked: bool) -> None:
        self._marked = marked
        self._update_status_label()
        self._apply_border()

    def _update_status_label(self) -> None:
        if self._is_recommended and not self._marked:
            self._status_label.setText("\u2705 " + self.tr("Recommended"))
            self._status_label.setStyleSheet("color: green; font-weight: bold;")
        elif self._marked:
            self._status_label.setText("\u274c " + self.tr("To delete"))
            self._status_label.setStyleSheet("color: red;")
        else:
            self._status_label.setText(self.tr("Keep"))
            self._status_label.setStyleSheet("")

    def _apply_border(self) -> None:
        if self._is_recommended and not self._marked:
            border = "2px solid green"
        elif self._marked:
            border = "2px solid red"
        else:
            border = "1px solid palette(mid)"
        self.setStyleSheet(
            f"#duplicateAssetCard {{ border: {border}; border-radius: 6px; background: palette(base); }}"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._marked = not self._marked
            self._update_status_label()
            self._apply_border()
            self.toggled.emit(self._asset.rel, self._marked)
        super().mousePressEvent(event)
