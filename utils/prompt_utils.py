import re
import json


def extract_json_blocks(text: str) -> dict:
    """
    Extract and merge all JSON objects from fenced code blocks in text.
    Handles nested objects correctly by using json.loads on the full block.
    """
    merged = {}
    for block in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        try:
            parsed = json.loads(block.group(1))
            if isinstance(parsed, dict):
                merged.update(parsed)
        except json.JSONDecodeError:
            continue
    return merged
