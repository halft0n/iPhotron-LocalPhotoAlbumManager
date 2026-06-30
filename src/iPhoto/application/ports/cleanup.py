"""Port protocol for the cleanup bounded context."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Protocol, Tuple


class CleanupRepositoryPort(Protocol):
    """Repository boundary for duplicate detection, screenshot management, and phash storage."""

    def find_exact_duplicate_groups(self) -> List[Dict[str, Any]]:
        """Return groups of assets sharing the same content hash.

        Each dict contains: ``id`` (content hash), ``rels`` (comma-separated
        relative paths), ``count``, ``total_bytes``.
        """
        ...

    def find_duplicate_group_details(self, content_id: str) -> List[Dict[str, Any]]:
        """Return full asset rows for a single duplicate group."""
        ...

    def count_exact_duplicate_groups(self) -> Tuple[int, int, int]:
        """Return ``(group_count, asset_count, wasted_bytes)``."""
        ...

    def find_screenshots(self) -> List[Dict[str, Any]]:
        """Return all asset rows flagged as screenshots."""
        ...

    def count_screenshots(self) -> Tuple[int, int]:
        """Return ``(count, total_bytes)``."""
        ...

    def update_screenshot_flag(self, rel: str, is_screenshot: bool) -> None:
        """Set the screenshot flag for a single asset."""
        ...

    def batch_update_screenshot_flags(
        self, updates: List[Tuple[str, bool]]
    ) -> None:
        """Batch-set screenshot flags ``[(rel, flag), ...]``."""
        ...

    def get_phash_progress(self) -> Tuple[int, int]:
        """Return ``(ready_count, total_eligible_count)``."""
        ...

    def get_pending_phash_batch(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Return up to *limit* rows whose phash has not been computed."""
        ...

    def update_phash(self, rel: str, phash: str, status: str = "ready") -> None:
        """Write the computed perceptual hash for a single asset."""
        ...

    def batch_update_phash(
        self, updates: List[Tuple[str, str, str]]
    ) -> None:
        """Batch-write phash results ``[(rel, phash, status), ...]``."""
        ...

    def find_assets_with_phash(self) -> List[Tuple[str, str]]:
        """Return ``[(rel, phash), ...]`` for all assets with a computed phash."""
        ...

    def read_all_visible(self) -> List[Dict[str, Any]]:
        """Return all non-deleted visible assets for reclassification."""
        ...

    def get_rows_by_rels(self, rels: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        """Return row data for given rels."""
        ...
