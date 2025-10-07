import os
import psycopg2
import psycopg2.extras

def get_dsn():
    return dict(
        host=os.getenv("MB_HOST", "localhost"),
        port=int(os.getenv("MB_PORT", "5433")),
        user=os.getenv("MB_USER", "musicbrainz"),
        password=os.getenv("MB_PASSWORD", "musicbrainz"),
        dbname=os.getenv("MB_DBNAME", "musicbrainz_db"),
        options=f"-c search_path={os.getenv('MB_SEARCH_PATH', 'musicbrainz')}"
    )

def connect():
    return psycopg2.connect(**get_dsn())

def dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
