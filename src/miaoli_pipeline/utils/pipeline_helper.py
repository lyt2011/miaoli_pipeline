"""GraphPipeline 的增量折叠与返回值判定辅助函数。"""

from typing			import Any, Dict, Mapping, Optional, Union

from langgraph.types	import Overwrite

from ..actions			import BaseNodeAction

# 处理器的返回值：Action / 纯增量 dict / None（无操作）
ActionResult = Optional[Union[BaseNodeAction, Dict[str, Any]]]


def merge_data(old_data: Mapping[str, Any], new_data: Mapping[str, Any], channels: Mapping[str, Any]) -> Dict[str, Any]:
	
	"""
	将 new_data 合进 old_data
	OverWrite 在此被展开/消费
	"""
	
	merged	= dict(old_data)
	
	for key, value in new_data.items():
		
		# 替换语义 直接换值
		if isinstance(value, Overwrite):
			merged[key] = value.value
			continue
		
		channel		= channels.get(key)
		operator	= getattr(channel, "operator", None)
		
		# 有特殊操作+增量信息->通过 operator 获取新量并返回
		if operator is not None and key in merged:
			merged[key] = operator(merged[key], value)
		
		# 无操作/不是增量 直接赋值
		else:
			merged[key] = value
	
	return merged

def accumulate_data(old_data: Mapping[str, Any], new_data: Mapping[str, Any], channels: Mapping[str, Any]) -> Dict[str, Any]:
	
	"""把同一个事件里多个处理器的产出折叠成一份增量"""
	
	merged	= dict(old_data)
	
	for key, value in new_data.items():
		
		channel		= channels.get(key)
		operator	= getattr(channel, "operator", None)
		
		# 无操作/不是增量 直接赋值
		if operator is None or key not in merged:
			merged[key] = value
			continue
		
		old	= merged[key]
		
		# 新来的要替换 -> 它已吸收此前的增量 直接接管
		if isinstance(value, Overwrite):
			merged[key] = value
		
		# 之前是替换 -> 新增量叠在替换结果之上 包装保留
		elif isinstance(old, Overwrite):
			merged[key] = Overwrite(operator(old.value, value))
		
		else:
			merged[key] = operator(old, value)
	
	return merged

def is_none_action(action: ActionResult) -> bool:
	return action is None

def is_update_action(action: ActionResult) -> bool:
	
	"""裸 dict 或 action 自带的 updates"""
	
	is_dict	= isinstance(action, dict)
	is_duck	= hasattr(action, "updates") and isinstance(action.updates, dict)
	
	return is_dict or is_duck
