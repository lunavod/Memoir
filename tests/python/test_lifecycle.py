"""Comprehensive lifecycle, error handling, and edge-case tests."""

import os, tempfile
from memoir import CaptureEngine, MonitorTarget


def test_double_release():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()
    pkt = engine.get_next_frame(2000)
    assert pkt is not None
    pkt.release()
    pkt.release()
    engine.stop()
    print("PASS: double release")


def test_cpu_bgra_after_release():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()
    pkt = engine.get_next_frame(2000)
    assert pkt is not None
    pkt.release()
    try:
        _ = pkt.cpu_bgra
        assert False, "Should have raised"
    except ValueError as e:
        assert "released" in str(e).lower()
    engine.stop()
    print("PASS: cpu_bgra after release")


def test_context_manager():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()
    pkt = engine.get_next_frame(2000)
    assert pkt is not None
    with pkt:
        _ = pkt.cpu_bgra
    try:
        _ = pkt.cpu_bgra
        assert False, "Should have raised"
    except ValueError:
        pass
    engine.stop()
    print("PASS: context manager")


def test_engine_context_manager():
    with CaptureEngine(MonitorTarget(0), max_fps=5.0) as engine:
        pkt = engine.get_next_frame(2000)
        assert pkt is not None
        pkt.release()
    print("PASS: engine context manager")


def test_stop_stops_recording():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = os.path.join(tmpdir, "stop_test")
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
        assert os.path.isfile(base + ".mp4")
        assert os.path.isfile(base + ".meta")
        print("PASS: stop stops recording")


def test_start_recording_while_recording():
    with tempfile.TemporaryDirectory() as tmpdir:
        base1 = os.path.join(tmpdir, "session1")
        base2 = os.path.join(tmpdir, "session2")
        engine = CaptureEngine(MonitorTarget(0), max_fps=10.0)
        engine.start()

        engine.start_recording(base1)
        try:
            engine.start_recording(base2)
            assert False, "Should have raised"
        except RuntimeError:
            pass

        engine.stop_recording()
        engine.stop()
        print("PASS: double start_recording raises")


def test_stop_recording_when_not_recording():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()
    engine.stop_recording()
    engine.stop()
    print("PASS: stop_recording no-op")


def test_get_next_frame_timeout():
    engine = CaptureEngine(MonitorTarget(0), max_fps=0.5)
    engine.start()
    engine.get_next_frame(500)
    pkt = engine.get_next_frame(0)
    if pkt:
        pkt.release()
    engine.stop()
    print("PASS: get_next_frame timeout")


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
    print("PASS: stats counters")


def test_get_last_error_initially_none():
    engine = CaptureEngine(MonitorTarget(0))
    engine.start()
    assert engine.get_last_error() is None
    engine.stop()
    print("PASS: get_last_error initially None")


if __name__ == "__main__":
    test_double_release()
    test_cpu_bgra_after_release()
    test_context_manager()
    test_engine_context_manager()
    test_stop_stops_recording()
    test_start_recording_while_recording()
    test_stop_recording_when_not_recording()
    test_get_next_frame_timeout()
    test_stats_counters()
    test_get_last_error_initially_none()
    print("\nAll lifecycle tests passed!")
