import pytest
from memoir_capture import CaptureEngine, MonitorTarget

pytestmark = pytest.mark.capture


def test_monitor_capture_frames():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()

    for i, packet in enumerate(engine.frames()):
        with packet:
            arr = packet.cpu_bgra
            assert arr.shape[2] == 4
            assert arr.shape[0] == packet.height
            assert arr.shape[1] == packet.width
        if i >= 4:
            break

    stats = engine.stats()
    assert stats.frames_accepted >= 5
    engine.stop()
