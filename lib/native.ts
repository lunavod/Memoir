import path from 'path'
import type { CaptureTarget, EngineOptions, FramePacket } from './types'

// Load the compiled N-API addon
let addon: any
try {
  addon = require(path.resolve(__dirname, '../build/Release/memoir_node.node'))
} catch {
  // Fallback for different build configurations
  addon = require(path.resolve(__dirname, '../build/Debug/memoir_node.node'))
}

export const CaptureEngine: {
  new (options: EngineOptions): {
    start(): void
    stop(): void
    getNextFrame(timeoutMs?: number): FramePacket | null
    startRecording(basePath: string, encoder?: string): import('./types').RecordingInfo
    startRecording(opts: {
      path: string
      videoName: string
      metaName: string
      encoder?: string
    }): import('./types').RecordingInfo
    stopRecording(): void
    isRecording(): boolean
    stats(): import('./types').EngineStats
    lastError(): string | null
  }
} = addon.CaptureEngine

export const ping: () => string = addon.ping
export const version: string = addon.version

/**
 * Capture a single frame and return it.
 * Creates a temporary engine, grabs one frame, stops.
 */
export function grab(
  target: CaptureTarget,
  opts?: { timeoutMs?: number; maxFps?: number },
): FramePacket {
  const engine = new CaptureEngine({ target, maxFps: opts?.maxFps ?? 60 })
  engine.start()
  try {
    const frame = engine.getNextFrame(opts?.timeoutMs ?? 5000)
    if (!frame) throw new Error('No frame captured within timeout')
    return frame
  } finally {
    engine.stop()
  }
}
