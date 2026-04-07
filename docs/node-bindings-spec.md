# memoir-node: N-API Bindings Specification

This document specifies the Node.js N-API bindings for the memoir-capture C++ library. The agent reading this is expected to be familiar with the existing codebase — the C++ core headers, the pybind11 bindings in `src/bindings/module.cpp`, and the Python wrapper layer in `memoir_capture/`.

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Target Node.js API](#2-target-nodejs-api)
3. [N-API Binding Implementation](#3-n-api-binding-implementation)
4. [Meta Reader/Writer (Pure TypeScript)](#4-meta-readerwriter-pure-typescript)
5. [Build System](#5-build-system)
6. [Consumer Architecture](#6-consumer-architecture)
7. [Testing Strategy](#7-testing-strategy)

---

## 1. Design Principles

1. **Synchronous blocking API** — The consumer is a Worker thread running a tick loop. `getNextFrame()` blocks until a frame arrives. No Promises on the hot path.
2. **Buffer for pixel data** — Use `napi_create_external_buffer` to wrap `pixel_data` without copying. The buffer holds a reference preventing GC of the underlying C++ memory.
3. **BigInt for 64-bit values** — `keyboard_mask`, `capture_qpc`, `host_accept_qpc` are 64-bit. Use BigInt to avoid precision loss.
4. **No iterator/generator** — Use a `while` loop with `getNextFrame()` instead.
5. **Meta reader/writer in pure TypeScript** — The `.meta` format is simple packed structs. No native dependency needed.

### What NOT to Port from Python

- `frames()` iterator — not needed. Use `while` loop with `getNextFrame()`.
- `on_frame(callback)` — the consumer manages its own loop.
- `submit_analysis_result()` — stub in Python, skip entirely.
- `save_png()` — Python convenience, not needed in Node.
- `grab()` — implement as a pure TypeScript wrapper if desired, not in C++.
- Context manager (`__enter__`/`__exit__`) — no JS equivalent needed; the consumer explicitly calls `start()`/`stop()`.
- `MetaFile` helper methods (`rows_where`, `time_range`, `concat`, `mask_from_names`, `duration_sec`) — the Python version has extensive sugar; only port `isPressed`, `pressedKeys`, and `synthesizeKeyEvents` as standalone functions.

---

## 2. Target Node.js API

### 2.1 Package Exports

The npm package `memoir-node` exports:

```typescript
// Native addon
export { CaptureEngine } from './native'

// Pure TypeScript
export { readMeta, writeMeta } from './meta'

// Types (all exported)
export {
  CaptureTarget,
  MonitorTarget,
  WindowTitleTarget,
  WindowExeTarget,
  KeySpec,
  EngineOptions,
  FramePacket,
  RecordingInfo,
  EngineStats,
  MetaHeader,
  MetaKeyEntry,
  MetaRow,
  MetaFile,
} from './types'

export function ping(): string
export const version: string
```

### 2.2 TypeScript Type Definitions

```typescript
// ─── Capture Targets ────────────────────────────────────────────

interface MonitorTarget {
  type: 'monitor'
  index: number  // 0 = primary monitor
}

interface WindowTitleTarget {
  type: 'windowTitle'
  pattern: string  // regex, supports (?i) prefix for case-insensitive
}

interface WindowExeTarget {
  type: 'windowExe'
  pattern: string  // regex matching exe filename
}

type CaptureTarget = MonitorTarget | WindowTitleTarget | WindowExeTarget

// ─── Key Tracking ───────────────────────────────────────────────

interface KeySpec {
  bit: number     // 0-63, bit position in keyboard_mask
  vk: number      // Windows virtual key code (e.g. 0x09 for Tab)
  name: string    // display name, max 31 ASCII chars
}

// ─── Engine Options ─────────────────────────────────────────────

interface EngineOptions {
  target: CaptureTarget
  maxFps?: number              // default: 10.0
  queueCapacity?: number       // default: 1 (bounded analysis queue)
  captureCursor?: boolean      // default: false
  keys?: KeySpec[]             // default: 40-key gaming set
  recordWidth?: number         // default: 1920
  recordHeight?: number        // default: 1080
  recordGop?: number           // default: 1 (all-intra)
}

// ─── Frame Packet ───────────────────────────────────────────────

interface FramePacket {
  readonly frameId: number           // monotonic, fits in JS safe integer range
  readonly width: number
  readonly height: number
  readonly stride: number            // row pitch in bytes (>= width * 4)
  readonly captureQpc: bigint        // WGC timestamp, 100ns units
  readonly hostAcceptQpc: bigint     // host QPC when accepted
  readonly keyboardMask: bigint      // 64-bit key state bitmask
  readonly data: Buffer              // BGRA pixels, length = stride * height

  release(): void                    // frees pixel memory, data becomes empty
  readonly released: boolean
}

// ─── Recording ──────────────────────────────────────────────────

interface RecordingInfo {
  basePath: string
  videoPath: string
  metaPath: string
  codec: string        // e.g. "hevc_nvenc", "hevc_amf", "libx265"
  width: number
  height: number
}

// ─── Stats ──────────────────────────────────────────────────────

interface EngineStats {
  framesSeen: number
  framesAccepted: number
  framesDroppedQueueFull: number
  framesDroppedError: number
  framesRecorded: number
  queueDepth: number
  recording: boolean
}
```

### 2.3 CaptureEngine API

```typescript
declare class CaptureEngine {
  /**
   * Create a capture engine.
   *
   * Does NOT start capture — call start() to begin.
   */
  constructor(options: EngineOptions)

  /**
   * Initialize D3D11, create WGC session, start capturing.
   * Throws if target window/monitor not found.
   */
  start(): void

  /**
   * Stop capture and any active recording.
   * Releases D3D resources. Can be restarted with start().
   */
  stop(): void

  /**
   * Block until the next frame is available.
   *
   * @param timeoutMs  -1 = block forever (default), 0 = poll, >0 = wait N ms
   * @returns FramePacket, or null on timeout / engine stopped
   *
   * IMPORTANT: This is a synchronous blocking call. Only use in a Worker thread.
   * The underlying C++ waits on a condition variable — the thread sleeps
   * without burning CPU.
   */
  getNextFrame(timeoutMs?: number): FramePacket | null

  /**
   * Start recording accepted frames to HEVC MP4 + binary .meta sidecar.
   *
   * @param basePath  Base path without extension — creates basePath.mp4 + basePath.meta
   * @param encoder   Force specific encoder: "hevc_nvenc", "hevc_amf", "libx265".
   *                  Default: auto-detect best available.
   * @returns Recording info with resolved paths and selected codec.
   * @throws If already recording or engine not running.
   */
  startRecording(basePath: string, encoder?: string): RecordingInfo

  /**
   * Start recording with explicit separate paths for video and meta files.
   *
   * @param opts.path       Directory for output files
   * @param opts.videoName  Video filename (without .mp4 extension)
   * @param opts.metaName   Meta filename (without .meta extension)
   * @param opts.encoder    Optional encoder override
   */
  startRecording(opts: {
    path: string
    videoName: string
    metaName: string
    encoder?: string
  }): RecordingInfo

  /**
   * Stop and finalize the current recording session.
   * Flushes the HEVC encoder and writes the MP4 trailer.
   * No-op if not recording.
   */
  stopRecording(): void

  /** Whether a recording session is active. */
  isRecording(): boolean

  /** Live engine counters. */
  stats(): EngineStats

  /** Last non-fatal error message, or null. */
  lastError(): string | null
}
```

### 2.4 Module-level Functions

```typescript
/**
 * Capture a single frame and return it.
 * Creates a temporary engine, grabs one frame, stops.
 */
declare function grab(
  target: CaptureTarget,
  opts?: { timeoutMs?: number; maxFps?: number }
): FramePacket

/** Health check — returns "memoir-node X.Y.Z loaded OK" */
declare function ping(): string

/** Library version string */
declare const version: string
```

---

## 3. N-API Binding Implementation

### 3.1 File to Create

Create `src/bindings/node_module.cpp` alongside the existing `module.cpp` (which stays for Python).

Use `node-addon-api` (the C++ wrapper for N-API). Include via:
```cpp
#include <napi.h>
```

### 3.2 FramePacket Wrapping

**Strategy:** Wrap `std::shared_ptr<FramePacket>` in a custom `Napi::ObjectWrap` subclass.

```cpp
class JsFramePacket : public Napi::ObjectWrap<JsFramePacket> {
    std::shared_ptr<memoir::FramePacket> pkt_;

    // Constructor ref for creating instances from C++
    static Napi::FunctionReference constructor;

public:
    static Napi::Object Init(Napi::Env env, Napi::Object exports) {
        Napi::Function func = DefineClass(env, "FramePacket", {
            InstanceAccessor<&JsFramePacket::GetFrameId>("frameId"),
            InstanceAccessor<&JsFramePacket::GetWidth>("width"),
            InstanceAccessor<&JsFramePacket::GetHeight>("height"),
            InstanceAccessor<&JsFramePacket::GetStride>("stride"),
            InstanceAccessor<&JsFramePacket::GetCaptureQpc>("captureQpc"),
            InstanceAccessor<&JsFramePacket::GetHostAcceptQpc>("hostAcceptQpc"),
            InstanceAccessor<&JsFramePacket::GetKeyboardMask>("keyboardMask"),
            InstanceAccessor<&JsFramePacket::GetData>("data"),
            InstanceAccessor<&JsFramePacket::GetReleased>("released"),
            InstanceMethod<&JsFramePacket::Release>("release"),
        });
        constructor = Napi::Persistent(func);
        constructor.SuppressDestruct();
        exports.Set("FramePacket", func);
        return exports;
    }

    // Factory: create JsFramePacket from C++ shared_ptr
    static Napi::Object NewInstance(Napi::Env env,
                                     std::shared_ptr<memoir::FramePacket> pkt) {
        Napi::Object obj = constructor.New({});
        auto* wrapper = Napi::ObjectWrap<JsFramePacket>::Unwrap(obj);
        wrapper->pkt_ = std::move(pkt);
        return obj;
    }

    // JS constructor (for internal use only — no direct construction from JS)
    JsFramePacket(const Napi::CallbackInfo& info)
        : Napi::ObjectWrap<JsFramePacket>(info) {}

    // Property getters
    Napi::Value GetFrameId(const Napi::CallbackInfo& info);
    Napi::Value GetWidth(const Napi::CallbackInfo& info);
    Napi::Value GetHeight(const Napi::CallbackInfo& info);
    Napi::Value GetStride(const Napi::CallbackInfo& info);
    Napi::Value GetCaptureQpc(const Napi::CallbackInfo& info);
    Napi::Value GetHostAcceptQpc(const Napi::CallbackInfo& info);
    Napi::Value GetKeyboardMask(const Napi::CallbackInfo& info);
    Napi::Value GetData(const Napi::CallbackInfo& info);
    Napi::Value GetReleased(const Napi::CallbackInfo& info);

    void Release(const Napi::CallbackInfo& info);
};
```

**Critical: Buffer creation for pixel data.**

Use `Napi::Buffer<uint8_t>::New()` with an external data pointer:

```cpp
Napi::Value JsFramePacket::GetData(const Napi::CallbackInfo& info) {
    if (pkt_->IsReleased()) {
        Napi::TypeError::New(info.Env(), "Packet already released")
            .ThrowAsJavaScriptException();
        return info.Env().Undefined();
    }

    // Create Buffer pointing at the packet's pixel_data.
    // The shared_ptr copy prevents the C++ memory from being freed
    // while the JS Buffer exists.
    auto ref = new std::shared_ptr<memoir::FramePacket>(pkt_);
    return Napi::Buffer<uint8_t>::New(
        info.Env(),
        pkt_->pixel_data.data(),
        pkt_->pixel_data.size(),
        [](Napi::Env, uint8_t*, std::shared_ptr<memoir::FramePacket>* ref) {
            delete ref;
        },
        ref
    );
}
```

This gives **zero-copy** access: the Buffer's data pointer points directly at the C++ vector's storage. The shared_ptr prevents premature deallocation.

**BigInt properties:**

```cpp
Napi::Value JsFramePacket::GetKeyboardMask(const Napi::CallbackInfo& info) {
    return Napi::BigInt::New(info.Env(),
        static_cast<uint64_t>(pkt_->keyboard_mask));
}

Napi::Value JsFramePacket::GetCaptureQpc(const Napi::CallbackInfo& info) {
    // capture_qpc is int64_t (signed)
    return Napi::BigInt::New(info.Env(),
        static_cast<int64_t>(pkt_->capture_qpc));
}
```

**`frameId` as Number:** Frame IDs are sequential from 0, unlikely to exceed 2^53 in a single session (that's 28 million years at 10 FPS). Use `Napi::Number`.

### 3.3 CaptureEngine Wrapping

Wrap `memoir::CaptureEngine` in a `Napi::ObjectWrap` subclass.

**Constructor — parsing EngineOptions:**

```cpp
JsCaptureEngine::JsCaptureEngine(const Napi::CallbackInfo& info)
    : Napi::ObjectWrap<JsCaptureEngine>(info) {

    Napi::Object opts = info[0].As<Napi::Object>();
    memoir::EngineConfig cfg;

    // Parse target
    Napi::Object target = opts.Get("target").As<Napi::Object>();
    std::string type = target.Get("type").As<Napi::String>().Utf8Value();

    if (type == "monitor") {
        cfg.target.type = memoir::CaptureTargetType::MonitorIndex;
        cfg.target.monitor_index = target.Get("index").As<Napi::Number>().Int32Value();
    } else if (type == "windowTitle") {
        cfg.target.type = memoir::CaptureTargetType::WindowTitleRegex;
        std::string s = target.Get("pattern").As<Napi::String>().Utf8Value();
        cfg.target.value_wstr = std::wstring(s.begin(), s.end());
    } else if (type == "windowExe") {
        cfg.target.type = memoir::CaptureTargetType::WindowExeRegex;
        std::string s = target.Get("pattern").As<Napi::String>().Utf8Value();
        cfg.target.value_wstr = std::wstring(s.begin(), s.end());
    }

    // Parse optional fields
    if (opts.Has("maxFps"))
        cfg.max_fps = opts.Get("maxFps").As<Napi::Number>().DoubleValue();
    if (opts.Has("queueCapacity"))
        cfg.analysis_queue_capacity = opts.Get("queueCapacity").As<Napi::Number>().Uint32Value();
    if (opts.Has("captureCursor"))
        cfg.capture_cursor = opts.Get("captureCursor").As<Napi::Boolean>().Value();
    if (opts.Has("recordWidth"))
        cfg.record_width = opts.Get("recordWidth").As<Napi::Number>().Uint32Value();
    if (opts.Has("recordHeight"))
        cfg.record_height = opts.Get("recordHeight").As<Napi::Number>().Uint32Value();
    if (opts.Has("recordGop"))
        cfg.record_gop = opts.Get("recordGop").As<Napi::Number>().Uint32Value();

    // Parse key map
    if (opts.Has("keys") && !opts.Get("keys").IsUndefined()) {
        Napi::Array keys = opts.Get("keys").As<Napi::Array>();
        for (uint32_t i = 0; i < keys.Length(); i++) {
            Napi::Object k = keys.Get(i).As<Napi::Object>();
            memoir::KeySpec ks{};
            ks.bit_index = k.Get("bit").As<Napi::Number>().Uint32Value();
            ks.virtual_key = k.Get("vk").As<Napi::Number>().Uint32Value();
            std::string name = k.Get("name").As<Napi::String>().Utf8Value();
            strncpy_s(ks.name, sizeof(ks.name), name.c_str(), _TRUNCATE);
            cfg.key_map.push_back(ks);
        }
    }

    engine_ = std::make_unique<memoir::CaptureEngine>(cfg);
}
```

**GetNextFrame — synchronous blocking call:**

```cpp
Napi::Value JsCaptureEngine::GetNextFrame(const Napi::CallbackInfo& info) {
    int timeout_ms = -1;
    if (info.Length() > 0 && !info[0].IsUndefined())
        timeout_ms = info[0].As<Napi::Number>().Int32Value();

    // This blocks the calling thread. That's intentional — the consumer
    // is a Worker thread. N-API has no GIL, so other threads are unaffected.
    auto pkt = engine_->GetNextFrame(timeout_ms);

    if (!pkt) return info.Env().Null();

    return JsFramePacket::NewInstance(info.Env(), pkt);
}
```

**Important:** Unlike the Python bindings, there is NO GIL to release. The blocking `GetNextFrame` simply blocks the calling thread. This is safe because:
- The consumer runs in a Worker thread (not the main V8 thread)
- N-API allows blocking calls from any thread
- Other Worker threads and the main thread continue executing

**StartRecording — handling two calling conventions:**

```cpp
Napi::Value JsCaptureEngine::StartRecording(const Napi::CallbackInfo& info) {
    memoir::RecordingInfo ri;

    if (info[0].IsString()) {
        // startRecording(basePath, encoder?)
        std::string basePath = info[0].As<Napi::String>().Utf8Value();
        std::string encoder;
        if (info.Length() > 1 && info[1].IsString())
            encoder = info[1].As<Napi::String>().Utf8Value();
        ri = engine_->StartRecording(basePath, encoder);
    } else {
        // startRecording({ path, videoName, metaName, encoder? })
        Napi::Object opts = info[0].As<Napi::Object>();
        std::string path = opts.Get("path").As<Napi::String>().Utf8Value();
        std::string videoName = opts.Get("videoName").As<Napi::String>().Utf8Value();
        std::string metaName = opts.Get("metaName").As<Napi::String>().Utf8Value();
        std::string encoder;
        if (opts.Has("encoder") && !opts.Get("encoder").IsUndefined())
            encoder = opts.Get("encoder").As<Napi::String>().Utf8Value();

        // Strip redundant extensions (matching Python behavior)
        if (videoName.size() > 4 && videoName.substr(videoName.size()-4) == ".mp4")
            videoName = videoName.substr(0, videoName.size()-4);
        if (metaName.size() > 5 && metaName.substr(metaName.size()-5) == ".meta")
            metaName = metaName.substr(0, metaName.size()-5);

        std::string videoPath = path + "/" + videoName + ".mp4";
        std::string metaPath = path + "/" + metaName + ".meta";
        ri = engine_->StartRecording(path, videoPath, metaPath, encoder);
    }

    // Return RecordingInfo as plain object
    Napi::Object result = Napi::Object::New(info.Env());
    result.Set("basePath", ri.base_path);
    result.Set("videoPath", ri.video_path);
    result.Set("metaPath", ri.meta_path);
    result.Set("codec", ri.codec);
    result.Set("width", ri.width);
    result.Set("height", ri.height);
    return result;
}
```

**Stats:**

```cpp
Napi::Value JsCaptureEngine::Stats(const Napi::CallbackInfo& info) {
    auto s = engine_->GetStats();
    Napi::Object obj = Napi::Object::New(info.Env());
    obj.Set("framesSeen", Napi::Number::New(info.Env(), static_cast<double>(s.frames_seen)));
    obj.Set("framesAccepted", Napi::Number::New(info.Env(), static_cast<double>(s.frames_accepted)));
    obj.Set("framesDroppedQueueFull", Napi::Number::New(info.Env(), static_cast<double>(s.frames_dropped_queue_full)));
    obj.Set("framesDroppedError", Napi::Number::New(info.Env(), static_cast<double>(s.frames_dropped_internal_error)));
    obj.Set("framesRecorded", Napi::Number::New(info.Env(), static_cast<double>(s.frames_recorded)));
    obj.Set("queueDepth", s.python_queue_depth);
    obj.Set("recording", s.recording_active);
    return obj;
}
```

### 3.4 Module Initialization

```cpp
Napi::Object Init(Napi::Env env, Napi::Object exports) {
    JsFramePacket::Init(env, exports);
    JsCaptureEngine::Init(env, exports);

    exports.Set("version", Napi::String::New(env, MEMOIR_VERSION_STRING));
    exports.Set("ping", Napi::Function::New(env, [](const Napi::CallbackInfo& info) {
        return Napi::String::New(info.Env(),
            std::string("memoir-node ") + MEMOIR_VERSION_STRING + " loaded OK");
    }));

    return exports;
}

NODE_API_MODULE(memoir_node, Init)
```

### 3.5 Error Handling

All C++ exceptions from the memoir core should be caught and converted to JS exceptions:

```cpp
void JsCaptureEngine::Start(const Napi::CallbackInfo& info) {
    try {
        engine_->Start();
    } catch (const std::exception& e) {
        Napi::Error::New(info.Env(), e.what()).ThrowAsJavaScriptException();
    }
}
```

Apply this pattern to `start()`, `stop()`, `getNextFrame()`, `startRecording()`, `stopRecording()`.

---

## 4. Meta Reader/Writer (Pure TypeScript)

The `.meta` binary format is simple enough to handle in pure TypeScript. This avoids requiring the native addon just for replay/analysis tools.

### 4.1 Binary Format

All values are little-endian. `#pragma pack(push, 1)` in the C++ structs — no padding.

**File structure:**
```
[Header: 32 bytes]
[Key entries: 40 bytes each × key_count]
[Row entries: 56 bytes each × N (until EOF)]
```

**Header (32 bytes):**
```
Offset  Size  Type      Field
0       8     char[8]   magic = "RCMETA1\0"
8       4     uint32    version = 1
12      4     uint32    reserved0 = 0
16      8     uint64    created_unix_ns
24      4     uint32    key_count
28      4     uint32    reserved1 = 0
```

**Key Entry (40 bytes):**
```
Offset  Size  Type      Field
0       4     uint32    bit_index
4       4     uint32    virtual_key
8       32    char[32]  name (null-padded ASCII)
```

**Row Entry (56 bytes):**

Matches Python struct format `"<QQ qq Q II II"` = 2×uint64 + 2×int64 + 1×uint64 + 4×uint32 = 56 bytes.

```
Offset  Size  Type      Field
0       8     uint64    frame_id
8       8     uint64    record_frame_index
16      8     int64     capture_qpc
24      8     int64     host_accept_qpc
32      8     uint64    keyboard_mask
40      4     uint32    width
44      4     uint32    height
48      4     uint32    analysis_stride
52      4     uint32    flags
```

### 4.2 TypeScript Types

```typescript
interface MetaHeader {
  version: number
  createdUnixNs: bigint
  keyCount: number
}

interface MetaKeyEntry {
  bit: number     // bit_index
  vk: number      // virtual_key
  name: string    // decoded ASCII name
}

interface MetaRow {
  frameId: bigint
  recordFrameIndex: bigint
  captureQpc: bigint
  hostAcceptQpc: bigint
  keyboardMask: bigint
  width: number
  height: number
  analysisStride: number
  flags: number
}

interface MetaFile {
  header: MetaHeader
  keys: MetaKeyEntry[]
  rows: MetaRow[]
}
```

### 4.3 Implementation Sketch

```typescript
import { readFileSync, writeFileSync } from 'fs'

const HEADER_SIZE = 32
const KEY_SIZE = 40
const ROW_SIZE = 56
const MAGIC = Buffer.from('RCMETA1\x00', 'ascii')

export function readMeta(path: string): MetaFile {
  const buf = readFileSync(path)
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)

  // Header
  const magic = buf.subarray(0, 8)
  if (!magic.equals(MAGIC)) throw new Error(`Bad magic: ${magic.toString('hex')}`)
  const version = view.getUint32(8, true)
  const createdUnixNs = view.getBigUint64(16, true)
  const keyCount = view.getUint32(24, true)

  // Keys
  let offset = HEADER_SIZE
  const keys: MetaKeyEntry[] = []
  for (let i = 0; i < keyCount; i++) {
    const bit = view.getUint32(offset, true)
    const vk = view.getUint32(offset + 4, true)
    const nameBytes = buf.subarray(offset + 8, offset + 40)
    const nullIdx = nameBytes.indexOf(0)
    const name = nameBytes.subarray(0, nullIdx === -1 ? 32 : nullIdx).toString('ascii')
    keys.push({ bit, vk, name })
    offset += KEY_SIZE
  }

  // Rows
  const rows: MetaRow[] = []
  while (offset + ROW_SIZE <= buf.length) {
    rows.push({
      frameId: view.getBigUint64(offset, true),
      recordFrameIndex: view.getBigUint64(offset + 8, true),
      captureQpc: view.getBigInt64(offset + 16, true),
      hostAcceptQpc: view.getBigInt64(offset + 24, true),
      keyboardMask: view.getBigUint64(offset + 32, true),
      width: view.getUint32(offset + 40, true),
      height: view.getUint32(offset + 44, true),
      analysisStride: view.getUint32(offset + 48, true),
      flags: view.getUint32(offset + 52, true),
    })
    offset += ROW_SIZE
  }

  return {
    header: { version, createdUnixNs, keyCount },
    keys,
    rows,
  }
}

export function writeMeta(
  path: string,
  keys: MetaKeyEntry[],
  rows: MetaRow[],
  createdUnixNs?: bigint,
): void {
  const size = HEADER_SIZE + keys.length * KEY_SIZE + rows.length * ROW_SIZE
  const buf = Buffer.alloc(size)
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)

  // Header
  MAGIC.copy(buf, 0)
  view.setUint32(8, 1, true)  // version
  view.setBigUint64(16, createdUnixNs ?? BigInt(Date.now()) * 1000000n, true)
  view.setUint32(24, keys.length, true)

  // Keys
  let offset = HEADER_SIZE
  for (const k of keys) {
    view.setUint32(offset, k.bit, true)
    view.setUint32(offset + 4, k.vk, true)
    buf.write(k.name.substring(0, 31), offset + 8, 'ascii')
    offset += KEY_SIZE
  }

  // Rows
  for (const r of rows) {
    view.setBigUint64(offset, r.frameId, true)
    view.setBigUint64(offset + 8, r.recordFrameIndex, true)
    view.setBigInt64(offset + 16, r.captureQpc, true)
    view.setBigInt64(offset + 24, r.hostAcceptQpc, true)
    view.setBigUint64(offset + 32, r.keyboardMask, true)
    view.setUint32(offset + 40, r.width, true)
    view.setUint32(offset + 44, r.height, true)
    view.setUint32(offset + 48, r.analysisStride, true)
    view.setUint32(offset + 52, r.flags, true)
    offset += ROW_SIZE
  }

  writeFileSync(path, buf)
}
```

### 4.4 Helper Utilities

```typescript
/** Check if a key was pressed in a given row */
export function isPressed(row: MetaRow, keyName: string, keys: MetaKeyEntry[]): boolean {
  const key = keys.find(k => k.name === keyName)
  if (!key) throw new Error(`Key "${keyName}" not in key map`)
  return (row.keyboardMask & (1n << BigInt(key.bit))) !== 0n
}

/** Get list of pressed key names for a row */
export function pressedKeys(row: MetaRow, keys: MetaKeyEntry[]): string[] {
  return keys.filter(k => (row.keyboardMask & (1n << BigInt(k.bit))) !== 0n).map(k => k.name)
}

/** Synthesize key events from consecutive rows (for replay) */
export function synthesizeKeyEvents(
  rows: MetaRow[],
  keys: MetaKeyEntry[],
): Array<{ frame: bigint; type: 'keyDown' | 'keyUp'; key: string }> {
  const events: Array<{ frame: bigint; type: 'keyDown' | 'keyUp'; key: string }> = []
  let prevMask = 0n

  for (const row of rows) {
    const diff = row.keyboardMask ^ prevMask
    if (diff !== 0n) {
      for (const k of keys) {
        const bit = 1n << BigInt(k.bit)
        if ((diff & bit) !== 0n) {
          events.push({
            frame: row.recordFrameIndex,
            type: (row.keyboardMask & bit) !== 0n ? 'keyDown' : 'keyUp',
            key: k.name,
          })
        }
      }
    }
    prevMask = row.keyboardMask
  }

  return events
}
```

---

## 5. Build System

### 5.1 Dual-Target Build (Python + Node from one repo)

The C++ core is cleanly separated from the binding layer. The build system should support both Python (pybind11) and Node (N-API) targets from the same repository, compiling the core once as a static library.

**CMakeLists.txt approach:**

```cmake
cmake_minimum_required(VERSION 3.20)
project(memoir-capture VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(MEMOIR_BUILD_PYTHON "Build Python bindings (pybind11)" OFF)
option(MEMOIR_BUILD_NODE   "Build Node.js bindings (N-API)"   OFF)

find_package(cppwinrt CONFIG REQUIRED)
find_package(FFMPEG REQUIRED)

# ── Shared core (static lib, compiled once) ──────────────────────

add_library(memoir_core STATIC
    src/core/capture_engine.cpp
    src/core/keyboard.cpp
    src/core/window_finder.cpp
    src/recording/recording_session.cpp
)

target_include_directories(memoir_core PUBLIC
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/src
    ${FFMPEG_INCLUDE_DIRS}
)

target_link_libraries(memoir_core PUBLIC
    Microsoft::CppWinRT
    d3d11
    dxgi
    windowsapp
    ${FFMPEG_LIBRARIES}
)

target_compile_definitions(memoir_core PUBLIC NOMINMAX)

if(MSVC)
    target_compile_options(memoir_core PRIVATE /bigobj)
endif()

# ── Python target (conditional) ──────────────────────────────────

if(MEMOIR_BUILD_PYTHON)
    find_package(pybind11 CONFIG REQUIRED)
    pybind11_add_module(_native src/bindings/module.cpp)
    target_link_libraries(_native PRIVATE memoir_core)

    install(TARGETS _native LIBRARY DESTINATION memoir_capture)
    # FFmpeg DLL copy for Python (existing logic)
    file(GLOB _FFMPEG_DLLS
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/av*.dll"
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/sw*.dll"
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/libx265.dll"
    )
    install(FILES ${_FFMPEG_DLLS} DESTINATION memoir_capture)
endif()

# ── Node target (conditional) ────────────────────────────────────

if(MEMOIR_BUILD_NODE)
    # cmake-js provides CMAKE_JS_INC and CMAKE_JS_LIB
    include_directories(${CMAKE_JS_INC})

    # node-addon-api headers
    execute_process(
        COMMAND node -p "require('node-addon-api').include_dir"
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        OUTPUT_VARIABLE NODE_ADDON_API_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )

    add_library(memoir_node SHARED src/bindings/node_module.cpp)

    set_target_properties(memoir_node PROPERTIES PREFIX "" SUFFIX ".node")

    target_include_directories(memoir_node PRIVATE ${NODE_ADDON_API_DIR})

    target_link_libraries(memoir_node PRIVATE
        memoir_core
        ${CMAKE_JS_LIB}
    )

    target_compile_definitions(memoir_node PRIVATE
        NAPI_VERSION=8
        NODE_ADDON_API_DISABLE_DEPRECATED
    )

    # Copy FFmpeg DLLs next to .node
    file(GLOB _FFMPEG_DLLS
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/av*.dll"
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/sw*.dll"
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/libx265.dll"
    )
    add_custom_command(TARGET memoir_node POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${_FFMPEG_DLLS} $<TARGET_FILE_DIR:memoir_node>
    )
endif()
```

**Build commands:**
```bash
# Python only (existing workflow, unchanged)
pip install build && python -m build --wheel

# Node only
npx cmake-js build --CDMEMOIR_BUILD_NODE=ON

# Both (dev)
cmake --preset default -DMEMOIR_BUILD_PYTHON=ON -DMEMOIR_BUILD_NODE=ON
cmake --build build --preset release
```

No conflicts — pybind11 and node-addon-api don't interact, and the core compiles identically for both. Both targets use the same vcpkg triplet (x64-windows-release).

### 5.2 vcpkg.json Changes

Remove `pybind11` from required deps (it's only needed for the Python target, and scikit-build-core adds it). Keep it as a feature:

```json
{
  "name": "memoir",
  "version": "0.1.0",
  "dependencies": [
    "cppwinrt",
    {
      "name": "ffmpeg",
      "features": ["avcodec", "avformat", "swscale", "nvcodec", "x265"]
    }
  ],
  "features": {
    "python": {
      "description": "Python bindings",
      "dependencies": ["pybind11"]
    }
  }
}
```

### 5.3 Node Package Structure

The Node package lives in a `node/` subdirectory or as a thin wrapper at the repo root:

```
memoir-capture/           # existing repo root
├── include/memoir/       # shared C++ headers
├── src/
│   ├── bindings/
│   │   ├── module.cpp        # Python (existing)
│   │   └── node_module.cpp   # Node (new)
│   ├── core/
│   └── recording/
├── memoir_capture/       # Python package (existing)
├── lib/                  # TypeScript source (new)
│   ├── index.ts
│   ├── types.ts
│   ├── meta.ts
│   └── native.ts         # Native addon loader + TS wrapper
├── CMakeLists.txt        # unified dual-target build
├── package.json          # Node package config (new)
├── tsconfig.json         # (new)
├── pyproject.toml        # Python package config (existing)
└── vcpkg.json
```

### 5.4 package.json

```json
{
  "name": "memoir-node",
  "version": "0.1.0",
  "description": "Windows-native screen capture with Node.js bindings",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {
    "install": "cmake-js compile --CDMEMOIR_BUILD_NODE=ON",
    "build": "cmake-js build --CDMEMOIR_BUILD_NODE=ON && tsc",
    "rebuild": "cmake-js rebuild --CDMEMOIR_BUILD_NODE=ON"
  },
  "dependencies": {
    "cmake-js": "^7.0.0",
    "node-addon-api": "^7.0.0"
  },
  "cmake-js": {
    "cmakeOptions": [
      "-DCMAKE_TOOLCHAIN_FILE=vcpkg/scripts/buildsystems/vcpkg.cmake",
      "-DVCPKG_OVERLAY_TRIPLETS=cmake/triplets",
      "-DVCPKG_TARGET_TRIPLET=x64-windows-release"
    ]
  }
}
```

### 5.5 FFmpeg DLL Distribution

The native addon links dynamically against FFmpeg. DLLs must ship alongside the `.node` file:
- `avcodec-62.dll`, `avformat-62.dll`, `avutil-60.dll`, `swscale-9.dll`, `swresample-6.dll`, `libx265.dll`

When used in an Electron app, these DLLs need to be included in the `asarUnpack` resources.

---

## 6. Consumer Architecture

### 6.1 Worker Thread Integration

The primary consumer is an Electron app (OverwatchSpotter) that runs a tick loop in a Worker thread:

```
Main thread (Electron)
  ├── UI (React renderer)
  ├── GEP bridge (WebSocket)
  ├── Match state management
  └── IPC to worker

Worker thread (tick loop)
  ├── memoir-node: CaptureEngine (frame acquisition + recording)
  ├── vision addon: OpenCV image processing (future)
  ├── onnxruntime-node: text recognition (future)
  └── Posts structured results to main thread
```

### 6.2 Typical Usage Pattern

```typescript
// tick-worker.ts — runs in Worker thread
import { CaptureEngine, type FramePacket } from 'memoir-node'
import { parentPort } from 'worker_threads'

const engine = new CaptureEngine({
  target: { type: 'windowExe', pattern: 'overwatch\\.exe' },
  maxFps: 10,
  keys: [
    { bit: 0, vk: 0x09, name: 'Tab' },
    { bit: 1, vk: 0xA4, name: 'LAlt' },
    { bit: 2, vk: 0xA5, name: 'RAlt' },
  ],
})

engine.start()

// Message handler for commands from main thread
parentPort!.on('message', (msg) => {
  switch (msg.cmd) {
    case 'startRecording':
      const info = engine.startRecording(msg.basePath)
      parentPort!.postMessage({ type: 'recordingStarted', info })
      break
    case 'stopRecording':
      engine.stopRecording()
      parentPort!.postMessage({ type: 'recordingStopped' })
      break
    case 'stop':
      engine.stop()
      process.exit(0)
  }
})

// Main tick loop
while (true) {
  const frame = engine.getNextFrame(2000)
  if (!frame) {
    const err = engine.lastError()
    if (err) {
      parentPort!.postMessage({ type: 'error', error: err })
      break
    }
    continue
  }

  const tabHeld = (frame.keyboardMask & 1n) !== 0n

  // frame.data is a Buffer with BGRA pixels
  // Can be passed to other native addons in the same thread (zero-copy)

  // Post lightweight results to main thread (no pixel data!)
  parentPort!.postMessage({
    type: 'tick',
    frameId: frame.frameId,
    width: frame.width,
    height: frame.height,
    tabHeld,
    keyboardMask: frame.keyboardMask.toString(), // BigInt can't be structured-cloned
  })

  frame.release()
}
```

### 6.3 Notes on Worker Thread Communication

- **Do NOT post `frame.data` to the main thread** — it's a large buffer (8MB at 1080p) and would be copied. Post only lightweight structured results.
- **BigInt cannot be cloned** via `postMessage` structured clone. Convert to string or Number before posting.
- **The `frame.data` Buffer becomes invalid after `release()`** — don't hold references past the release call.
- **Commands to the worker** (start/stop recording, stop engine) go via `postMessage` and are processed between frames.

---

## 7. Testing Strategy

### 7.1 Unit Tests (no display needed)

- **Meta reader/writer round-trip**: write a meta file, read it back, verify all fields match
- **Key event synthesis**: create rows with known masks, verify synthesized events
- **Type checks**: verify TypeScript types compile correctly

### 7.2 Integration Tests (require display + capture target)

- **Capture single frame**: `grab({ type: 'monitor', index: 0 })`, verify frame dimensions and data length
- **Capture stream**: start engine, get 10 frames, verify monotonic frame IDs
- **Recording**: start recording, capture frames, stop, verify .mp4 and .meta files exist
- **Meta file**: read recorded .meta, verify row count matches frame count
- **Keyboard state**: verify keyboard_mask is a bigint, bit operations work
- **Timeout**: `getNextFrame(0)` with no target returns null immediately
- **Error handling**: start with invalid target, verify error thrown

### 7.3 Test Commands

```bash
# All tests (requires display)
npm test

# Meta tests only (CI-safe, no display)
npm test -- --grep "meta"
```
