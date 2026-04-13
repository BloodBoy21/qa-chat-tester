import os
import functools
import inspect
from typing import Callable, Any, List
from typing import get_type_hints

DEFAULT_MODEL = os.getenv("MODEL_NAME", "gemini-2.5-flash")


def _gemini_safe_hint(t):
    """
    Normalize a Python type hint so ADK produces a Gemini-compatible JSON Schema.

    Rules:
      - bare `list`      → `list[str]`  (Gemini requires `items` on every array)
      - bare `dict`      → `str`        (Gemini rejects `additionalProperties`)
      - `dict[K, V]`     → `str`        (same — parameterised dicts still emit
                                          additionalProperties in the schema)
    Everything else is returned unchanged (str, bool, int, list[str],
    Pydantic BaseModel subclasses, etc. are all fine as-is).
    """
    if t is list:
        return list[str]
    origin = getattr(t, "__origin__", None)
    if t is dict or origin is dict:
        return str
    return t


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

        Also normalizes type hints for Gemini API compatibility:
          - bare `list`          → `list[str]`   (API requires items field in array schema)
          - bare `dict`          → `str`          (API rejects additionalProperties)
          - `dict[K, V]`         → `str`          (same reason)
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
            k: _gemini_safe_hint(v)
            for k, v in hints.items()
            if k not in default_params
        }

        return wrapper
