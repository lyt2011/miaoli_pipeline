# miaoli-pipeline

基于优先级的异步事件管线：把事件处理器编排进 langgraph 状态图。

本包从 `miaoli_bot` 拆出，**专门服务于 `miaoli_bot`**。事件名、状态结构、上下文结构全部由调用方提供，包本身不预设任何业务概念。

## 安装

```bash
pip install miaoli-pipeline
```

## 包结构

```
miaoli_pipeline/
├── core/       GraphPipeline
├── actions/    node_actions/：Continue / Goto / Abort
├── protocols/  node_action：BaseNodeAction / Delta
├── channels/   section_patch：SectionPatch
├── runtimes/   Handler
├── errors/     AgentAborted
└── utils/      pipeline_helper：merge_data / accumulate_data / is_none_action / is_update_action
```

根 `__init__.py` 只暴露 `actions` / `channels` / `core` / `errors` / `protocols` / `runtimes`。`utils` 是内部辅助层，不暴露。

符号请从所属层导入：

```python
from miaoli_pipeline.core		import GraphPipeline
from miaoli_pipeline.actions	import Goto, Continue, Abort
from miaoli_pipeline.protocols	import BaseNodeAction, Delta
from miaoli_pipeline.channels	import SectionPatch
from miaoli_pipeline.runtimes	import Handler
from miaoli_pipeline.errors		import AgentAborted
from miaoli_pipeline.utils		import merge_data, accumulate_data
```

## 核心概念

| 概念 | 说明 |
|---|---|
| **event** | 一个事件名，在图里对应一个节点 |
| **handler** | 注册到某个事件的处理函数，签名 `(state, runtime) -> ActionResult` |
| **priority** | 同一事件内多个 handler 的执行顺序，**数值越大越先跑** |
| **ActionResult** | handler 的返回值：`None`（无操作）/ `dict`（增量）/ `BaseNodeAction` 子类（控制流） |

## 快速开始

```python
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END

from miaoli_pipeline.actions	import Goto
from miaoli_pipeline.core		import GraphPipeline

class State(TypedDict):
	log: Annotated[list, operator.add]

async def first(state, runtime):
	return {"log": ["first"]}

async def second(state, runtime):
	return {"log": ["second"]}

async def decide(state, runtime):
	if len(state["log"]) >= 2:
		return Goto(goto=END)
	return None

pipeline = GraphPipeline(State)
pipeline.wire(["start", "next"])        # 首个事件是图入口

pipeline.register("start", first, priority=10)
pipeline.register("start", second, priority=0)
pipeline.register("start", decide, priority=-10)

pipeline.compile()
result = await pipeline.ainvoke({"log": []}, thread_id="demo", context=None)
```

## 返回的四种 Action

| Action | 效果 |
|---|---|
| `Continue(updates=None)` | 停止本事件剩余的 handler，已累积的增量照常返回 |
| `Goto(goto=..., updates=None)` | 跳转到指定节点（事件名 / `Send` / 列表），可跨事件 |
| `Abort(reason="")` | 抛出 `AgentAborted`，冒泡到 `ainvoke` 调用处 |
| 裸 `dict` | 当作增量折叠，继续执行下一个 handler |

`Abort` 转成的 `AgentAborted` 继承 `langgraph.errors.GraphBubbleUp`，因此不会被管线内层的 `except Exception` 吞掉。

## 增量折叠

同一事件内多个 handler 的返回值由 `accumulate_data` 折叠，语义与 langgraph 通道一致：

- 通道有 `operator`（`Annotated[T, func]`）→ 用 `operator` 合并
- 值是 `Overwrite(...)` → 整体替换，并吸收此前累积的增量
- 通道没有 `operator` → 直接赋值（后写覆盖先写）

## 通道：SectionPatch

按 id 打补丁的段落字典，用于「多个节点各写自己那一段」的场景。

```python
from typing import Annotated, Dict, TypedDict
from miaoli_pipeline.channels import SectionPatch

class State(TypedDict):
	sections: Annotated[Dict[str, str], SectionPatch]
```

写入用 `None` 表示删除该键：

```python
return {"sections": {"identity": "你是喵璃", "style": "简短些"}}   # 写两段
return {"sections": {"style": None}}                              # 删掉 style
```

### 与 `Annotated[dict, lambda a, b: {**a, **b}]` 的区别

按 key 合并这件事 `dict` 展开本身就能做，`SectionPatch` 的价值在 `update()` 的返回语义：

| | `BinaryOperatorAggregate`（官方） | `SectionPatch` |
|---|---|---|
| 同值重写时的版本 bump | **每次都 bump** | 内容没变就不 bump |
| `MISSING` 语义 | `__init__` 里就 `typ()`，恒为 `is_available()` | 保持 `MISSING`，没写过就是没写过 |
| 删除键 | 需 `RemoveMessage` 一类专用类型 | `None`（JSON Merge Patch，RFC 7386） |
| 空序列 `update([])` | `False` | `False` |

`update()` 的返回值会被 `pregel/_algo.py` 用来决定是否给通道 bump 版本：

```python
if channels[chan].update(vals) and next_version is not None:
	checkpoint["channel_versions"][chan] = next_version
```

官方 `BinaryOperatorAggregate.update()` 除空序列外**无条件返回 `True`**，所以内容一字未改也会每一步落盘。`SectionPatch` 用结构化对比（`value_snapshot != self.value`）判定变更，同值重写不产生新 checkpoint。

实测：4 次 `invoke` 每次写同一个值，官方通道 bump 4 次，`SectionPatch` bump 1 次。

## 为什么 `BaseNodeAction` 不继承数据

`BaseNodeAction` 的语义是**「我要改控制流」**。一个 `BaseNodeAction` 子类若不属于 `Continue` / `Goto` / `Abort`，会被判定为未知 Action 并打 `ERROR` 日志，**不会静默跳过**。

这是刻意的设计：如果拿 Action 当「数据载体」，一旦忘了在 `_dispatch` 里加分支，就会出现「既不报错也不生效」的静默失效 —— 而这正是本包想避免的问题。

纯数据请直接返回 `dict`。

## 异常处理

单个 handler 抛出的普通异常会被记录日志并跳过，**不影响同一事件的其它 handler**。只有 `GraphBubbleUp` 的子类（含 `AgentAborted`）会向上冒泡。

## 依赖

- Python >= 3.11
- `langgraph >= 1.2, < 2`
