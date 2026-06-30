"""Background worker for batch perceptual hash computation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Tuple

from PySide6.QtCore import QObject, QRunnable, Signal

if TYPE_CHECKING:
    from ....bootstrap.library_cleanup_service import LibraryCleanupService

_logger = logging.getLogger(__name__)


class PhashWorkerSignals(QObject):
    batchComplete = Signal(list)
    progress = Signal(int, int)
    finished = Signal()
    error = Signal(str)


class PerceptualHashWorker(QRunnable):
    """QRunnable that computes perceptual hashes in batches."""

    BATCH_SIZE = 200

    def __init__(
        self,
        cleanup_service: LibraryCleanupService,
        library_root: Path,
        thumbnail_cache_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.signals = PhashWorkerSignals()
        self._cleanup_service = cleanup_service
        self._library_root = library_root
        self._thumbnail_cache_dir = thumbnail_cache_dir
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from ....infrastructure.services.phash_computer import PerceptualHashComputer
        from ....utils.pathutils import ensure_work_dir

        cache_dir = self._thumbnail_cache_dir or (
            ensure_work_dir(self._library_root) / "cache" / "thumbs"
        )

        try:
            while not self._cancelled:
                batch = self._cleanup_service.get_pending_phash_batch(self.BATCH_SIZE)
                if not batch:
                    break

                results: List[Tuple[str, str, str]] = []
                for row in batch:
                    if self._cancelled:
                        break
                    rel = str(row.get("rel", ""))
                    if not rel:
                        continue

                    thumb_key = row.get("thumb_cache_key")
                    phash: str | None = None

                    if isinstance(thumb_key, str) and thumb_key.strip():
                        from ....infrastructure.services.thumbnail_cache_keys import (
                            thumbnail_cache_file_for_key,
                        )
                        thumb_path = thumbnail_cache_file_for_key(cache_dir, thumb_key)
                        if thumb_path.is_file():
                            phash = PerceptualHashComputer.compute_phash_from_thumbnail(thumb_path)

                    if phash is None:
                        original = self._library_root / rel
                        if original.is_file():
                            phash = PerceptualHashComputer.compute_phash(original)

                    if phash is not None:
                        results.append((rel, phash, "ready"))
                    else:
                        results.append((rel, "", "error"))

                if results:
                    self._cleanup_service.commit_phash_batch(results)
                    self.signals.batchComplete.emit(results)

                ready, total = self._cleanup_service.get_phash_progress()
                self.signals.progress.emit(ready, total)

        except Exception as exc:
            _logger.error("phash worker failed: %s", exc, exc_info=True)
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
