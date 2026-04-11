import re

_SNAKE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z0-9])([A-Z])")
_NON_ALNUM = re.compile(r"[^0-9a-zA-Z]+")


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
