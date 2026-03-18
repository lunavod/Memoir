"""Typed Python wrapper around the native CaptureEngine."""

from __future__ import annotations

import os
from typing import Iterator

from memoir import _native
from memoir._types import (
    CaptureTarget,
    EngineStats,
    MonitorTarget,
    RecordingInfo,
    WindowExeTarget,
    WindowTitleTarget,
)

# Re-export FramePacket directly — it's a pybind11 class with proper
# attribute access and context manager support already.
FramePacket = _native.FramePacket


def _target_to_dict(target: CaptureTarget) -> dict:
    if isinstance(target, MonitorTarget):
        return {"type": "monitor_index", "value": target.index}
    elif isinstance(target, WindowTitleTarget):
        return {"type": "window_title", "value": target.pattern}
    elif isinstance(target, WindowExeTarget):
        return {"type": "window_exe", "value": target.pattern}
    else:
        raise TypeError(f"Unknown target type: {type(target)}")


class CaptureEngine:
    """Memoir capture engine with optional recording.

    Args:
        target: What to capture — a MonitorTarget, WindowTitleTarget,
            or WindowExeTarget.
        max_fps: Maximum accepted frame rate.
        analysis_queue_capacity: Bounded queue size for Python delivery.
        capture_cursor: Include the cursor in captured frames.
        record_width: Recording output width in pixels.
        record_height: Recording output height in pixels.
        record_gop: GOP size for recording (1 = all-intra).
    """

    def __init__(
        self,
        target: CaptureTarget,
        *,
        max_fps: float = 10.0,
        analysis_queue_capacity: int = 1,
        capture_cursor: bool = False,
        record_width: int = 1920,
        record_height: int = 1080,
        record_gop: int = 1,
    ) -> None:
        self._engine = _native.CaptureEngine(
            _target_to_dict(target),
            max_fps=max_fps,
            analysis_queue_capacity=analysis_queue_capacity,
            capture_cursor=capture_cursor,
            record_width=record_width,
            record_height=record_height,
            record_gop=record_gop,
        )

    # -- context manager --

    def __enter__(self) -> CaptureEngine:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # -- lifecycle --

    def start(self) -> None:
        """Start capturing frames."""
        self._engine.start()

    def stop(self) -> None:
        """Stop capture and any active recording."""
        self._engine.stop()

    def close(self) -> None:
        """Alias for stop()."""
        self._engine.stop()

    # -- frame delivery --

    def get_next_frame(self, timeout_ms: int = -1) -> FramePacket | None:
        """Return the next accepted frame, or None on timeout.

        Args:
            timeout_ms: -1 = block forever, 0 = poll, >0 = wait up to N ms.
        """
        return self._engine.get_next_frame(timeout_ms)

    def frames(self) -> Iterator[FramePacket]:
        """Yield accepted frames until the engine stops."""
        return self._engine.frames()

    # -- recording --

    def start_recording(self, base_path: str | os.PathLike) -> RecordingInfo:
        """Start recording accepted frames to ``base_path.mp4`` + ``.meta``.

        Raises RuntimeError if already recording.
        """
        d = self._engine.start_recording(str(base_path))
        return RecordingInfo(**d)

    def stop_recording(self) -> None:
        """Stop the current recording session. No-op if not recording."""
        self._engine.stop_recording()

    def is_recording(self) -> bool:
        """Return whether a recording session is active."""
        return self._engine.is_recording()

    # -- diagnostics --

    def stats(self) -> EngineStats:
        """Return live engine counters."""
        d = self._engine.stats()
        return EngineStats(**d)

    def get_last_error(self) -> str | None:
        """Return the last non-fatal error message, or None."""
        return self._engine.get_last_error()

    def submit_analysis_result(
        self,
        frame_id: int,
        flags: int = 0,
        payload: bytes | None = None,
    ) -> None:
        """Submit an analysis result for a frame (stub in v1)."""
        self._engine.submit_analysis_result(frame_id, flags, payload)
