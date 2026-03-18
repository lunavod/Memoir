import pytest
from memoir_capture import CaptureEngine, MonitorTarget

pytestmark = pytest.mark.capture


def test_double_release():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()
    pkt = engine.get_next_frame(2000)
    assert pkt is not None
    pkt.release()
    pkt.release()
    engine.stop()


def test_cpu_bgra_after_release():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()
    pkt = engine.get_next_frame(2000)
    assert pkt is not None
    pkt.release()
    with pytest.raises(ValueError, match="released"):
        _ = pkt.cpu_bgra
    engine.stop()


def test_context_manager():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()
    pkt = engine.get_next_frame(2000)
    assert pkt is not None
    with pkt:
        _ = pkt.cpu_bgra
    with pytest.raises(ValueError):
        _ = pkt.cpu_bgra
    engine.stop()


def test_engine_context_manager():
    with CaptureEngine(MonitorTarget(0), max_fps=5.0) as engine:
        pkt = engine.get_next_frame(2000)
        assert pkt is not None
        pkt.release()


def test_stop_stops_recording(tmp_path):
    base = str(tmp_path / "stop_test")
    engine = CaptureEngine(MonitorTarget(0), max_fps=10.0)
    engine.start()

    engine.start_recording(base)
    assert engine.is_recording()

    for i, pkt in enumerate(engine.frames()):
        pkt.release()
        if i >= 4:
            break

    engine.stop()
    assert not engine.is_recording()
    assert (tmp_path / "stop_test.mp4").exists()
    assert (tmp_path / "stop_test.meta").exists()


def test_start_recording_while_recording(tmp_path):
    engine = CaptureEngine(MonitorTarget(0), max_fps=10.0)
    engine.start()

    engine.start_recording(str(tmp_path / "session1"))
    with pytest.raises(RuntimeError):
        engine.start_recording(str(tmp_path / "session2"))

    engine.stop_recording()
    engine.stop()


def test_stop_recording_when_not_recording():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()
    engine.stop_recording()  # no-op
    engine.stop()


def test_get_next_frame_timeout():
    engine = CaptureEngine(MonitorTarget(0), max_fps=0.5)
    engine.start()
    engine.get_next_frame(500)
    pkt = engine.get_next_frame(0)
    if pkt:
        pkt.release()
    engine.stop()


def test_stats_counters():
    engine = CaptureEngine(MonitorTarget(0), max_fps=10.0, analysis_queue_capacity=1)
    engine.start()

    for i, pkt in enumerate(engine.frames()):
        pkt.release()
        if i >= 9:
            break

    stats = engine.stats()
    assert stats.frames_accepted >= 10
    assert stats.frames_seen >= stats.frames_accepted
    assert stats.python_queue_depth == 0
    engine.stop()


def test_get_last_error_initially_none():
    engine = CaptureEngine(MonitorTarget(0))
    engine.start()
    assert engine.get_last_error() is None
    engine.stop()
