# iPhotron 国际化阶段 1-3 交接文档

> 日期：2026-06-07  
> 状态：阶段 1-2 已实现；阶段 3 已完成 `InfoPanel` 与 People Dashboard 首批业务页面迁移；Python-aware 提取工具已补齐；待后续阶段继续迁移其余业务页面
> 对应指南：`docs/requirements/i18n/i18n_multilingual_architecture_guide.md`

---

## 1. 当前完成范围

前序实施覆盖架构指南中的阶段 1「基础设施」和阶段 2「核心壳层 UI」。目标是先把国际化作为运行时服务接入应用，并让桌面主窗口的基础菜单、标题栏、核心操作和基础提示可以在运行时切换语言。

本轮继续推进阶段 3「主要业务页面」，已完成 `InfoPanel` 与 People Dashboard 迁移，并补齐首个 locale-aware formatter helper。

已完成内容：

- 新增 `src/iPhoto/gui/i18n/`：
  - `language.py`：定义 `LanguageInfo`。
  - `translation_manager.py`：负责读取语言元数据、解析系统语言、加载/卸载 `QTranslator`、监听 `ui.language` 设置变化并发出 `languageChanged`。
  - `formatters.py`：使用当前 UI 有效语言对应的 `QLocale` 格式化日期时间、整数、小数和文件大小。
  - `__init__.py`：导出 `TranslationManager`、`LanguageInfo`、`formatters` 和 `tr()`。
- 新增包内翻译资源目录 `src/iPhoto/resources/i18n/`：
  - `languages.json`
  - `iPhoto_de.ts`
  - `iPhoto_de.qm`
  - `iPhoto_zh_CN.ts`
  - `iPhoto_zh_CN.qm`
- 扩展 settings：
  - `DEFAULT_SETTINGS["ui"]["language"] = "system"`
  - schema 允许 `system`、`de`、`zh-CN`
  - 旧 settings 文件可继续通过 `merge_with_defaults()` 自动补齐。
- `RuntimeContext` 已持有 `translation`，创建顺序为：
  - settings
  - translation
  - theme
  - 其他运行时服务
- `RuntimeEntryContract` 和 legacy `AppContext` 已补充 `translation`。
- `pyproject.toml` package data 已包含 `.ts` 和 `.qm`。
- 主窗口新增语言菜单：
  - `Settings > Language > System`
  - `Settings > Language > Deutsch`
  - `Settings > Language > 简体中文`
- `MainCoordinator` 已将语言 action 写入 `settings.set("ui.language", code)`，由 `TranslationManager` 监听设置变更并应用翻译。
- `MainWindow` 新增 `retranslate_ui_tree()`，并在语言变化后通过 `QTimer.singleShot(0, ...)` 延迟刷新，避免用户从菜单切换语言时 Qt 正在关闭 popup menu 导致 `QMenu` 底层对象失效。
- `MainHeaderWidget` 已显式创建并持有 `QMenu`，避免 PySide ownership 导致语言切换时访问已删除的菜单对象。
- `TranslationManager.apply_language()` 已同步更新 `formatters` 使用的当前 `QLocale`：
  - `de` 使用 `de_DE`。
  - `zh-CN` 使用 `zh_CN`。
  - 英文兜底使用 `en_US`。
- `MenuActionSpec` 生成的 `QAction` 和 submenu action 已写入稳定 `action_id` 到 `action.data()`，避免翻译后的 label 被业务逻辑用作命令判断。
- 已迁移的核心 UI 文案包括：
  - 主菜单和设置子菜单。
  - 语言、外观、导出、滚轮、分享相关菜单项。
  - 主窗口标题栏按钮 tooltip。
  - 选择/取消选择按钮。
  - edit 顶部基础 action 文案。
  - 基础目录选择、绑定基础图库、恢复失败确认等对话框文案。
  - 地图扩展下载提示、进度、错误和重启提示。
  - 状态栏扫描、加载、导入、移动/删除/恢复等核心进度提示。
- 已迁移的业务页面：
  - `InfoPanel` 标题、关闭 tooltip、location 区域按钮/placeholder/fallback、metadata loading/unavailable 状态。
  - `InfoPanel` face avatar context menu 和新建/选择人物弹窗文案。
  - `InfoPanel` metadata 格式化改用当前 UI locale，而不是 `QLocale.system()`。
  - face 菜单命令识别改为稳定 `action_id`，不再依赖 `chosen.text()`。
  - `PeopleDashboardWidget` 标题、刷新按钮、section 标题、菜单项、输入框、确认/警告弹窗、空态/加载/扫描/已填充状态文案。
  - `PeopleDashboardWidget.retranslate_ui()` 已支持运行时刷新长期存在页面的固定文案和当前状态文案，不重建已加载人物/分组卡片。
  - `people_dashboard_dialogs` 默认 merge 确认弹窗与人物选择弹窗文案；调用方传入的自定义弹窗文案由调用方负责翻译。
  - People Dashboard 菜单继续依赖 `MenuActionSpec.action_id` / `QAction.data()`，不依赖翻译后的 label 判断命令。
  - 继续不翻译文件名、路径、人物名、地点搜索结果、相机/镜头/codec 原始值等用户数据或技术原始值。

---

## 2. 工具链与验证

新增/更新工具：

- `scripts/i18n_compile.sh`
  - 调用 `pyside6-lrelease`。
  - 从 `.ts` 生成 `.qm`。
- `tools/extract_i18n_strings.py`
  - 使用 Python `ast` 扫描源码中的翻译调用。
  - 识别 `QCoreApplication.translate(context, text, ...)`。
  - 识别项目封装 `tr(context, text, ...)`。
  - 识别局部别名，例如 `tr = QCoreApplication.translate` 后的 `tr(...)`。
  - 只提取字面量 context/source text，跳过动态 context、动态文案和 f-string，避免误提取用户数据。
  - 合并到现有 `.ts` 时保留已有译文，不覆盖已完成翻译。
  - 新增未翻译 message 会标记为 `type="unfinished"`。
  - 支持基础 translator comment/disambiguation 和 `%n` plural metadata。
- `scripts/i18n_extract.sh`
  - 已改为调用 `tools/extract_i18n_strings.py`，不再依赖当前不可用的 `pyside6-lupdate` Python 提取路径。
  - 当前扫描 `src/iPhoto/gui` 和 `src/maps`。
  - 更新 `src/iPhoto/resources/i18n/iPhoto_de.ts` 和 `src/iPhoto/resources/i18n/iPhoto_zh_CN.ts`。
  - 脚本已加保护：如果提取结果不包含 `<message>`，会恢复原 `.ts` 并退出失败，避免误清空已有翻译。

阶段 1-2 原始验证：

```bash
pytest tests/test_i18n_translation_manager.py \
  tests/test_settings_manager.py \
  tests/application/test_appctx_runtime_context.py \
  tests/gui/test_main.py \
  tests/application/test_runtime_context.py \
  tests/architecture/test_layer_boundaries.py -q
```

结果：

```text
46 passed
```

本轮提取工具补齐后执行验证：

```bash
pytest tests/test_i18n_extract_tool.py -q
```

结果：

```text
8 passed
```

工具链提取验证：

```bash
bash scripts/i18n_extract.sh
```

结果：

```text
Extracted 105 translation messages.
```

说明：105 是当前源码中已包裹翻译调用去重后的可提取 message 数；当前 `iPhoto_de.ts` 和 `iPhoto_zh_CN.ts` 各包含 105 条 message，0 条 unfinished。

翻译编译验证：

```bash
bash scripts/i18n_compile.sh
```

结果：

```text
Generated 105 translation(s) (105 finished and 0 unfinished)
Generated 105 translation(s) (105 finished and 0 unfinished)
```

阶段 3 `InfoPanel` 迁移后工具链验证：

```bash
bash scripts/i18n_extract.sh
```

结果：

```text
Extracted 132 translation messages.
```

说明：132 是当前源码中已包裹翻译调用去重后的可提取 message 数；当前 `iPhoto_de.ts` 和 `iPhoto_zh_CN.ts` 各包含 132 条 message，0 条 unfinished。

```bash
bash scripts/i18n_compile.sh
```

结果：

```text
Generated 132 translation(s) (132 finished and 0 unfinished)
Generated 132 translation(s) (132 finished and 0 unfinished)
```

静态检查：

```bash
python -m ruff check src/iPhoto/gui/i18n
python -m ruff check tools/extract_i18n_strings.py
```

结果：

```text
All checks passed
```

说明：全仓库级 `ruff check` 仍会命中历史规则噪声，例如测试中的 `assert`、Qt mixedCase 方法名、旧类型注解风格等。本轮只保证新增 i18n 包和相关测试通过目标验证。

本轮还执行了目标回归：

```bash
pytest tests/test_info_panel.py \
  tests/test_i18n_translation_manager.py \
  tests/test_i18n_extract_tool.py -q
```

结果：

```text
59 passed
```

阶段 1-2 相关回归：

```bash
pytest tests/test_i18n_translation_manager.py \
  tests/test_settings_manager.py \
  tests/application/test_runtime_context.py \
  tests/architecture/test_layer_boundaries.py -q
```

结果：

```text
30 passed
```

阶段 3 People Dashboard 迁移后工具链验证：

```bash
bash scripts/i18n_extract.sh
```

结果：

```text
Extracted 173 translation messages.
```

说明：173 是当前源码中已包裹翻译调用去重后的可提取 message 数；当前 `iPhoto_de.ts` 和 `iPhoto_zh_CN.ts` 各包含 173 条 message，0 条 unfinished。

```bash
bash scripts/i18n_compile.sh
```

结果：

```text
Generated 173 translation(s) (173 finished and 0 unfinished)
Generated 173 translation(s) (173 finished and 0 unfinished)
```

本轮 People/i18n/InfoPanel 目标回归：

```bash
pytest tests/gui/widgets/test_people_dashboard_widget.py \
  tests/test_i18n_translation_manager.py \
  tests/test_i18n_extract_tool.py \
  tests/test_info_panel.py -q
```

结果：

```text
91 passed
```

阶段 1-2 相关回归复跑：

```bash
pytest tests/test_i18n_translation_manager.py \
  tests/test_settings_manager.py \
  tests/application/test_runtime_context.py \
  tests/architecture/test_layer_boundaries.py -q
```

结果：

```text
35 passed
```

本轮源码静态检查：

```bash
python -m ruff check \
  src/iPhoto/gui/ui/widgets/people_dashboard_widget.py \
  src/iPhoto/gui/ui/widgets/people_dashboard_dialogs.py
```

结果：

```text
All checks passed
```

---

## 3. 已知限制

当前完成的是核心壳层国际化，以及 `InfoPanel` 和 People Dashboard 首批业务页面迁移，不是全应用文案迁移。

仍未完成的主要区域：

- albums dashboard、gallery context menu 等业务页面文案。
- detail/player/edit sidebar 中仍有 tooltip、按钮、状态文案未完整迁移。
- `src/maps/main.py` 独立地图预览入口未迁移。
- `tools/check_i18n_strings.py` 硬编码文案门禁尚未实现。
- locale-aware formatter 已具备日期时间、整数、小数和文件大小能力，但百分比、复数和更完整的 domain-specific 格式化仍未系统接入。
- `tools/extract_i18n_strings.py` 只提取已经包裹的翻译调用；未包裹硬编码文案仍需要页面迁移和后续门禁识别。
- 当前提取器故意跳过动态 context/source text。后续迁移时应把用户可见文案改成稳定字面量加 `.format(...)` 占位符，而不是动态拼接。

运行时注意点：

- 语言切换依赖 `settingsChanged("ui.language")`。
- `TranslationManager` 负责全局安装 translator。由于 Qt translator 是 application-wide 状态，测试中多个 manager 会互相替换当前 translator，这是预期行为。
- 主窗口语言刷新已改为 deferred retranslate，后续新增同步刷新逻辑时不要直接在 menu action triggered 的调用栈中访问 popup menu 对象。
- `InfoPanel` 已实现 `retranslate_ui()`，并由 `MainWindow.retranslate_ui_tree()` 自动调用。
- `PeopleDashboardWidget` 已实现 `retranslate_ui()`，并由 `MainWindow.retranslate_ui_tree()` 自动调用；运行时切换语言会刷新页面标题、按钮、section 标题和当前状态文案，但不会重载或重建已有卡片。
- 后续迁移 context menu 时不要用 `action.text()` 判断命令；应依赖 `MenuActionSpec.action_id` / `QAction.data()`。
- 如果传入 `InfoPanel.set_location_capability(fallback_text=...)` 的是外部自定义文案，该文案按调用方负责翻译；默认 fallback 已由 `InfoPanel` 自身翻译。
- 如果传入 `GroupPeopleDialog(title_text=..., prompt_text=..., confirm_text=...)` 或 `MergeConfirmDialog.confirm_action(...)` 的是自定义文案，该文案按调用方负责翻译；People Dashboard 内部调用已完成翻译。

---

## 4. 下一步建议

建议按架构指南继续推进阶段 3-5。

优先级 1：迁移主要业务页面

建议按用户可见度排序：

1. `src/iPhoto/gui/ui/widgets/albums_dashboard.py`
2. gallery/detail/player/edit sidebar 相关 widgets 和 controllers
3. context menu registry：`src/iPhoto/gui/ui/menus/*`

每个 widget/controller 迁移时需要同步完成：

- 将用户可见文案改为 `QCoreApplication.translate()` 或 `tr()`。
- 为长期存在的 widget 增加 `retranslate_ui()`。
- 避免拼接自然语言句子，动态值使用 `{name}`、`{count}` 等占位符。
- 不翻译文件名、路径、相册名、人物名、EXIF 原始值和内部诊断。
- 每完成一个页面后运行 `bash scripts/i18n_extract.sh`，补齐 `.ts` 中新增 message，再运行 `bash scripts/i18n_compile.sh`。

优先级 2：地图独立入口

- 迁移 `src/maps/main.py` 的菜单、对话框、状态栏和窗口标题。
- 初期可以继续使用同一 `iPhoto_*.qm`。
- 如果后续 maps 文案明显膨胀，再拆分 `maps_*.ts/.qm`。

优先级 3：继续扩展格式化 helper

`src/iPhoto/gui/i18n/formatters.py` 已新增，后续建议继续补：

- 百分比、复数和相对时间格式化。
- 更多页面接入 formatter，避免 widget 直接调用 `QLocale.system()`。
- 对数量文案优先使用 Qt `%n` plural 机制，而不是自行拼接。

优先级 4：硬编码门禁

新增 `tools/check_i18n_strings.py` 并接入架构测试：

- 扫描 GUI 层高风险 API：
  - `QAction(...)`
  - `addMenu(...)`
  - `setText(...)`
  - `setToolTip(...)`
  - `setPlaceholderText(...)`
  - `setWindowTitle(...)`
  - `QMessageBox.*(...)`
  - `showMessage(...)`
- 允许历史 allowlist，但新增 UI 文案不应进入 allowlist。
- 明确排除 objectName、CSS、icon filename、enum、logger、test fixture。

---

## 5. 交接检查清单

后续接手者开始新阶段前建议先执行：

```bash
pytest tests/test_i18n_translation_manager.py \
  tests/test_info_panel.py \
  tests/test_i18n_extract_tool.py \
  tests/test_settings_manager.py \
  tests/application/test_appctx_runtime_context.py \
  tests/gui/test_main.py \
  tests/application/test_runtime_context.py \
  tests/architecture/test_layer_boundaries.py -q

bash scripts/i18n_extract.sh
bash scripts/i18n_compile.sh
```

如果只接手提取工具链，可先执行：

```bash
pytest tests/test_i18n_extract_tool.py -q
python -m ruff check src/iPhoto/gui/i18n tools/extract_i18n_strings.py
```

手动验收建议：

- 启动 GUI。
- 打开 `Settings > Language`。
- 切换到 `简体中文`，确认菜单、核心按钮和标题栏 tooltip 刷新且不崩溃。
- 切换到 `Deutsch`，确认同样即时刷新。
- 切回 `System`，确认设置持久化且应用不崩溃。
- 在切换语言后打开基础图库绑定、地图扩展入口、扫描/加载流程，检查核心提示文案。
- 在切换语言后打开 detail 的 Info 面板，检查标题、关闭 tooltip、location fallback/download/confirm 文案、face 菜单和 metadata loading/unavailable 文案。
- 在切换语言后打开 People 页面，检查标题、刷新按钮、Groups/People & Pets section、人物/分组菜单、merge/hide/disband 弹窗和空态/加载/扫描状态文案。
