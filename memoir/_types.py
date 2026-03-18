"""Typed dataclasses for all Memoir public API return values."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Capture targets
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MonitorTarget:
    """Capture a monitor by index (0 = primary)."""
    index: int = 0


@dataclass(frozen=True, slots=True)
class WindowTitleTarget:
    """Capture a window whose title matches a regex."""
    pattern: str


@dataclass(frozen=True, slots=True)
class WindowExeTarget:
    """Capture a window whose executable name matches a regex."""
    pattern: str


CaptureTarget = MonitorTarget | WindowTitleTarget | WindowExeTarget


# ---------------------------------------------------------------------------
# Engine stats
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EngineStats:
    frames_seen: int
    frames_accepted: int
    frames_dropped_queue_full: int
    frames_dropped_internal_error: int
    frames_recorded: int
    python_queue_depth: int
    recording_active: bool


# ---------------------------------------------------------------------------
# Recording info
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RecordingInfo:
    base_path: str
    video_path: str
    meta_path: str
    codec: str
    width: int
    height: int


# ---------------------------------------------------------------------------
# Metadata file types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MetaHeader:
    magic: bytes
    version: int
    created_unix_ns: int
    key_count: int


@dataclass(frozen=True, slots=True)
class MetaKeyEntry:
    bit_index: int
    virtual_key: int
    name: str


@dataclass(frozen=True, slots=True)
class MetaRow:
    frame_id: int
    record_frame_index: int
    capture_qpc: int
    host_accept_qpc: int
    keyboard_mask: int
    width: int
    height: int
    analysis_stride: int
    flags: int = 0


@dataclass(frozen=True, slots=True)
class MetaFile:
    """Complete contents of a .meta file."""
    header: MetaHeader
    keys: list[MetaKeyEntry]
    rows: list[MetaRow]
