from memoir import CaptureEngine, MonitorTarget


def test_monitor_capture():
    engine = CaptureEngine(MonitorTarget(0), max_fps=5.0)
    engine.start()

    for i, packet in enumerate(engine.frames()):
        with packet:
            arr = packet.cpu_bgra
            print(f"Frame {packet.frame_id}: shape={arr.shape} "
                  f"keyboard=0x{packet.keyboard_mask:016x}")
            assert arr.shape[2] == 4
            assert arr.shape[0] == packet.height
            assert arr.shape[1] == packet.width
        if i >= 4:
            break

    stats = engine.stats()
    print(f"Stats: {stats}")
    assert stats.frames_accepted >= 5

    engine.stop()
    print("Monitor capture test passed!")


if __name__ == "__main__":
    test_monitor_capture()
