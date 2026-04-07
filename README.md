# memoir-capture

Windows-native screen capture module with Python bindings for real-time frame analysis and deterministic replay recording.

Memoir captures frames from a window or monitor using Windows Graphics Capture (WGC), delivers them to Python as NumPy arrays, and optionally records them to HEVC video with per-frame metadata — all without GPU-to-CPU roundtrips in the recording path.

## Features

- **WGC capture** — continuous frame capture from any window or monitor
- **NumPy delivery** — BGRA frames as `(H, W, 4)` uint8 arrays via bounded queue
- **Hardware-accelerated recording** — lossless HEVC encoding (YUV 4:4:4) via NVENC, AMF, or software x265 fallback
- **Binary metadata** — `.meta` sidecar with per-frame keyboard state, timestamps, and frame IDs
- **Dynamic recording** — start/stop recording without restarting capture
- **Frame-accurate keyboard** — key state snapshot at the exact moment each frame is accepted
- **Typed Python API** — full type annotations, dataclasses, context managers

## Requirements

- Windows 10 1903+ (for WGC `CreateFreeThreaded`)
- Python 3.10+
- NVIDIA GPU (NVENC), AMD GPU (AMF), or CPU-only (x265 software fallback) for recording
- Visual Studio 2022 (for building from source)

## Installation

### From PyPI (prebuilt)

```
pip install memoir-capture
```

### From source

```powershell
# Clone with vcpkg
git clone https://github.com/lunavod/memoir-capture.git
cd Memoir
git clone https://github.com/microsoft/vcpkg.git vcpkg --depth 1
.\vcpkg\bootstrap-vcpkg.bat -disableMetrics

# Build
pip install build numpy
python -m build --wheel

# Install
pip install dist\memoir_capture-*.whl
```

The first build takes ~15 minutes (vcpkg builds FFmpeg). Subsequent builds use cached binaries.

For local development without installing:

```powershell
.\scripts\build.ps1
# memoir_capture/ package is ready to import from the project root
```

## Quick Start

### Capture frames

```python
import memoir_capture

engine = memoir_capture.CaptureEngine(
    memoir_capture.MonitorTarget(0),    # primary monitor
    max_fps=10.0,
)
engine.start()

for packet in engine.frames():
    with packet:
        img = packet.cpu_bgra           # numpy (H, W, 4) uint8
        print(f"Frame {packet.frame_id}: {img.shape}")
        print(f"Keys: 0x{packet.keyboard_mask:016x}")
    break

engine.stop()
```

### Capture a specific window

```python
engine = memoir_capture.CaptureEngine(
    memoir_capture.WindowTitleTarget(r"(?i)notepad"),
    max_fps=30.0,
)
```

### Record to MP4

```python
engine = memoir_capture.CaptureEngine(
    memoir_capture.MonitorTarget(0),
    max_fps=10.0,
    record_width=1920,
    record_height=1080,
    record_gop=1,           # 1 = all-intra (frame-accurate seeking)
)
engine.start()

info = engine.start_recording("session_001")
print(f"Recording to {info.video_path}")  # session_001.mp4

for i, packet in enumerate(engine.frames()):
    packet.release()
    if i >= 99:
        break

engine.stop_recording()     # finalizes .mp4 + .meta
engine.stop()
```

### Read metadata

```python
meta = memoir_capture.MetaReader.read("session_001.meta")

print(f"Keys tracked: {[k.name for k in meta.keys]}")

for row in meta.rows:
    print(f"Frame {row.frame_id}: keyboard=0x{row.keyboard_mask:016x}")
```

### Write metadata (for synthetic replays)

```python
from memoir_capture import MetaWriter, MetaKeyEntry, MetaRow

keys = [MetaKeyEntry(0, 0x57, "W"), MetaKeyEntry(1, 0x41, "A")]

with MetaWriter("synthetic.meta", keys) as w:
    w.write_row(MetaRow(
        frame_id=0, record_frame_index=0,
        capture_qpc=0, host_accept_qpc=0,
        keyboard_mask=0b01,
        width=1920, height=1080, analysis_stride=7680,
    ))
```

### Context manager

```python
with memoir_capture.CaptureEngine(memoir_capture.MonitorTarget(0)) as engine:
    packet = engine.get_next_frame(timeout_ms=2000)
    if packet:
        with packet:
            process(packet.cpu_bgra)
```

## API Reference

### `CaptureEngine(target, *, max_fps, ...)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target` | required | `MonitorTarget(index)`, `WindowTitleTarget(regex)`, or `WindowExeTarget(regex)` |
| `max_fps` | `10.0` | Maximum accepted frame rate |
| `analysis_queue_capacity` | `1` | Bounded queue size for Python delivery |
| `capture_cursor` | `False` | Include cursor in capture |
| `record_width` | `1920` | Recording output width |
| `record_height` | `1080` | Recording output height |
| `record_gop` | `1` | GOP size (1 = all-intra, higher = smaller files) |

**Methods**: `start()`, `stop()`, `get_next_frame(timeout_ms)`, `frames()`, `start_recording(base_path, *, encoder=None)`, `stop_recording()`, `is_recording()`, `stats()`

### `FramePacket`

| Property | Type | Description |
|----------|------|-------------|
| `frame_id` | `int` | Monotonic ID (only accepted frames get IDs) |
| `cpu_bgra` | `np.ndarray` | `(H, W, 4)` uint8 BGRA pixel data |
| `keyboard_mask` | `int` | 64-bit bitmask of tracked keys |
| `capture_qpc` | `int` | WGC capture timestamp (100ns units) |
| `width`, `height`, `stride` | `int` | Frame dimensions |

Supports `with packet:` (auto-release) and explicit `packet.release()`.

### Recording

Encoding: lossless HEVC (QP=0), YUV 4:4:4, full color range. The encoder is selected automatically in priority order: `hevc_nvenc` (NVIDIA) → `hevc_amf` (AMD) → `libx265` (software). You can force a specific encoder:

```python
info = engine.start_recording("session_001", encoder="libx265")
```

| Setting | File size (10s, 1080p) |
|---------|----------------------|
| GOP=1 (all-intra) | ~52 MB |
| GOP=10 | ~17 MB |
| GOP=30 | ~14 MB |

## Architecture

```
WGC FrameArrived (thread pool)
  │
  ├─ FPS limiter → drop if too soon
  ├─ Queue check → drop if full (drop-new policy)
  │
  ├─ Accept: assign frame_id, snapshot keyboard
  ├─ GPU→CPU: CopyResource → staging → Map → memcpy
  ├─ Recording: swscale (BGRA→YUV444) → HEVC encoder → MP4
  └─ Enqueue → Python consumer
```

- Single `ID3D11DeviceContext` + mutex for all GPU ops
- WGC `CreateFreeThreaded` — no DispatcherQueue needed
- Recording runs on the callback thread (well within budget at 10fps)
- `FramePacket` owns its pixel buffer; `release()` frees it

## Testing

```powershell
# Full suite (requires display + supported GPU or x265)
pytest -v

# Headless (CI-safe)
pytest --headless -v
```

## License

MIT. Links against FFmpeg (LGPL 2.1+).
