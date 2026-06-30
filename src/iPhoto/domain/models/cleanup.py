"""Value objects for the photo cleanup bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class DuplicateAsset:
    """A single asset within a duplicate group."""

    rel: str
    abs_path: Path
    parent_album_path: str
    size_bytes: int
    width: int
    height: int
    created_at: Optional[datetime]
    make: Optional[str]
    model: Optional[str]
    has_gps: bool
    is_favorite: bool
    thumb_cache_key: Optional[str]
    micro_thumbnail: Optional[bytes]


@dataclass(frozen=True)
class DuplicateGroup:
    """A group of exact-duplicate photos sharing the same content hash."""

    content_id: str
    assets: List[DuplicateAsset]
    total_size_bytes: int
    wasted_bytes: int


@dataclass(frozen=True)
class SimilarGroup:
    """A group of perceptually similar photos."""

    group_id: str
    assets: List[DuplicateAsset]
    similarity_scores: Dict[Tuple[str, str], float]
    max_distance: int


@dataclass(frozen=True)
class CleanupSummary:
    """Aggregate statistics for the cleanup dashboard."""

    exact_duplicate_groups: int
    exact_duplicate_assets: int
    exact_duplicate_wasted_bytes: int
    similar_groups: int
    similar_assets: int
    screenshot_count: int
    screenshot_bytes: int
