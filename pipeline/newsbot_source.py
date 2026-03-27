"""Read articles from newsbot SQLite DB for video generation."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .log import log

# Default path on Mac Mini
DEFAULT_NEWSBOT_DB = Path.home() / "newsbot" / "data" / "news.db"


@dataclass
class NewsbotArticle:
    """Article from newsbot DB with video-relevant fields."""

    id: int
    title: str
    content: str
    source_name: str
    score: float
    tiktok_hook: str
    hot_take: str
    summary_ru: str
    headline_ru: str
    content_hash: str
    created_at: str


def _ensure_video_column(conn: sqlite3.Connection) -> None:
    """Add video_generated column if it doesn't exist (idempotent)."""
    try:
        conn.execute(
            "ALTER TABLE articles ADD COLUMN video_generated INTEGER DEFAULT 0"
        )
        conn.commit()
        log("Added video_generated column to newsbot DB")
    except sqlite3.OperationalError:
        pass  # Column already exists


def get_next_article(db_path: Optional[Path] = None) -> Optional[NewsbotArticle]:
    """Get the top-scoring delivered article that hasn't been made into a video yet.

    We only pick from delivered articles (delivered=1) because those have already
    been vetted and published by newsbot. Ordered by score DESC.
    """
    db = db_path or DEFAULT_NEWSBOT_DB
    if not db.exists():
        log(f"Newsbot DB not found: {db}")
        return None

    conn = sqlite3.connect(str(db), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    _ensure_video_column(conn)

    row = conn.execute(
        """
        SELECT id, title, content, source_name, score,
               COALESCE(tiktok_hook, '') as tiktok_hook,
               COALESCE(hot_take, '') as hot_take,
               COALESCE(summary_ru, '') as summary_ru,
               COALESCE(headline_ru, '') as headline_ru,
               content_hash, created_at
        FROM articles
        WHERE delivered = 1
          AND video_generated = 0
        ORDER BY score DESC, created_at DESC
        LIMIT 1
        """,
    ).fetchone()

    conn.close()

    if not row:
        log("No unprocessed delivered articles found")
        return None

    article = NewsbotArticle(**dict(row))
    log(
        f"Selected article #{article.id}: {article.headline_ru or article.title} (score={article.score})"
    )
    return article


def mark_video_generated(content_hash: str, db_path: Optional[Path] = None) -> None:
    """Mark an article as having been turned into a video."""
    db = db_path or DEFAULT_NEWSBOT_DB
    conn = sqlite3.connect(str(db), check_same_thread=False)
    _ensure_video_column(conn)
    conn.execute(
        "UPDATE articles SET video_generated = 1 WHERE content_hash = ?",
        (content_hash,),
    )
    conn.commit()
    conn.close()
    log(f"Marked article {content_hash[:12]}... as video_generated")
