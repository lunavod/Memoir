import { describe, it, expect } from 'vitest'
import { CaptureEngine } from '../../lib/native'

const addon = require('../../build/Release/memoir_node.node')

const UNIQUE_TITLE = 'MemoirTestWindow_node_39f7a2'

describe('window close', () => {
  it('returns null and error after target window closes', () => {
    const win = new addon.TestWindow(UNIQUE_TITLE, 400, 300)

    try {
      const engine = new CaptureEngine({
        target: { type: 'windowTitle', pattern: UNIQUE_TITLE },
        maxFps: 30,
      })
      engine.start()

      // Capture at least one frame to confirm it works
      win.fill(128, 128, 128)
      const pkt = engine.getNextFrame(5000)
      expect(pkt).not.toBeNull()
      pkt!.release()

      // Destroy the window
      win.destroy()

      // After the target is destroyed, getNextFrame should return null
      const frame = engine.getNextFrame(3000)
      expect(frame).toBeNull()

      const err = engine.lastError()
      expect(err).not.toBeNull()
      expect(err!.toLowerCase()).toContain('closed')

      engine.stop()
    } finally {
      try { win.destroy() } catch {}
    }
  })
})
