import { describe, it, expect, afterEach } from 'vitest'
import { CaptureEngine } from '../../lib/native'
import { mkdtempSync, rmSync, existsSync, statSync, mkdirSync } from 'fs'
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

function recordFrames(engine: any, n: number) {
  for (let i = 0; i < n; i++) {
    const pkt = engine.getNextFrame(5000)
    if (pkt) pkt.release()
  }
}

describe('split recording', () => {
  it('creates files at separate paths', () => {
    tmpDir = mkdtempSync(join(tmpdir(), 'memoir-split-'))
    const recDir = join(tmpDir, 'session')
    mkdirSync(recDir)

    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 10,
    })
    engine.start()

    try {
      warmUp(engine)

      const info = engine.startRecording({
        path: recDir,
        videoName: 'data',
        metaName: 'keys',
      })
      expect(info.videoPath).toContain('data.mp4')
      expect(info.metaPath).toContain('keys.meta')

      recordFrames(engine, 5)
      engine.stopRecording()

      expect(existsSync(join(recDir, 'data.mp4'))).toBe(true)
      expect(existsSync(join(recDir, 'keys.meta'))).toBe(true)
      expect(statSync(join(recDir, 'data.mp4')).size).toBeGreaterThan(0)
      expect(statSync(join(recDir, 'keys.meta')).size).toBeGreaterThan(0)
    } finally {
      engine.stop()
    }
  })

  it('strips .mp4 extension from videoName', () => {
    tmpDir = mkdtempSync(join(tmpdir(), 'memoir-split-'))
    const recDir = join(tmpDir, 'strip_mp4')
    mkdirSync(recDir)

    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 10,
    })
    engine.start()

    try {
      warmUp(engine)

      const info = engine.startRecording({
        path: recDir,
        videoName: 'data.mp4',
        metaName: 'keys',
      })
      expect(info.videoPath).toContain('data.mp4')
      expect(info.videoPath).not.toContain('data.mp4.mp4')

      recordFrames(engine, 5)
    } finally {
      engine.stop()
    }
  })

  it('strips .meta extension from metaName', () => {
    tmpDir = mkdtempSync(join(tmpdir(), 'memoir-split-'))
    const recDir = join(tmpDir, 'strip_meta')
    mkdirSync(recDir)

    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 10,
    })
    engine.start()

    try {
      warmUp(engine)

      const info = engine.startRecording({
        path: recDir,
        videoName: 'data',
        metaName: 'keys.meta',
      })
      expect(info.metaPath).toContain('keys.meta')
      expect(info.metaPath).not.toContain('keys.meta.meta')

      recordFrames(engine, 5)
    } finally {
      engine.stop()
    }
  })

  it('strips both extensions', () => {
    tmpDir = mkdtempSync(join(tmpdir(), 'memoir-split-'))
    const recDir = join(tmpDir, 'strip_both')
    mkdirSync(recDir)

    const engine = new CaptureEngine({
      target: { type: 'monitor', index: 0 },
      maxFps: 10,
    })
    engine.start()

    try {
      warmUp(engine)

      const info = engine.startRecording({
        path: recDir,
        videoName: 'data.mp4',
        metaName: 'keys.meta',
      })
      expect(info.videoPath).toContain('data.mp4')
      expect(info.videoPath).not.toContain('data.mp4.mp4')
      expect(info.metaPath).toContain('keys.meta')
      expect(info.metaPath).not.toContain('keys.meta.meta')

      recordFrames(engine, 5)
    } finally {
      engine.stop()
    }
  })
})
