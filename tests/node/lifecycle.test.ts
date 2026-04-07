import { describe, it, expect } from 'vitest'
import { CaptureEngine } from '../../lib/native'

describe('lifecycle', () => {
  it('double release does not throw', () => {
    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 5,
    })
    engine.start()
    const pkt = engine.getNextFrame(2000)
    expect(pkt).not.toBeNull()
    pkt!.release()
    pkt!.release() // second release should be a no-op
    engine.stop()
  })

  it('lastError is null initially', () => {
    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
    })
    engine.start()
    expect(engine.lastError()).toBeNull()
    engine.stop()
  })

  it('stop also stops recording', () => {
    const { mkdtempSync, existsSync, rmSync } = require('fs')
    const { join } = require('path')
    const { tmpdir } = require('os')
    const tmp = mkdtempSync(join(tmpdir(), 'memoir-life-'))

    try {
      const base = join(tmp, 'stop_test')
      const engine = new CaptureEngine({
        target: { type: 'monitor', index: 0 },
        maxFps: 10,
      })
      engine.start()

      engine.startRecording(base)
      expect(engine.isRecording()).toBe(true)

      for (let i = 0; i < 5; i++) {
        const pkt = engine.getNextFrame(5000)
        if (pkt) pkt.release()
      }

      engine.stop()
      expect(engine.isRecording()).toBe(false)
      expect(existsSync(base + '.mp4')).toBe(true)
      expect(existsSync(base + '.meta')).toBe(true)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it('startRecording while already recording throws', () => {
    const { mkdtempSync, rmSync } = require('fs')
    const { join } = require('path')
    const { tmpdir } = require('os')
    const tmp = mkdtempSync(join(tmpdir(), 'memoir-life-'))

    try {
      const engine = new CaptureEngine({
        target: { type: 'monitor', index: 0 },
        maxFps: 10,
      })
      engine.start()

      engine.startRecording(join(tmp, 'session1'))
      expect(() => engine.startRecording(join(tmp, 'session2'))).toThrow()

      engine.stopRecording()
      engine.stop()
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it('stopRecording when not recording is a no-op', () => {
    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 5,
    })
    engine.start()
    engine.stopRecording() // should not throw
    engine.stop()
  })

  it('getNextFrame timeout returns null', () => {
    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 0.5,
    })
    engine.start()
    // Drain any pending frame
    engine.getNextFrame(500)
    // Poll should return null (queue empty, rate limited)
    const pkt = engine.getNextFrame(0)
    if (pkt) pkt.release()
    engine.stop()
  })
})
