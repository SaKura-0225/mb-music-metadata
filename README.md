# mb-music-metadata（MB-only 离线元数据管线）

以本地 **MusicBrainz** PostgreSQL 全量镜像为唯一数据源，通过 **catalog number（品番）** 查询发行信息，输出**规范化 JSON**，并通过 **Schema 校验**。在此基础上，提供 **Excel 写回** 工具，把「产品名称 / 版本 / 版本详情 / 歌手 / Barcode」同步到你的归档表。

> 关键词：离线、可重复、可追溯、对新版 MB schema 兼容（2024+：`release_country` 存日期、`cover_art_archive` 存封面等）。


## 功能一览

- **离线查询**：完全基于本地 MB 镜像，无网络依赖；SQL 已适配 2024+ 新 schema。
- **标准化输出**：`normalizer.py` 统一输出 JSON（时长 `M:SS`、介质聚合「`2×CD + DVD-Video`」、艺人拼接、封面 URL 构造等）。
- **Schema 校验**：产出的 JSON 符合 `mb-album-v1.json`，严格类型约束。
- **CLI 友好**：支持单条 `--catalog` 与批量 `--batch`（文件/目录/默认清单）。
- **多碟识别**：支持 `VVCL-1583~4`、`SECL-2409～13`、`SECL-2409〜13` 等区间写法；内部只查首号，避免重复抓取。
- **品番语义统一**：
  - `identifiers.catalog_number_compact` = **用户输入原样**（用于文件命名与溯源）；
  - `identifiers.catalog_number_compact_db` = **数据库聚合结果**（由 normalizer 生成）。
- **Excel 写回**：一条命令把五列同步到你的 `采购统计` 表（默认“只填空”，可切换“覆盖”）。


## 目录结构（核心）

```
mb-music-metadata/
├─ out/                         # 输出 JSON（文件名=输入的 catalog，如 SECL-1193~4.json）
├─ vgmmb/
│  ├─ cli.py                    # 命令入口：mb-lookup（单条/批量）
│  ├─ queries.py                # SQL 聚合：日期、格式、注记、封面等
│  ├─ normalizer.py             # 归一化：时长、介质、艺人、封面 URL、catalog 压缩等
│  ├─ schema.py                 # Schema 加载与校验
│  ├─ excel_sync.py             # Excel 写回（命令：mb-sync-excel）
│  └─ data/
│     ├─ schemas/mb-album-v1.json
│     ├─ format_mapping.json
│     ├─ label_alias.json
│     └─ catalog.txt            # 示例批量清单
└─ pyproject.toml               # 依赖与命令入口配置
```


## 安装

环境要求：
- Python 3.9+
- 本地 PostgreSQL 已导入 **MusicBrainz** 镜像（并设置 `search_path` 指向 MB schema，通常为 `musicbrainz`）

安装（可编辑模式）：
```bash
pip install -e .
```

数据库连接（环境变量覆盖默认值）：
```
MB_HOST, MB_PORT, MB_USER, MB_PASSWORD, MB_DBNAME, MB_SEARCH_PATH
```
> 例如：`MB_HOST=localhost MB_PORT=5433 MB_USER=musicbrainz MB_PASSWORD=musicbrainz MB_DBNAME=musicbrainz_db MB_SEARCH_PATH=musicbrainz`


## 使用：查询与导出 JSON

### 1) 单条查询
```bash
mb-lookup --catalog KSLA-0052 --out out --validate
# 若省略 --out，则输出到 stdout（可重定向）
mb-lookup --catalog KSLA-0052 --validate > KSLA-0052.json
```

### 2) 批量查询
三种写法：
```bash
# 从文件读取（每行一个品番；支持 ~ / ～ / 〜 区间）
mb-lookup --batch file=vgmmb/data/catalog.txt --out out --validate

# 遍历目录下的若干清单文件
mb-lookup --batch dir=./lists --out out --validate

# 仅写 --batch（不带参数）默认读取 data/catalogs.txt
mb-lookup --batch --out out --validate
```
> 为避免重复抓取，区间输入（如 `VVCL-1583~4`）内部只查 **首号**，但输出 JSON 会包含 `catalog_numbers` 全量数组，且文件名等于**原始输入**（如 `VVCL-1583~4.json`）。


## JSON 字段要点（节选）

```jsonc
{
  "identifiers": {
    "catalog_number": "VVCL-1583",               // 主品番（首号）
    "catalog_numbers": ["VVCL-1583", "VVCL-1584"],
    "catalog_number_compact": "VVCL-1583~4",     // 用户输入原样（用于命名与溯源）
    "catalog_number_compact_db": "VVCL-1583~4",  // DB 聚合后的紧凑写法
    "barcode": null
  },
  "title": {
    "raw": "作品原始标题",
    "product_name": "归一化后的产品名称"
  },
  "artist_credit": "A / B / C",                  // 已拼接的艺人串
  "media_compact": "2×CD + DVD-Video",           // 介质聚合
  "duration_total": "1:34:56",                   // 或按曲目提供 M:SS
  "cover": { "front": "https://..." }
}
```
> 以上字段由 `queries.py` + `normalizer.py` 共同生成，最终通过 `schema.py` 进行 `mb-album-v1.json` 校验。


## 写回 Excel（归档表同步）

把 `out/` 下的 JSON 结果写回到你的 Excel（默认表名 `采购统计`，主键列 `catelog`）：

```bash
# 仅填空模式（推荐，避免覆盖你手工修订）
mb-sync-excel --excel 海淘复盘.xlsx --sheet 采购统计 --json-dir out --mode fill-only

# 强制覆盖（慎用）
mb-sync-excel --excel 海淘复盘.xlsx --sheet 采购统计 --json-dir out --mode overwrite
```

写回映射：
- **产品名称** ← `title.product_name`（回退 `title.raw` / 顶层 `title`）
- **版本** ← `edition` / `version` / `annotations.version` / `notes.version`
- **版本详情** ← `media_compact`（回退 `format_compact` / `media` / `format`）
- **歌手** ← `artist_credit`（如果是数组自动拼接为 `"A / B / C"`）
- **Barcode** ← `identifiers.barcode`

其他特性：
- 区间写法自动识别 `~ / ～ / 〜`；优先用**输入名**匹配 JSON（如 `SECL-1193~4.json`），找不到再回退到首号文件（如 `SECL-1193.json`）。
- 未命中的行会导出一份 CSV 报告（与 Excel 同目录，文件名类似 `海淘复盘_未命中报告.csv`）。


## 典型工作流

```bash
# 1) 批量抓取 JSON 到 out/
mb-lookup --batch file=vgmmb/data/catalog.txt --out out --validate

# 2) 写回 Excel 归档
mb-sync-excel --excel 海淘复盘.xlsx --sheet 采购统计 --json-dir out --mode fill-only
```


## 疑难排查

- **连接失败 / 查不到表**  
  检查环境变量是否正确，`MB_SEARCH_PATH` 是否指向 MB 的 schema（常见为 `musicbrainz`）。
- **Excel 文件被占用**  
  关闭正在打开该 Excel 的应用后再写回；或使用 `--dry-run` 先预览。
- **区间文件命名不一致**  
  建议始终以**用户输入原样**命名 JSON（项目默认如此），否则写回会回退到“首号匹配”。
- **艺人字段格式错乱**  
  在 `normalizer.py` 中确保输出 `artist_credit` 为拼接后的**字符串**，而不是复杂结构。


## 路线图（Roadmap）

- 查询缓存与并发抓取（减少对本地 DB 的压力）。
- 输出 JSON 加入 `source.collected_at` 与版本号，便于比对与追溯。
- 更多格式映射与标签清洗（BD/DVD/CD/数字版等的细粒度一致性）。
- 反向适配 VGMdb 上传结构（从本地 JSON → VGMdb 表单）。


## 许可证

本项目采用 **MIT License**（见仓库 `LICENSE`）。
