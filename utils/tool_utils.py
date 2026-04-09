import re

import inspect


_SNAKE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z0-9])([A-Z])")
_NON_ALNUM = re.compile(r"[^0-9a-zA-Z]+")

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "float": float,
    "boolean": bool,
    "bool": bool,
    "list": list,
    "array": list,
    "dictionary": dict,
    "dict": dict,
    "object": dict,
}

_NORMAL_TYPES: dict[str, str] = {
    "string": "string",
    "str": "string",
    "integer": "integer",
    "number": "float",
    "float": "float",
    "boolean": "bool",
    "bool": "bool",
    "list": "list",
    "array": "list",
    "dictionary": "dict",
    "dict": "dict",
    "object": "dict",
}


def fix_params(params: list[dict]) -> list[dict]:
    for p in params:
        p["type"] = _NORMAL_TYPES.get(p["type"], p["type"])
    return params


def to_snake_case(s: str) -> str:
    """
    Convierte `s` a snake_case:
      • 'MyTool'           -> 'my_tool'
      • 'my-tool v2'       -> 'my_tool_v2'
      • 'SomeXMLParser'    -> 'some_xml_parser'
    """
    s = _NON_ALNUM.sub("_", s)
    s = _SNAKE_1.sub(r"\1_\2", s)
    s = _SNAKE_2.sub(r"\1_\2", s)
    return s.lower().strip("_")


def make_signature(params: list[dict]) -> inspect.Signature:
    """
    Construye un `inspect.Signature` a partir de la lista de parámetros
    declarados en el `tool_doc`.
    """
    parameters = []
    for p in params:
        ptype = _TYPE_MAP.get(p.get("type", "").lower(), str)
        parameters.append(
            inspect.Parameter(
                p["name"],
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=ptype,
            )
        )
    return inspect.Signature(parameters, return_annotation=dict)
