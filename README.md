# agent-pipeline

基于优先级的异步事件管线：把事件处理器编排进 langgraph 状态图。

事件名、状态结构、上下文结构全部由调用方提供 —— 本包不预设任何业务概念。

## 安装

```bash
pip install agent-pipeline
```

## 包结构

```
agent_pipeline/
├── core/       GraphPipeline
├── actions/    node_actions/：BaseNodeAction / Delta / Continue / Goto / Abort
├── runtimes/   Handler
├── errors/     AgentAborted
└── utils/      pipeline_helper：merge_data / accumulate_data / is_none_action / is_update_action
```

符号请从所属层导入（根 `__init__.py` 只暴露 `actions` / `core` / `errors` / `runtimes`，`utils` 是内部辅助层）：

```python
from agent_pipeline.core      import GraphPipeline
from agent_pipeline.actions   import Goto, Continue, Abort, BaseNodeAction
from agent_pipeline.runtimes  import Handler
from agent_pipeline.errors    import AgentAborted
from agent_pipeline.utils     import merge_data, accumulate_data
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

from agent_pipeline.actions import Continue, Goto
from agent_pipeline.core import GraphPipeline


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

## 为什么 `BaseNodeAction` 不继承数据

`BaseNodeAction` 的语义是**「我要改控制流」**。一个 `BaseNodeAction` 子类若不属于 `Continue` / `Goto` / `Abort`，会被判定为未知 Action 并打 `ERROR` 日志，**不会静默跳过**。

这是刻意的设计：如果拿 Action 当「数据载体」，一旦忘了在 `_dispatch` 里加分支，就会出现「既不报错也不生效」的静默失效 —— 而这正是本包想避免的问题。

纯数据请直接返回 `dict`。

## 异常处理

单个 handler 抛出的普通异常会被记录日志并跳过，**不影响同一事件的其它 handler**。只有 `GraphBubbleUp` 的子类（含 `AgentAborted`）会向上冒泡。

## 依赖

- Python >= 3.11
- `langgraph >= 1.2, < 2`
