import re
import json


def extract_json_blocks(text: str) -> dict:
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    matches = re.findall(pattern, text, re.DOTALL)

    merged = {}
    for match in matches:
        try:
            merged.update(json.loads(match))
        except json.JSONDecodeError:
            continue

    return merged
