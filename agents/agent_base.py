import os
from typing import Callable, Dict, Any, List, Union
from utils.built_in_func import call_built_in
from loguru import logger
import uuid
import functools
import inspect
from typing import Callable, get_type_hints

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash-exp")


class AgentBase:
    def __init__(
        self,
        context: str,
        user_id: str = "default_user",
        tools: List[Callable] = [],
        model: str = MODEL_NAME,
        sub_agents: List[Any] = [],
    ):
        self.model = model
        self.user_id = user_id
        self.context = context
        self.tools = tools
        self.sub_agents = sub_agents
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

        # Remove fixed params from signature
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

    def _uuid_session_str(self) -> str:
        """
        Generate a UUID session string based on the user ID.
        """
        return str(uuid.uuid4())
