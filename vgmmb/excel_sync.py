# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

CAT_RANGE_SEPS = ["~", "～", "〜"]

def _normalize_input(catalog: str) -> str:
    return (catalog or "").strip()

def _first_from_range(catalog: str) -> str:
    if not catalog:
        return catalog
    s = catalog.strip()
    for sep in CAT_RANGE_SEPS[1:]:
        s = s.replace(sep, CAT_RANGE_SEPS[0])
    return s.split(CAT_RANGE_SEPS[0], 1)[0] if CAT_RANGE_SEPS[0] in s else s

def _try_get(d: Dict[str, Any], path: str) -> Any:
    cur = d
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur

def _extract_fields(payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    name = _try_get(payload, "title.product_name") or _try_get(payload, "title.raw") or payload.get("title")
    if isinstance(name, dict): name = None

    version = (_try_get(payload, "title.edition_name") or _try_get(payload, "version")
               or _try_get(payload, "annotations.version") or _try_get(payload, "notes.version"))
    if isinstance(version, list): version = " / ".join(map(str, version))
    if isinstance(version, dict): version = json.dumps(version, ensure_ascii=False)

    vdetail = (_try_get(payload, "media_compact") or _try_get(payload, "format_compact")
               or _try_get(payload, "media") or _try_get(payload, "format"))
    if isinstance(vdetail, list): vdetail = " + ".join(map(str, vdetail))
    if isinstance(vdetail, dict): vdetail = json.dumps(vdetail, ensure_ascii=False)

    artist = (_try_get(payload, "artist_credit") or _try_get(payload, "artists_credit")
              or _try_get(payload, "artists_joined"))
    if isinstance(artist, list): artist = " / ".join(map(str, artist))
    if isinstance(artist, dict): artist = json.dumps(artist, ensure_ascii=False)

    barcode = _try_get(payload, "identifiers.barcode") or payload.get("barcode")
    if isinstance(barcode, list): barcode = ", ".join(map(str, barcode))
    if isinstance(barcode, dict): barcode = json.dumps(barcode, ensure_ascii=False)

    return {"产品名称": name, "版本": version, "版本详情": vdetail, "歌手": artist, "Barcode": barcode}

def _load_json_by_catalog(json_dir: Path, catalog_input: str) -> Optional[Dict[str, Any]]:
    base = _normalize_input(catalog_input)
    if not base: return None

    candidates = [json_dir / f"{base}.json"]
    unified = base
    for sep in CAT_RANGE_SEPS[1:]: unified = unified.replace(sep, CAT_RANGE_SEPS[0])
    if unified != base: candidates.append(json_dir / f"{unified}.json")
    first = _first_from_range(base)
    if first != base: candidates.append(json_dir / f"{first}.json")

    for p in candidates:
        if p.exists():
            try:
                return json.loads((p.read_text(encoding="utf-8")))
            except Exception:
                return None
    return None

def update_excel(
    excel_path: Path,
    sheet_name: str = "采购统计",
    json_dir: Path = Path("out"),
    mode: str = "fill-only",
    catalog_col: str = "catelog",
    commit: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    if catalog_col not in df.columns:
        raise KeyError(f"Sheet '{sheet_name}' does not contain column '{catalog_col}'")

    targets = ["产品名称", "版本", "版本详情", "歌手", "Barcode"]
    for col in targets:
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df))

    missing = []
    updated = 0
    for idx, row in df.iterrows():
        cin = str(row.get(catalog_col) or "").strip()
        if not cin: continue
        payload = _load_json_by_catalog(json_dir, cin)
        if not payload:
            missing.append({"row_index": idx, catalog_col: cin})
            continue
        fields = _extract_fields(payload)
        for col in targets:
            new_val = fields.get(col)
            if new_val is None or (isinstance(new_val, float) and pd.isna(new_val)):
                continue
            if mode == "fill-only":
                if pd.isna(row.get(col)) or row.get(col) in (None, "", " "):
                    df.at[idx, col] = new_val; updated += 1
            else:
                df.at[idx, col] = new_val; updated += 1

    missing_df = pd.DataFrame(missing, columns=["row_index", catalog_col])
    if commit:
        with pd.ExcelWriter(excel_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as xw:
            df.to_excel(xw, sheet_name=sheet_name, index=False)
    return df, missing_df

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync normalized MB JSON into Excel archive.")
    parser.add_argument("--excel", required=True, help="Path to the Excel file (e.g., 海淘复盘.xlsx)")
    parser.add_argument("--sheet", default="采购统计")
    parser.add_argument("--json-dir", default="out")
    parser.add_argument("--mode", choices=["fill-only", "overwrite"], default="fill-only")
    parser.add_argument("--catalog-col", default="catelog")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    df, miss = update_excel(
        excel_path=Path(args.excel),
        sheet_name=args.sheet,
        json_dir=Path(args.json_dir),
        mode=args.mode,
        catalog_col=args.catalog_col,
        commit=not args.dry_run,
    )
    print("[SUMMARY] Updated columns:", list(df.columns))
    print("[SUMMARY] Missing:", len(miss))
    if len(miss) > 0:
        report_path = Path(args.excel).with_suffix("").as_posix() + "_未命中报告.csv"
        miss.to_csv(report_path, index=False, encoding="utf-8-sig")
        print(f"[SUMMARY] Missing report saved to: {report_path}")
