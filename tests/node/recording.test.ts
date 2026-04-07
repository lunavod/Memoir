import { describe, it, expect, afterEach } from 'vitest'
import { CaptureEngine } from '../../lib/native'
import { readMeta } from '../../lib/meta'
import { mkdtempSync, rmSync, existsSync, statSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'

let tmpDir: string

afterEach(() => {
  if (tmpDir) {
    rmSync(tmpDir, { recursive: true, force: true })
  }
})

function warmUp(engine: any, n = 3) {
  for (let i = 0; i < n; i++) {
    const pkt = engine.getNextFrame(5000)
    if (pkt) pkt.release()
  }
}

describe('recording', () => {
  it('records 30 frames at custom resolution', () => {
    tmpDir = mkdtempSync(join(tmpdir(), 'memoir-rec-'))
    const base = join(tmpDir, 'test_session')

    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 10,
      recordWidth: 1280,
      recordHeight: 720,
    })
    engine.start()

    try {
      warmUp(engine)

      const info = engine.startRecording(base)
      expect(info.width).toBe(1280)
      expect(info.height).toBe(720)
      expect(engine.isRecording()).toBe(true)

      for (let i = 0; i < 30; i++) {
        const pkt = engine.getNextFrame(5000)
        expect(pkt).not.toBeNull()
        pkt!.release()
      }

      engine.stopRecording()
      expect(engine.isRecording()).toBe(false)

      const s = engine.stats()
      expect(s.framesRecorded).toBe(30)

      expect(existsSync(base + '.mp4')).toBe(true)
      expect(statSync(base + '.mp4').size).toBeGreaterThan(1000)

      const meta = readMeta(base + '.meta')
      expect(meta.rows.length).toBe(30)
      for (let i = 0; i < 30; i++) {
        expect(meta.rows[i].recordFrameIndex).toBe(BigInt(i))
      }
    } finally {
      engine.stop()
    }
  })

  it('records with libx265 encoder', () => {
    tmpDir = mkdtempSync(join(tmpdir(), 'memoir-rec-'))
    const base = join(tmpDir, 'x265_session')

    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 10,
      recordWidth: 1280,
      recordHeight: 720,
    })
    engine.start()

    try {
      warmUp(engine)

      const info = engine.startRecording(base, 'libx265')
      expect(info.codec).toBe('libx265')

      for (let i = 0; i < 20; i++) {
        const pkt = engine.getNextFrame(5000)
        expect(pkt).not.toBeNull()
        pkt!.release()
      }

      engine.stopRecording()
      const s = engine.stats()
      expect(s.framesRecorded).toBe(20)

      expect(existsSync(base + '.mp4')).toBe(true)
      expect(statSync(base + '.mp4').size).toBeGreaterThan(1000)

      const meta = readMeta(base + '.meta')
      expect(meta.rows.length).toBe(20)
    } finally {
      engine.stop()
    }
  })
})
