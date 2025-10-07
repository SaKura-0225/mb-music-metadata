# MB Pipeline (MB-only)

以本地 MusicBrainz PostgreSQL 为唯一数据源，按 catalog number（品番）查询发行，输出规范化 JSON，并按基础 schema 校验。

## 依赖
- Python 3.9+
- 本地 PostgreSQL（MusicBrainz 完整导入）
- 已知连接（默认）：
  - host=localhost  port=5433
  - user=musicbrainz  password=musicbrainz
  - dbname=musicbrainz_db
  - search_path=musicbrainz

可通过环境变量覆盖：
MB_HOST, MB_PORT, MB_USER, MB_PASSWORD, MB_DBNAME, MB_SEARCH_PATH

## 安装与运行
```bash
pip install -e .
mb-lookup --catalog PCCG-01965 --out pccg-01965.json --validate
# 或输出到 stdout
mb-lookup --catalog PCCG-01965 --validate
# 读取纯文本/CSV 每行一个品番，逐条输出 JSON 文件到 out/
mb-lookup --batch file=catnums.txt --out out --validate
