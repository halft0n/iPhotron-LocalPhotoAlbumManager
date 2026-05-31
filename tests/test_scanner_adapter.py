from __future__ import annotations

from pathlib import Path

from iPhoto.io import scanner_adapter


def test_process_media_paths_falls_back_to_minimal_row_when_metadata_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "Library"
    root.mkdir()
    asset = root / "broken.jpg"
    asset.write_bytes(b"jpeg-data")

    monkeypatch.setattr(
        scanner_adapter._metadata_provider,
        "get_metadata_batch",
        lambda paths: [],
    )
    monkeypatch.setattr(
        scanner_adapter._metadata_provider,
        "normalize_metadata",
        lambda _root, _path, _raw: (_ for _ in ()).throw(RuntimeError("exif failure")),
    )
    monkeypatch.setattr(
        scanner_adapter._thumbnail_generator,
        "generate_micro_thumbnail",
        lambda _path: None,
    )

    rows = list(scanner_adapter.process_media_paths(root, [asset], []))

    assert len(rows) == 1
    row = rows[0]
    assert row["rel"] == "broken.jpg"
    assert row["bytes"] == len(b"jpeg-data")
    assert row["media_type"] == 0
    assert row["face_status"] == "pending"
    assert row["id"].startswith("as_")
    assert row["thumbnail_state"] == "failed"
    assert row["thumb_error"] == "thumbnail_unavailable"


def test_process_media_paths_keeps_row_when_thumbnail_generation_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "Library"
    root.mkdir()
    asset = root / "thumb_fail.jpg"
    asset.write_bytes(b"jpeg-data")

    monkeypatch.setattr(
        scanner_adapter._metadata_provider,
        "get_metadata_batch",
        lambda paths: [],
    )
    monkeypatch.setattr(
        scanner_adapter._metadata_provider,
        "normalize_metadata",
        lambda _root, _path, _raw: {
            "rel": "thumb_fail.jpg",
            "bytes": len(b"jpeg-data"),
            "dt": "2024-01-01T00:00:00Z",
            "ts": 1704067200000000,
            "id": "as_thumb_fail",
            "mime": "image/jpeg",
            "media_type": 0,
            "face_status": "pending",
        },
    )
    monkeypatch.setattr(
        scanner_adapter._thumbnail_generator,
        "generate_micro_thumbnail",
        lambda _path: (_ for _ in ()).throw(RuntimeError("thumb failure")),
    )

    rows = list(scanner_adapter.process_media_paths(root, [asset], []))

    assert len(rows) == 1
    row = rows[0]
    assert row["rel"] == "thumb_fail.jpg"
    assert row["id"] == "as_thumb_fail"
    assert row["face_status"] == "pending"
    assert row["thumbnail_state"] == "failed"
    assert "thumb failure" in row["thumb_error"]
    assert "micro_thumbnail" not in row


def test_process_media_paths_sets_ready_thumbnail_before_visible_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "Library"
    root.mkdir()
    asset = root / "ready.jpg"
    asset.write_bytes(b"jpeg-data")

    monkeypatch.setattr(
        scanner_adapter._metadata_provider,
        "get_metadata_batch",
        lambda paths: [],
    )
    monkeypatch.setattr(
        scanner_adapter._metadata_provider,
        "normalize_metadata",
        lambda _root, _path, _raw: {
            "rel": "ready.jpg",
            "bytes": len(b"jpeg-data"),
            "dt": "2024-01-01T00:00:00Z",
            "ts": 1704067200000000,
            "id": "as_ready",
            "mime": "image/jpeg",
            "media_type": 0,
            "face_status": "pending",
        },
    )
    monkeypatch.setattr(
        scanner_adapter._thumbnail_generator,
        "generate_micro_thumbnail",
        lambda _path: b"thumb-bytes",
    )

    rows = list(scanner_adapter.process_media_paths(root, [asset], []))

    assert len(rows) == 1
    row = rows[0]
    assert row["thumbnail_state"] == "ready"
    assert row["micro_thumbnail"] == b"thumb-bytes"
