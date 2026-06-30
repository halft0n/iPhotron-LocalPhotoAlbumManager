"""Tests for LibraryCleanupService."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from iPhoto.bootstrap.library_cleanup_service import LibraryCleanupService
from iPhoto.domain.models.cleanup import DuplicateAsset, DuplicateGroup


class FakeCleanupRepository:
    """In-memory fake for CleanupRepositoryPort."""

    def __init__(self):
        self._assets: List[Dict[str, Any]] = []

    def add_asset(self, row: Dict[str, Any]) -> None:
        self._assets.append(row)

    def find_exact_duplicate_groups(self) -> List[Dict[str, Any]]:
        from collections import Counter
        id_counts = Counter(a["id"] for a in self._assets if not a.get("is_deleted"))
        groups = []
        for aid, count in id_counts.items():
            if count >= 2:
                matching = [a for a in self._assets if a["id"] == aid and not a.get("is_deleted")]
                rels = ",".join(a["rel"] for a in matching)
                total_bytes = sum(a.get("bytes", 0) for a in matching)
                groups.append({"id": aid, "rels": rels, "count": count, "total_bytes": total_bytes})
        return groups

    def find_duplicate_group_details(self, content_id: str) -> List[Dict[str, Any]]:
        return [a for a in self._assets if a["id"] == content_id and not a.get("is_deleted")]

    def count_exact_duplicate_groups(self) -> Tuple[int, int, int]:
        groups = self.find_exact_duplicate_groups()
        total_assets = sum(g["count"] for g in groups)
        wasted = sum(g["total_bytes"] - max(a.get("bytes", 0) for a in self._assets if a["id"] == g["id"]) for g in groups)
        return (len(groups), total_assets, wasted)

    def find_screenshots(self) -> List[Dict[str, Any]]:
        return [a for a in self._assets if a.get("is_screenshot") and not a.get("is_deleted")]

    def count_screenshots(self) -> Tuple[int, int]:
        ss = self.find_screenshots()
        return (len(ss), sum(a.get("bytes", 0) for a in ss))

    def update_screenshot_flag(self, rel: str, is_screenshot: bool) -> None:
        for a in self._assets:
            if a["rel"] == rel:
                a["is_screenshot"] = int(is_screenshot)

    def batch_update_screenshot_flags(self, updates):
        for rel, flag in updates:
            self.update_screenshot_flag(rel, flag)

    def get_phash_progress(self) -> Tuple[int, int]:
        eligible = [a for a in self._assets if a.get("phash_status") != "skipped"]
        ready = [a for a in eligible if a.get("phash_status") == "ready"]
        return (len(ready), len(eligible))

    def get_pending_phash_batch(self, limit=500):
        return [a for a in self._assets if a.get("phash_status") in ("pending", "")][:limit]

    def update_phash(self, rel, phash, status="ready"):
        for a in self._assets:
            if a["rel"] == rel:
                a["phash"] = phash
                a["phash_status"] = status

    def batch_update_phash(self, updates):
        for rel, phash, status in updates:
            self.update_phash(rel, phash, status)

    def find_assets_with_phash(self):
        return [(a["rel"], a["phash"]) for a in self._assets if a.get("phash")]

    def read_all_visible(self):
        return [
            a for a in self._assets
            if not a.get("is_deleted") and not a.get("live_role")
        ]

    def get_rows_by_rels(self, rels):
        rel_set = set(rels)
        return {a["rel"]: dict(a) for a in self._assets if a["rel"] in rel_set}


class TestLibraryCleanupService:
    def _make_service(self) -> Tuple[LibraryCleanupService, FakeCleanupRepository]:
        repo = FakeCleanupRepository()
        service = LibraryCleanupService(Path("/tmp/test_lib"), repo)
        return service, repo

    def _add_duplicate_pair(self, repo: FakeCleanupRepository):
        repo.add_asset({
            "id": "hash_abc", "rel": "folder1/photo.jpg",
            "bytes": 3000000, "w": 4032, "h": 3024,
            "dt": "2024-03-15T14:23:00Z", "make": "Canon", "model": "EOS R5",
            "has_gps": True, "is_favorite": True, "is_deleted": False,
            "parent_album_path": "folder1",
            "thumb_cache_key": "key1", "micro_thumbnail": None,
        })
        repo.add_asset({
            "id": "hash_abc", "rel": "backup/photo_copy.jpg",
            "bytes": 3000000, "w": 4032, "h": 3024,
            "dt": "2024-03-15T14:23:00Z", "make": None, "model": None,
            "has_gps": False, "is_favorite": False, "is_deleted": False,
            "parent_album_path": "backup",
            "thumb_cache_key": "key2", "micro_thumbnail": None,
        })

    def test_find_exact_duplicates(self):
        service, repo = self._make_service()
        self._add_duplicate_pair(repo)

        groups = service.find_exact_duplicates()
        assert len(groups) == 1
        assert len(groups[0].assets) == 2
        assert groups[0].content_id == "hash_abc"

    def test_auto_select_keeper_prefers_favorite(self):
        service, repo = self._make_service()
        self._add_duplicate_pair(repo)

        groups = service.find_exact_duplicates()
        keeper = service.auto_select_keeper(groups[0])
        assert keeper == "folder1/photo.jpg"

    def test_cleanup_summary(self):
        service, repo = self._make_service()
        self._add_duplicate_pair(repo)
        repo.add_asset({
            "id": "hash_ss", "rel": "Screenshots/ss.png",
            "bytes": 500000, "w": 1080, "h": 1920,
            "is_screenshot": 1, "is_deleted": False,
            "parent_album_path": "Screenshots",
            "phash_status": "pending",
        })

        summary = service.get_cleanup_summary()
        assert summary.exact_duplicate_groups == 1
        assert summary.exact_duplicate_assets == 2
        assert summary.screenshot_count == 1
        assert summary.screenshot_bytes == 500000

    def test_find_screenshots(self):
        service, repo = self._make_service()
        repo.add_asset({
            "id": "ss1", "rel": "Screenshots/ss1.png",
            "bytes": 200000, "is_screenshot": 1, "is_deleted": False,
        })
        repo.add_asset({
            "id": "normal1", "rel": "photos/normal.jpg",
            "bytes": 300000, "is_screenshot": 0, "is_deleted": False,
        })

        screenshots = service.find_screenshots()
        assert len(screenshots) == 1

    def test_phash_progress(self):
        service, repo = self._make_service()
        repo.add_asset({"id": "a", "rel": "a.jpg", "phash_status": "ready", "phash": "abc"})
        repo.add_asset({"id": "b", "rel": "b.jpg", "phash_status": "pending"})
        repo.add_asset({"id": "c", "rel": "c.jpg", "phash_status": "skipped"})

        ready, total = service.get_phash_progress()
        assert ready == 1
        assert total == 2  # skipped not counted
