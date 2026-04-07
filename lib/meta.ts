import { readFileSync, writeFileSync } from 'fs'
import type { MetaFile, MetaKeyEntry, MetaRow } from './types'

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
  view.setUint32(8, 1, true) // version
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

// ─── Helpers ────────────────────────────────────────────────────

export function isPressed(row: MetaRow, keyName: string, keys: MetaKeyEntry[]): boolean {
  const key = keys.find(k => k.name === keyName)
  if (!key) throw new Error(`Key "${keyName}" not in key map`)
  return (row.keyboardMask & (1n << BigInt(key.bit))) !== 0n
}

export function pressedKeys(row: MetaRow, keys: MetaKeyEntry[]): string[] {
  return keys.filter(k => (row.keyboardMask & (1n << BigInt(k.bit))) !== 0n).map(k => k.name)
}

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
