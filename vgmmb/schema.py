from pathlib import Path
import json
from jsonschema import Draft202012Validator

def load_schema(path: Path):
    try:
        text = path.read_text(encoding="utf-8")  # 既然你确认是 utf-8，就用 utf-8
        data = json.loads(text)
    except json.JSONDecodeError as e:
        snippet = text[:120].replace("\n", "\\n")
        raise SystemExit(f"[Schema JSON error] {path} at pos {e.pos}: {e.msg}\n"
                         f"→ File begins with: {snippet}")
    Draft202012Validator.check_schema(data)
    return data

def validate(instance: dict, schema: dict):
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    return errors
