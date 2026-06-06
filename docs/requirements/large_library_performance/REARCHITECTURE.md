# 超大型相册性能架构迁移开发需求

> **版本:** 1.0 | **日期:** 2026-05-30  
> **状态:** 未来开发需求  
> **范围:** 大型相册导入、All Photos/聚合相册打开、首次启动、日常滚动浏览、扫描实时可见更新、缩略图入库保障

---

## 1. 背景与目标

当前项目已经有正确的运行时骨架：`RuntimeContext`、`LibrarySession`、`.iPhoto/global_index.db`、`LibraryAssetQueryService`、`get_assets_page()`、`read_geometry_only()`、`GalleryCollectionStore`、`ThumbnailCacheService` 等模块已经为大型库优化提供了基础。

但在超级大型相册场景下，用户仍会遇到以下不稳定体验：

- 超大型相册导入时，扫描、元数据提取、缩略图生成、数据库写入和 UI 更新互相牵制。
- All Photos 等聚合相册有时进入全量读取、内存过滤、全量排序或全量模型 reset。
- 首次启动仍可能被库绑定、自动扫描、People/Maps/缩略图 warmup 等后台工作拖慢。
- 浏览滚动时存在同步补行、全量 snapshot hash、缩略图生成无限制、空白/黑格显示等问题。
- 扫描过程中用户不能稳定感知媒体内容正在进入库，或看到已经出现但没有缩略图的媒体格。

本文档定义一次面向大型库的架构迁移需求。目标不是微调单个函数，而是让开发人员能按本文迁移到新的扫描、新数据库、新查询逻辑和新 UI 更新机制。

---

## 2. 规模定义与性能 SLO

### 2.1 目标规模

| 档位 | 资产数量 | 目录数量 | 典型用途 |
| --- | ---: | ---: | --- |
| L1 | 10k | 100-1k | 普通用户库，CI 性能基线 |
| L2 | 100k | 1k-10k | 大型个人图库，必须流畅 |
| L3 | 1M | 10k+ | 超大型归档库，允许后台任务长时间运行，但 UI 必须稳定 |

### 2.2 用户可感知指标

| 场景 | SLO | 硬性约束 |
| --- | --- | --- |
| 冷启动首帧 | 主窗口首帧 <= 1.5s | 不得等待全量库扫描、People、Maps、缩略图 warmup |
| 恢复上次库 | 已有 100k 资产库可交互 <= 3s | 只绑定库、打开首屏、延后重任务 |
| All Photos 首屏 | 100k <= 800ms，1M <= 1.5s | 禁止加载全量资产对象 |
| 可见窗口查询 | P95 <= 80ms | 必须 SQL 下推过滤、排序、分页 |
| 连续滚动 | P95 帧间隔 <= 24ms | 不得在 UI 线程做磁盘扫描、原图解码、全量 hash |
| 扫描可见更新 | 新媒体发现到首批可见 P95 <= 500ms，最差 <= 2s | 发布到 UI 的资产必须已有缩略图 |
| 扫描写入 | 默认批量 >= 500 行/事务 | 小批 UI 发布与大批 DB 写入可以分离 |
| 缩略图命中 | L1/L2 hit 不触发 generator | 空白/黑格不得作为正常媒体状态 |

---

## 3. 当前问题定位

### 3.1 已有可复用基础

- `src/iPhoto/cache/index_store/repository.py`
  - 已有 WAL、`get_assets_page()`、`read_geometry_only()`、`count()`、部分索引。
- `src/iPhoto/bootstrap/library_asset_query_service.py`
  - 已经作为 session-backed 查询边界，能避免 GUI 直接依赖 repository singleton。
- `src/iPhoto/gui/viewmodels/gallery_collection_store.py`
  - 已有窗口化缓存、可见范围优先、lookahead/lookbehind。
- `src/iPhoto/infrastructure/services/thumbnail_cache_service.py`
  - 已有 L1 memory、L2 disk、异步生成雏形。
- `src/iPhoto/bootstrap/library_scan_service.py`
  - 已经把扫描纳入 `LibrarySession` 边界。

### 3.2 必须消除的不稳定路径

- `read_all()` 后在 Python 内存中过滤、排序、切片。
- `_requires_in_memory_query()` 覆盖常见筛选，导致大库查询退回全量扫描。
- `GalleryListModelAdapter._snapshot_hash()` 遍历所有 row 并调用 `asset_at()`。
- `row_for_path()`、live motion 查找、location resolve 对全库线性扫描。
- 扫描 chunk size 过小，DB 写入事务频繁，Qt signal 过密。
- 扫描提交 metadata-only row，UI 先显示空白媒体格，再等待缩略图。
- 缩略图队列没有严格优先级、并发上限、失败冷却和取消策略。
- 启动自动扫描、People/Maps 初始化、shader/thumbnail warmup 与首屏竞争资源。

---

## 4. 目标架构

### 4.1 总体原则

```text
UI query surface
  -> CollectionQuery / ViewportRequest
  -> SQL count + keyset/page query
  -> DTO window
  -> thumbnail-ready grid

Scan pipeline
  -> discover
  -> stat/cache validation
  -> metadata extraction
  -> thumbnail extraction
  -> DB commit
  -> visible publish
  -> derived jobs enqueue
```

核心规则：

- 扫描和浏览是两个独立的低耦合数据流，通过数据库 revision 和事件连接。
- 可见 UI 永远消费“已可显示”的资产，不直接消费半成品扫描行。
- 扫描可以后台持续运行，但不能阻塞 All Photos 打开、滚动和用户操作。
- 聚合相册、物理相册、筛选视图和搜索视图统一使用 query descriptor。
- 数据库 schema 必须让常见过滤、排序、分页都在 SQL 层完成。

### 4.2 运行时边界

- `RuntimeContext.resume_startup_tasks()` 只做：
  - 创建或绑定 `LibrarySession`。
  - 打开默认 collection 的首屏 query。
  - 启动低优先级增量扫描 job，但不得等待其完成。
- `LibrarySession` 暴露：
  - `asset_queries`: 分页查询、计数、按 path/id 定位。
  - `scans`: job 创建、取消、进度、visible publish。
  - `thumbnails`: thumbnail cache、优先级队列、ready/failure state。
- GUI 只能通过 session surface 读取数据，不再触碰 repository singleton。

---

## 5. 数据库与索引需求

### 5.1 逻辑库拆分

可以继续使用单个 SQLite 文件实现，但逻辑上必须拆分以下数据：

| 数据域 | 可重建 | 示例 |
| --- | --- | --- |
| 扫描事实 | 是 | 文件路径、bytes、mtime、content id、media type、EXIF/QuickTime facts |
| 缩略图派生状态 | 是 | micro thumbnail、disk thumb key、thumbnail status |
| 查询派生索引 | 是 | timeline bucket、sort key、album membership |
| 用户状态 | 否 | favorite、hidden、trash decision、manual order、manual cover |
| People/Map/Edit 用户状态 | 否 | people names、manual faces、manual location override、sidecar edits |

扫描 merge 只能更新可重建事实和派生状态，不得覆盖用户状态。

### 5.2 `assets` 必需字段

在现有 `assets` 表基础上增加或规范以下字段：

| 字段 | 类型 | 必需 | 说明 |
| --- | --- | --- | --- |
| `rel` | TEXT PRIMARY KEY | 是 | library-relative path |
| `id` | TEXT NOT NULL | 是 | stable asset id |
| `parent_album_path` | TEXT | 是 | album/path 查询前缀 |
| `dt` | TEXT | 是 | ISO 时间，用于兼容现有逻辑 |
| `ts` | INTEGER | 是 | UTC microseconds，主排序字段 |
| `sort_ts` | INTEGER | 是 | `COALESCE(capture_ts, mtime_ts)`，禁止运行时解析字符串排序 |
| `media_type` | INTEGER | 是 | 0 image, 1 video, 后续可扩展 |
| `live_role` | INTEGER | 是 | 0 visible, 1 motion component, etc. |
| `is_favorite` | INTEGER | 是 | 用户状态 overlay 或 materialized cache |
| `is_deleted` | INTEGER | 是 | trash/Recently Deleted 过滤 |
| `has_gps` | INTEGER | 是 | GPS SQL 下推 |
| `thumbnail_state` | TEXT | 是 | `ready`, `pending`, `failed`, `stale` |
| `micro_thumbnail` | BLOB | 条件必需 | 可见资产必须具备其一 |
| `thumb_cache_key` | TEXT | 条件必需 | 可见资产必须具备其一 |
| `thumb_updated_at` | INTEGER | 是 | thumbnail 生成或确认时间 |
| `thumb_error` | TEXT | 否 | 失败原因，供诊断 |
| `scan_job_id` | TEXT | 否 | 最近一次写入来源 |
| `index_revision` | INTEGER | 是 | collection 增量刷新依据 |

硬性规则：

- `thumbnail_state='ready'` 的资产必须满足 `micro_thumbnail IS NOT NULL OR thumb_cache_key IS NOT NULL`。
- `thumbnail_state!='ready'` 的资产不得进入普通媒体 grid；只能进入内部 staging、诊断列表或失败态 UI。
- 扫描阶段允许 metadata-only 暂存，但不得作为可见 collection 查询结果返回。

### 5.3 新增 job 表

建议新增 `scan_jobs`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `job_id` | TEXT PRIMARY KEY | 扫描 job |
| `root` | TEXT | 扫描根路径 |
| `scope` | TEXT | library, album, watcher, import |
| `status` | TEXT | queued, running, paused, cancelled, completed, failed |
| `stage` | TEXT | discover, metadata, thumbnail, db_commit, visible_publish |
| `found_count` | INTEGER | 已发现文件数 |
| `processed_count` | INTEGER | 已处理文件数 |
| `visible_count` | INTEGER | 已发布到 UI 的 ready 资产数 |
| `failed_count` | INTEGER | 失败数 |
| `started_at` | INTEGER | UTC ms |
| `updated_at` | INTEGER | UTC ms |
| `finished_at` | INTEGER | UTC ms |

建议新增 `scan_events`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event_id` | INTEGER PRIMARY KEY | 单调递增 |
| `job_id` | TEXT | 所属 job |
| `event_type` | TEXT | stage_changed, batch_committed, file_failed |
| `payload_json` | TEXT | 小型事件 payload |
| `created_at` | INTEGER | UTC ms |

### 5.4 必需索引

必须覆盖以下查询：

```sql
CREATE INDEX IF NOT EXISTS idx_assets_visible_global
ON assets (live_role, is_deleted, thumbnail_state, sort_ts DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_assets_visible_album
ON assets (parent_album_path, live_role, is_deleted, thumbnail_state, sort_ts DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_assets_visible_media
ON assets (media_type, live_role, is_deleted, thumbnail_state, sort_ts DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_assets_visible_favorite
ON assets (is_favorite, live_role, is_deleted, thumbnail_state, sort_ts DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_assets_gps
ON assets (has_gps, live_role, is_deleted, thumbnail_state, sort_ts DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_assets_rel_lookup
ON assets (rel);

CREATE INDEX IF NOT EXISTS idx_assets_id_lookup
ON assets (id);

CREATE INDEX IF NOT EXISTS idx_assets_revision
ON assets (index_revision);
```

SQLite 要求：

- 保持 WAL。
- `synchronous=NORMAL`。
- 读连接和写连接分离。
- 写事务采用批量 merge，默认 500-2000 行/事务。
- 对 L3 规模提供 `EXPLAIN QUERY PLAN` 回归，禁止出现常见 collection 的全表排序。

---

## 6. 查询与 Collection 需求

### 6.1 CollectionQuery

新增或扩展 `AssetQuery`，形成稳定 query descriptor：

| 字段 | 说明 |
| --- | --- |
| `collection_type` | all_photos, album, favorites, videos, map, people, search |
| `album_path` | album collection 的路径 |
| `include_subalbums` | 是否包含子相册 |
| `media_types` | image/video/live |
| `is_favorite` | favorite 过滤 |
| `has_gps` | map/geotagged 过滤 |
| `date_from/date_to` | 日期范围 |
| `sort_key` | 默认 `sort_ts` |
| `sort_order` | 默认 DESC |
| `limit` | page/window size |
| `cursor` | keyset cursor，包含 `sort_ts` + `id` |
| `offset` | 仅允许小 offset 或测试；深分页必须用 cursor |
| `min_thumbnail_state` | 默认 ready |

### 6.2 Query API

`LibraryAssetQueryService` 必须提供以下能力：

```python
count_collection(query: CollectionQuery) -> int
read_collection_page(query: CollectionQuery, cursor: PageCursor | None) -> PageResult
read_collection_window(query: CollectionQuery, first: int, limit: int) -> WindowResult
find_row_by_path(query: CollectionQuery, path: Path) -> int | None
find_live_partner(asset_id: str) -> AssetDTO | None
```

约束：

- All Photos、album、favorites、videos、GPS 日期范围都必须 SQL 下推。
- 禁止在常规 collection 打开路径中调用 `read_all()`。
- `has_gps`、`date_from/date_to`、`is_favorite=False` 不得自动退回全量内存过滤。
- `offset` 超过 5,000 时必须转 keyset 或 anchor seek；不得深度 OFFSET。
- `count_collection()` 可使用精确 count；L3 场景允许后续增加 approximate count，但 UI 必须标识。

---

## 7. 扫描流水线需求

### 7.1 分阶段流水线

扫描必须拆为以下阶段：

1. `discover`
   - 遍历目录，输出候选文件。
   - 使用 bounded queue，避免一次性 materialize 百万路径。
2. `stat_cache_validation`
   - 比对 `bytes`、`mtime_ns`、可选 content signature、`thumb_cache_key`。
   - 未变化资产直接复用 metadata 和 thumbnail state。
3. `metadata_extraction`
   - ExifTool 必须长驻或批处理，不得每文件启动进程。
   - 视频 metadata 与图片 metadata 可独立 worker pool。
4. `thumbnail_extraction`
   - 每个将进入可见索引的资产必须先生成 micro thumbnail 或 L2 disk thumbnail。
   - RAW/视频优先使用内嵌预览、低成本帧、已有缓存。
5. `db_commit`
   - 以大批量事务写入 ready rows。
   - metadata-only row 只能写入 staging 表或 `thumbnail_state='pending'` 且不可见。
6. `visible_publish`
   - 发布 `scan_batch_committed` 事件，事件只包含 ready rows 的轻量数据。
7. `derived_jobs_enqueue`
   - People、reverse geocoding、similarity、OCR 等非首屏任务延后。

### 7.2 实时 UI 更新

扫描过程中用户必须能实时或接近实时看到媒体内容更新：

- UI 可见批次发布间隔：100-250ms 合并一次，或 ready row 达到 50-200 个立即发布。
- 新媒体从 discover 到首批可见：P95 <= 500ms，最差 <= 2s。
- `scan_batch_committed` 只包含缩略图已 ready 的资产。
- All Photos、当前相册、筛选视图必须能根据当前 query 判断批次是否影响可见窗口。
- 扫描中不得反复 `beginResetModel()`/`endResetModel()`；只允许局部 `rowsInserted` 或窗口 `dataChanged`。

建议事件 payload：

```python
@dataclass(frozen=True)
class ScanBatchCommitted:
    job_id: str
    root: Path
    collection_revision: int
    ready_count: int
    rows: list[AssetSummaryDTO]
    stage_elapsed_ms: dict[str, float]
```

`AssetSummaryDTO` 必须包含：

- `id`
- `rel`
- `parent_album_path`
- `sort_ts`
- `media_type`
- `thumbnail_state='ready'`
- `micro_thumbnail` 或 `thumb_cache_key`
- `is_favorite`
- `live_role`

### 7.3 缩略图入库硬性要求

入库可见索引的最小单位是：

```text
metadata + thumbnail_state + (micro_thumbnail OR thumb_cache_key)
```

禁止：

- 先把 metadata-only row 返回给 gallery，再让 UI 显示黑格。
- 用 `None` pixmap 当作正常媒体展示状态。
- 缩略图失败后无限重试并持续占用 worker。

失败策略：

- 单个资产缩略图失败时写入 `thumbnail_state='failed'`、`thumb_error`。
- 失败资产不出现在普通媒体 grid，除非用户打开诊断/失败列表。
- 支持用户手动重试缩略图生成。
- 扫描 job 的 `failed_count` 必须区分 metadata failed 与 thumbnail failed。

### 7.4 Live Photo 配对

Live Photo 配对不得采用全局 O(n*m) 比较。

要求：

- 扫描时为候选图片/视频建立局部索引：
  - normalized stem
  - parent directory
  - content id
  - capture-time bucket，例如秒级或 2 秒窗口
- 先 exact match，再 time-window fallback。
- 时间字段使用 `ts/sort_ts` 整数，不在内层循环解析 ISO 字符串。
- 配对更新作为同一 scan scope 的派生写入，不得触发全库重算。

---

## 8. 缩略图系统需求

### 8.1 缓存层级

| 层级 | 内容 | 生命周期 | 说明 |
| --- | --- | --- | --- |
| L0 | `micro_thumbnail` BLOB | DB 可重建 | grid 首屏兜底，体积小 |
| L1 | in-memory `QPixmap/QImage` | 进程内 LRU | 可见窗口高频命中 |
| L2 | disk thumbnail | `.iPhoto/cache/thumbs` | 512px 或配置尺寸 |
| L3 | source decode | 原始文件 | 只能后台 worker 使用 |

### 8.2 队列优先级

缩略图任务优先级：

1. 扫描入库必需缩略图。
2. 当前可见区。
3. lookahead/lookbehind。
4. pinned/current row。
5. 空闲预热。

要求：

- 每个 `(asset_id, size, edit_revision)` 只能有一个 pending task。
- 不可见任务可以取消或降级。
- 最大并发按 CPU/磁盘能力限制，默认 `max(1, os.cpu_count() // 2)`，且 UI 可配置。
- RAW/视频必须有低成本路径：内嵌 JPEG、ffmpeg 单帧、sidecar cache。
- L2 key 必须包含 path/content signature、size、edit revision、renderer version，避免旧图污染。

### 8.3 UI 展示策略

- 普通媒体格只显示 `thumbnail_state='ready'` 的资产。
- 如果 L1/L2 未命中但 DB 有 micro thumbnail，立即显示 micro thumbnail，并后台补 L2。
- 如果用户主动进入失败列表，可以显示失败态卡片，但必须与普通媒体格视觉区分。
- 滚动路径不得同步解码原图。

---

## 9. Gallery/UI 迁移需求

### 9.1 Model reset

必须替换 `GalleryListModelAdapter._snapshot_hash()` 的全量遍历策略。

目标：

- collection 加载后生成 `collection_revision`。
- scan commit、move/delete、favorite 等操作只递增受影响 revision。
- `data_changed` 判断基于 `(collection_id, collection_revision, total_count, window_range)`。
- 禁止为了判断变化遍历 `range(count)` 调用 `asset_at()`。

### 9.2 Window cache

`GalleryCollectionStore` 保留窗口化方向，但需要补齐：

- 可取消的 query request id，旧请求返回后必须丢弃。
- 可见范围变化去抖 16-50ms。
- 合并连续滚动请求，避免每行触发单独 DB 查询。
- `asset_at()` 不得在 UI 线程触发深分页查询；只能返回已缓存 DTO 或稳定占位。
- 对 All Photos 这种 broad query，首屏先 80-200 个 DTO，后续窗口按需加载。

### 9.3 定位查询

以下能力不得线性扫全库：

- `row_for_path(path)`
- live motion partner 查找
- favorite/hidden/trash 状态读取
- location cache 写回

必须通过：

- `rel/id` SQL lookup。
- collection anchor query。
- 小型 LRU path->row cache。
- 后台定位任务，完成后再滚动到目标。

---

## 10. 首次启动迁移需求

### 10.1 启动阶段

启动分为：

| 阶段 | 允许工作 | 禁止工作 |
| --- | --- | --- |
| process bootstrap | Qt app、theme、settings、window shell | 扫描、People、Maps heavy probe |
| first paint | 显示主窗口、占位 sidebar、最近库入口 | 绑定大库并 count 全量 |
| session bind | 打开 library session、DB schema quick check | full rescan、thumbnail warmup |
| first collection | count + first page query | read_all、全量 DTO、全量 path exists |
| idle tasks | 增量扫描、People、Maps、预热 | 抢占 UI 可见任务 |

### 10.2 自动扫描

- 如果已有 `global_index.db`，启动时只 schedule 低优先级增量扫描。
- 如果没有 index，启动扫描也必须 progressive，不得等待扫描完成才显示 UI。
- 自动扫描必须可暂停、取消、降速。
- 用户手动触发扫描时提高优先级，但仍不允许阻塞浏览。

---

## 11. 迁移路线图

### Phase 0: 性能观测先行

- 增加结构化日志：
  - startup stage
  - collection count/page query
  - query plan
  - scan stage duration
  - thumbnail queue depth/hit/miss/failure
  - visible publish latency
  - model reset/window reload
  - UI stall > 50ms
- 新增 JSON benchmark 输出，保存到 `tools/benchmarks/results/` 或测试临时目录。

### Phase 1: 查询层禁止全量路径

- 扩展 `AssetQuery`/新增 `CollectionQuery`。
- 把常见筛选全部 SQL 下推。
- 添加缺失索引。
- 为 `read_all()` 加运行时审计：GUI collection 路径调用时记录 warning，测试中失败。

### Phase 2: Gallery model 稳定化

- 替换全量 snapshot hash。
- 增加 query request id/cancel。
- 局部刷新替代全量 reset。
- 修复 `row_for_path()` 和 live partner 线性扫描。

### Phase 3: 缩略图 ready 入库

- 增加 thumbnail state 字段和迁移。
- 扫描 ready row 必须带 micro thumbnail 或 disk thumb key。
- 缩略图失败进入失败态，不进入普通 grid。
- 实现 L1/L2/pending 去重、优先级、并发限制、取消。

### Phase 4: 扫描作业化与实时发布

- 增加 `scan_jobs`/`scan_events`。
- 扫描流水线分阶段。
- DB 大批 commit，UI 小批 publish。
- All Photos/current album/favorites/videos 都支持扫描中增量出现 ready 媒体。

### Phase 5: 启动延迟加载

- `resume_startup_tasks()` 只绑定库和首屏。
- People/Maps/Face scan/shader warmup 全部 idle 或页面触发。
- 自动扫描改为低优先级 job。

### Phase 6: 大库压力验收

- 10k、100k、1M synthetic rows。
- `tools/testbase` opt-in 真实素材。
- GUI offscreen 或 model-level 滚动 benchmark。
- 查询计划回归。

---

## 12. 验收测试矩阵

### 12.1 单元与集成测试

| 测试 | 要求 |
| --- | --- |
| `test_all_photos_first_page_uses_page_query` | All Photos 首屏只执行 count + page，不调用 `read_all()` |
| `test_collection_query_sql_pushdown` | favorites/videos/gps/date range 均生成 SQL filter |
| `test_gallery_reset_does_not_materialize_all_rows` | model reset 不遍历全部 row |
| `test_row_for_path_uses_lookup` | path 定位不扫描全库 |
| `test_scan_batch_contains_only_thumbnail_ready_rows` | UI scan batch 内每个资产都有 ready thumbnail |
| `test_metadata_only_rows_are_not_visible` | pending/failed row 不出现在普通 collection |
| `test_thumbnail_cache_hit_never_generates` | L1/L2 hit 不触发 generator |
| `test_thumbnail_failure_has_cooldown` | 失败资产不会无限重试 |
| `test_scan_merge_preserves_user_state` | scan merge 不覆盖 favorite/trash/manual state |
| `test_live_pairing_is_bucketed` | 大量候选下配对不退化为 O(n*m) |

### 12.2 性能基线

| 数据规模 | 场景 | 指标 |
| ---: | --- | --- |
| 10k | CI synthetic scan merge | <= 5s，作为现有 baseline 延续 |
| 100k | All Photos first page | <= 800ms |
| 100k | keyset next page P95 | <= 80ms |
| 100k | gallery reset | 不超过 1 个窗口 DTO materialization |
| 100k | scroll 5k rows | P95 frame <= 24ms |
| 100k | scan visible publish | P95 <= 500ms |
| 1M | All Photos first page | <= 1.5s |
| 1M | deep scroll/window load | 不使用深 OFFSET |
| 1M | memory | gallery DTO cache <= window upper bound + pinned rows |

### 12.3 手动验收

- 打开 100k+ 已索引库：
  - 主窗口先出现。
  - All Photos 首屏快速显示。
  - 后台扫描进度持续变化。
  - 新扫描到的媒体逐步插入当前视图。
  - 插入的媒体都有可见缩略图。
- 快速滚动：
  - 不出现大面积黑格。
  - 不因缩略图生成卡住 UI。
  - 停止滚动后清晰缩略图逐步补齐。
- 缩略图失败素材：
  - 普通 grid 不显示空白卡。
  - 诊断入口能看到失败原因并重试。

---

## 13. 可观测性要求

所有性能关键路径必须输出结构化事件，至少包含：

```json
{
  "event": "collection_page_query",
  "collection": "all_photos",
  "limit": 120,
  "cursor": "present",
  "elapsed_ms": 42.5,
  "rows": 120,
  "query_plan": "idx_assets_visible_global"
}
```

必需事件：

- `startup_stage`
- `library_bind`
- `collection_count_query`
- `collection_page_query`
- `collection_window_reload`
- `gallery_model_reset`
- `scan_stage_changed`
- `scan_batch_committed`
- `scan_visible_publish`
- `thumbnail_cache_hit`
- `thumbnail_cache_miss`
- `thumbnail_generate_started`
- `thumbnail_generate_finished`
- `thumbnail_generate_failed`
- `ui_stall`

日志采样：

- 正常运行 INFO 只记录 stage 和慢查询。
- DEBUG 可记录每个 query plan。
- benchmark 模式输出完整 JSONL。

---

## 14. 兼容与迁移

### 14.1 数据库迁移流程

1. 检测 schema version。
2. 关闭扫描 job 和 thumbnail worker。
3. 备份 `.iPhoto/global_index.db` 到 timestamped backup。
4. 创建新字段、新表、新索引。
5. 分批回填：
   - `sort_ts`
   - `has_gps`
   - `is_deleted`
   - `thumbnail_state`
   - `index_revision`
6. 对缺失 thumbnail 的旧资产标记 `thumbnail_state='stale'`。
7. 启动低优先级 thumbnail backfill job。
8. 校验：
   - row count 一致。
   - favorite/trash/user state 一致。
   - ready row 均有 thumbnail。
9. 写入新 schema version。

### 14.2 旧库体验

- 迁移后旧资产如果还没有缩略图，不得立即导致 All Photos 空白。
- 首屏优先 backfill 当前可见窗口缩略图。
- 后台逐步修复旧资产 thumbnail state。
- 用户可以继续浏览已经 ready 的资产。

---

## 15. 参考案例与行业惯例

### 15.1 Immich

- External Libraries 扫描外部文件系统后创建资产，并让这些资产出现在主 timeline；这说明外部库扫描和主聚合视图需要同一套资产索引与可见发布逻辑。
- Jobs and Workers 把 API 与后台 microservices/jobs 分离；新资产会触发 metadata extraction、thumbnail generation、machine learning 等一系列后台 job。这与本文要求的扫描分阶段、后台派生任务、UI 不阻塞一致。

### 15.2 PhotoPrism

- PhotoPrism 文档明确指出缩略图是浏览性能的关键；按需反复生成缩略图会让应用不可用，初始索引时会生成固定尺寸内的缩略图。
- PhotoPrism 对 SQLite 在大索引和高并发下的锁等待有明确警示；本项目仍优先 SQLite，但必须用 WAL、短读事务、批量写事务和查询索引降低锁竞争。
- PhotoPrism 的高级设置将预览图、动态预览、质量、尺寸和再生成作为独立能力，说明缩略图缓存应有版本、质量、大小和 backfill 策略。

### 15.3 digiKam

- digiKam 把 core database、thumbnail database、similarity database、face database 分离，证明大型相册应用通常不会把所有事实、缩略图、相似度和人脸数据混在一个逻辑域里。
- 本项目可以先使用单 SQLite 文件，但必须在 schema 和 repository 语义上拆分可重建事实、缩略图派生数据和不可丢失用户状态。

---

## 16. 参考资料

- [Immich External Libraries](https://docs.immich.app/features/libraries/)
- [Immich Jobs and Workers](https://docs.immich.app/administration/jobs-workers/)
- [PhotoPrism FAQ](https://docs.photoprism.app/getting-started/faq/)
- [PhotoPrism Advanced Settings](https://docs.photoprism.app/user-guide/settings/advanced/)
- [digiKam Database](https://docs.digikam.org/en/getting_started/database_intro.html)
