# CaptureEngine Guide

## Overview

`CaptureEngine` is the main interface to memoir-capture. It captures frames from a window or monitor, delivers them to Python as NumPy arrays, and optionally records them to HEVC video.

## Creating an Engine

```python
from memoir_capture import CaptureEngine, MonitorTarget, WindowTitleTarget, WindowExeTarget
```

### Capture a monitor

```python
engine = CaptureEngine(MonitorTarget(0))       # primary monitor
engine = CaptureEngine(MonitorTarget(1))       # second monitor
```

### Capture a window by title (regex)

```python
engine = CaptureEngine(WindowTitleTarget(r"(?i)notepad"))
engine = CaptureEngine(WindowTitleTarget(r"(?i)overwatch"))
```

### Capture a window by executable name (regex)

```python
engine = CaptureEngine(WindowExeTarget(r"(?i)chrome\.exe"))
```

### Regex syntax notes

Window title and exe patterns use **C++ ECMAScript regex**, not Python `re`. Most common patterns work the same, but there are differences:

| Feature | Syntax | Supported? |
|---------|--------|------------|
| Case-insensitive | `(?i)` prefix | Yes (stripped and converted to icase flag) |
| Character classes | `[a-z]`, `\d`, `\w`, `\s` | Yes |
| Quantifiers | `+`, `*`, `?`, `{n,m}` | Yes |
| Alternation | `foo\|bar` | Yes |
| Non-capturing group | `(?:...)` | Yes |
| Lookahead | `(?=...)`, `(?!...)` | Yes |
| Lookbehind | `(?<=...)`, `(?<!...)` | **No** |
| Named groups | `(?P<name>...)` | **No** (use `(?:...)` instead) |
| Other inline flags | `(?s)`, `(?m)`, `(?x)` | **No** |
| Unicode categories | `\p{L}` | **No** |

For simple matching (which covers 99% of window targeting), the syntax is identical to Python. If you need advanced features, find the window handle separately and pass a `WindowTitleTarget` with a simple pattern.

## Engine Parameters
```

## Engine Parameters

```python
engine = CaptureEngine(
    MonitorTarget(0),
    max_fps=10.0,               # max accepted frames per second
    analysis_queue_capacity=1,   # frames buffered for Python (1 = latest only)
    capture_cursor=False,        # include mouse cursor in capture
    key_map=None,                # custom keyboard tracking (see below)
    record_width=1920,           # recording output width
    record_height=1080,          # recording output height
    record_gop=1,                # GOP size (1 = all-intra, higher = smaller files)
)
```

### Frame Rate (`max_fps`)

Controls how many frames per second are accepted into the pipeline. Frames arriving faster than this are silently dropped. The actual rate depends on the source — a game running at 60fps with `max_fps=10` will accept ~10 frames and drop ~50 per second.

### Queue Capacity (`analysis_queue_capacity`)

How many accepted frames can wait in the queue for Python to consume. Default is 1, meaning only the most recent frame is available. If Python is slow and the queue is full, new frames are dropped (drop-new policy).

Higher values (e.g., 3-5) let Python fall behind slightly without losing frames, at the cost of increased latency.

### GOP Size (`record_gop`)

Controls the Group of Pictures size for recording:

| GOP | Behavior | File size (10s, 1080p) | Seeking |
|-----|----------|----------------------|---------|
| 1   | Every frame is a keyframe (all-intra) | ~52 MB | Instant random access |
| 10  | Keyframe every 10 frames | ~17 MB | Seek to nearest keyframe |
| 30  | Keyframe every 30 frames | ~14 MB | Seek to nearest keyframe |

Use GOP=1 for deterministic replay where any frame must be independently decodable. Use higher values for debug recordings you'll just watch.

## Lifecycle

### Basic

```python
engine = CaptureEngine(MonitorTarget(0))
engine.start()
# ... use the engine ...
engine.stop()
```

### Context Manager

```python
with CaptureEngine(MonitorTarget(0)) as engine:
    for packet in engine.frames():
        with packet:
            process(packet.cpu_bgra)
        break
```

The engine automatically stops on exit, including when the block raises an exception.

### Engine States

```
Created → Running → Stopping → Stopped
                ↘ Faulted (e.g., window closed)
```

If the captured window closes while running, the engine transitions to `Faulted`. `get_next_frame()` returns `None` and `frames()` stops iterating. Any active recording is finalized when you call `stop()` or the engine is garbage collected.

## Getting Frames

### Blocking iterator (most common)

```python
for packet in engine.frames():
    with packet:
        img = packet.cpu_bgra  # numpy (H, W, 4) uint8, BGRA
        # ... analyze img ...
```

The iterator blocks until a frame is available and stops when the engine stops.

### Manual with timeout

```python
packet = engine.get_next_frame(timeout_ms=500)  # wait up to 500ms
if packet is not None:
    with packet:
        process(packet.cpu_bgra)
```

Timeout values:
- `-1` — block forever
- `0` — non-blocking poll (returns immediately)
- `>0` — wait up to N milliseconds

### FramePacket Properties

| Property | Type | Description |
|----------|------|-------------|
| `frame_id` | `int` | Monotonic ID, only assigned to accepted frames |
| `cpu_bgra` | `np.ndarray` | `(H, W, 4)` uint8 BGRA pixel data |
| `keyboard_mask` | `int` | 64-bit bitmask of tracked keys at capture time |
| `capture_qpc` | `int` | WGC capture timestamp (100-nanosecond units) |
| `host_accept_qpc` | `int` | Host QPC at the moment the frame was accepted |
| `width` | `int` | Frame width in pixels |
| `height` | `int` | Frame height in pixels |
| `stride` | `int` | Row stride in bytes (may be > width × 4 due to alignment) |
| `channels` | `int` | Always 4 (BGRA) |

### Releasing Frames

Frames hold memory. Always release them when done:

```python
# Option 1: context manager (recommended)
with packet:
    use(packet.cpu_bgra)

# Option 2: explicit release
packet.release()
```

Accessing `cpu_bgra` after release raises `ValueError`. Double release is safe (no-op).

## Recording

### Start and stop

```python
info = engine.start_recording("recordings/session_001")
# info.video_path = "recordings/session_001.mp4"
# info.meta_path  = "recordings/session_001.meta"

# ... frames are captured and recorded simultaneously ...

engine.stop_recording()
```

Recording can be started and stopped while capture continues. Only accepted frames (the ones delivered to Python) are recorded.

### Recording quality

Default encoding: **lossless HEVC** (QP=0, YUV 4:4:4, full color range, NVENC hardware).

The recording path: captured BGRA → swscale (resize + BGRA→YUV444) → hevc_nvenc (GPU encode) → MP4 mux.

### Multiple sessions

```python
engine.start_recording("session_001")
# ... record some frames ...
engine.stop_recording()

engine.start_recording("session_002")
# ... record more frames ...
engine.stop_recording()
```

Each session produces its own `.mp4` + `.meta` pair. Frame IDs continue incrementing across sessions (they're global to the engine lifetime).

### Checking state

```python
engine.is_recording()      # True/False
engine.stats()             # EngineStats with frames_recorded count
engine.get_last_error()    # error string if recording failed, else None
```

## Keyboard Tracking

Every accepted frame includes a `keyboard_mask` — a 64-bit bitmask snapshot of which tracked keys were pressed at the exact moment the frame was accepted.

### Default key map (40 keys)

| Bits | Keys |
|------|------|
| 0-3 | W, A, S, D |
| 4-7 | Up, Down, Left, Right |
| 8-11 | Space, LShift, LCtrl, LAlt |
| 12-21 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 0 |
| 22-23 | Tab, Escape |
| 24-29 | Q, E, R, F, G, Z |
| 30-32 | X, C, V |
| 33-34 | Enter, Backspace |
| 35-39 | F1, F2, F3, F4, F5 |

### Custom key map

```python
from memoir_capture import MetaKeyEntry

# Track only WASD and Space
keys = [
    MetaKeyEntry(bit_index=0, virtual_key=0x57, name="W"),
    MetaKeyEntry(bit_index=1, virtual_key=0x41, name="A"),
    MetaKeyEntry(bit_index=2, virtual_key=0x53, name="S"),
    MetaKeyEntry(bit_index=3, virtual_key=0x44, name="D"),
    MetaKeyEntry(bit_index=4, virtual_key=0x20, name="Space"),
]

engine = CaptureEngine(MonitorTarget(0), key_map=keys)
```

`virtual_key` is a [Windows virtual-key code](https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes). `bit_index` is the position in the 64-bit mask (0-63).

### Reading the mask

```python
mask = packet.keyboard_mask
w_pressed = bool(mask & (1 << 0))
space_pressed = bool(mask & (1 << 4))
```

## Statistics

```python
stats = engine.stats()
```

Returns an `EngineStats` dataclass:

| Field | Description |
|-------|-------------|
| `frames_seen` | Total frames delivered by WGC |
| `frames_accepted` | Frames that passed FPS + queue checks |
| `frames_dropped_queue_full` | Dropped because Python was behind |
| `frames_dropped_internal_error` | Dropped due to GPU/readback errors |
| `frames_recorded` | Frames written to the current recording |
| `python_queue_depth` | Frames currently waiting in the queue |
| `recording_active` | Whether a recording session is running |

## Threading

The GIL is released during all blocking operations (`start`, `stop`, `get_next_frame`, `start_recording`, `stop_recording`). Frame capture and recording happen on a background thread and never block Python.

It is safe to call `engine.stop()` from a different thread than the one consuming frames — the blocked `get_next_frame()` will return `None`.
