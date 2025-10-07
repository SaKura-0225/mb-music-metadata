import argparse
from pathlib import Path
from importlib import resources

from .log import setup_logging
from .queries import query_by_catalog
from .normalizer import normalize_record, load_label_alias
from .schema import load_schema, validate
from .io import write_json, read_lines, first_from_catalog_range, is_catalog_range




def _resolve_pkg_file(relpath: str) -> str:
    # relpath 例如 "data/schemas/mb-album-v1.json"
    with resources.as_file(resources.files("vgmmb").joinpath(relpath)) as p:
        return str(p)

def _one(catalog: str, args, schema, label_alias_map):
    best, artists, tracks, cover = query_by_catalog(catalog, with_cover=args.with_cover)
    if not best:
        raise SystemExit(f"[NOT FOUND] {catalog}")

    out = normalize_record(best, artists, tracks, label_alias_map, cover=cover)
    # --- 新增：记录用户输入的原始品番 ---
    if is_catalog_range(args.catalog):
        out.setdefault("identifiers", {})["catalog_number_compact_in"] = args.catalog
    if args.validate:
        errors = validate(out, schema)
        if errors:
            for e in errors:
                print(f"[SCHEMA ERROR] {catalog} -> {e.message} at {list(e.path)}")
    write_json(out, Path(args.out) if args.out and not args.batch else None)

def main():
    setup_logging()
    p = argparse.ArgumentParser(
        prog="mb-lookup",
        description="Lookup release by catalog number from local MusicBrainz and emit normalized JSON"
    )
    p.add_argument("--catalog", help="Catalog number (e.g., PCCG-01965)")
    p.add_argument("--batch", help="Batch file=path or dir=path; read each line as a catalog number")
    p.add_argument("--out", help="Output file (single) or output directory (batch). Omit to print to stdout.")
    p.add_argument("--validate", action="store_true", help="Validate against schema")
    p.add_argument("--with-cover", action="store_true", help="Fetch one best cover (Front preferred)")
    # 默认值为 None，后面用包内资源兜底
    p.add_argument("--schema", default=None)
    p.add_argument("--label-alias", default=None)
    args = p.parse_args()

    # —— 先解析默认路径（包内资源）——
    if args.schema is None:
        args.schema = _resolve_pkg_file("data/schemas/mb-album-v1.json")
    if args.label_alias is None:
        args.label_alias = _resolve_pkg_file("data/label_alias.json")

    # —— 再加载 schema / 别名映射 —— 
    schema = load_schema(Path(args.schema)) if args.validate else None
    label_alias_map = load_label_alias(Path(args.label_alias)) if args.label_alias else {}

    # —— 最后再分支到单条或批量 —— 
    if args.catalog and not args.batch:
        norm_cat = first_from_catalog_range(args.catalog)
        _one(norm_cat, args, schema, label_alias_map)
        return

    if args.batch:
        kv = args.batch.split("=", 1)
        if len(kv) != 2 or kv[0] not in ("file", "dir"):
            raise SystemExit("--batch expects 'file=...' or 'dir=...'")
        mode, path = kv
        path = Path(path)

        out_dir = Path(args.out) if args.out else Path("out")
        out_dir.mkdir(parents=True, exist_ok=True)

        if mode == "file":
            for raw in read_lines(path):
                cat = first_from_catalog_range(raw)
                try:
                    best, artists, tracks, cover = query_by_catalog(cat, with_cover=args.with_cover)
                    if not best:
                        print(f"[NOT FOUND] {cat}")
                        continue
                    out = normalize_record(best, artists, tracks, label_alias_map, cover=cover)
                    if is_catalog_range(raw):
                        out.setdefault("identifiers", {})["catalog_number_compact_in"] = raw
                    if args.validate:
                        errors = validate(out, schema)
                        if errors:
                            for e in errors:
                                print(f"[SCHEMA ERROR] {cat} -> {e.message} at {list(e.path)}")
                            continue
                    write_json(out, out_dir / f"{cat}.json")
                except Exception as ex:
                    print(f"[ERROR] {cat}: {ex}")
            return
        else:  # dir
            for fp in path.glob("*.txt"):
                for raw in read_lines(fp):
                    cat = first_from_catalog_range(raw)
                    try:
                        best, artists, tracks, cover = query_by_catalog(cat, with_cover=args.with_cover)
                        if not best:
                            print(f"[NOT FOUND] {cat}")
                            continue
                        out = normalize_record(best, artists, tracks, label_alias_map, cover=cover)
                        if is_catalog_range(raw):
                            out.setdefault("identifiers", {})["catalog_number_compact_in"] = raw
                        if args.validate:
                            errors = validate(out, schema)
                            if errors:
                                for e in errors:
                                    print(f"[SCHEMA ERROR] {cat} -> {e.message} at {list(e.path)}")
                                continue
                        write_json(out, out_dir / f"{cat}.json")
                    except Exception as ex:
                        print(f"[ERROR] {cat}: {ex}")
            return

    p.print_help()
