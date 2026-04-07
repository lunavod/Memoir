# memoir-node

Windows-native screen capture module with Node.js bindings for real-time frame analysis and deterministic replay recording.

Memoir captures frames from a window or monitor using Windows Graphics Capture (WGC), delivers them as Buffers, and optionally records them to HEVC video with per-frame metadata.

## Features

- **WGC capture** — continuous frame capture from any window or monitor
- **Zero-copy Buffers** — BGRA frames delivered as Node.js Buffers without copying
- **Hardware-accelerated recording** — lossless HEVC encoding via NVENC, AMF, or x265 fallback
- **Binary metadata** — `.meta` sidecar with per-frame keyboard state, timestamps, and frame IDs
- **Dynamic recording** — start/stop recording without restarting capture
- **Frame-accurate keyboard** — key state snapshot at the exact moment each frame is accepted
- **Pure TypeScript meta reader/writer** — read and write `.meta` files without the native addon
- **Synchronous blocking API** — designed for Worker threads running tick loops

## Requirements

- Windows 10 1903+
- Node.js 18+
- x64 architecture
- NVIDIA GPU (NVENC), AMD GPU (AMF), or CPU-only (x265) for recording

## Installation

```
npm install memoir-node
```

## Quick Start

### Capture frames

```typescript
import { CaptureEngine } from 'memoir-node'

const engine = new CaptureEngine({
  target: { type: 'monitor', index: 0 },  // primary monitor
  maxFps: 10,
})
engine.start()

const frame = engine.getNextFrame(5000)
if (frame) {
  console.log(`Frame ${frame.frameId}: ${frame.width}x${frame.height}`)
  console.log(`Keys: ${frame.keyboardMask.toString(16)}`)
  // frame.data is a Buffer with BGRA pixels
  frame.release()
}

engine.stop()
```

### Capture a specific window

```typescript
const engine = new CaptureEngine({
  target: { type: 'windowTitle', pattern: '(?i)notepad' },
  maxFps: 30,
})
```

Or by executable name:

```typescript
const engine = new CaptureEngine({
  target: { type: 'windowExe', pattern: 'notepad\\.exe' },
  maxFps: 30,
})
```

### Record to MP4

```typescript
const engine = new CaptureEngine({
  target: { type: 'monitor', index: 0 },
  maxFps: 10,
  recordWidth: 1920,
  recordHeight: 1080,
})
engine.start()

const info = engine.startRecording('session_001')
console.log(`Recording to ${info.videoPath}`)  // session_001.mp4

for (let i = 0; i < 100; i++) {
  const frame = engine.getNextFrame(5000)
  if (frame) frame.release()
}

engine.stopRecording()  // finalizes .mp4 + .meta
engine.stop()
```

### Read metadata

```typescript
import { readMeta, pressedKeys } from 'memoir-node'

const meta = readMeta('session_001.meta')
console.log(`Keys tracked: ${meta.keys.map(k => k.name)}`)

for (const row of meta.rows) {
  console.log(`Frame ${row.frameId}: ${pressedKeys(row, meta.keys).join(', ')}`)
}
```

### Write metadata (for synthetic replays)

```typescript
import { writeMeta, type MetaKeyEntry, type MetaRow } from 'memoir-node'

const keys: MetaKeyEntry[] = [
  { bit: 0, vk: 0x57, name: 'W' },
  { bit: 1, vk: 0x41, name: 'A' },
]

const rows: MetaRow[] = [{
  frameId: 0n, recordFrameIndex: 0n,
  captureQpc: 0n, hostAcceptQpc: 0n,
  keyboardMask: 0b01n,
  width: 1920, height: 1080, analysisStride: 7680, flags: 0,
}]

writeMeta('synthetic.meta', keys, rows)
```

### Worker thread usage (Electron)

```typescript
// tick-worker.ts — runs in Worker thread
import { CaptureEngine } from 'memoir-node'
import { parentPort } from 'worker_threads'

const engine = new CaptureEngine({
  target: { type: 'windowExe', pattern: 'myapp\\.exe' },
  maxFps: 10,
})
engine.start()

while (true) {
  const frame = engine.getNextFrame(2000)
  if (!frame) {
    const err = engine.lastError()
    if (err) { parentPort!.postMessage({ type: 'error', error: err }); break }
    continue
  }

  // frame.data is a Buffer — process it here, don't post it to main thread
  parentPort!.postMessage({
    type: 'tick',
    frameId: frame.frameId,
    width: frame.width,
    height: frame.height,
  })

  frame.release()
}
```

## API Reference

### `new CaptureEngine(options)`

| Option | Default | Description |
|--------|---------|-------------|
| `target` | required | `{ type: 'monitor', index }`, `{ type: 'windowTitle', pattern }`, or `{ type: 'windowExe', pattern }` |
| `maxFps` | `10` | Maximum accepted frame rate |
| `queueCapacity` | `1` | Bounded queue size |
| `captureCursor` | `false` | Include cursor in capture |
| `keys` | 40-key gaming set | Array of `{ bit, vk, name }` for keyboard tracking |
| `recordWidth` | `1920` | Recording output width |
| `recordHeight` | `1080` | Recording output height |
| `recordGop` | `1` | GOP size (1 = all-intra) |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `start()` | `void` | Initialize D3D11, create WGC session, begin capturing |
| `stop()` | `void` | Stop capture and any active recording |
| `getNextFrame(timeoutMs?)` | `FramePacket \| null` | Block until frame available. -1 = forever, 0 = poll |
| `startRecording(basePath, encoder?)` | `RecordingInfo` | Start recording to `basePath.mp4` + `basePath.meta` |
| `startRecording(opts)` | `RecordingInfo` | Start recording with `{ path, videoName, metaName, encoder? }` |
| `stopRecording()` | `void` | Finalize recording |
| `isRecording()` | `boolean` | Whether a recording session is active |
| `stats()` | `EngineStats` | Live counters |
| `lastError()` | `string \| null` | Last non-fatal error |

### `FramePacket`

| Property | Type | Description |
|----------|------|-------------|
| `frameId` | `number` | Monotonic frame ID |
| `data` | `Buffer` | BGRA pixels, length = stride * height |
| `keyboardMask` | `bigint` | 64-bit key state bitmask |
| `captureQpc` | `bigint` | WGC timestamp (100ns units) |
| `hostAcceptQpc` | `bigint` | Host QPC when frame was accepted |
| `width`, `height`, `stride` | `number` | Frame dimensions |
| `released` | `boolean` | Whether pixel memory has been freed |

Call `frame.release()` when done to free pixel memory.

### Recording

Encoding: lossless HEVC (QP=0), YUV 4:4:4. Encoder selected automatically: `hevc_nvenc` (NVIDIA) → `hevc_amf` (AMD) → `libx265` (software). Force a specific encoder:

```typescript
const info = engine.startRecording('session', 'libx265')
console.log(info.codec) // "libx265"
```

### Meta utilities

```typescript
import { readMeta, writeMeta, isPressed, pressedKeys, synthesizeKeyEvents } from 'memoir-node'

// Read
const meta = readMeta('session.meta')

// Check keys
isPressed(meta.rows[0], 'W', meta.keys)       // boolean
pressedKeys(meta.rows[0], meta.keys)           // string[]

// Generate key events for replay
const events = synthesizeKeyEvents(meta.rows, meta.keys)
// [{ frame: 0n, type: 'keyDown', key: 'W' }, ...]
```

## Architecture

```
WGC FrameArrived (thread pool)
  │
  ├─ FPS limiter → drop if too soon
  ├─ Queue check → drop if full (drop-new policy)
  │
  ├─ Accept: assign frame_id, snapshot keyboard
  ├─ GPU→CPU: CopyResource → staging → Map → memcpy → Buffer (zero-copy)
  ├─ Recording: swscale (BGRA→YUV444) → HEVC encoder → MP4
  └─ Enqueue → Node.js consumer
```

`getNextFrame()` is a synchronous blocking call that waits on a condition variable. No GIL concerns (unlike Python) — the calling thread simply sleeps until a frame arrives. Use in a Worker thread to avoid blocking the main V8 thread.

## License

MIT. Links against FFmpeg (LGPL 2.1+).
