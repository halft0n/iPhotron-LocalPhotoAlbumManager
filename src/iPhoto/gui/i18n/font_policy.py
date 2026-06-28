"""Application font policy for translated Qt UI text."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication

_LOGGER = logging.getLogger(__name__)
_SIMPLIFIED_CHINESE_LANGUAGE = "zh-CN"
_WINDOWS_SIMPLIFIED_CHINESE_FONTS = (
    "Microsoft YaHei",
    "Microsoft Yahei",
    "微软雅黑",
)
_LINUX_SIMPLIFIED_CHINESE_FONTS = ("Noto Sans CJK SC",)


@dataclass
class _FontState:
    app_id: int | None = None
    original_font: QFont | None = None
    applied_family: str | None = None
    substitution_family: str | None = None
    original_substitutions: list[str] | None = None
    applied_substitution: str | None = None


_STATE = _FontState()


def simplified_chinese_font_family(
    platform: str,
    available_families: Iterable[str],
) -> str | None:
    """Return the preferred Simplified Chinese UI font available on *platform*."""

    candidates = _font_candidates_for_platform(platform)
    if not candidates:
        return None

    available_by_name = {
        _normalise_family_name(family): family
        for family in available_families
        if family and not str(family).startswith("@")
    }
    for candidate in candidates:
        family = available_by_name.get(_normalise_family_name(candidate))
        if family:
            return family
    return None


def apply_language_font(effective_language: str) -> str | None:
    """Apply the app font matching *effective_language* and return its family."""

    app = QGuiApplication.instance()
    if app is None:
        return None

    _ensure_state_for_app(app)

    if effective_language != _SIMPLIFIED_CHINESE_LANGUAGE:
        _restore_language_font(app)
        return None

    platform = sys.platform
    if platform.startswith("linux"):
        return _apply_linux_simplified_chinese_substitution(app)
    if platform != "win32":
        _restore_language_font(app)
        return None

    _restore_linux_substitution()
    return _apply_windows_simplified_chinese_font(app)


def _apply_windows_simplified_chinese_font(app: QGuiApplication) -> str | None:
    family = simplified_chinese_font_family(sys.platform, _available_font_families())
    if family is None:
        _LOGGER.info("No Simplified Chinese UI font override available on %s", sys.platform)
        return None

    if _STATE.original_font is None:
        _STATE.original_font = QFont(app.font())

    font = QFont(app.font())
    font.setFamily(family)
    app.setFont(font)
    _STATE.applied_family = family
    return family


def _apply_linux_simplified_chinese_substitution(app: QGuiApplication) -> str:
    _restore_windows_font(app)

    base_family = str(app.font().family() or "").strip()
    preferred_family = _LINUX_SIMPLIFIED_CHINESE_FONTS[0]
    if not base_family:
        return preferred_family

    if _STATE.substitution_family != base_family:
        _restore_linux_substitution()
        _STATE.substitution_family = base_family
        _STATE.original_substitutions = list(QFont.substitutes(base_family))

    existing = _STATE.original_substitutions or []
    substitutions = _deduplicated_families([preferred_family, *existing])
    QFont.removeSubstitutions(base_family)
    QFont.insertSubstitutions(base_family, substitutions)
    _STATE.applied_substitution = preferred_family
    return preferred_family


def _font_candidates_for_platform(platform: str) -> tuple[str, ...]:
    if platform == "win32":
        return _WINDOWS_SIMPLIFIED_CHINESE_FONTS
    if platform.startswith("linux"):
        return _LINUX_SIMPLIFIED_CHINESE_FONTS
    return ()


def _normalise_family_name(family: object) -> str:
    return str(family).strip().casefold()


def _deduplicated_families(families: Iterable[str]) -> list[str]:
    deduplicated: list[str] = []
    seen: set[str] = set()
    for family in families:
        normalized = _normalise_family_name(family)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduplicated.append(str(family).strip())
    return deduplicated


def _available_font_families() -> list[str]:
    try:
        return list(QFontDatabase.families())
    except Exception:  # noqa: BLE001 - font probing must never block GUI startup.
        _LOGGER.warning("Unable to inspect Qt font database", exc_info=True)
        return []


def _ensure_state_for_app(app: QGuiApplication) -> None:
    app_id = id(app)
    if _STATE.app_id == app_id:
        return
    _STATE.app_id = app_id
    _STATE.original_font = None
    _STATE.applied_family = None
    _STATE.substitution_family = None
    _STATE.original_substitutions = None
    _STATE.applied_substitution = None


def _restore_language_font(app: QGuiApplication) -> None:
    _restore_windows_font(app)
    _restore_linux_substitution()


def _restore_windows_font(app: QGuiApplication) -> None:
    if _STATE.applied_family is None:
        return
    if _STATE.original_font is not None:
        app.setFont(QFont(_STATE.original_font))
    _STATE.original_font = None
    _STATE.applied_family = None


def _restore_linux_substitution() -> None:
    base_family = _STATE.substitution_family
    if base_family is None:
        return

    QFont.removeSubstitutions(base_family)
    if _STATE.original_substitutions:
        QFont.insertSubstitutions(base_family, list(_STATE.original_substitutions))
    _STATE.substitution_family = None
    _STATE.original_substitutions = None
    _STATE.applied_substitution = None


__all__ = ["apply_language_font", "simplified_chinese_font_family"]
