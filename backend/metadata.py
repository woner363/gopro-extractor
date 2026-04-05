"""Media file metadata extraction (EXIF dates, creation time)."""

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def get_creation_date(file_path: Path) -> datetime | None:
    """Extract creation date from a media file.

    Tries in order:
    1. EXIF DateTimeOriginal (for photos)
    2. ffprobe creation_time (for videos)
    3. File modification time (fallback)
    """
    ext = file_path.suffix.lower()

    if ext in (".jpg", ".jpeg", ".heic", ".png"):
        date = _get_exif_date(file_path)
        if date:
            return date

    if ext in (".mp4", ".mov"):
        date = _get_video_date(file_path)
        if date:
            return date

    # Fallback to file modification time
    return datetime.fromtimestamp(file_path.stat().st_mtime)


def _get_exif_date(file_path: Path) -> datetime | None:
    """Extract EXIF DateTimeOriginal from an image."""
    try:
        from PIL import Image
        from PIL.ExifTags import Tags

        with Image.open(file_path) as img:
            exif = img.getexif()
            if not exif:
                return None

            # DateTimeOriginal = tag 36867
            date_str = exif.get(36867) or exif.get(306)  # DateTimeOriginal or DateTime
            if date_str:
                return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except Exception as e:
        logger.debug("EXIF read failed for %s: %s", file_path.name, e)
    return None


def _get_video_date(file_path: Path) -> datetime | None:
    """Extract creation_time from video using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_entries", "format_tags=creation_time",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            creation_time = (
                data.get("format", {})
                .get("tags", {})
                .get("creation_time", "")
            )
            if creation_time:
                # Format: "2026-01-15T12:30:00.000000Z"
                creation_time = creation_time.replace("Z", "+00:00")
                return datetime.fromisoformat(creation_time).replace(tzinfo=None)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("ffprobe not available for %s", file_path.name)
    except Exception as e:
        logger.debug("Video date extraction failed for %s: %s", file_path.name, e)
    return None
