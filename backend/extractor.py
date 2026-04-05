"""Decrypt iPad backup and extract GoPro Quik media files."""

import logging
import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from iphone_backup_decrypt import EncryptedBackup

from models import MediaFile, MediaType, ExtractResult
from metadata import get_creation_date

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov"}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | PHOTO_EXTENSIONS

# Only extract from the real media store, not app cache/resources
GOPRO_MEDIA_PATH_PREFIX = "GPCoordinatedStore-com.gopro.softtubes/Files/"

# GoPro camera file naming patterns:
#   GH0xxxxx.MP4  - HERO video (H.264)
#   GX0xxxxx.MP4  - HERO video (H.265/HEVC)
#   GH02xxxx.MP4  - Multi-chapter continuation
#   GOPR0xxx.JPG  - HERO photo
#   trimmedXX.MP4 - User-trimmed clip in Quik
# NOT GoPro camera files:
#   Screenail.jpg, Thumbnail.jpg - GoPro app cache previews
#   UUID.jpg (e.g. B559AC05-...jpg) - Quik app internal
import re
_GOPRO_FILENAME_RE = re.compile(
    r"^(GH|GX|GL|GP|GOPR|trimmed)\d", re.IGNORECASE
)

# Reusable local mirror for SMB backup directories
_local_mirror: Path | None = None

# Max retries for SMB read errors
MAX_RETRIES = 3


def _is_gopro_camera_file(filename: str) -> bool:
    """Check if a filename matches GoPro camera naming convention."""
    return bool(_GOPRO_FILENAME_RE.match(filename))


def _ensure_local_mirror(backup_path: Path) -> Path:
    """Create a local mirror of a NAS backup to avoid SMB read issues.

    Copies Manifest.db and Manifest.plist to local /tmp, then symlinks
    the hash directories (00-ff) back to NAS. Manifest decryption runs
    locally; individual file reads go through symlinks to NAS.
    """
    global _local_mirror

    if not str(backup_path).startswith("/Volumes/"):
        return backup_path

    if _local_mirror and _local_mirror.exists():
        marker = _local_mirror / ".mirror_source"
        if marker.exists() and marker.read_text() == str(backup_path):
            logger.info("Reusing local mirror: %s", _local_mirror)
            return _local_mirror

    mirror = Path(tempfile.mkdtemp(prefix="gopro_mirror_"))
    logger.info("Creating local mirror: %s -> %s", backup_path, mirror)

    for name in ("Manifest.db", "Manifest.plist", "Info.plist", "Status.plist"):
        src = backup_path / name
        if src.exists():
            shutil.copy2(str(src), str(mirror / name))
            logger.info("Copied %s (%d MB)", name, src.stat().st_size // 1024 // 1024)

    for item in backup_path.iterdir():
        if item.is_dir() and len(item.name) == 2:
            link = mirror / item.name
            if not link.exists():
                link.symlink_to(item)

    (mirror / ".mirror_source").write_text(str(backup_path))
    _local_mirror = mirror
    return mirror


def validate_backup_password(backup_path: Path, password: str) -> bool:
    """Validate backup password by attempting to decrypt Manifest.db."""
    local_path = _ensure_local_mirror(backup_path)
    backup = EncryptedBackup(
        backup_directory=str(local_path),
        passphrase=password,
    )
    with backup.manifest_db_cursor() as cursor:
        cursor.execute("SELECT count(*) FROM Files")
        count = cursor.fetchone()[0]
    logger.info("Password validated, backup has %d files", count)
    return True


def scan_gopro_media(backup_path: Path, password: str) -> list[dict]:
    """Scan backup for GoPro media files without extracting."""
    local_path = _ensure_local_mirror(backup_path)
    backup = EncryptedBackup(
        backup_directory=str(local_path),
        passphrase=password,
    )

    ext_clauses = " OR ".join(
        [f"relativePath LIKE '%{ext}'" for ext in MEDIA_EXTENSIONS]
    )

    query = f"""
        SELECT fileID, relativePath, domain, flags
        FROM Files
        WHERE domain LIKE '%gopro%'
          AND flags = 1
          AND ({ext_clauses})
        ORDER BY relativePath
    """

    results = []
    with backup.manifest_db_cursor() as cursor:
        cursor.execute(query)
        for row in cursor.fetchall():
            file_id, rel_path, domain, flags = row

            if GOPRO_MEDIA_PATH_PREFIX not in rel_path:
                continue

            filename = Path(rel_path).name

            # Only keep actual GoPro camera files
            if not _is_gopro_camera_file(filename):
                continue

            ext = Path(filename).suffix.lower()

            if ext in VIDEO_EXTENSIONS:
                media_type = MediaType.VIDEO
            elif ext in PHOTO_EXTENSIONS:
                media_type = MediaType.PHOTO
            else:
                continue

            results.append({
                "file_id": file_id,
                "relative_path": rel_path,
                "domain": domain,
                "filename": filename,
                "media_type": media_type,
            })

    logger.info("Scan found %d GoPro media files", len(results))
    return results


def _extract_single_file(
    backup: EncryptedBackup,
    entry: dict,
    export_dir: Path,
    organize_by_date: bool,
) -> MediaFile | None:
    """Extract and export a single file with retry logic.

    1. Decrypt to local /tmp (retry on Errno 22)
    2. Read metadata for date organization
    3. Move to export directory
    4. Clean up temp file
    """
    filename = entry["filename"]
    rel_path = entry["relative_path"]
    domain = entry["domain"]
    media_type = entry["media_type"]
    local_tmp = None

    try:
        local_tmp = Path(tempfile.mktemp(
            prefix="gopro_",
            suffix=Path(filename).suffix,
            dir=tempfile.gettempdir(),
        ))

        # Decrypt with retry for SMB errors
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                backup.extract_file(
                    relative_path=rel_path,
                    domain_like=domain,
                    output_filename=str(local_tmp),
                )
                break
            except OSError as e:
                if attempt < MAX_RETRIES and e.errno in (22, 5):  # EINVAL, EIO
                    logger.warning(
                        "Retry %d/%d for %s: %s", attempt, MAX_RETRIES, filename, e
                    )
                    time.sleep(1)
                    # Clean partial file
                    if local_tmp.exists():
                        local_tmp.unlink()
                else:
                    raise

        file_size = local_tmp.stat().st_size

        # Determine destination path
        if organize_by_date:
            creation_date = get_creation_date(local_tmp)
            if creation_date:
                dest_dir = export_dir / creation_date.strftime("%Y/%m")
            else:
                dest_dir = export_dir / "unsorted"
        else:
            dest_dir = export_dir

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        # Avoid filename collisions
        if dest_path.exists():
            stem = dest_path.stem
            suffix = dest_path.suffix
            counter = 1
            while dest_path.exists():
                dest_path = dest_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        # Move to export (move is faster than copy when same filesystem,
        # falls back to copy+delete otherwise)
        shutil.move(str(local_tmp), str(dest_path))
        local_tmp = None  # Already moved

        return MediaFile(
            file_id=entry["file_id"],
            relative_path=rel_path,
            domain=domain,
            original_filename=filename,
            media_type=media_type,
            size=file_size,
            staged_path=dest_path,
        )

    except Exception as e:
        logger.warning("Failed to extract %s: %s", rel_path, e)
        return None

    finally:
        if local_tmp and local_tmp.exists():
            try:
                local_tmp.unlink()
            except OSError:
                pass


def extract_and_export(
    backup_path: Path,
    password: str,
    export_dir: Path,
    organize_by_date: bool = True,
    progress_callback=None,
) -> ExtractResult:
    """Extract GoPro media from backup directly to export directory.

    Optimizations:
    - Local mirror for Manifest.db decryption (no SMB reads)
    - Only extracts real GoPro media (~128 files, not ~4700)
    - Retry logic for SMB Errno 22 on individual files
    - Concurrent extraction with thread pool
    - Files decrypted to local /tmp then moved to export dir
    """
    export_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Export directory: %s", export_dir)

    if progress_callback:
        progress_callback(0, "Preparing backup...")

    local_path = _ensure_local_mirror(backup_path)

    if progress_callback:
        progress_callback(2, "Decrypting backup database...")

    # Single backup object for scanning
    backup = EncryptedBackup(
        backup_directory=str(local_path),
        passphrase=password,
    )

    # Query media entries using the already-opened backup
    ext_clauses = " OR ".join(
        [f"relativePath LIKE '%{ext}'" for ext in MEDIA_EXTENSIONS]
    )
    query = f"""
        SELECT fileID, relativePath, domain, flags
        FROM Files
        WHERE domain LIKE '%gopro%'
          AND flags = 1
          AND ({ext_clauses})
        ORDER BY relativePath
    """

    media_entries = []
    with backup.manifest_db_cursor() as cursor:
        cursor.execute(query)
        for row in cursor.fetchall():
            file_id, rel_path, domain, flags = row
            if GOPRO_MEDIA_PATH_PREFIX not in rel_path:
                continue
            filename = Path(rel_path).name
            ext = Path(filename).suffix.lower()
            if ext in VIDEO_EXTENSIONS:
                media_type = MediaType.VIDEO
            elif ext in PHOTO_EXTENSIONS:
                media_type = MediaType.PHOTO
            else:
                continue
            media_entries.append({
                "file_id": file_id,
                "relative_path": rel_path,
                "domain": domain,
                "filename": filename,
                "media_type": media_type,
            })

    if not media_entries:
        logger.warning("No GoPro media files found in backup.")
        return ExtractResult()

    logger.info("Found %d GoPro media files to extract", len(media_entries))

    if progress_callback:
        progress_callback(5, f"Found {len(media_entries)} files, starting export...")

    result = ExtractResult()
    result.total_found = len(media_entries)
    extracted_files = []
    completed = 0
    lock = Lock()

    # Each thread needs its own EncryptedBackup (sqlite3 is not thread-safe)
    def make_backup():
        return EncryptedBackup(
            backup_directory=str(local_path),
            passphrase=password,
        )

    def process_entry(entry):
        nonlocal completed
        thread_backup = make_backup()
        mf = _extract_single_file(thread_backup, entry, export_dir, organize_by_date)

        with lock:
            completed += 1
            if progress_callback and (completed % 3 == 0 or completed == len(media_entries)):
                percent = 5 + int(completed / len(media_entries) * 95)
                progress_callback(
                    percent,
                    f"Exporting {completed}/{len(media_entries)}: {entry['filename']}"
                )
        return mf

    # Use 3 threads — balances SMB bandwidth vs parallelism
    # (each thread does: SMB read → CPU decrypt → SMB write)
    num_workers = 3 if str(backup_path).startswith("/Volumes/") else 2

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_entry, e): e for e in media_entries}
        for future in as_completed(futures):
            mf = future.result()
            if mf:
                extracted_files.append(mf)
                result.total_bytes += mf.size
                if mf.media_type == MediaType.VIDEO:
                    result.videos += 1
                else:
                    result.photos += 1

    result.files = extracted_files

    if progress_callback:
        progress_callback(100, f"Exported {len(extracted_files)} files")

    logger.info(
        "Export complete: %d videos, %d photos, %.1f GB total",
        result.videos, result.photos, result.total_bytes / 1024 / 1024 / 1024
    )
    return result
