import os
import functools
import inspect
from typing import Callable, Any, List
from typing import get_type_hints

DEFAULT_MODEL = os.getenv("MODEL_NAME", "gemini-2.5-flash")


class AgentBase:
    def __init__(
        self,
        context: str,
        user_id: str = "default_user",
        tools: List[Callable] = None,
        model: str = DEFAULT_MODEL,
        sub_agents: List[Any] = None,
    ):
        self.model = model
        self.user_id = user_id
        self.context = context
        self.tools = tools or []
        self.sub_agents = sub_agents or []
        self.run_id = None

    def set_run_id(self, run_id):
        self.run_id = run_id

    def Build(self):
        raise NotImplementedError("Build method not implemented in base class.")

    def _build_tool(self, func: Callable) -> Callable:
        """
        Build a tool function with fixed default parameters.
        Preserves signature and type hints so ADK generates a valid schema.
        """
        default_params = {"user_id": self.user_id, "run_id": self.run_id}

        sig = inspect.signature(func)
        hints = get_type_hints(func)

        new_params = [
            p for name, p in sig.parameters.items() if name not in default_params
        ]

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            merged = {**default_params, **kwargs}
            return func(*args, **merged)

        wrapper.__signature__ = sig.replace(parameters=new_params)
        wrapper.__annotations__ = {
            k: v for k, v in hints.items() if k not in default_params
        }

        return wrapper
