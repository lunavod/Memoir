// Types
export type {
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

// Pure TypeScript meta reader/writer
export { readMeta, writeMeta, isPressed, pressedKeys, synthesizeKeyEvents } from './meta'

// Native addon
export { CaptureEngine, ping, version, grab } from './native'
