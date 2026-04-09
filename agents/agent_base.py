import os
from typing import Callable, Dict, Any, List, Union
import json
from utils.tool_utils import (
    fix_params,
    to_snake_case,
    make_signature,
)
from utils.built_in_func import call_built_in
from loguru import logger
import uuid

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash-exp")


class AgentBase:
    def __init__(
        self,
        context: str,
        user_id: str = "default_user",
        tools: List[Callable] = [],
        model: str = MODEL_NAME,
    ):
        self.model = model
        self.user_id = user_id
        self.context = context
        self.tools = tools

    def Build(self):
        raise NotImplementedError("Build method not implemented in base class.")

    @property
    def sub_agents(self):
        return []

    def _build_tool(
        self,
        doc: Dict[str, Any],
    ) -> Union[Callable, List[Callable]]:

        raw_name = doc.get("name", "")
        name = to_snake_case(raw_name)
        description = doc.get("description", "")
        params = doc.get("params", [])
        params = fix_params(params)
        docstring = doc.get("docstring", "")
        fref = doc.get("functionRef", "")

        if not docstring:
            lines = [description] if description else [f"Tool **{name}**."]
            if params:
                lines.append("")
                lines.append("Args:")
                for p in params:
                    ptype = p.get("type", "string")
                    lines.append(f"    {p['name']} ({ptype})")
            docstring = "\n".join(lines) + "\n"

        def _wrap(caller: Callable[[dict], object]) -> Callable:
            sig = make_signature(params)

            def tool_func(**kwargs):
                return caller(kwargs)

            tool_func.__name__ = name
            tool_func.__doc__ = docstring
            # pyrefly: ignore [missing-attribute]
            tool_func.__signature__ = sig
            tool_func.__annotations__ = {
                p.name: p.annotation for p in sig.parameters.values()
            }
            tool_func.__annotations__["return"] = dict
            return tool_func

        default_kwargs = {"user_id": self.user_id}
        return _wrap(lambda kw: call_built_in(fref, {**default_kwargs, **kw}))

    def _uuid_session_str(self) -> str:
        """
        Generate a UUID session string based on the user ID.
        """
        return str(uuid.uuid4())
