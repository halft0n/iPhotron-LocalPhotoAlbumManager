"""Heuristic screenshot classifier -- pure domain service, no I/O."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Optional


class ScreenshotClassifier:
    """Score-based screenshot classifier using filename, path, resolution, and EXIF cues."""

    FILENAME_PATTERNS = [
        re.compile(r"^Screenshot[_\s\-]", re.IGNORECASE),
        re.compile(r"^Screen\s?Shot\s", re.IGNORECASE),
        re.compile(r"^截图", re.IGNORECASE),
        re.compile(r"^屏幕截图", re.IGNORECASE),
        re.compile(r"^Bildschirmfoto", re.IGNORECASE),
        re.compile(r"^Captura\s?de\s?pantalla", re.IGNORECASE),
        re.compile(r"_screenshot\.", re.IGNORECASE),
        re.compile(r"^snap\d{4}", re.IGNORECASE),
    ]

    PATH_PATTERNS = [
        "/screenshots/",
        "/截图/",
        "/screen shots/",
        "/bildschirmfotos/",
    ]

    KNOWN_SCREEN_RESOLUTIONS: frozenset[tuple[int, int]] = frozenset({
        # iPhone
        (1170, 2532), (1284, 2778), (1179, 2556), (1290, 2796),
        (1125, 2436), (828, 1792), (750, 1334), (1242, 2688),
        (1080, 2340), (1242, 2208), (640, 1136),
        # iPad
        (2048, 2732), (1620, 2160), (2388, 1668), (2360, 1640),
        # Android
        (1080, 1920), (1080, 2400), (1440, 2560), (1440, 3200),
        (1080, 2340), (1440, 3120), (720, 1280), (720, 1520),
        (1080, 2160), (2560, 1600),
        # Desktop
        (1920, 1080), (2560, 1440), (3840, 2160), (1366, 768),
        (1440, 900), (2560, 1600), (3024, 1964), (2880, 1800),
    })

    _THRESHOLD = 40

    @classmethod
    def classify(
        cls,
        rel: str,
        w: int,
        h: int,
        make: Optional[str],
        model: Optional[str],
        mime: Optional[str],
    ) -> bool:
        """Return *True* when *rel* is likely a screenshot."""
        return cls.score(rel, w, h, make, model, mime) >= cls._THRESHOLD

    @classmethod
    def score(
        cls,
        rel: str,
        w: int,
        h: int,
        make: Optional[str],
        model: Optional[str],
        mime: Optional[str],
    ) -> int:
        """Return an integer confidence score (higher = more likely screenshot)."""
        points = 0

        filename = PurePosixPath(rel).name
        if any(p.search(filename) for p in cls.FILENAME_PATTERNS):
            points += 60

        rel_lower = rel.lower().replace("\\", "/")
        if any(p in rel_lower for p in cls.PATH_PATTERNS):
            points += 40

        if w and h:
            dims = (min(w, h), max(w, h))
            if dims in cls.KNOWN_SCREEN_RESOLUTIONS:
                points += 25

        if not make and not model:
            points += 10
            if mime and "png" in mime.lower():
                points += 10

        return points
