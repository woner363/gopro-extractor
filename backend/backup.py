"""iPad backup creation via idevicebackup2."""

import subprocess
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from models import BackupInfo

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"


class BackupError(Exception):
    pass


class BackupPasswordError(BackupError):
    pass


def get_default_backup_dir() -> Path:
    """Return the default macOS backup directory."""
    return DEFAULT_BACKUP_DIR


def find_existing_backup(
    udid: str, backup_dir: Path | None = None, max_age_hours: int = 24
) -> BackupInfo | None:
    """Find an existing backup for the given UDID within max_age_hours."""
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    backup_path = backup_dir / udid

    if not backup_path.exists():
        return None

    manifest = backup_path / "Manifest.db"
    if not manifest.exists():
        return None

    mod_time = datetime.fromtimestamp(manifest.stat().st_mtime)
    age_hours = (datetime.now() - mod_time).total_seconds() / 3600

    if age_hours > max_age_hours:
        logger.info(
            "Existing backup is %.1f hours old (max %d), needs refresh",
            age_hours, max_age_hours
        )
        return None

    backup_size = sum(f.stat().st_size for f in backup_path.rglob("*") if f.is_file())

    logger.info("Found recent backup: %s (%.1f hours old)", backup_path, age_hours)
    return BackupInfo(
        path=backup_path,
        udid=udid,
        date=mod_time,
        encrypted=True,
        size_bytes=backup_size,
    )


def create_backup(
    udid: str,
    backup_dir: Path | None = None,
    progress_callback=None,
) -> BackupInfo:
    """Create an encrypted iPad backup using idevicebackup2.

    Args:
        udid: Device UDID.
        backup_dir: Directory to store backup. Defaults to macOS standard location.
        progress_callback: Optional callback(percent: int, message: str).

    Returns:
        BackupInfo with the backup details.
    """
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "idevicebackup2",
        "-u", udid,
        "backup",
        str(backup_dir),
    ]

    logger.info("Starting backup: %s", " ".join(cmd))
    if progress_callback:
        progress_callback(0, "Starting backup...")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        last_percent = 0
        for line in iter(process.stdout.readline, ""):
            line = line.strip()
            if not line:
                continue

            logger.debug("idevicebackup2: %s", line)

            # Parse progress from output like "Receiving files... (50%)"
            match = re.search(r"(\d+)%", line)
            if match and progress_callback:
                percent = int(match.group(1))
                if percent > last_percent:
                    last_percent = percent
                    progress_callback(percent, line)

            if "error" in line.lower():
                if "password" in line.lower() or "encrypt" in line.lower():
                    raise BackupPasswordError(
                        "Backup encryption password error. "
                        "Please set up encrypted backup in Finder first."
                    )

        process.wait()

        if process.returncode != 0:
            raise BackupError(
                f"idevicebackup2 exited with code {process.returncode}"
            )

    except FileNotFoundError:
        raise BackupError(
            "idevicebackup2 not found. Install: brew install libimobiledevice"
        )

    backup_path = backup_dir / udid
    if not (backup_path / "Manifest.db").exists():
        raise BackupError(f"Backup completed but Manifest.db not found at {backup_path}")

    backup_size = sum(f.stat().st_size for f in backup_path.rglob("*") if f.is_file())

    if progress_callback:
        progress_callback(100, "Backup complete!")

    return BackupInfo(
        path=backup_path,
        udid=udid,
        date=datetime.now(),
        encrypted=True,
        size_bytes=backup_size,
    )
