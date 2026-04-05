"""SHA-256 deduplication database."""

import hashlib
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from models import MediaFile

logger = logging.getLogger(__name__)

DEFAULT_DB_DIR = Path.home() / ".gopro_extractor"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "dedup.db"


class DedupDB:
    """SQLite-based deduplication database."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS uploaded_files (
                sha256 TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                size INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_uploaded TEXT NOT NULL,
                nas_path TEXT
            )
        """)
        self.conn.commit()

    def is_duplicate(self, sha256: str) -> bool:
        """Check if a file hash already exists in the database."""
        cursor = self.conn.execute(
            "SELECT 1 FROM uploaded_files WHERE sha256 = ?", (sha256,)
        )
        return cursor.fetchone() is not None

    def record_upload(self, media_file: MediaFile, nas_path: str):
        """Record a successfully uploaded file."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """
            INSERT OR REPLACE INTO uploaded_files
            (sha256, filename, size, media_type, first_seen, last_uploaded, nas_path)
            VALUES (?, ?, ?, ?, COALESCE(
                (SELECT first_seen FROM uploaded_files WHERE sha256 = ?), ?
            ), ?, ?)
            """,
            (
                media_file.sha256,
                media_file.original_filename,
                media_file.size,
                media_file.media_type.value,
                media_file.sha256,
                now,
                now,
                nas_path,
            ),
        )
        self.conn.commit()

    def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = self.conn.execute(
            "SELECT COUNT(*), SUM(size), COUNT(DISTINCT media_type) FROM uploaded_files"
        )
        row = cursor.fetchone()
        return {
            "total_files": row[0] or 0,
            "total_bytes": row[1] or 0,
            "media_types": row[2] or 0,
        }

    def close(self):
        self.conn.close()


def hash_file(path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file using streaming reads."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def filter_new_files(
    files: list[MediaFile],
    db: DedupDB,
    progress_callback=None,
) -> tuple[list[MediaFile], list[MediaFile]]:
    """Separate files into new and duplicate lists.

    Returns:
        (new_files, duplicate_files)
    """
    new_files = []
    duplicate_files = []

    for i, media_file in enumerate(files):
        if media_file.staged_path and media_file.staged_path.exists():
            sha256 = hash_file(media_file.staged_path)
            media_file.sha256 = sha256

            if db.is_duplicate(sha256):
                duplicate_files.append(media_file)
                logger.debug("Duplicate: %s", media_file.original_filename)
            else:
                new_files.append(media_file)

        if progress_callback:
            percent = int((i + 1) / len(files) * 100)
            progress_callback(
                percent,
                f"Hashing {i + 1}/{len(files)}: {media_file.original_filename}"
            )

    logger.info(
        "Dedup result: %d new, %d duplicates",
        len(new_files), len(duplicate_files)
    )
    return new_files, duplicate_files
