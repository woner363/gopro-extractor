#!/bin/bash
# Check dependencies for GoPro Extractor on macOS

echo "=== GoPro Extractor Dependency Check ==="
echo ""

# Check Python
if command -v python3 &> /dev/null; then
    echo "✓ Python3: $(python3 --version)"
else
    echo "✗ Python3: NOT FOUND"
    echo "  Install: brew install python"
fi

# Check libimobiledevice
if command -v idevice_id &> /dev/null; then
    echo "✓ libimobiledevice: $(idevice_id --version 2>&1 | head -1)"
else
    echo "✗ libimobiledevice: NOT FOUND"
    echo "  Install: brew install libimobiledevice"
fi

# Check Node.js
if command -v node &> /dev/null; then
    echo "✓ Node.js: $(node --version)"
else
    echo "✗ Node.js: NOT FOUND"
    echo "  Install: brew install node"
fi

# Check ffprobe (optional)
if command -v ffprobe &> /dev/null; then
    echo "✓ ffprobe: $(ffprobe -version 2>&1 | head -1)"
else
    echo "○ ffprobe: NOT FOUND (optional, for video date extraction)"
    echo "  Install: brew install ffmpeg"
fi

# Check Python packages
echo ""
echo "=== Python Packages ==="
python3 -c "import iphone_backup_decrypt; print('✓ iphone-backup-decrypt')" 2>/dev/null || echo "✗ iphone-backup-decrypt: pip install iphone-backup-decrypt"
python3 -c "import PIL; print('✓ Pillow')" 2>/dev/null || echo "✗ Pillow: pip install Pillow"
python3 -c "import yaml; print('✓ pyyaml')" 2>/dev/null || echo "✗ pyyaml: pip install pyyaml"

# Check for connected devices
echo ""
echo "=== Connected Devices ==="
if command -v idevice_id &> /dev/null; then
    DEVICES=$(idevice_id -l 2>/dev/null)
    if [ -n "$DEVICES" ]; then
        echo "✓ Found device(s):"
        echo "$DEVICES"
    else
        echo "○ No iOS devices connected"
    fi
fi

echo ""
echo "=== Done ==="
