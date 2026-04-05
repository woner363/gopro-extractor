"""Data models for GoPro Extractor."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum


class MediaType(Enum):
    VIDEO = "video"
    PHOTO = "photo"


@dataclass
class DeviceInfo:
    udid: str
    name: str
    product_type: str = ""
    ios_version: str = ""


@dataclass
class MediaFile:
    file_id: str
    relative_path: str
    domain: str
    original_filename: str
    media_type: MediaType
    size: int = 0
    sha256: str = ""
    creation_date: datetime | None = None
    staged_path: Path | None = None

    @property
    def extension(self) -> str:
        return Path(self.original_filename).suffix.lower()

    @property
    def is_video(self) -> bool:
        return self.extension in (".mp4", ".mov")

    @property
    def is_photo(self) -> bool:
        return self.extension in (".jpg", ".jpeg", ".heic", ".png")


@dataclass
class BackupInfo:
    path: Path
    udid: str
    date: datetime
    encrypted: bool = True
    size_bytes: int = 0


@dataclass
class UploadResult:
    total_files: int = 0
    uploaded_files: int = 0
    skipped_duplicates: int = 0
    failed_files: int = 0
    total_bytes: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ExtractResult:
    total_found: int = 0
    videos: int = 0
    photos: int = 0
    total_bytes: int = 0
    files: list[MediaFile] = field(default_factory=list)
