import json
import os
import re


def get_project_root():
    return os.path.dirname(os.path.dirname(__file__))


def load_app_config(config_path: str):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
        if not raw:
            return {}
        return json.loads(raw)


def _relaxed_json_loads(raw: str):
    cleaned = re.sub(r"(?m)^\s*//.*$", "", raw)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return json.loads(cleaned)


def load_static_config(static_path: str):
    with open(static_path, "r", encoding="utf-8") as f:
        raw = f.read()
    data = _relaxed_json_loads(raw)
    structure = data.get("structure", {})
    if not structure:
        raise ValueError("Missing structure in static config")
    merged = dict(structure)
    for key, value in data.items():
        if key != "structure":
            merged[key] = value
    return merged


def load_llm_pricing(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    unit = config.get("unit", "per_1k_tokens")
    if unit != "per_1k_tokens":
        raise ValueError(f"Unsupported pricing unit: {unit}")
    models = config.get("models", {})
    if not models:
        raise ValueError("No models found in config_llm.json")
    return models

