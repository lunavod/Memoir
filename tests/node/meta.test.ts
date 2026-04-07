import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { readMeta, writeMeta, isPressed, pressedKeys, synthesizeKeyEvents } from '../../lib/meta'
import type { MetaKeyEntry, MetaRow } from '../../lib/types'
import { mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'

let tmpDir: string

beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'memoir-test-'))
})

afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true })
})

const testKeys: MetaKeyEntry[] = [
  { bit: 0, vk: 0x57, name: 'W' },
  { bit: 1, vk: 0x41, name: 'A' },
  { bit: 2, vk: 0x53, name: 'S' },
]

const testRows: MetaRow[] = [
  {
    frameId: 10n,
    recordFrameIndex: 0n,
    captureQpc: 1000n,
    hostAcceptQpc: 1001n,
    keyboardMask: 0b101n, // W + S pressed
    width: 1920,
    height: 1080,
    analysisStride: 7680,
    flags: 0,
  },
  {
    frameId: 11n,
    recordFrameIndex: 1n,
    captureQpc: 2000n,
    hostAcceptQpc: 2001n,
    keyboardMask: 0b010n, // A pressed
    width: 1920,
    height: 1080,
    analysisStride: 7680,
    flags: 0,
  },
]

describe('meta round-trip', () => {
  it('writes and reads back correctly', () => {
    const path = join(tmpDir, 'roundtrip.meta')
    const createdNs = 1700000000000000000n

    writeMeta(path, testKeys, testRows, createdNs)
    const meta = readMeta(path)

    // Header
    expect(meta.header.version).toBe(1)
    expect(meta.header.createdUnixNs).toBe(createdNs)
    expect(meta.header.keyCount).toBe(3)

    // Keys
    expect(meta.keys).toHaveLength(3)
    expect(meta.keys[0]).toEqual({ bit: 0, vk: 0x57, name: 'W' })
    expect(meta.keys[1]).toEqual({ bit: 1, vk: 0x41, name: 'A' })
    expect(meta.keys[2]).toEqual({ bit: 2, vk: 0x53, name: 'S' })

    // Rows
    expect(meta.rows).toHaveLength(2)
    expect(meta.rows[0].frameId).toBe(10n)
    expect(meta.rows[0].keyboardMask).toBe(0b101n)
    expect(meta.rows[0].captureQpc).toBe(1000n)
    expect(meta.rows[0].hostAcceptQpc).toBe(1001n)
    expect(meta.rows[0].width).toBe(1920)
    expect(meta.rows[0].height).toBe(1080)
    expect(meta.rows[0].analysisStride).toBe(7680)
    expect(meta.rows[0].flags).toBe(0)

    expect(meta.rows[1].frameId).toBe(11n)
    expect(meta.rows[1].recordFrameIndex).toBe(1n)
    expect(meta.rows[1].keyboardMask).toBe(0b010n)
  })

  it('handles empty rows', () => {
    const path = join(tmpDir, 'empty.meta')
    writeMeta(path, testKeys, [])
    const meta = readMeta(path)

    expect(meta.header.keyCount).toBe(3)
    expect(meta.keys).toHaveLength(3)
    expect(meta.rows).toHaveLength(0)
  })

  it('handles empty keys and rows', () => {
    const path = join(tmpDir, 'minimal.meta')
    writeMeta(path, [], [])
    const meta = readMeta(path)

    expect(meta.header.keyCount).toBe(0)
    expect(meta.keys).toHaveLength(0)
    expect(meta.rows).toHaveLength(0)
  })

  it('truncates key names to 31 chars', () => {
    const longName = 'A'.repeat(40)
    const keys: MetaKeyEntry[] = [{ bit: 0, vk: 0x41, name: longName }]
    const path = join(tmpDir, 'longname.meta')

    writeMeta(path, keys, [])
    const meta = readMeta(path)

    expect(meta.keys[0].name.length).toBeLessThanOrEqual(31)
    expect(meta.keys[0].name).toBe('A'.repeat(31))
  })

  it('defaults createdUnixNs to current time', () => {
    const path = join(tmpDir, 'default-time.meta')
    const before = BigInt(Date.now()) * 1000000n

    writeMeta(path, [], [])
    const meta = readMeta(path)

    const after = BigInt(Date.now()) * 1000000n
    expect(meta.header.createdUnixNs).toBeGreaterThanOrEqual(before)
    expect(meta.header.createdUnixNs).toBeLessThanOrEqual(after)
  })

  it('rejects files with bad magic', () => {
    const path = join(tmpDir, 'bad.meta')
    const buf = Buffer.alloc(32)
    buf.write('BADMAGIC', 0, 'ascii')
    require('fs').writeFileSync(path, buf)

    expect(() => readMeta(path)).toThrow('Bad magic')
  })
})

describe('isPressed', () => {
  it('returns true for pressed keys', () => {
    expect(isPressed(testRows[0], 'W', testKeys)).toBe(true)
    expect(isPressed(testRows[0], 'S', testKeys)).toBe(true)
  })

  it('returns false for unpressed keys', () => {
    expect(isPressed(testRows[0], 'A', testKeys)).toBe(false)
  })

  it('throws for unknown key name', () => {
    expect(() => isPressed(testRows[0], 'X', testKeys)).toThrow('Key "X" not in key map')
  })
})

describe('pressedKeys', () => {
  it('returns names of pressed keys', () => {
    expect(pressedKeys(testRows[0], testKeys)).toEqual(['W', 'S'])
    expect(pressedKeys(testRows[1], testKeys)).toEqual(['A'])
  })

  it('returns empty array when no keys pressed', () => {
    const row: MetaRow = { ...testRows[0], keyboardMask: 0n }
    expect(pressedKeys(row, testKeys)).toEqual([])
  })
})

describe('synthesizeKeyEvents', () => {
  it('produces key events from mask transitions', () => {
    const events = synthesizeKeyEvents(testRows, testKeys)

    // Frame 0: W and S go down (mask goes from 0 to 0b101)
    const frame0 = events.filter(e => e.frame === 0n)
    expect(frame0).toContainEqual({ frame: 0n, type: 'keyDown', key: 'W' })
    expect(frame0).toContainEqual({ frame: 0n, type: 'keyDown', key: 'S' })

    // Frame 1: W and S go up, A goes down (mask changes from 0b101 to 0b010)
    const frame1 = events.filter(e => e.frame === 1n)
    expect(frame1).toContainEqual({ frame: 1n, type: 'keyUp', key: 'W' })
    expect(frame1).toContainEqual({ frame: 1n, type: 'keyDown', key: 'A' })
    expect(frame1).toContainEqual({ frame: 1n, type: 'keyUp', key: 'S' })
  })

  it('returns empty array for empty rows', () => {
    expect(synthesizeKeyEvents([], testKeys)).toEqual([])
  })

  it('returns empty array when mask never changes from zero', () => {
    const rows: MetaRow[] = [
      { ...testRows[0], keyboardMask: 0n },
      { ...testRows[1], keyboardMask: 0n },
    ]
    expect(synthesizeKeyEvents(rows, testKeys)).toEqual([])
  })
})
