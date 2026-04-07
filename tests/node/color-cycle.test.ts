/**
 * End-to-end test: create a colored window, capture + record it,
 * cycle through colors, verify both live frames and recorded MP4.
 *
 * Mirrors tests/python/test_color_cycle.py
 */

import { describe, it, expect } from 'vitest'
import { CaptureEngine } from '../../lib/native'
import { execSync } from 'child_process'
import { mkdtempSync, rmSync, existsSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'

// TestWindow is a native Win32 window exposed by our addon
const addon = require('../../build/Release/memoir_node.node')

const WINDOW_TITLE = 'Memoir Color Test 48291'
const WINDOW_W = 640
const WINDOW_H = 480
const TOLERANCE = 35

const COLORS: Array<[string, [number, number, number]]> = [
  ['red',   [0, 0, 255]],     // BGR
  ['green', [0, 255, 0]],
  ['blue',  [255, 0, 0]],
]

function sampleCenterBGR(
  data: Buffer,
  width: number,
  height: number,
  stride: number,
  size = 40,
): [number, number, number] {
  const cy = Math.floor(height / 2)
  const cx = Math.floor(width / 2)
  let sumB = 0, sumG = 0, sumR = 0
  let count = 0

  const yStart = Math.max(0, cy - size)
  const yEnd = Math.min(height, cy + size)
  const xStart = Math.max(0, cx - size)
  const xEnd = Math.min(width, cx + size)

  for (let y = yStart; y < yEnd; y++) {
    for (let x = xStart; x < xEnd; x++) {
      const offset = y * stride + x * 4
      sumB += data[offset]
      sumG += data[offset + 1]
      sumR += data[offset + 2]
      count++
    }
  }

  return [sumB / count, sumG / count, sumR / count]
}

/**
 * Consume frames for durationMs, continuously calling fill() to force
 * WGC to deliver new frames. Returns center BGR of each captured frame.
 */
function drainFrames(
  engine: any,
  win: any,
  bgr: [number, number, number],
  durationMs: number,
): Array<[number, number, number]> {
  const results: Array<[number, number, number]> = []
  const deadline = Date.now() + durationMs

  while (Date.now() < deadline) {
    win.fill(bgr[0], bgr[1], bgr[2])
    const pkt = engine.getNextFrame(50)
    if (!pkt) continue
    results.push(sampleCenterBGR(pkt.data, pkt.width, pkt.height, pkt.stride))
    pkt.release()
  }

  return results
}

/** Read recorded MP4 frames via ffmpeg, return center BGR of each frame. */
function readRecordedFrames(
  mp4Path: string,
  width: number,
  height: number,
): Array<[number, number, number]> {
  const result = execSync(
    `ffmpeg -i "${mp4Path}" -f rawvideo -pix_fmt bgra pipe:1`,
    { maxBuffer: 200 * 1024 * 1024, stdio: ['pipe', 'pipe', 'ignore'] },
  )

  const frameSize = width * height * 4
  const frames: Array<[number, number, number]> = []

  for (let offset = 0; offset + frameSize <= result.length; offset += frameSize) {
    const frameData = result.subarray(offset, offset + frameSize)
    frames.push(sampleCenterBGR(
      Buffer.from(frameData), width, height, width * 4, 20,
    ))
  }

  return frames
}

describe('color cycle', () => {
  it('captures correct colors live and in recording', () => {
    let tmpDir = ''
    const win = new addon.TestWindow(WINDOW_TITLE, WINDOW_W, WINDOW_H)

    try {
      tmpDir = mkdtempSync(join(tmpdir(), 'memoir-color-'))

      const engine = new CaptureEngine({
        target: { type: 'windowTitle', pattern: WINDOW_TITLE },
        maxFps: 60,
        recordWidth: WINDOW_W,
        recordHeight: WINDOW_H,
      })
      engine.start()

      try {
        // Warm up
        drainFrames(engine, win, [128, 128, 128], 150)

        // Start recording and cycle colors
        const base = join(tmpDir, 'color_test')
        engine.startRecording(base)

        const liveResults: Array<{
          name: string
          expected: [number, number, number]
          actual: [number, number, number] | null
        }> = []

        for (const [name, bgr] of COLORS) {
          const samples = drainFrames(engine, win, bgr, 150)
          liveResults.push({
            name,
            expected: bgr,
            actual: samples.length > 0 ? samples[samples.length - 1] : null,
          })
        }

        // Drain a few more to flush pipeline
        drainFrames(engine, win, COLORS[COLORS.length - 1][1], 100)

        engine.stopRecording()
        const stats = engine.stats()
        engine.stop()

        console.log(`\nFrames accepted: ${stats.framesAccepted}`)
        console.log(`Frames recorded: ${stats.framesRecorded}`)

        // --- Verify live ---
        console.log('\n=== Live colors ===')
        for (const { name, expected, actual } of liveResults) {
          expect(actual).not.toBeNull()
          const [ab, ag, ar] = actual!
          console.log(`  ${name.padEnd(6)}: expected=${JSON.stringify(expected)}, got=[${ab.toFixed(0)}, ${ag.toFixed(0)}, ${ar.toFixed(0)}]`)
          const maxDiff = Math.max(
            Math.abs(expected[0] - ab),
            Math.abs(expected[1] - ag),
            Math.abs(expected[2] - ar),
          )
          expect(maxDiff).toBeLessThan(TOLERANCE)
        }

        // --- Verify recorded MP4 ---
        const mp4 = base + '.mp4'
        expect(existsSync(mp4)).toBe(true)

        const recorded = readRecordedFrames(mp4, WINDOW_W, WINDOW_H)
        console.log(`\n=== Recorded ${recorded.length} frames ===`)
        expect(recorded.length).toBeGreaterThanOrEqual(COLORS.length)

        for (const { name, expected } of liveResults) {
          const found = recorded.some(f => {
            const maxDiff = Math.max(
              Math.abs(expected[0] - f[0]),
              Math.abs(expected[1] - f[1]),
              Math.abs(expected[2] - f[2]),
            )
            return maxDiff < TOLERANCE
          })
          console.log(`  ${name.padEnd(6)}: ${found ? 'FOUND' : 'MISSING'}`)
          expect(found).toBe(true)
        }

        console.log('\nColor cycle test passed!')
      } finally {
        try { engine.stop() } catch {}
      }
    } finally {
      win.destroy()
      if (tmpDir) rmSync(tmpDir, { recursive: true, force: true })
    }
  })
})
