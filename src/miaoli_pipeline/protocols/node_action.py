from abc	import ABC
from typing	import Any, Dict, Optional

Delta = Optional[Dict[str, Any]]

class BaseNodeAction(ABC):
	
	"""节点 action 基类 啥也不干的"""
	
	...
