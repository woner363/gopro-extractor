"""iPad device detection via libimobiledevice."""

import subprocess
import logging

from models import DeviceInfo

logger = logging.getLogger(__name__)


class DeviceNotFoundError(Exception):
    pass


def _run_cmd(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return stdout."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"Command not found: {cmd[0]}. "
            "Install libimobiledevice: brew install libimobiledevice"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Command timed out: {' '.join(cmd)}")


def list_devices() -> list[str]:
    """List connected iOS device UDIDs."""
    output = _run_cmd(["idevice_id", "-l"])
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def get_device_info(udid: str | None = None) -> DeviceInfo:
    """Get info about a connected device."""
    cmd = ["ideviceinfo"]
    if udid:
        cmd.extend(["-u", udid])

    output = _run_cmd(cmd, timeout=15)
    if not output:
        raise DeviceNotFoundError("No device found or device not paired.")

    info = {}
    for line in output.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            info[key.strip()] = value.strip()

    device_udid = udid or info.get("UniqueDeviceID", "unknown")
    return DeviceInfo(
        udid=device_udid,
        name=info.get("DeviceName", "Unknown iPad"),
        product_type=info.get("ProductType", ""),
        ios_version=info.get("ProductVersion", ""),
    )


def detect_ipad() -> DeviceInfo:
    """Detect a connected iPad. Raises DeviceNotFoundError if none found."""
    devices = list_devices()
    if not devices:
        raise DeviceNotFoundError(
            "No iOS device detected. Please connect your iPad via USB "
            "and trust this computer."
        )

    logger.info("Found %d device(s): %s", len(devices), devices)
    return get_device_info(devices[0])


def check_libimobiledevice() -> bool:
    """Check if libimobiledevice tools are available."""
    try:
        _run_cmd(["idevice_id", "--version"])
        return True
    except RuntimeError:
        return False
