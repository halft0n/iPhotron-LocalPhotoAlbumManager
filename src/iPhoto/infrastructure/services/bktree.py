"""BK-Tree data structure for efficient Hamming distance lookups."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple


class BKTree:
    """BK-Tree for fast nearest-neighbor search on discrete metric spaces.

    Designed for Hamming distance on perceptual hashes, where the triangle
    inequality holds.
    """

    def __init__(self, distance_fn: Callable[[str, str], int]) -> None:
        self._distance_fn = distance_fn
        self._root: Optional[_BKNode] = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def add(self, item: str) -> None:
        if self._root is None:
            self._root = _BKNode(item)
            self._size += 1
            return
        node = self._root
        while True:
            d = self._distance_fn(node.value, item)
            if d == 0:
                return
            child = node.children.get(d)
            if child is None:
                node.children[d] = _BKNode(item)
                self._size += 1
                return
            node = child

    def find_within(self, item: str, max_distance: int) -> List[Tuple[str, int]]:
        """Return all items within *max_distance* of *item* as (value, distance) pairs."""
        if self._root is None:
            return []
        results: List[Tuple[str, int]] = []
        stack = [self._root]
        while stack:
            node = stack.pop()
            d = self._distance_fn(node.value, item)
            if d <= max_distance:
                results.append((node.value, d))
            lo = max(0, d - max_distance)
            hi = d + max_distance
            for child_d, child in node.children.items():
                if lo <= child_d <= hi:
                    stack.append(child)
        return results


class _BKNode:
    __slots__ = ("value", "children")

    def __init__(self, value: str) -> None:
        self.value = value
        self.children: dict[int, _BKNode] = {}


def group_by_similarity(
    hash_pairs: List[Tuple[str, str]],
    max_distance: int = 8,
) -> List[List[str]]:
    """Group ``(rel, phash)`` pairs by perceptual similarity.

    Returns a list of groups, each group being a list of ``rel`` values whose
    pairwise Hamming distance is at most *max_distance*.

    Uses a BK-Tree for O(N log N) average lookup instead of O(N^2) brute force.
    """
    from .phash_computer import PerceptualHashComputer

    if not hash_pairs:
        return []

    tree = BKTree(PerceptualHashComputer.hamming_distance)
    phash_to_rels: dict[str, list[str]] = {}

    for rel, phash in hash_pairs:
        if not phash:
            continue
        phash_to_rels.setdefault(phash, []).append(rel)
        tree.add(phash)

    visited: set[str] = set()
    groups: List[List[str]] = []

    for phash in phash_to_rels:
        if phash in visited:
            continue
        neighbors = tree.find_within(phash, max_distance)
        group_rels: List[str] = []
        for neighbor_hash, _dist in neighbors:
            if neighbor_hash not in visited:
                visited.add(neighbor_hash)
                group_rels.extend(phash_to_rels.get(neighbor_hash, []))

        if len(group_rels) >= 2:
            groups.append(group_rels)

    return groups
