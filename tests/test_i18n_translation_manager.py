from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="PySide6 is required for i18n tests", exc_type=ImportError)
pytest.importorskip("PySide6.QtWidgets", reason="Qt widgets not available", exc_type=ImportError)
pytest.importorskip("PySide6.QtTest", reason="Qt test helpers not available", exc_type=ImportError)

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QWidget

from iPhoto.gui.i18n import TranslationManager
from iPhoto.gui.i18n.language import LanguageInfo
from iPhoto.gui.ui.main_window import MainWindow
from iPhoto.gui.ui.widgets.main_header import MainHeaderWidget
from iPhoto.settings.manager import SettingsManager
from iPhoto.settings.schema import merge_with_defaults, validate_settings


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _settings(tmp_path: Path) -> SettingsManager:
    manager = SettingsManager(path=tmp_path / "settings.json")
    manager.load()
    return manager


def test_settings_language_default_and_schema() -> None:
    merged = merge_with_defaults({"ui": {"theme": "dark"}})

    assert merged["ui"]["language"] == "system"
    validate_settings({**merged, "ui": {**merged["ui"], "language": "de"}})
    validate_settings({**merged, "ui": {**merged["ui"], "language": "zh-CN"}})

    invalid = {**merged, "ui": {**merged["ui"], "language": "fr"}}
    with pytest.raises(Exception):
        validate_settings(invalid)


def test_translation_manager_reads_languages_and_switches_to_chinese(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    manager = _settings(tmp_path)
    translations = TranslationManager(manager)
    spy = QSignalSpy(translations.languageChanged)

    translations.apply_language()
    translations.set_language("zh-CN")
    qapp.processEvents()

    codes = {item.code for item in translations.available_languages()}
    assert {"system", "de", "zh-CN"}.issubset(codes)
    assert manager.get("ui.language") == "zh-CN"
    assert translations.current_language() == "zh-CN"
    assert translations.effective_language() == "zh-CN"
    assert spy.count() >= 1
    assert QCoreApplication.translate("MainHeader", "Language", None) == "语言"


def test_translation_manager_falls_back_when_qm_is_missing(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    manager = _settings(tmp_path)
    translations = TranslationManager(manager)
    translations._available["de"] = LanguageInfo(
        code="de",
        native_name="Deutsch",
        english_name="German",
        qt_locale="de_DE",
        qm="missing.qm",
    )

    translations.apply_language("de")
    qapp.processEvents()

    assert translations.current_language() == "de"
    assert translations.effective_language() == "en"


def test_main_header_language_menu_actions_are_exclusive(qapp: QApplication) -> None:
    parent = QWidget()
    try:
        header = MainHeaderWidget(None, parent)
        language_actions = header.language_group.actions()

        assert header.language_menu.title() == "Language"
        assert [action.data() for action in language_actions] == ["system", "de", "zh-CN"]
        assert [action.text() for action in language_actions] == [
            "System",
            "Deutsch",
            "简体中文",
        ]
        header.language_de.setChecked(True)
        assert header.language_de.isChecked()
        assert not header.language_system.isChecked()
    finally:
        parent.deleteLater()


def test_main_window_language_change_queues_retranslate(monkeypatch, qapp: QApplication) -> None:
    calls: list[str] = []
    window = MainWindow.__new__(MainWindow)
    window.ui = type(
        "FakeUi",
        (),
        {
            "main_header": object(),
            "retranslateUi": lambda _ui, _window: calls.append("ui"),
        },
    )()
    window.window_manager = None
    monkeypatch.setattr(window, "findChildren", lambda _type: [])

    window._schedule_retranslate_ui_tree()
    qapp.processEvents()

    assert calls == ["ui"]
