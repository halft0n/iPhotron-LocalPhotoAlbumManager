from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from iPhoto.gui.ui.widgets import dialogs


class _FakeFileMode:
    Directory = "directory"


class _FakeAcceptMode:
    AcceptOpen = "accept-open"


class _FakeOption:
    ShowDirsOnly = "show-dirs-only"
    DontUseNativeDialog = "dont-use-native-dialog"


class _FakeQFileDialog:
    FileMode = _FakeFileMode
    AcceptMode = _FakeAcceptMode
    Option = _FakeOption

    static_calls: ClassVar[list[tuple[object, str, str]]] = []
    instances: ClassVar[list[_FakeQFileDialog]] = []
    static_result = ""
    exec_result = 1
    selected_result: ClassVar[list[str]] = []

    def __init__(self, parent: object, caption: str, directory: str) -> None:
        self.parent = parent
        self.caption = caption
        self.directory = directory
        self.file_mode: object | None = None
        self.accept_mode: object | None = None
        self.options: list[tuple[object, bool]] = []
        self.instances.append(self)

    @classmethod
    def getExistingDirectory(cls, parent: object, caption: str, directory: str) -> str:  # noqa: N802
        cls.static_calls.append((parent, caption, directory))
        return cls.static_result

    def setFileMode(self, mode: object) -> None:  # noqa: N802
        self.file_mode = mode

    def setAcceptMode(self, mode: object) -> None:  # noqa: N802
        self.accept_mode = mode

    def setOption(self, option: object, enabled: bool) -> None:  # noqa: N802
        self.options.append((option, enabled))

    def exec(self) -> int:
        return self.exec_result

    def selectedFiles(self) -> list[str]:  # noqa: N802
        return list(self.selected_result)


def _install_fake_qfiledialog(monkeypatch) -> type[_FakeQFileDialog]:
    _FakeQFileDialog.static_calls = []
    _FakeQFileDialog.instances = []
    _FakeQFileDialog.static_result = ""
    _FakeQFileDialog.exec_result = 1
    _FakeQFileDialog.selected_result = []
    monkeypatch.setattr(dialogs, "QFileDialog", _FakeQFileDialog)
    return _FakeQFileDialog


def test_select_directory_uses_native_static_dialog_on_non_macos(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_dialog = _install_fake_qfiledialog(monkeypatch)
    monkeypatch.setattr(dialogs.sys, "platform", "linux")
    parent = object()
    selected = tmp_path / "selected"
    fake_dialog.static_result = str(selected)

    result = dialogs.select_directory(
        parent,
        "Select Basic Library",
        use_qt_directory_dialog_on_macos=True,
    )

    assert result == selected
    assert fake_dialog.static_calls == [(parent, "Select Basic Library", "")]
    assert fake_dialog.instances == []


def test_select_directory_uses_native_static_dialog_on_macos_when_flag_is_disabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_dialog = _install_fake_qfiledialog(monkeypatch)
    monkeypatch.setattr(dialogs.sys, "platform", "darwin")
    parent = object()
    start = tmp_path / "start"
    selected = tmp_path / "selected"
    fake_dialog.static_result = str(selected)

    result = dialogs.select_directory(parent, "Select album", start=start)

    assert result == selected
    assert fake_dialog.static_calls == [(parent, "Select album", str(start))]
    assert fake_dialog.instances == []


def test_select_directory_uses_qt_directory_dialog_on_macos_when_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_dialog = _install_fake_qfiledialog(monkeypatch)
    monkeypatch.setattr(dialogs.sys, "platform", "darwin")
    start = tmp_path / "start"
    selected = tmp_path / "selected"
    fake_dialog.selected_result = [str(selected)]

    result = dialogs.select_directory(
        object(),
        "Select Basic Library",
        start=start,
        use_qt_directory_dialog_on_macos=True,
    )

    assert result == selected
    assert fake_dialog.static_calls == []
    assert len(fake_dialog.instances) == 1
    dialog = fake_dialog.instances[0]
    assert dialog.caption == "Select Basic Library"
    assert dialog.directory == str(start)
    assert dialog.file_mode == fake_dialog.FileMode.Directory
    assert dialog.accept_mode == fake_dialog.AcceptMode.AcceptOpen
    assert dialog.options == [
        (fake_dialog.Option.ShowDirsOnly, True),
        (fake_dialog.Option.DontUseNativeDialog, True),
    ]


def test_select_directory_qt_macos_dialog_returns_none_when_cancelled(monkeypatch) -> None:
    fake_dialog = _install_fake_qfiledialog(monkeypatch)
    monkeypatch.setattr(dialogs.sys, "platform", "darwin")
    fake_dialog.exec_result = 0

    result = dialogs.select_directory(
        object(),
        "Select Basic Library",
        use_qt_directory_dialog_on_macos=True,
    )

    assert result is None
    assert len(fake_dialog.instances) == 1


def test_select_directory_qt_macos_dialog_uses_home_as_default_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_dialog = _install_fake_qfiledialog(monkeypatch)
    monkeypatch.setattr(dialogs.sys, "platform", "darwin")
    monkeypatch.setattr(dialogs.Path, "home", lambda: tmp_path)
    fake_dialog.selected_result = []

    result = dialogs.select_directory(
        object(),
        "Select Basic Library",
        use_qt_directory_dialog_on_macos=True,
    )

    assert result is None
    assert fake_dialog.instances[0].directory == str(tmp_path)
