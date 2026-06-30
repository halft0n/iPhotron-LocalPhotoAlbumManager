"""Coordinator wiring the cleanup dashboard UI to the cleanup service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional

from PySide6.QtCore import QObject, QCoreApplication

from ..ui.widgets import dialogs
from ..ui.widgets.cleanup_dashboard import _format_bytes

if TYPE_CHECKING:
    from ..services.deletion_service import DeletionService
    from ..ui.widgets.cleanup_dashboard import CleanupDashboardWidget
    from ..ui.widgets.duplicate_group_list import DuplicateGroupListWidget
    from ..ui.widgets.screenshot_gallery import ScreenshotGalleryWidget
    from ..ui.widgets.similar_group_list import SimilarGroupListWidget
    from ..viewmodels.cleanup_viewmodel import CleanupViewModel

_logger = logging.getLogger(__name__)


class CleanupCoordinator(QObject):
    """Binds cleanup UI widgets to the CleanupViewModel and service layer."""

    def __init__(
        self,
        dashboard: CleanupDashboardWidget,
        cleanup_vm: CleanupViewModel,
        *,
        deletion_service: DeletionService,
        library_root_getter: Callable[[], Path | None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._dashboard = dashboard
        self._vm = cleanup_vm
        self._deletion_service = deletion_service
        self._library_root_getter = library_root_getter
        self._dup_list: Optional[DuplicateGroupListWidget] = None
        self._ss_gallery: Optional[ScreenshotGalleryWidget] = None
        self._sim_list: Optional[SimilarGroupListWidget] = None
        self._started = False
        self._current_phash_worker = None
        self._phash_running = False

        self._connect()

    def _connect(self) -> None:
        self._vm.summaryChanged.connect(self._on_summary_changed)
        self._vm.duplicatesLoaded.connect(self._on_duplicates_loaded)
        self._vm.screenshotsLoaded.connect(self._on_screenshots_loaded)
        self._vm.selectionChanged.connect(self._dashboard.batch_bar.update_selection)
        self._dashboard.tabChanged.connect(self._on_tab_changed)
        self._dashboard.deleteRequested.connect(self._on_delete_requested)

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        from ..ui.widgets.duplicate_group_list import DuplicateGroupListWidget
        from ..ui.widgets.screenshot_gallery import ScreenshotGalleryWidget
        from ..ui.widgets.similar_group_list import (
            PhashProgressWidget,
            SimilarGroupListWidget,
            SimilarityThresholdWidget,
        )
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        self._dup_list = DuplicateGroupListWidget()
        self._dashboard.set_duplicate_tab(self._dup_list)

        sim_container = QWidget()
        sim_layout = QVBoxLayout(sim_container)
        sim_layout.setContentsMargins(0, 0, 0, 0)
        self._phash_progress = PhashProgressWidget()
        sim_layout.addWidget(self._phash_progress)
        self._sim_threshold = SimilarityThresholdWidget()
        sim_layout.addWidget(self._sim_threshold)
        self._sim_list = SimilarGroupListWidget()
        sim_layout.addWidget(self._sim_list, 1)
        self._dashboard.set_similar_tab(sim_container)

        self._ss_gallery = ScreenshotGalleryWidget()
        self._ss_gallery.selectionChanged.connect(self._dashboard.batch_bar.update_selection)
        self._ss_gallery.deleteRequested.connect(self._on_delete_requested)
        self._ss_gallery.markNonScreenshot.connect(self._on_mark_non_screenshot)
        self._dashboard.set_screenshot_tab(self._ss_gallery)

        self._sim_threshold.thresholdChanged.connect(self._on_threshold_changed)

        self._vm.load_summary()
        self._vm.load_exact_duplicates()

    def _on_summary_changed(self, summary) -> None:
        if summary is None:
            return
        self._dashboard.update_summary(
            dup_groups=summary.exact_duplicate_groups,
            dup_assets=summary.exact_duplicate_assets,
            dup_wasted=summary.exact_duplicate_wasted_bytes,
            sim_groups=summary.similar_groups,
            sim_assets=summary.similar_assets,
            ss_count=summary.screenshot_count,
            ss_bytes=summary.screenshot_bytes,
        )

    def _on_duplicates_loaded(self, groups: list) -> None:
        if self._dup_list is None:
            return
        self._dup_list.clear_groups()
        from ..ui.widgets.duplicate_group_card import DuplicateGroupCard

        for group in groups:
            recommended = self._vm.auto_select_keeper(group)
            card = DuplicateGroupCard(group, recommended)
            card.assetToggled.connect(self._on_dup_asset_toggled)
            self._dup_list.add_group_card(card)

    def _on_screenshots_loaded(self, rows: list) -> None:
        if self._ss_gallery is not None:
            self._ss_gallery.set_screenshots(rows)

    def _on_tab_changed(self, index: int) -> None:
        if index == 2 and self._ss_gallery is not None:
            self._vm.load_screenshots()
        elif index == 1:
            completed, total = self._vm.get_phash_progress()
            if hasattr(self, "_phash_progress"):
                self._phash_progress.set_progress(completed, total)
            if completed < total:
                self._start_phash_computation()
            else:
                self._load_similar_groups()

    def _start_phash_computation(self) -> None:
        if not hasattr(self, "_phash_running") or self._phash_running:
            return
        self._phash_running = True

        from PySide6.QtCore import QThreadPool

        from ..ui.tasks.phash_worker import PerceptualHashWorker

        cleanup_service = self._vm._cleanup_service
        if cleanup_service is None:
            self._phash_running = False
            return

        worker = PerceptualHashWorker(
            cleanup_service,
            cleanup_service.library_root,
        )
        worker.signals.progress.connect(self._on_phash_progress)
        worker.signals.finished.connect(self._on_phash_finished)
        worker.signals.error.connect(self._on_phash_error)
        self._current_phash_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_phash_error(self, message: str) -> None:
        _logger.warning("Phash computation error: %s", message)
        self._phash_running = False

    def shutdown(self) -> None:
        if self._current_phash_worker is not None:
            self._current_phash_worker.cancel()
            self._current_phash_worker = None
        self._phash_running = False

    def _on_phash_progress(self, completed: int, total: int) -> None:
        if hasattr(self, "_phash_progress"):
            self._phash_progress.set_progress(completed, total)
        self._vm.phashProgressChanged.emit(completed, total)

    def _on_phash_finished(self) -> None:
        self._phash_running = False
        self._load_similar_groups()

    def _load_similar_groups(self) -> None:
        if self._vm._cleanup_service is None or self._sim_list is None:
            return
        threshold = 8
        if hasattr(self, "_sim_threshold"):
            threshold = self._sim_threshold._slider.value()
        groups = self._vm._cleanup_service.find_similar_photos(threshold)
        self._sim_list.clear_groups()
        from ..ui.widgets.similar_group_list import SimilarGroupCard

        for group in groups:
            if hasattr(self._vm, "auto_select_keeper_from_assets"):
                recommended = self._vm.auto_select_keeper_from_assets(group.assets)
            else:
                recommended = group.assets[0].rel if group.assets else ""
            card = SimilarGroupCard(group.group_id, group.assets, recommended)
            card.assetToggled.connect(self._on_dup_asset_toggled)
            self._sim_list.add_group_card(card)

    def _on_threshold_changed(self, value: int) -> None:
        self._load_similar_groups()

    def _on_dup_asset_toggled(self, rel: str, marked: bool) -> None:
        self._recalculate_marked()

    def _recalculate_marked(self) -> None:
        self._vm.clear_marks()
        all_marked: dict[str, int] = {}

        if self._dup_list is not None:
            for card in self._dup_list.group_cards():
                for rel in card.marked_for_delete:
                    for asset in card.group.assets:
                        if asset.rel == rel:
                            all_marked[rel] = asset.size_bytes
                            break

        if self._sim_list is not None:
            for card in self._sim_list.group_cards():
                if hasattr(card, "marked_for_delete"):
                    for rel in card.marked_for_delete:
                        if hasattr(card, "_asset_cards"):
                            for ac in card._asset_cards:
                                if ac.asset.rel == rel:
                                    all_marked[rel] = ac.asset.size_bytes
                                    break

        if all_marked:
            self._vm.mark_for_deletion(
                list(all_marked.keys()),
                bytes_per_rel=all_marked,
            )

    def _on_mark_non_screenshot(self, rel: str) -> None:
        self._vm.update_screenshot_flag(rel, False)
        self._vm.load_screenshots()
        self._vm.load_summary()

    def _on_delete_requested(self, _rels=None) -> None:
        current_tab = self._dashboard.tabs.currentIndex()
        if current_tab == 2 and self._ss_gallery is not None:
            rels = self._ss_gallery.selected_rels()
            total_bytes = self._ss_gallery.selected_total_bytes()
        else:
            rels = self._vm.get_marked_rels()
            total_bytes = self._vm.marked_total_bytes()
        if not rels:
            return

        count = len(rels)
        message = QCoreApplication.translate(
            "CleanupCoordinator",
            "Delete {0} marked items ({1})? They will be moved to Recently Deleted.",
        ).format(count, _format_bytes(total_bytes))
        if not dialogs.confirm_action(
            self._dashboard,
            message,
            title=QCoreApplication.translate("CleanupCoordinator", "Confirm Delete"),
            yes_label=QCoreApplication.translate("CleanupCoordinator", "Delete"),
            no_label=QCoreApplication.translate("CleanupCoordinator", "Cancel"),
        ):
            return

        paths = self._paths_for_rels(rels)
        if not paths:
            dialogs.show_warning(
                self._dashboard,
                QCoreApplication.translate(
                    "CleanupCoordinator",
                    "Basic Library has not been configured.",
                ),
            )
            return

        deleted = self._deletion_service.delete_assets(paths)
        if not deleted:
            return

        self._vm.clear_marks()
        self._vm.load_summary()
        self._vm.load_exact_duplicates()
        self._vm.load_screenshots()
        self._vm.batchDeleteCompleted.emit(count, len(paths))

    def _paths_for_rels(self, rels: List[str]) -> List[Path]:
        library_root = self._library_root_getter()
        if library_root is None:
            return []
        return [library_root / rel for rel in rels if rel]
