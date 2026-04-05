"""JSON-RPC server over stdin/stdout for Electron IPC communication."""

import json
import sys
import logging
import shutil
import tempfile
from pathlib import Path

import yaml

from device import detect_ipad, list_devices, check_libimobiledevice, DeviceNotFoundError
from backup import find_existing_backup, create_backup, BackupError, BackupPasswordError, DEFAULT_BACKUP_DIR
from extractor import validate_backup_password, scan_gopro_media, extract_and_export
from dedup import DedupDB, hash_file, filter_new_files
from uploader import validate_nas_path, NASConnectionError

logger = logging.getLogger("gopro_extractor")

# Global state
_config = {}
_dedup_db = None


def load_config(config_path: str | None = None) -> dict:
    """Load configuration from YAML file."""
    defaults = {
        "backup": {
            "password": "",
            "reuse_existing": True,
            "max_age_hours": 48,
        },
        "nas": {
            "mount_path": "",
            "organize_by_date": True,
        },
        "staging": {
            "cleanup_after_upload": True,
        },
        "logging": {
            "level": "INFO",
        },
    }

    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        for section, values in user_config.items():
            if section in defaults and isinstance(values, dict):
                defaults[section].update(values)
            else:
                defaults[section] = values

    return defaults


def send_response(id: int | str, result=None, error=None):
    """Send a JSON-RPC response to stdout."""
    response = {"jsonrpc": "2.0", "id": id}
    if error:
        response["error"] = {"code": -1, "message": str(error)}
    else:
        response["result"] = result
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def send_notification(method: str, params: dict):
    """Send a JSON-RPC notification (no id) to stdout."""
    notification = {"jsonrpc": "2.0", "method": method, "params": params}
    sys.stdout.write(json.dumps(notification) + "\n")
    sys.stdout.flush()


def make_progress_callback(stage: str):
    """Create a progress callback that sends JSON-RPC notifications."""
    def callback(percent: int, message: str):
        send_notification("progress", {
            "stage": stage,
            "percent": percent,
            "message": message,
        })
    return callback


# --- RPC Method Handlers ---

def handle_check_environment(params: dict) -> dict:
    """Check if all required tools are available."""
    has_libimobiledevice = check_libimobiledevice()
    has_ffprobe = shutil.which("ffprobe") is not None

    return {
        "libimobiledevice": has_libimobiledevice,
        "python": True,
        "ffprobe": has_ffprobe,
        "ready": has_libimobiledevice,
    }


def handle_detect_device(params: dict) -> dict:
    """Detect connected iPad."""
    try:
        device = detect_ipad()
        return {
            "found": True,
            "udid": device.udid,
            "name": device.name,
            "product_type": device.product_type,
            "ios_version": device.ios_version,
        }
    except DeviceNotFoundError as e:
        return {"found": False, "error": str(e)}


def handle_list_devices(params: dict) -> dict:
    """List all connected iOS devices."""
    devices = list_devices()
    return {"devices": devices, "count": len(devices)}


def handle_check_backup(params: dict) -> dict:
    """Check for existing backup without creating one."""
    backup_dir = params.get("backup_dir")
    if backup_dir:
        backup_dir = Path(backup_dir)

    try:
        device = detect_ipad()
    except DeviceNotFoundError as e:
        return {"found": False, "error": str(e)}

    max_age = params.get("max_age_hours", 48)
    existing = find_existing_backup(device.udid, backup_dir=backup_dir, max_age_hours=max_age)

    if existing:
        age_hours = (
            __import__("datetime").datetime.now() - existing.date
        ).total_seconds() / 3600
        return {
            "found": True,
            "path": str(existing.path),
            "date": existing.date.isoformat(),
            "size_bytes": existing.size_bytes,
            "age_hours": round(age_hours, 1),
        }

    # Also check default location
    default_existing = find_existing_backup(device.udid, max_age_hours=max_age)
    if default_existing:
        age_hours = (
            __import__("datetime").datetime.now() - default_existing.date
        ).total_seconds() / 3600
        return {
            "found": True,
            "path": str(default_existing.path),
            "date": default_existing.date.isoformat(),
            "size_bytes": default_existing.size_bytes,
            "age_hours": round(age_hours, 1),
        }

    return {"found": False}


def handle_create_backup(params: dict) -> dict:
    """Create an iPad backup."""
    backup_dir = params.get("backup_dir")
    if backup_dir:
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        device = detect_ipad()
    except DeviceNotFoundError as e:
        return {"error": str(e)}

    try:
        backup_info = create_backup(
            udid=device.udid,
            backup_dir=backup_dir,
            progress_callback=make_progress_callback("backup"),
        )
        return {
            "status": "created",
            "path": str(backup_info.path),
            "date": backup_info.date.isoformat(),
            "size_bytes": backup_info.size_bytes,
        }
    except BackupPasswordError as e:
        return {"error": f"Password error: {e}"}
    except BackupError as e:
        return {"error": f"Backup failed: {e}"}


def _find_backup_dir(user_path: Path) -> Path | None:
    """Find the actual backup directory containing Manifest.db.

    The user may select:
    - The exact UDID folder (contains Manifest.db directly)
    - A parent folder (we search up to 3 levels deep)
    """
    if (user_path / "Manifest.db").exists():
        return user_path

    # Search subdirectories (up to 3 levels)
    for depth in range(1, 4):
        pattern = "/".join(["*"] * depth) + "/Manifest.db"
        matches = sorted(user_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            return matches[0].parent

    return None


def handle_validate_password(params: dict) -> dict:
    """Validate backup password by decrypting Manifest.db."""
    backup_path = params.get("backup_path")
    password = params.get("password", "")

    if not backup_path:
        return {"valid": False, "error": "backup_path is required"}
    if not password:
        return {"valid": False, "error": "password is required"}

    user_path = Path(backup_path)
    if not user_path.exists():
        return {"valid": False, "error": f"Path not found: {backup_path}"}

    actual_backup = _find_backup_dir(user_path)
    if not actual_backup:
        return {"valid": False, "error": f"No backup found in {backup_path} (Manifest.db not found)"}

    try:
        validate_backup_password(actual_backup, password)
        return {"valid": True, "backup_path": str(actual_backup)}
    except ValueError:
        return {"valid": False, "error": "Incorrect password"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def handle_scan_media(params: dict) -> dict:
    """Scan backup for GoPro media files (preview without extracting)."""
    backup_path = params.get("backup_path")
    password = params.get("password", "")

    if not backup_path or not password:
        return {"error": "backup_path and password are required"}

    try:
        entries = scan_gopro_media(Path(backup_path), password)
    except Exception as e:
        return {"error": str(e)}

    videos = [e for e in entries if e["media_type"].value == "video"]
    photos = [e for e in entries if e["media_type"].value == "photo"]

    return {
        "total": len(entries),
        "videos": len(videos),
        "photos": len(photos),
        "files": [
            {"filename": e["filename"], "type": e["media_type"].value}
            for e in entries
        ],
    }


def handle_export_media(params: dict) -> dict:
    """Extract and export GoPro media from backup to export directory.

    This combines extraction + date organization + dedup in one step.
    Files are decrypted locally then moved to the export directory.
    """
    global _dedup_db

    backup_path = params.get("backup_path")
    password = params.get("password", "")
    export_dir = params.get("export_dir")
    organize_by_date = params.get("organize_by_date", True)
    skip_duplicates = params.get("skip_duplicates", True)

    if not backup_path or not password or not export_dir:
        return {"error": "backup_path, password, and export_dir are required"}

    import time as _time
    t_start = _time.time()

    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Dedup DB lives in the export directory
    dedup_db_path = export_dir / ".gopro_extractor" / "dedup.db"
    _dedup_db = DedupDB(db_path=dedup_db_path)

    try:
        result = extract_and_export(
            backup_path=Path(backup_path),
            password=password,
            export_dir=export_dir,
            organize_by_date=organize_by_date,
            progress_callback=make_progress_callback("export"),
        )
    except Exception as e:
        logger.exception("Export failed")
        return {"error": str(e)}

    # Dedup: hash exported files and record them
    new_count = 0
    dup_count = 0
    final_files = []

    for j, mf in enumerate(result.files):
        if mf.staged_path and mf.staged_path.exists():
            sha = hash_file(mf.staged_path)
            mf.sha256 = sha

            if skip_duplicates and _dedup_db.is_duplicate(sha):
                # Remove duplicate from export dir
                try:
                    mf.staged_path.unlink()
                except OSError:
                    pass
                dup_count += 1
            else:
                _dedup_db.record_upload(mf, str(mf.staged_path))
                new_count += 1
                final_files.append(mf)

        if j % 5 == 0:
            send_notification("progress", {
                "stage": "dedup",
                "percent": int((j + 1) / max(len(result.files), 1) * 100),
                "message": f"Checking duplicates {j + 1}/{len(result.files)}",
            })

    _dedup_db.close()
    _dedup_db = None

    elapsed = _time.time() - t_start

    return {
        "total_found": result.total_found,
        "videos": result.videos,
        "photos": result.photos,
        "total_bytes": result.total_bytes,
        "exported": new_count,
        "duplicates": dup_count,
        "export_dir": str(export_dir),
        "elapsed_seconds": round(elapsed, 1),
        "files": [
            {
                "filename": f.original_filename,
                "type": f.media_type.value,
                "size": f.size,
                "path": str(f.staged_path) if f.staged_path else None,
            }
            for f in final_files
        ],
    }


def handle_get_disk_space(params: dict) -> dict:
    """Get available disk space for a path."""
    path = params.get("path", "/")
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        stat = shutil.disk_usage(str(p))
        return {
            "total": stat.total,
            "used": stat.used,
            "free": stat.free,
        }
    except Exception as e:
        return {"error": str(e)}


def handle_get_stats(params: dict) -> dict:
    """Get dedup database statistics."""
    db_path = params.get("db_path")
    if db_path:
        db = DedupDB(db_path=Path(db_path))
    else:
        db = DedupDB()
    stats = db.get_stats()
    db.close()
    return stats


# --- RPC Dispatcher ---

METHODS = {
    "check_environment": handle_check_environment,
    "detect_device": handle_detect_device,
    "list_devices": handle_list_devices,
    "check_backup": handle_check_backup,
    "create_backup": handle_create_backup,
    "validate_password": handle_validate_password,
    "scan_media": handle_scan_media,
    "export_media": handle_export_media,
    "get_disk_space": handle_get_disk_space,
    "get_stats": handle_get_stats,
}


def main():
    global _config

    log_dir = Path.home() / ".gopro_extractor"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "backend.log"),
        ],
    )

    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    _config = load_config(config_path)

    logger.info("GoPro Extractor backend started")

    send_notification("ready", {"version": "2.0.0"})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            send_response(None, error=f"Invalid JSON: {e}")
            continue

        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        if method not in METHODS:
            send_response(req_id, error=f"Unknown method: {method}")
            continue

        try:
            result = METHODS[method](params)
            send_response(req_id, result=result)
        except Exception as e:
            logger.exception("Error in %s", method)
            send_response(req_id, error=str(e))


if __name__ == "__main__":
    main()
