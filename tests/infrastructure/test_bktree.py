"""Tests for the BK-Tree data structure and similarity grouping."""

from __future__ import annotations

import pytest

from iPhoto.infrastructure.services.bktree import BKTree, group_by_similarity
from iPhoto.infrastructure.services.phash_computer import PerceptualHashComputer


class TestBKTree:
    def test_add_and_find(self):
        tree = BKTree(PerceptualHashComputer.hamming_distance)
        tree.add("ff00ff00ff00ff00")
        tree.add("ff00ff00ff00ff01")
        tree.add("0000000000000000")

        results = tree.find_within("ff00ff00ff00ff00", 2)
        hashes = {h for h, d in results}
        assert "ff00ff00ff00ff00" in hashes
        assert "ff00ff00ff00ff01" in hashes
        assert "0000000000000000" not in hashes

    def test_empty_tree(self):
        tree = BKTree(PerceptualHashComputer.hamming_distance)
        assert tree.find_within("ff00ff00ff00ff00", 10) == []

    def test_exact_match(self):
        tree = BKTree(PerceptualHashComputer.hamming_distance)
        tree.add("abcdef0123456789")
        results = tree.find_within("abcdef0123456789", 0)
        assert len(results) == 1
        assert results[0][1] == 0

    def test_no_duplicates(self):
        tree = BKTree(PerceptualHashComputer.hamming_distance)
        tree.add("ff00ff00ff00ff00")
        tree.add("ff00ff00ff00ff00")
        assert len(tree) == 1

    def test_large_distance(self):
        tree = BKTree(PerceptualHashComputer.hamming_distance)
        tree.add("ffffffffffffffff")
        tree.add("0000000000000000")
        results = tree.find_within("ffffffffffffffff", 64)
        assert len(results) == 2


class TestGroupBySimilarity:
    def test_two_similar_photos(self):
        pairs = [
            ("a.jpg", "ff00ff00ff00ff00"),
            ("b.jpg", "ff00ff00ff00ff01"),
        ]
        groups = group_by_similarity(pairs, max_distance=2)
        assert len(groups) == 1
        assert set(groups[0]) == {"a.jpg", "b.jpg"}

    def test_no_similar_photos(self):
        pairs = [
            ("a.jpg", "ffffffffffffffff"),
            ("b.jpg", "0000000000000000"),
        ]
        groups = group_by_similarity(pairs, max_distance=2)
        assert len(groups) == 0

    def test_empty_input(self):
        groups = group_by_similarity([], max_distance=8)
        assert groups == []

    def test_single_photo(self):
        pairs = [("a.jpg", "ff00ff00ff00ff00")]
        groups = group_by_similarity(pairs, max_distance=8)
        assert len(groups) == 0

    def test_multiple_groups(self):
        pairs = [
            ("a.jpg", "ff00ff00ff00ff00"),
            ("b.jpg", "ff00ff00ff00ff01"),
            ("c.jpg", "0000000000000000"),
            ("d.jpg", "0000000000000001"),
        ]
        groups = group_by_similarity(pairs, max_distance=2)
        assert len(groups) == 2

    def test_three_way_group(self):
        pairs = [
            ("a.jpg", "ff00ff00ff00ff00"),
            ("b.jpg", "ff00ff00ff00ff01"),
            ("c.jpg", "ff00ff00ff00ff03"),
        ]
        groups = group_by_similarity(pairs, max_distance=3)
        assert len(groups) == 1
        assert len(groups[0]) == 3


class TestHammingDistance:
    def test_identical(self):
        assert PerceptualHashComputer.hamming_distance("abcd", "abcd") == 0

    def test_single_bit_diff(self):
        assert PerceptualHashComputer.hamming_distance(
            "ff00ff00ff00ff00", "ff00ff00ff00ff01"
        ) == 1

    def test_all_bits_diff(self):
        assert PerceptualHashComputer.hamming_distance(
            "ffffffffffffffff", "0000000000000000"
        ) == 64

    def test_invalid_hash(self):
        assert PerceptualHashComputer.hamming_distance("invalid", "hash") == 64
