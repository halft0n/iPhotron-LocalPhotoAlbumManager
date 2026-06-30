"""Session-bound service for photo cleanup operations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..application.ports.cleanup import CleanupRepositoryPort
from ..domain.models.cleanup import (
    CleanupSummary,
    DuplicateAsset,
    DuplicateGroup,
    SimilarGroup,
)
from ..domain.services.screenshot_classifier import ScreenshotClassifier


class LibraryCleanupService:
    """Cleanup feature surface bound to a library session."""

    def __init__(
        self,
        library_root: Path,
        repository: CleanupRepositoryPort,
    ) -> None:
        self.library_root = Path(library_root)
        self._repo = repository

    def get_cleanup_summary(self) -> CleanupSummary:
        dup_groups, dup_assets, dup_wasted = self._repo.count_exact_duplicate_groups()
        ss_count, ss_bytes = self._repo.count_screenshots()
        phash_ready, _phash_total = self._repo.get_phash_progress()
        similar_groups_count = 0
        similar_assets_count = 0
        if phash_ready > 0:
            try:
                from ..infrastructure.services.bktree import group_by_similarity

                hash_pairs = self._repo.find_assets_with_phash()
                if hash_pairs:
                    raw_groups = group_by_similarity(hash_pairs, max_distance=8)
                    similar_groups_count = len([g for g in raw_groups if len(g) >= 2])
                    similar_assets_count = sum(len(g) for g in raw_groups if len(g) >= 2)
            except Exception:
                pass
        return CleanupSummary(
            exact_duplicate_groups=dup_groups,
            exact_duplicate_assets=dup_assets,
            exact_duplicate_wasted_bytes=dup_wasted,
            similar_groups=similar_groups_count,
            similar_assets=similar_assets_count,
            screenshot_count=ss_count,
            screenshot_bytes=ss_bytes,
        )

    def find_exact_duplicates(self) -> List[DuplicateGroup]:
        raw_groups = self._repo.find_exact_duplicate_groups()
        result: List[DuplicateGroup] = []
        for group_row in raw_groups:
            content_id = str(group_row.get("id", ""))
            if not content_id:
                continue
            detail_rows = self._repo.find_duplicate_group_details(content_id)
            if len(detail_rows) < 2:
                continue
            assets = [self._row_to_duplicate_asset(row) for row in detail_rows]
            total = sum(a.size_bytes for a in assets)
            biggest = max(a.size_bytes for a in assets)
            result.append(DuplicateGroup(
                content_id=content_id,
                assets=assets,
                total_size_bytes=total,
                wasted_bytes=total - biggest,
            ))
        return result

    def auto_select_keeper(self, group: DuplicateGroup) -> str:
        """Return the ``rel`` of the recommended asset to keep.

        Priority: favorite > GPS > EXIF > resolution > size > earliest date.
        """
        def _rank(asset: DuplicateAsset) -> tuple:
            return (
                asset.is_favorite,
                asset.has_gps,
                bool(asset.make or asset.model),
                asset.width * asset.height if asset.width and asset.height else 0,
                asset.size_bytes,
                -(asset.created_at.timestamp() if asset.created_at else 0),
            )

        best = max(group.assets, key=_rank)
        return best.rel

    def find_screenshots(self) -> List[Dict[str, Any]]:
        return self._repo.find_screenshots()

    def count_screenshots(self) -> Tuple[int, int]:
        return self._repo.count_screenshots()

    def update_screenshot_flag(self, rel: str, is_screenshot: bool) -> None:
        self._repo.update_screenshot_flag(rel, is_screenshot)

    def reclassify_screenshots(self) -> int:
        updated = 0
        for row in self._repo.read_all_visible():
            rel = str(row.get("rel", ""))
            if not rel:
                continue
            is_ss = ScreenshotClassifier.classify(
                rel,
                int(row.get("w") or 0),
                int(row.get("h") or 0),
                row.get("make"),
                row.get("model"),
                row.get("mime"),
            )
            current = bool(row.get("is_screenshot"))
            if is_ss != current:
                self._repo.update_screenshot_flag(rel, is_ss)
                updated += 1
        return updated

    def get_phash_progress(self) -> Tuple[int, int]:
        return self._repo.get_phash_progress()

    def get_pending_phash_batch(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self._repo.get_pending_phash_batch(limit)

    def commit_phash_batch(
        self, results: List[Tuple[str, str, str]]
    ) -> None:
        self._repo.batch_update_phash(results)

    def find_assets_with_phash(self) -> List[Tuple[str, str]]:
        return self._repo.find_assets_with_phash()

    def find_similar_photos(self, max_distance: int = 8) -> List[SimilarGroup]:
        from ..infrastructure.services.bktree import group_by_similarity
        from ..infrastructure.services.phash_computer import PerceptualHashComputer

        hash_pairs = self._repo.find_assets_with_phash()
        if not hash_pairs:
            return []

        raw_groups = group_by_similarity(hash_pairs, max_distance)
        result: list[SimilarGroup] = []

        for i, group_rels in enumerate(raw_groups):
            if len(group_rels) < 2:
                continue
            rows_by_rel = self._repo.get_rows_by_rels(group_rels)

            assets = []
            for rel in group_rels:
                row = rows_by_rel.get(rel)
                if row:
                    assets.append(self._row_to_duplicate_asset(row))

            if len(assets) < 2:
                continue

            rel_phash = {rel: ph for rel, ph in hash_pairs if rel in group_rels}
            scores: Dict[Tuple[str, str], float] = {}
            rels_list = [a.rel for a in assets]
            for j in range(len(rels_list)):
                for k in range(j + 1, len(rels_list)):
                    a, b = rels_list[j], rels_list[k]
                    ha = rel_phash.get(a, "")
                    hb = rel_phash.get(b, "")
                    if ha and hb:
                        dist = PerceptualHashComputer.hamming_distance(ha, hb)
                        similarity = max(0, round((1 - dist / 64) * 100)) / 100
                        scores[(a, b)] = similarity

            max_dist = 0
            for a, b in scores:
                ha = rel_phash.get(a, "")
                hb = rel_phash.get(b, "")
                if ha and hb:
                    d = PerceptualHashComputer.hamming_distance(ha, hb)
                    max_dist = max(max_dist, d)

            result.append(SimilarGroup(
                group_id=f"sim_{i}",
                assets=assets,
                similarity_scores=scores,
                max_distance=max_dist,
            ))

        return result

    def _row_to_duplicate_asset(self, row: Dict[str, Any]) -> DuplicateAsset:
        rel = str(row.get("rel", ""))
        dt_raw = row.get("dt")
        created_at: Optional[datetime] = None
        if isinstance(dt_raw, str) and dt_raw:
            try:
                created_at = datetime.fromisoformat(
                    dt_raw.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return DuplicateAsset(
            rel=rel,
            abs_path=self.library_root / rel,
            parent_album_path=str(row.get("parent_album_path") or ""),
            size_bytes=int(row.get("bytes") or 0),
            width=int(row.get("w") or 0),
            height=int(row.get("h") or 0),
            created_at=created_at,
            make=row.get("make"),
            model=row.get("model"),
            has_gps=bool(row.get("has_gps")),
            is_favorite=bool(row.get("is_favorite")),
            thumb_cache_key=row.get("thumb_cache_key"),
            micro_thumbnail=row.get("micro_thumbnail"),
        )
