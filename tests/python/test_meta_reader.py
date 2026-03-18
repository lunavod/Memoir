"""Validates .meta binary format via MetaReader and round-trips via MetaWriter."""

import os, tempfile
from memoir import (
    CaptureEngine, MonitorTarget,
    MetaReader, MetaWriter, MetaKeyEntry, MetaRow,
)


def test_meta_from_recording():
    """Record frames, then read the .meta file with MetaReader."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = os.path.join(tmpdir, "meta_test")

        engine = CaptureEngine(MonitorTarget(0), max_fps=10.0)
        engine.start()

        engine.start_recording(base)
        for i, pkt in enumerate(engine.frames()):
            pkt.release()
            if i >= 9:
                break
        engine.stop_recording()
        engine.stop()

        meta = MetaReader.read(base + ".meta")
        print(f"Magic: {meta.header.magic}")
        print(f"Version: {meta.header.version}")
        print(f"Keys: {len(meta.keys)}")
        print(f"Rows: {len(meta.rows)}")

        assert meta.header.version == 1
        assert len(meta.keys) > 0
        assert meta.keys[0].name == "W"
        assert len(meta.rows) >= 10

        for i, row in enumerate(meta.rows):
            assert row.record_frame_index == i

        fids = [r.frame_id for r in meta.rows]
        assert fids == sorted(fids)
        assert len(set(fids)) == len(fids)

        print("Meta reader test passed!")


def test_meta_roundtrip():
    """Write a .meta with MetaWriter, read it back with MetaReader."""
    keys = [
        MetaKeyEntry(0, 0x57, "W"),
        MetaKeyEntry(1, 0x41, "A"),
        MetaKeyEntry(2, 0x53, "S"),
    ]
    rows = [
        MetaRow(frame_id=10, record_frame_index=0,
                capture_qpc=1000, host_accept_qpc=1001,
                keyboard_mask=0b101, width=1920, height=1080,
                analysis_stride=7680),
        MetaRow(frame_id=11, record_frame_index=1,
                capture_qpc=2000, host_accept_qpc=2001,
                keyboard_mask=0b010, width=1920, height=1080,
                analysis_stride=7680),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "roundtrip.meta")

        with MetaWriter(path, keys) as w:
            for row in rows:
                w.write_row(row)

        meta = MetaReader.read(path)

        assert meta.header.version == 1
        assert meta.header.key_count == 3
        assert len(meta.keys) == 3
        assert meta.keys[0].name == "W"
        assert meta.keys[2].name == "S"

        assert len(meta.rows) == 2
        assert meta.rows[0].frame_id == 10
        assert meta.rows[0].keyboard_mask == 0b101
        assert meta.rows[1].frame_id == 11
        assert meta.rows[1].record_frame_index == 1

        print("Meta roundtrip test passed!")


if __name__ == "__main__":
    test_meta_from_recording()
    test_meta_roundtrip()
