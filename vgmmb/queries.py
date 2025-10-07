from .db import connect, dict_cursor

OFFICIAL_STATUS_ID = 1  # MusicBrainz: status=1 通常表示 official

SQL_MAIN = """
SELECT
  rl.catalog_number,
  r.id            AS release_id,
  r.gid           AS release_gid,
  r.name          AS release_title,
  rg.id           AS rg_id,
  rg.gid          AS rg_gid,
  rg.name         AS rg_title,
  l.id            AS label_id,
  l.gid           AS label_gid,
  l.name          AS label_name,
  r.barcode,
  r.status        AS release_status,
  r.packaging,
  -- JP 发行标记
  CASE WHEN EXISTS (
    SELECT 1
    FROM musicbrainz.release_country rc
    JOIN musicbrainz.iso_3166_1 i1 ON i1.area = rc.country
    WHERE rc.release = r.id AND i1.code = 'JP'
  ) THEN TRUE ELSE FALSE END AS is_jp,

  -- 发行日期：取最早的一条
  (
    SELECT make_date(rc.date_year, COALESCE(rc.date_month, 1), COALESCE(rc.date_day, 1))
    FROM musicbrainz.release_country rc
    WHERE rc.release = r.id AND rc.date_year IS NOT NULL
    ORDER BY rc.date_year ASC, rc.date_month ASC NULLS LAST, rc.date_day ASC NULLS LAST
    LIMIT 1
  ) AS release_date,

  -- ★ 版本注记 / 状态 / 包装
  r.comment AS edition_note,
  rs.name   AS release_status_name,
  rp.name   AS packaging_name,


  -- ★ 格式聚合（修正：保留数量 → 2×CD + DVD-Video）
(
  SELECT STRING_AGG(
           CASE WHEN mc.cnt > 1 THEN mc.cnt::text || '' || mc.fmt ELSE mc.fmt END,
           '+' ORDER BY mc.fmt
         )
  FROM (
    SELECT
      COALESCE(mf.name, 'Unknown') AS fmt,
      COUNT(*) AS cnt
    FROM musicbrainz.medium m
    LEFT JOIN musicbrainz.medium_format mf ON mf.id = m.format
    WHERE m.release = r.id
    GROUP BY COALESCE(mf.name, 'Unknown')
  ) AS mc
) AS medium_formats,

  -- ★ 所有品番
  (
    SELECT array_agg(DISTINCT rl2.catalog_number)
    FROM musicbrainz.release_label rl2
    WHERE rl2.release = r.id AND rl2.catalog_number IS NOT NULL
  ) AS catalog_numbers

FROM musicbrainz.release_label rl
JOIN musicbrainz.release r        ON r.id = rl.release
JOIN musicbrainz.release_group rg ON rg.id = r.release_group
JOIN musicbrainz.label l          ON l.id = rl.label
LEFT JOIN musicbrainz.release_status    rs ON rs.id = r.status
LEFT JOIN musicbrainz.release_packaging rp ON rp.id = r.packaging
WHERE rl.catalog_number ILIKE %s
"""


SQL_ARTIST = """
SELECT acn.position, acn.join_phrase, COALESCE(acn.name, a.name) AS display_name
FROM release r
JOIN artist_credit ac ON ac.id = r.artist_credit
JOIN artist_credit_name acn ON acn.artist_credit = ac.id
LEFT JOIN artist a ON a.id = acn.artist
WHERE r.id = %s
ORDER BY acn.position
"""

SQL_TRACKS = """
SELECT rm.position AS disc_no,
       t.position  AS track_no,
       t.number    AS track_num_label,
       COALESCE(t.name, rec.name) AS track_title,
       rec.length  AS track_length_ms
FROM medium rm
JOIN track t ON t.medium = rm.id
LEFT JOIN recording rec ON rec.id = t.recording
WHERE rm.release = %s
ORDER BY rm.position, t.position
"""

# 取一张“最优封面”：优先 Front，其次按 ordering 升序
SQL_COVER_ONE = """
SELECT
  ca.id,
  ca.mime_type,
  it.suffix AS file_suffix,
  ca.filesize,
  ca.thumb_250_filesize,
  ca.thumb_500_filesize,
  ca.thumb_1200_filesize,
  EXISTS (
    SELECT 1
    FROM cover_art_archive.cover_art_type cat
    JOIN cover_art_archive.art_type at ON at.id = cat.type_id
    WHERE cat.id = ca.id AND at.name = 'Front'
  ) AS is_front
FROM cover_art_archive.cover_art ca
LEFT JOIN cover_art_archive.image_type it ON it.mime_type = ca.mime_type
WHERE ca.release = %s
ORDER BY is_front DESC, ca.ordering ASC
LIMIT 1
"""

def _rank_release(row):
    score = 0
    if row.get("is_jp"):
        score += 10
    if row["release_status"] == OFFICIAL_STATUS_ID:
        score += 5
    # 用 release_date 的年份打分；没有就给很晚的年份
    if row.get("release_date"):
        score += max(0, 3000 - int(row["release_date"].year))
    else:
        score += 0  # 没日期不加分
    return score

def query_by_catalog(catalog: str, with_cover: bool = False):
    with connect() as conn, dict_cursor(conn) as cur:
        cur.execute(SQL_MAIN, (catalog,))
        rows = cur.fetchall()
        if not rows:
            return None, None, None, None

        best = sorted(rows, key=_rank_release, reverse=True)[0]
        rid = best["release_id"]

        cur.execute(SQL_ARTIST, (rid,))
        artists = cur.fetchall()

        cur.execute(SQL_TRACKS, (rid,))
        tracks = cur.fetchall()

        cover = None
        if with_cover:
            cur.execute(SQL_COVER_ONE, (rid,))
            cover = cur.fetchone()

        return best, artists, tracks, cover
