"""Tests for the ScreenshotClassifier domain service."""

from __future__ import annotations

import pytest

from iPhoto.domain.services.screenshot_classifier import ScreenshotClassifier


class TestScreenshotClassifier:
    """Test screenshot classification heuristics."""

    def test_filename_screenshot_english(self):
        assert ScreenshotClassifier.classify(
            "Screenshot_2024-03-15.png", 1080, 1920, None, None, "image/png"
        )

    def test_filename_screenshot_chinese(self):
        assert ScreenshotClassifier.classify(
            "截图_2024-03-15.png", 1080, 1920, None, None, "image/png"
        )

    def test_filename_screenshot_german(self):
        assert ScreenshotClassifier.classify(
            "Bildschirmfoto 2024-03-15.png", 1920, 1080, None, None, "image/png"
        )

    def test_filename_screen_shot_with_space(self):
        assert ScreenshotClassifier.classify(
            "Screen Shot 2024-03-15 at 14.23.45.png", 2560, 1440, None, None, "image/png"
        )

    def test_path_screenshots_folder(self):
        assert ScreenshotClassifier.classify(
            "DCIM/Screenshots/img_001.png", 1080, 1920, None, None, "image/png"
        )

    def test_path_chinese_screenshots_folder(self):
        assert ScreenshotClassifier.classify(
            "手机相册/截图/img_001.png", 1080, 1920, None, None, "image/png"
        )

    def test_normal_photo_not_screenshot(self):
        assert not ScreenshotClassifier.classify(
            "vacation/2024/IMG_1234.jpg", 4032, 3024, "Canon", "EOS R5", "image/jpeg"
        )

    def test_normal_photo_with_screen_resolution(self):
        # Screen resolution alone is not enough (25 + 10 = 35 < 40)
        assert not ScreenshotClassifier.classify(
            "photos/photo.jpg", 1920, 1080, None, None, "image/jpeg"
        )

    def test_png_no_exif_screen_resolution_is_screenshot(self):
        # Screen resolution + no EXIF + PNG = 25 + 10 + 10 = 45 >= 40
        assert ScreenshotClassifier.classify(
            "photos/image.png", 1920, 1080, None, None, "image/png"
        )

    def test_zero_dimensions(self):
        # Should not crash with zero dimensions
        result = ScreenshotClassifier.classify(
            "photo.jpg", 0, 0, None, None, "image/jpeg"
        )
        # No filename pattern, no resolution, no EXIF gives 10 points < 40
        assert not result

    def test_score_method(self):
        score = ScreenshotClassifier.score(
            "Screenshot_2024.png", 1080, 1920, None, None, "image/png"
        )
        # filename=60, resolution=25, no_exif=10, png=10 = 105
        assert score >= 60

    def test_filename_suffix_pattern(self):
        assert ScreenshotClassifier.classify(
            "game_screenshot.png", 1920, 1080, None, None, "image/png"
        )

    def test_snap_pattern(self):
        assert ScreenshotClassifier.classify(
            "snap0001.png", 1920, 1080, None, None, "image/png"
        )

    def test_spanish_captura(self):
        assert ScreenshotClassifier.classify(
            "Captura de pantalla 2024.png", 1080, 1920, None, None, "image/png"
        )

    def test_video_file_not_screenshot(self):
        assert not ScreenshotClassifier.classify(
            "video.mp4", 1920, 1080, None, None, "video/mp4"
        )

    def test_iphone_resolution_with_camera_info(self):
        # Has camera info, so only gets 25 points for resolution
        assert not ScreenshotClassifier.classify(
            "IMG_0001.jpg", 1170, 2532, "Apple", "iPhone 14 Pro", "image/jpeg"
        )
