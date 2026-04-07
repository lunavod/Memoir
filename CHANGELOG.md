# Changelog

## 0.2.0

### Added
- **Node.js N-API bindings** — new `memoir-node` npm package with synchronous
  blocking API designed for Worker thread tick loops.
- `CaptureEngine` class for Node.js with `getNextFrame()`, `startRecording()`,
  `stopRecording()`, `stats()`, `lastError()`, and split-path recording.
- `FramePacket` with zero-copy Buffer access, BigInt for 64-bit fields.
- Pure TypeScript `.meta` reader/writer (`readMeta`, `writeMeta`) with helpers
  (`isPressed`, `pressedKeys`, `synthesizeKeyEvents`).
- `TestWindow` native helper for integration tests (Win32 window creation).
- Full Node.js test suite (37 tests) with parity to Python tests, including
  color cycle end-to-end verification.
- `README-node.md` with Node.js API documentation, auto-swapped at publish.
- CI job for building, testing, and publishing Node.js package to npm via
  trusted publishing (OIDC).

### Changed
- Refactored `CMakeLists.txt` to compile C++ core as a static library
  (`memoir_core`) shared between Python and Node targets.
- Added `MEMOIR_BUILD_PYTHON` and `MEMOIR_BUILD_NODE` CMake options.
- Added `node` CMake preset to `CMakePresets.json`.

## 0.1.5

### Added
- Encoder fallback chain: automatically selects `hevc_nvenc` → `hevc_amf` →
  `libx265` based on available hardware. Recording no longer requires an
  NVIDIA GPU.
- `encoder` parameter on `start_recording()` to force a specific FFmpeg
  encoder (e.g. `encoder="libx265"` for software encoding).
- `libx265` software encoder bundled via vcpkg/FFmpeg for machines without
  hardware encoding support.
- Test for recording with `libx265` (`test_record_5s_libx265`).

## 0.1.4

### Fixed
- Detect window closure via `IsWindow()` check in `GetNextFrame()` when the
  WGC `Closed` event does not fire. The engine now reliably transitions to
  `Faulted` with error `"Capture target closed"` when the captured window
  is destroyed.

### Added
- Test for window-close detection (`test_window_close.py`).

## 0.1.3

### Added
- `start_recording(path=, video_name=, meta_name=)` overload for placing
  video and metadata files under a directory with separate names.
  Redundant `.mp4`/`.meta` extensions are stripped automatically.
- Syntax sugar for `MetaFile`, `FramePacket`, and engine (sequence protocol,
  key lookup helpers, `save_png`, `on_frame` callback, `grab()` convenience).

## 0.1.2

### Added
- Custom `key_map` parameter for `CaptureEngine` to select which keys are
  tracked in the keyboard bitmask.
- Engine and metadata documentation (`docs/engine.md`).

### Fixed
- Support `(?i)` case-insensitive flag in window regex patterns.

## 0.1.1

### Fixed
- Finalize recording on destructor when engine is faulted.
- CI: skip `cv2` import on headless runners, cache vcpkg on failure.
- CI: fix cache key and `save-always` deprecation issues.

### Changed
- Renamed Python import from `memoir` to `memoir_capture`.
- Renamed PyPI package to `memoir-capture`.

## 0.1.0

### Added
- Initial implementation of Memoir capture/replay module.
- Windows Graphics Capture (WGC) backend with monitor index, window title
  regex, and window exe regex targets.
- Hardware-accelerated HEVC recording via NVENC with `.mp4` + `.meta` output.
- Python bindings via pybind11 with `CaptureEngine`, `FramePacket`, and
  `RecordingInfo` types.
- Typed Python wrapper package with dataclasses for all return values.
- `.meta` binary format with per-frame keyboard bitmask, QPC timestamps,
  and resolution info.
- CI/CD with GitHub Actions, PyPI trusted publishing, and GitHub Releases.
- pytest test suite with `--headless` marker for CI runners.
