"""ViewModel for the cleanup dashboard."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QObject, Signal

from ...domain.models.cleanup import CleanupSummary, DuplicateGroup


class CleanupViewModel(QObject):
    """Presentation state for the cleanup dashboard."""

    summaryChanged = Signal(object)
    duplicatesLoaded = Signal(list)
    screenshotsLoaded = Signal(list)
    similarLoaded = Signal(list)
    phashProgressChanged = Signal(int, int)
    batchDeleteCompleted = Signal(int, int)
    selectionChanged = Signal(int, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cleanup_service = None
        self._summary: Optional[CleanupSummary] = None
        self._duplicate_groups: List[DuplicateGroup] = []
        self._screenshots: List[Dict[str, Any]] = []
        self._marked_for_delete: Set[str] = set()
        self._marked_bytes: int = 0

    def bind_cleanup_service(self, service) -> None:
        self._cleanup_service = service

    @property
    def summary(self) -> Optional[CleanupSummary]:
        return self._summary

    @property
    def duplicate_groups(self) -> List[DuplicateGroup]:
        return list(self._duplicate_groups)

    @property
    def screenshots(self) -> List[Dict[str, Any]]:
        return list(self._screenshots)

    def load_summary(self) -> None:
        if self._cleanup_service is None:
            return
        self._summary = self._cleanup_service.get_cleanup_summary()
        self.summaryChanged.emit(self._summary)

    def load_exact_duplicates(self) -> None:
        if self._cleanup_service is None:
            return
        self._duplicate_groups = self._cleanup_service.find_exact_duplicates()
        self.duplicatesLoaded.emit(self._duplicate_groups)

    def load_screenshots(self) -> None:
        if self._cleanup_service is None:
            return
        self._screenshots = self._cleanup_service.find_screenshots()
        self.screenshotsLoaded.emit(self._screenshots)

    def auto_select_keeper(self, group: DuplicateGroup) -> str:
        if self._cleanup_service is None:
            return group.assets[0].rel if group.assets else ""
        return self._cleanup_service.auto_select_keeper(group)

    def mark_for_deletion(self, rels: List[str], bytes_per_rel: Dict[str, int] | None = None) -> None:
        for rel in rels:
            if rel not in self._marked_for_delete:
                self._marked_for_delete.add(rel)
                if bytes_per_rel:
                    self._marked_bytes += bytes_per_rel.get(rel, 0)
        self.selectionChanged.emit(len(self._marked_for_delete), self._marked_bytes)

    def unmark_for_deletion(self, rels: List[str], bytes_per_rel: Dict[str, int] | None = None) -> None:
        for rel in rels:
            if rel in self._marked_for_delete:
                self._marked_for_delete.discard(rel)
                if bytes_per_rel:
                    self._marked_bytes -= bytes_per_rel.get(rel, 0)
        self._marked_bytes = max(0, self._marked_bytes)
        self.selectionChanged.emit(len(self._marked_for_delete), self._marked_bytes)

    def clear_marks(self) -> None:
        self._marked_for_delete.clear()
        self._marked_bytes = 0
        self.selectionChanged.emit(0, 0)

    def get_marked_rels(self) -> List[str]:
        return list(self._marked_for_delete)

    def marked_count(self) -> int:
        return len(self._marked_for_delete)

    def marked_total_bytes(self) -> int:
        return self._marked_bytes

    def update_screenshot_flag(self, rel: str, is_screenshot: bool) -> None:
        if self._cleanup_service is not None:
            self._cleanup_service.update_screenshot_flag(rel, is_screenshot)

    def get_phash_progress(self) -> Tuple[int, int]:
        if self._cleanup_service is None:
            return (0, 0)
        return self._cleanup_service.get_phash_progress()
