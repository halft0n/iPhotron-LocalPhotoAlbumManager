"""Perceptual hash computation and comparison utilities."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)


class PerceptualHashComputer:
    """Compute and compare perceptual hashes using the imagehash library."""

    @staticmethod
    def compute_phash(image_path: Path, hash_size: int = 8) -> Optional[str]:
        """Compute the pHash for an image file, returning a hex string or None on failure."""
        try:
            from PIL import Image
            import imagehash

            with Image.open(image_path) as img:
                h = imagehash.phash(img, hash_size=hash_size)
                return str(h)
        except Exception as exc:
            _logger.debug("phash computation failed for %s: %s", image_path, exc)
            return None

    @staticmethod
    def compute_phash_from_thumbnail(
        thumbnail_path: Path, hash_size: int = 8
    ) -> Optional[str]:
        """Compute pHash from a pre-generated thumbnail (faster than original)."""
        return PerceptualHashComputer.compute_phash(thumbnail_path, hash_size)

    @staticmethod
    def hamming_distance(hash_a: str, hash_b: str) -> int:
        """Compute the Hamming distance between two hex-encoded hashes."""
        try:
            int_a = int(hash_a, 16)
            int_b = int(hash_b, 16)
            xor = int_a ^ int_b
            return bin(xor).count("1")
        except (ValueError, TypeError):
            return 64
