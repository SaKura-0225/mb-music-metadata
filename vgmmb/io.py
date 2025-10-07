import json
from pathlib import Path
from typing import Iterable
import re

CAT_RANGE_RE = re.compile(r"^([A-Z0-9]+-?)(\d+)\s*[~～〜]\s*(\d+)([A-Za-z]?)$")

def is_catalog_range(s: str | None) -> bool:
    return bool(s and CAT_RANGE_RE.match(s.strip()))

def write_json(obj: dict, out_path: Path | None):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    else:
        print(text)

def read_lines(path: Path) -> Iterable[str]:
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            yield s

def first_from_catalog_range(cat: str) -> str:
    """
    'VVCL-1583~4' -> 'VVCL-1583'
    'SECL-1193~4' -> 'SECL-1193'
    'KICA-0001~0003' -> 'KICA-0001'
    其它非区间 -> 原样返回
    """
    c = (cat or "").strip()
    m = CAT_RANGE_RE.match(c)
    if not m:
        return c
    prefix, start_str, end_str, tail = m.groups()
    width = len(start_str)  # 保持前导0
    start = int(start_str)
    # 无论 end 是否小于 start，我们都只取 start
    return f"{prefix}{start:0{width}d}{tail}"