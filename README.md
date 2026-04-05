# GoPro Extractor

A macOS desktop application for extracting GoPro Quik media (videos and photos) from encrypted iPad backups and organizing them on local storage or NAS.

## Why This Tool?

GoPro Quik on iPad stores all media inside its app sandbox, which cannot be accessed via iTunes file sharing or the Files app. The only way to retrieve the original camera files is through an **encrypted iPad backup** — this tool automates the entire process: backup decryption, GoPro media identification, metadata-based date organization, and deduplication.

## Features

- **Two operation modes** — Create a new iPad backup, or extract from an existing one
- **Smart file detection** — Only extracts real GoPro camera files (GH/GX/GOPR/GL/GP/trimmed), ignoring app thumbnails and cache
- **Date organization** — Automatically sorts exported media into `YYYY/MM/` folders based on shooting date
- **Deduplication** — SHA-256 based tracking to skip previously exported files
- **SMB/NAS optimized** — Local mirror strategy for reliable backup decryption over network mounts
- **Live progress** — Real-time progress bar and elapsed timer during export
- **Concurrent extraction** — Multi-threaded decryption with retry logic for SMB errors

## Screenshots

```
┌─────────────────────────────────┐
│  GoPro Extractor                │
│                                 │
│  What would you like to do?     │
│                                 │
│  [+] Create iPad Backup         │
│  [📦] Extract from Existing     │
│       Backup                    │
└─────────────────────────────────┘
```

## Prerequisites

- **macOS** (Apple Silicon or Intel)
- **libimobiledevice** — for iPad communication
- **Python 3.10+** — for the backend (only needed for development)
- **Node.js 18+** — for building (only needed for development)
- **ffprobe** (optional) — for video date extraction

### Install Dependencies (Development)

```bash
brew install libimobiledevice
brew install python node
brew install ffmpeg  # optional, for video date metadata
```

## Quick Start (Pre-built App)

1. Download `GoPro Extractor-x.x.x-arm64.dmg` from Releases
2. Drag to Applications and open
3. Choose **Extract from Existing Backup** (if you already have an iPad backup) or **Create iPad Backup** (connect iPad via USB first)
4. Enter the backup encryption password
5. Select an export directory (local or NAS mount)
6. Done — files are organized in `<export-dir>/GoPro/YYYY/MM/`

## Development Setup

```bash
# Clone the project
cd gopro-extractor

# Install Node.js dependencies
npm install

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Run in development mode
npm run dev
```

## Building

```bash
# Full build: React frontend + Python backend + macOS DMG
npm run build

# Individual steps
npm run build:renderer   # Vite build (React)
npm run build:python     # PyInstaller (Python backend)
```

Output:
- `release/GoPro Extractor-x.x.x-arm64.dmg` — distributable installer
- `release/mac-arm64/GoPro Extractor.app` — standalone application

## Project Structure

```
gopro-extractor/
├── electron/               # Electron main process
│   ├── main.js             # Window management, IPC handlers
│   ├── preload.js          # Context bridge (renderer ↔ main)
│   └── python-bridge.js    # JSON-RPC communication with Python
├── src/                    # React frontend
│   ├── App.jsx             # Main UI (mode selection, extraction flow)
│   ├── components/         # StatusCard, ProgressBar
│   └── hooks/              # useBackend, useDirectoryPicker
├── backend/                # Python backend
│   ├── main.py             # JSON-RPC server (stdin/stdout)
│   ├── device.py           # iPad detection (libimobiledevice)
│   ├── backup.py           # Backup creation (idevicebackup2)
│   ├── extractor.py        # Backup decryption + GoPro media extraction
│   ├── dedup.py            # SHA-256 deduplication database
│   ├── uploader.py         # NAS file upload
│   ├── metadata.py         # EXIF/video date extraction
│   └── models.py           # Data models
├── config/
│   └── default.yaml        # Default configuration
├── scripts/
│   └── check-deps.sh       # Dependency checker
└── package.json
```

## Architecture

```
Electron (React UI)  ←──IPC──→  Electron Main  ←──JSON-RPC/stdio──→  Python Backend
                                     │
                      ┌──────────────┼──────────────┐
                      ▼              ▼              ▼
                   iPad/USB    Local Backup    NAS (SMB)
```

- **Frontend**: React + Tailwind CSS, two independent modes (Backup / Extract)
- **IPC**: Electron IPC bridges the renderer to the main process
- **Backend**: Python subprocess communicates via JSON-RPC over stdin/stdout
- **Extraction**: `iphone-backup-decrypt` decrypts the backup, files are filtered by GoPro naming patterns and organized by EXIF/metadata date

## Configuration

Edit `config/default.yaml`:

```yaml
backup:
  password: ""              # Backup encryption password
  reuse_existing: true      # Reuse recent backups
  max_age_hours: 48         # Max age before re-backup

nas:
  mount_path: ""            # SMB mount path (e.g. /Volumes/home/Photos)
  organize_by_date: true    # Sort into YYYY/MM/ folders

staging:
  cleanup_after_upload: true

logging:
  level: INFO
```

## How It Works

1. **Backup Decryption** — Opens the encrypted iPad backup's `Manifest.db` using the user-provided password
2. **Media Discovery** — Queries for files in the GoPro Quik domain (`GPCoordinatedStore-com.gopro.softtubes/Files/`)
3. **Filename Filtering** — Only keeps files matching GoPro camera naming (`GH`, `GX`, `GOPR`, `GL`, `GP`, `trimmed`)
4. **Concurrent Extraction** — Decrypts files to local temp, reads metadata for date, moves to export directory
5. **Deduplication** — Hashes each file with SHA-256 and records in a local SQLite database to avoid re-exporting

## Dependency Check

```bash
./scripts/check-deps.sh
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Manifest.db not found" | Select the correct backup folder (contains a UDID subfolder) — the app auto-searches up to 3 levels deep |
| Errno 22 during extraction | SMB read error — the app retries 3 times automatically; some files may still fail over unreliable connections |
| "Incorrect password" | Verify the backup encryption password set in Finder > iPad > Encrypt local backup |
| No GoPro files found | Ensure GoPro Quik app has media on the iPad and the backup is recent |

## License

MIT
