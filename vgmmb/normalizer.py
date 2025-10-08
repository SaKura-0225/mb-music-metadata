import json
from datetime import datetime
from pathlib import Path

import re
from itertools import groupby

CAT_RE = re.compile(r'^([A-Za-z0-9]+-?)(\d+)([A-Za-z]?)$')  # 前缀-数字-可选尾字母

# 加载映射表
FMT_MAP_PATH = Path(__file__).resolve().parent / "data" / "format_mapping.json"
with open(FMT_MAP_PATH, encoding="utf-8") as f:
    FORMAT_MAP = json.load(f)

def map_format(fmt_name: str) -> str:
    if not fmt_name:
        return None
    name = fmt_name.strip()
    m = re.match(r"^(\d+)x?(.*)$", name)  # 支持 "2Blu-ray"、"2xBlu-ray"
    prefix_num, core = (m.group(1), m.group(2).strip()) if m else (None, name)
    mapped_core = FORMAT_MAP.get(core) or ("BD" if "blu" in core.lower() or "bd" in core.lower()
                                           else "DVD" if "dvd" in core.lower()
                                           else core)
    return f"{prefix_num}{mapped_core}" if prefix_num else mapped_core


def _lcp(a: str, b: str) -> int:
    """longest common prefix length for two strings"""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i

def compact_catalog_numbers(catalog_numbers):
    """
    输入: ['SVWC-7853','SVWC-7854','SVWC-7855'] ...
    输出: 'SVWC-7853~5, KSLA-0012~4, SVWC-70359~60'
    规则:
      - 仅对同 (prefix, width, tail) 分组内做连续合并
      - 保留数字宽度(前导0)，尾字母必须一致才归为同组
      - 非连续编号不合并；无法解析的品番保留原样
    """
    if not catalog_numbers:
        return None

    parsed = []
    leftovers = []  # 解析失败的原样保留
    for code in catalog_numbers:
        m = CAT_RE.match(code.strip())
        if not m:
            leftovers.append(code.strip())
            continue
        prefix, num_str, tail = m.group(1), m.group(2), m.group(3)
        width = len(num_str)
        parsed.append({
            "raw": code.strip(),
            "prefix": prefix,
            "num": int(num_str),
            "num_str": num_str,
            "width": width,
            "tail": tail
        })

    # 先按 (prefix, width, tail, num) 排序，便于 groupby + 连续段识别
    parsed.sort(key=lambda x: (x["prefix"], x["width"], x["tail"], x["num"]))

    compact_chunks = []

    # 分组：同前缀、同宽度、同尾字母
    for (prefix, width, tail), items_iter in groupby(parsed, key=lambda x: (x["prefix"], x["width"], x["tail"])):
        items = list(items_iter)
        # 连续段切分
        start = items[0]["num"]
        prev = start
        for i in range(1, len(items)):
            cur = items[i]["num"]
            if cur != prev + 1:  # 断段
                # 输出一段 [start, prev]
                s = f"{start:0{width}d}"
                e = f"{prev:0{width}d}"
                # 计算公共前缀长度（数字部分）
                k = _lcp(s, e)
                if start == prev:
                    # 单点：不写 1×，直接回放 raw（更稳妥）
                    raw = next(x["raw"] for x in items if x["num"] == start)
                    compact_chunks.append(raw)
                else:
                    # 多点范围：prefix + s[:k] + s[k:]~e[k:] + tail
                    head = s[:k]
                    left = s[k:]
                    right = e[k:]
                    compact_chunks.append(f"{prefix}{head}{left}~{right}{tail}")
                # 开启新段
                start = cur
            prev = cur
        # 收尾最后一段
        s = f"{start:0{width}d}"
        e = f"{prev:0{width}d}"
        k = _lcp(s, e)
        if start == prev:
            raw = next(x["raw"] for x in items if x["num"] == start)
            compact_chunks.append(raw)
        else:
            head = s[:k]
            left = s[k:]
            right = e[k:]
            compact_chunks.append(f"{prefix}{head}{left}~{right}{tail}")

    # 拼上解析失败的原样项（保持稳定顺序，放在末尾更直观；也可放在最前）
    compact_all = compact_chunks + leftovers
    return ", ".join(compact_all)


def _fmt_mmss(ms):
    if ms is None:
        return None
    sec = int(ms) // 1000
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"

def load_label_alias(path: Path):
    if path and path.exists():
        # 兼容 Windows 可能带 BOM 的 UTF-8
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {}

def normalize_date(y, m, d):
    if not y:
        return None
    m = m or 1
    d = d or 1
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

def build_artist_display(artists):
    return "".join(f'{a["display_name"]}{a["join_phrase"] or ""}' for a in artists)

def _ext_from_suffix(sfx: str | None) -> str:
    # 安全回退
    return (sfx or "jpg").lstrip(".").lower()

def build_caa_urls(release_gid: str, img_id: int, ext: str):
    # CAA 规则：按 image id 访问，尺寸用 -250/-500/-1200 后缀
    base = f"https://coverartarchive.org/release/{release_gid}/{img_id}"
    return {
        "full":  f"{base}.{ext}",
        "thumb_250":  f"{base}-250.{ext}",
        "thumb_500":  f"{base}-500.{ext}",
        "thumb_1200": f"{base}-1200.{ext}",
    }

def normalize_record(best, artists, tracks, label_alias_map=None, cover=None):
    product_name = best["release_title"]
    edition_name = (best.get("edition_note") or "").strip() or None
    if edition_name is None:
        edition_name = "通常盤"
    label_name = best["label_name"] or ""
    if label_alias_map:
        for canonical, aliases in label_alias_map.items():
            if label_name == canonical or label_name in aliases:
                label_name = canonical
                break
    # 解析日期（ISO 格式字符串）
    date_str = ""
    if best.get("release_date"):
        # psycopg2 自动转成 datetime.date
        date_str = str(best["release_date"])
    # 构造封面（可拼接 URL）
    images = {}
    if cover:
        ext = _ext_from_suffix(cover.get("file_suffix"))
        urls = build_caa_urls(str(best["release_gid"]), int(cover["id"]), ext)
        images["cover"] = {
            "id": int(cover["id"]),
            "is_front": bool(cover["is_front"]),
            "mime": cover.get("mime_type"),
            "bytes": cover.get("filesize"),
            "urls": urls,
        }

    raw_fmt = best.get("medium_formats") or ""
    if raw_fmt:
        # 拆分，如 "2Blu-ray+CD" → ["2Blu-ray", "CD"]
        parts = [p.strip() for p in re.split(r"\+|,", raw_fmt) if p.strip()]
        mapped_parts = [map_format(p) for p in parts]
        fmt_display = "+".join(dict.fromkeys(mapped_parts))  # 去重保持顺序
    else:
        fmt_display = "Unknown"


    out = {
        "source": {
            "site": "musicbrainz",
            "collected_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"
        },
        "identifiers": {
            "catalog_number": best["catalog_number"],
            "catalog_numbers": best.get("catalog_numbers") or [],
            "catalog_number_compact_db": compact_catalog_numbers(best.get("catalog_numbers") or []),
            "barcode": best["barcode"],
            "mbids": {
                "release": str(best["release_gid"]) if best["release_gid"] else None,
                "release_group": str(best["rg_gid"]) if best["rg_gid"] else None,
                "label": str(best["label_gid"]) if best["label_gid"] else None
            }
        },
        "title": {
            "product_name": product_name,
            "edition_name": edition_name,
            },
        "artist_credit": [a["display_name"] for a in artists],
        "artist_display": build_artist_display(artists) if artists else None,
        "label": label_name,
        "date": date_str,
        "country": None,  # 如需国家码，可再查 release_country→area_iso_3166_1
        "format": fmt_display,
        "tracks": [
            {
                "disc": int(t["disc_no"]),
                "no": int(t["track_no"]),
                "title": t["track_title"],
                "length": _fmt_mmss(t["track_length_ms"]),
                "length_ms": int(t["track_length_ms"]) if t["track_length_ms"] is not None else None
            }
            for t in tracks
        ],
        "images": images
    }
    return out
