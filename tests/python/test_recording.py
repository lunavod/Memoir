import os
import pytest
from memoir_capture import CaptureEngine, MonitorTarget

pytestmark = pytest.mark.capture


def test_record_30_frames(tmp_path):
    base = str(tmp_path / "test_session")
    mp4 = base + ".mp4"

    engine = CaptureEngine(
        MonitorTarget(0), max_fps=10.0,
        record_width=1280, record_height=720,
    )
    engine.start()

    # Warm up
    for i, pkt in enumerate(engine.frames()):
        pkt.release()
        if i >= 2:
            break

    info = engine.start_recording(base)
    assert info.width == 1280
    assert info.height == 720
    assert engine.is_recording()

    for i, pkt in enumerate(engine.frames()):
        pkt.release()
        if i >= 29:
            break

    engine.stop_recording()
    assert not engine.is_recording()

    stats = engine.stats()
    assert stats.frames_recorded >= 30
    engine.stop()

    assert os.path.isfile(mp4)
    assert os.path.getsize(mp4) > 1000
