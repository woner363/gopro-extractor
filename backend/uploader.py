"""Upload media files to NAS via mounted SMB share."""

import logging
import shutil
from pathlib import Path

from models import MediaFile, UploadResult
from metadata import get_creation_date
from dedup import DedupDB

logger = logging.getLogger(__name__)


class NASConnectionError(Exception):
    pass


class NASWriteError(Exception):
    pass


def validate_nas_path(nas_path: Path) -> bool:
    """Verify NAS mount point is accessible and writable."""
    if not nas_path.exists():
        raise NASConnectionError(
            f"NAS path not found: {nas_path}. "
            "Please mount your QNAP NAS in Finder first."
        )
    if not nas_path.is_dir():
        raise NASConnectionError(f"NAS path is not a directory: {nas_path}")

    # Test write access
    test_file = nas_path / ".gopro_extractor_write_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
    except PermissionError:
        raise NASConnectionError(
            f"No write permission on NAS path: {nas_path}"
        )
    return True


def build_dest_path(
    nas_base: Path,
    media_file: MediaFile,
    organize_by_date: bool = True,
    date_format: str = "%Y/%m",
) -> Path:
    """Build the destination path on NAS for a media file.

    Organizes files into YYYY/MM/ subdirectories based on creation date.
    """
    if organize_by_date and media_file.staged_path:
        creation_date = get_creation_date(media_file.staged_path)
        if creation_date:
            date_subdir = creation_date.strftime(date_format)
            return nas_base / date_subdir / media_file.original_filename

    return nas_base / media_file.original_filename


def upload_files(
    files: list[MediaFile],
    nas_path: Path,
    dedup_db: DedupDB,
    organize_by_date: bool = True,
    progress_callback=None,
) -> UploadResult:
    """Upload media files to NAS.

    Args:
        files: List of MediaFile objects with staged_path set.
        nas_path: Base NAS directory path (e.g., /Volumes/NAS/GoPro).
        dedup_db: Deduplication database to record uploads.
        organize_by_date: Organize into YYYY/MM/ subdirectories.
        progress_callback: Optional callback(percent: int, message: str).

    Returns:
        UploadResult with upload statistics.
    """
    validate_nas_path(nas_path)

    result = UploadResult(total_files=len(files))

    for i, media_file in enumerate(files):
        if not media_file.staged_path or not media_file.staged_path.exists():
            result.failed_files += 1
            result.errors.append(f"Staged file missing: {media_file.original_filename}")
            continue

        dest_path = build_dest_path(nas_path, media_file, organize_by_date)

        # Avoid overwriting existing files
        if dest_path.exists():
            stem = dest_path.stem
            suffix = dest_path.suffix
            parent = dest_path.parent
            counter = 1
            while dest_path.exists():
                dest_path = parent / f"{stem}_{counter}{suffix}"
                counter += 1

        try:
            # Create destination directory
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy with metadata preservation
            shutil.copy2(str(media_file.staged_path), str(dest_path))

            # Verify copy
            src_size = media_file.staged_path.stat().st_size
            dst_size = dest_path.stat().st_size
            if src_size != dst_size:
                raise NASWriteError(
                    f"Size mismatch after copy: {src_size} vs {dst_size}"
                )

            # Record in dedup database
            dedup_db.record_upload(media_file, str(dest_path))

            result.uploaded_files += 1
            result.total_bytes += src_size

            logger.info("Uploaded: %s -> %s", media_file.original_filename, dest_path)

        except Exception as e:
            result.failed_files += 1
            result.errors.append(f"{media_file.original_filename}: {e}")
            logger.error("Upload failed for %s: %s", media_file.original_filename, e)

        if progress_callback:
            percent = int((i + 1) / len(files) * 100)
            progress_callback(
                percent,
                f"Uploading {i + 1}/{len(files)}: {media_file.original_filename}"
            )

    logger.info(
        "Upload complete: %d uploaded, %d failed, %.1f MB",
        result.uploaded_files,
        result.failed_files,
        result.total_bytes / 1024 / 1024,
    )
    return result
