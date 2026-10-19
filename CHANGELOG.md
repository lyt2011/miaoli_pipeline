# Changelog

## v1.0.0 - 2026-10-19

> 🧱 **首个正式版本**：从 `miaoli_bot` 拆出，改名 `miaoli_pipeline`，专门服务于 `miaoli_bot`。

包定位从「通用管线」收窄为「miaoli_bot 专用」。事件名、状态结构、上下文结构全部由调用方提供，包本身不预设业务概念。1.0 之后只修 bug，API 不再变动。

### Added

- `channels/section_patch.py`：`SectionPatch` 通道，按 id 打补丁的段落字典。写入 `None` 表示删除该键（JSON Merge Patch，RFC 7386）。
- `channels/`：通道层，根 `__init__.py` 暴露 `SectionPatch`。
- `protocols/node_action.py`：`BaseNodeAction` 与 `Delta` 从 `actions/node_actions/base.py` 迁入，`protocols/` 统一存放抽象基类。
- `README.md`：补充 `SectionPatch` 章节，说明它与 `Annotated[dict, lambda a, b: {**a, **b}]` 的行为差异。

### Changed

- 包名 `agent_pipeline` → `miaoli_pipeline`，发行名 `agent-pipeline` → `miaoli-pipeline`。
- `pyproject.toml` 的 `description` 改为「miaoli_bot 的事件管线」。
- 版本号 `0.1.0` → `1.0.0`。

### Removed

- `protocols/section_action.py`、`actions/section_actions/`（`BaseSectionAction` / `Set` / `Remove`）：段落更新改为 plain `dict`，不再需要 action 对象。

  这些类必须写成 `@dataclass` 才能被 `JsonPlusSerializer` 序列化 —— langgraph 的 `put_writes` 会把 writes 里的对象本身写进 checkpoint，普通对象会 `TypeError`。而 dataclass 在严格模式下还需要额外维护 `allowed_msgpack_modules` 白名单，否则反序列化会静默降级成 plain dict。改用 `dict` 后走 msgpack 原生编码路径，整个序列化问题消失。

### Note

- `SectionPatch.update()` 用结构化对比判定变更，同值重写不 bump 通道版本。官方 `BinaryOperatorAggregate.update()` 除空序列外无条件返回 `True`，内容未改也会每步落盘。
- `SectionPatch` 在从未被写过时保持 `MISSING`（`is_available()` 为 `False`），不预先物化成 `{}`。
- `SectionPatch` 的「先合并再应用」语义要求 patch 操作是幂等的（设值 / 删键）。若将来引入 `Append` 这类累积操作，需改为「顺序应用到副本上，最后整体对比」。
