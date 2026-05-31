# Large Library Performance Refactor Log

Date: 2026-05-30
Branch: `codex/large-library-performance`

## Scope

This branch implements the staged mainline for the large-library performance
requirements. It covers Phase 0-2 foundations and one scan batching baseline:

- opt-in performance events and full-scan query auditing
- SQL-first collection DTOs and repository/query-service APIs
- Gallery model/store changes that avoid full snapshot traversal and synchronous
  deep row fetches
- larger default scan merge chunks

The existing deletion of `docs/requirements/INITIAL_SCAN_LARGE_LIBRARY_STABILITY.md`
was preserved and not modified.

## Completed Changes

- Added `emit_perf_event()` and full-scan auditing under
  `iPhoto.infrastructure.services.performance_events`.
- Added `CollectionQuery`, `CollectionType`, `SortDirection`, `PageCursor`,
  `PageResult`, and `WindowResult` while keeping `AssetQuery`.
- Added collection query SQL builders and repository APIs:
  `count_collection()`, `read_collection_page()`, `read_collection_window()`,
  `find_row_by_path()`, and `find_live_partner()`.
- Added schema columns and indexes for large-library collection access:
  `sort_ts`, `is_deleted`, `has_gps`, `thumbnail_state`, thumbnail cache fields,
  and `index_revision`.
- Routed eligible `LibraryAssetQueryService` queries through collection SQL so
  GPS, date range, favorite false, media type, favorites, and album filters do
  not fall back to Python materialization.
- Changed Gallery behavior so `asset_at()` returns only cached rows, and
  `row_for_path()` uses query-service lookup instead of scanning every window.
- Replaced the model reset snapshot hash with a count/window/revision signature.
- Changed live motion lookup to prefer repository-backed partner lookup instead
  of scanning every row in the model.
- Increased the default scan merge chunk size from 50 to 500 rows.
- Fixed the deep-scroll placeholder stall for aggregate and physical-folder
  albums. `read_collection_window()` now uses an anchor/keyset fallback for
  windows beyond the shallow offset threshold instead of raising, and Gallery
  window fetch failures are contained so later visible-range requests can
  recover.
- Fixed the related Detail/Playback failure where deep-scroll placeholders could
  not be opened or operated on. The root cause was missing collection rows, not
  just missing thumbnail pixmaps: Gallery viewport range reporting could expand
  to the end of the album, and Detail/Playback relied on cached-only
  `asset_at()` reads. The branch now bounds viewport windows and adds an
  explicit `ensure_row_loaded()` path for user-initiated opens/navigation while
  keeping `asset_at()` cache-only.

## Verification

Final commands run:

```bash
.venv/bin/pytest tests/ui/test_media_selection_session.py tests/gui/viewmodels/test_detail_viewmodel.py tests/gui/viewmodels/test_gallery_collection_store.py tests/test_asset_grid_scroll.py
```

Result:

- 42 passed
- 1 warning from pytest config: unknown `env` option

```bash
.venv/bin/pytest tests/application/test_library_asset_query_service.py tests/cache/test_index_store_features.py tests/gui/viewmodels/test_gallery_list_model_adapter.py tests/application/test_library_scan_service.py tests/performance/test_refactor_performance_baseline.py
```

Result:

- 50 passed
- 1 warning from pytest config: unknown `env` option

```bash
python3 -m compileall -q src/iPhoto
```

Result: passed.

## Handoff

Next recommended work:

- Phase 3: make visible rows require `thumbnail_state='ready'` plus
  `micro_thumbnail` or `thumb_cache_key`; migrate old rows to `stale` and
  backfill visible windows first.
- Phase 4: add `scan_jobs` and `scan_events`, then publish explicit
  `ScanBatchCommitted` batches containing only thumbnail-ready rows.
- Phase 5: split startup into first paint, session bind, first collection, and
  idle jobs so automatic scanning and People/Maps work cannot block startup.
- Phase 6: add opt-in 100k/1M synthetic benchmarks and stricter query-plan
  assertions.

Known constraints:

- The new collection APIs return dict rows for compatibility; a later pass can
  introduce typed DTO rows once GUI callers are fully migrated.
- Thumbnail cache priority, cancellation, failure cooldown, and scan-time
  thumbnail guarantees are still future work.
- Phase 3 will still improve placeholder quality by enforcing thumbnail-ready
  visible rows, but it is no longer expected to fix deep-scroll loading stalls;
  that bug is handled in this branch.
