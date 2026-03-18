"""memoir-capture — Windows-native capture/replay module with Python bindings."""

from __future__ import annotations

import os
import sys

# FFmpeg DLLs sit next to this package (project root).
# Python 3.8+ on Windows requires explicit DLL directory registration.
if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(_root):
        os.add_dll_directory(_root)

from memoir_capture._native import __version__, ping, FramePacket  # noqa: E402
from memoir_capture._types import (  # noqa: E402
    CaptureTarget,
    EngineStats,
    MetaFile,
    MetaHeader,
    MetaKeyEntry,
    MetaRow,
    MonitorTarget,
    RecordingInfo,
    WindowExeTarget,
    WindowTitleTarget,
)
from memoir_capture._engine import CaptureEngine  # noqa: E402
from memoir_capture._meta import MetaReader, MetaWriter  # noqa: E402

__all__ = [
    # version
    "__version__",
    "ping",
    # engine
    "CaptureEngine",
    "FramePacket",
    # targets
    "CaptureTarget",
    "MonitorTarget",
    "WindowTitleTarget",
    "WindowExeTarget",
    # stats / info
    "EngineStats",
    "RecordingInfo",
    # metadata
    "MetaReader",
    "MetaWriter",
    "MetaFile",
    "MetaHeader",
    "MetaKeyEntry",
    "MetaRow",
]
