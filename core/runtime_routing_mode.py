"""Persistent SolMode/GrokMode operator-intent state (Task 1R corrective).

MANUAL_ONLY invariant (normative, spec §2.1): the persisted mode changes
ONLY through an explicit operator call to ``write_mode`` (via the CLI).
No health, telemetry, or selection code path may write mode state.

Reads are STRICTLY READ-ONLY: ``read_mode`` performs ZERO filesystem
mutation — no sidecars, no parent directories, no temp files — regardless
of missing, unreadable, symlinked, corrupt, or schema-invalid state.
Anomalies surface through return value only: any invalid condition fails
closed to SOL_MODE.

State lives at one authoritative path per target home
(``~/.agents/runtime-routing/mode.json`` by default), strict schema::

    {"version": 1, "mode": "SolMode" | "GrokMode"}

Canonical stored values are exactly ``SolMode`` / ``GrokMode``; legacy
``sol_mode``/``grok_mode`` and all other spellings are INVALID. Missing
version, non-1 version, extra keys, or wrong shapes fail closed to
SOL_MODE.

Writes are atomic (same-directory tmp + ``os.replace``, fsync), file mode
0600, directory 0700. Symlinked authoritative paths are refused on write
without touching the target, and not followed on read.
"""

from __future__ import annotations

from enum import Enum
import json
import os
from pathlib import Path

__all__ = [
    "RoutingMode",
    "SOL_MODE",
    "GROK_MODE",
    "MODE_STATE_PATH_DEFAULT",
    "STATE_SCHEMA_VERSION",
    "parse_mode",
    "read_mode",
    "write_mode",
]


class RoutingMode(Enum):
    SOL_MODE = "SolMode"
    GROK_MODE = "GrokMode"


SOL_MODE = RoutingMode.SOL_MODE
GROK_MODE = RoutingMode.GROK_MODE

MODE_STATE_PATH_DEFAULT = Path.home() / ".agents" / "runtime-routing" / "mode.json"
STATE_SCHEMA_VERSION = 1

_STATE_DIR_MODE = 0o700
_STATE_FILE_MODE = 0o600


def parse_mode(value: object) -> RoutingMode:
    """Parse an exact canonical mode string; anything else raises ValueError."""
    if not isinstance(value, str):
        raise ValueError(f"mode must be a string, got {type(value).__name__}")
    try:
        return RoutingMode(value)
    except ValueError as exc:
        raise ValueError(
            f"invalid mode {value!r}; expected one of: "
            f"{', '.join(m.value for m in RoutingMode)}"
        ) from exc


def read_mode(state_path: Path | None = None) -> RoutingMode:
    """Load persisted mode; fail closed to SOL_MODE on any anomaly.

    ZERO filesystem mutation: never creates directories, files, temp files,
    or anomaly sidecars. Symlinks at the authoritative path are rejected
    without being followed. Never raises on bad content.
    """
    path = MODE_STATE_PATH_DEFAULT if state_path is None else Path(state_path)
    if path.is_symlink():
        return SOL_MODE
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, OSError):
        return SOL_MODE

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return SOL_MODE

    # Strict schema: exact key set {version, mode}, version == 1 required.
    if not isinstance(data, dict) or set(data) != {"version", "mode"}:
        return SOL_MODE

    version = data["version"]
    if not isinstance(version, int) or isinstance(version, bool) \
            or version != STATE_SCHEMA_VERSION:
        return SOL_MODE

    try:
        return parse_mode(data["mode"])
    except ValueError:
        return SOL_MODE


def write_mode(mode: RoutingMode, state_path: Path | None = None) -> None:
    """Atomically persist the operator's explicit mode choice.

    Same-filesystem temp file + ``os.replace`` (atomic swap, no partial
    content visible under the authoritative name). File mode 0600, dir 0700.
    Symlinked destination paths are rejected without touching the target.
    """
    if not isinstance(mode, RoutingMode):
        raise ValueError(
            f"write_mode expects a RoutingMode member, got {mode!r}; "
            f"valid: {', '.join(m.value for m in RoutingMode)}"
        )
    path = MODE_STATE_PATH_DEFAULT if state_path is None else Path(state_path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    if path.is_symlink():
        raise RuntimeError(
            f"refusing to write through symlinked state path: {path}"
        )

    payload = json.dumps(
        {"version": STATE_SCHEMA_VERSION, "mode": mode.value},
        sort_keys=True,
    ).encode("utf-8")

    tmp = parent / f".{path.name}.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _STATE_FILE_MODE)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, _STATE_FILE_MODE)
        os.replace(tmp, path)          # atomic within the same directory
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    try:
        os.chmod(parent, _STATE_DIR_MODE)
    except OSError:
        pass
