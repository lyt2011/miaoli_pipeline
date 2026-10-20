# Changelog

## v1.0.2 - 2026-10-20

> 🧱 **修复 `Abort` / `Continue` / `Goto` 在 Python 3.12 下导入即报错**。三个文件的 `__init__` 注解用了 `Optional` 但没导入。

Python 3.14 的 PEP 649 是惰性求值，注解只在被读取时才解析，所以本地（3.14.4）导入完全正常；Python 3.12 是立即求值，类体执行到 `def __init__(self, *, updates: Optional[dict] = None)` 时就会抛 `NameError: name 'Optional' is not defined`。

部署到服务器（3.12.14）时才暴露：`import miaoli_pipeline` 直接失败，整包不可用。

### Fixed

- `actions/node_actions/abort.py`、`continue_.py`：补 `from typing import Optional`。
- `actions/node_actions/goto.py`：`from typing import List, Union` → `List, Optional, Union`。

### Note

- 本地验证用 `typing.get_type_hints()` 强制立即求值可提前发现这类问题。注意要连**方法**一起扫 —— 只对类调 `get_type_hints()` 不会求值方法注解，会漏掉这三处。

## v1.0.1 - 2026-10-19

> 🧱 **修复自定义通道在 `GraphPipeline` 里不折叠的问题**。判据从「有没有 `.operator` 属性」换成「有没有对应的通道实例」。

`SectionPatch` 没有 `.operator` —— 那是 `BinaryOperatorAggregate` 的私有属性（`langgraph/channels/binop.py:75`），其余内置通道全都没有。`pipeline_helper` 拿它当「这个通道能不能折叠」的判据，于是 `SectionPatch` 被判成不能折叠，同一事件内多个 handler 的写入互相覆盖。

实测：6 个 handler 各写一段，修复前只留最后一段，修复后 6 段齐全。同一个 `SectionPatch` 在 langgraph 原生路径下（两个节点同一 superstep）行为是正确的，只有走 `GraphPipeline` 才丢数据。

### Changed

- `utils/pipeline_helper.py`：`merge_data` → `merge_into_state`，`accumulate_data` → `merge_into_updates`。原名两个都是「合并」的意思，且参数名完全相同（`old_data` / `new_data`），无法从签名区分；改名后用后缀标明合并落点，参数名区分成 `state` / `accumulated`。
- `utils/pipeline_helper.py`：`merge_into_state` 与 `merge_into_updates` 的判据从 `getattr(channel, "operator", None)` 换成 `channel is None`。有通道就交给通道自己的 `update()`，没有就直接赋值。
- `utils/__init__.py`：再导出与 `__all__` 同步。

### Added

- `utils/pipeline_helper.py`：`apply_deltas(channel, base, deltas)` —— 克隆通道、喂增量、取结果。语义对齐 langgraph 的 `apply_writes`（`pregel/_algo.py:232`）与 `DeltaChannel.replay_writes`（`channels/delta.py:139`）。`get()` 抛 `EmptyChannelError` 时返回 `MISSING`。

### Fixed

- 同一事件内多个 handler 写同一个自定义通道时，先写的数据被后写的覆盖。现在通过 `apply_deltas` 走通道自己的 `update()` 折叠，任何 `BaseChannel` 子类都自动生效，不需要额外提供 `.operator`。

### Note

- `Overwrite` 的解包与重包装逻辑保留不变。`merge_into_state` 产出 `view`（给下一个 handler 读），必须解包；`merge_into_updates` 产出 `updates`（交给 langgraph 写），必须保留包装。
- `apply_deltas` 对官方通道与自定义通道一视同仁，`pipeline_helper` 不再认识任何具体通道类型。
- 自定义通道若要在折叠时生效，必须实现 `from_checkpoint` —— 它是 `BaseChannel` 的抽象方法，不实现无法实例化。

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
