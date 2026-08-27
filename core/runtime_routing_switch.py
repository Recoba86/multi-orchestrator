"""Runtime routing master enable/disable switch (Task 12 Phase B).

Manages persistent master switch state at ~/.agents/runtime-routing/enabled.json.
When enabled is false (OFF), runtime mode-aware routing is bypassed and legacy
wrapper authority is restored.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Optional

__all__ = [
    "ROUTING_SWITCH_PATH_DEFAULT",
    "SWITCH_SCHEMA_VERSION",
    "is_routing_enabled",
    "set_routing_enabled",
]

ROUTING_SWITCH_PATH_DEFAULT = Path.home() / ".agents" / "runtime-routing" / "enabled.json"
SWITCH_SCHEMA_VERSION = 1

_STATE_DIR_MODE = 0o700
_STATE_FILE_MODE = 0o600


def is_routing_enabled(path: Optional[Path] = None) -> bool:
    """Check if runtime routing is enabled. Fails safe to False (OFF) on any anomaly."""
    switch_path = ROUTING_SWITCH_PATH_DEFAULT if path is None else Path(path)
    if switch_path.is_symlink():
        return False

    try:
        raw = switch_path.read_bytes()
    except (FileNotFoundError, OSError):
        return False

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False

    if not isinstance(data, dict) or data.get("version") != SWITCH_SCHEMA_VERSION:
        return False

    val = data.get("enabled")
    if not isinstance(val, bool):
        return False

    return val


def set_routing_enabled(enabled: bool, path: Optional[Path] = None) -> None:
    """Atomically persist runtime routing enabled state with 0600 file permissions."""
    if not isinstance(enabled, bool):
        raise ValueError(f"enabled must be a boolean, got {enabled!r}")

    switch_path = ROUTING_SWITCH_PATH_DEFAULT if path is None else Path(path)
    parent = switch_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    if switch_path.is_symlink():
        raise RuntimeError(f"Refusing to write switch state to symlink: {switch_path}")

    payload = json.dumps(
        {"version": SWITCH_SCHEMA_VERSION, "enabled": enabled},
        sort_keys=True,
    ).encode("utf-8")

    tmp = parent / f".{switch_path.name}.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _STATE_FILE_MODE)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)

    try:
        os.chmod(tmp, _STATE_FILE_MODE)
        os.replace(tmp, switch_path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    try:
        os.chmod(parent, _STATE_DIR_MODE)
    except OSError:
        pass
