"""End-to-end test: create a colored window, capture + record it,
cycle through colors, verify both live and in the MP4."""

import time

import cv2
import numpy as np
import pytest

from memoir import CaptureEngine, WindowTitleTarget

WINDOW_NAME = "Memoir Color Test 48291"
WINDOW_W, WINDOW_H = 640, 480
TOLERANCE = 35

COLORS = [
    ("red",   (0, 0, 255)),     # BGR
    ("green", (0, 255, 0)),
    ("blue",  (255, 0, 0)),
]

_counter = 0

def fill_window(bgr):
    """Draw solid color with a tiny changing counter in the corner.
    The counter forces WGC to see new content each call and deliver frames."""
    global _counter
    img = np.full((WINDOW_H, WINDOW_W, 3), bgr, dtype=np.uint8)
    # 1px text in corner — invisible to center sampling but triggers WGC
    cv2.putText(img, str(_counter), (2, 12),
                cv2.FONT_HERSHEY_PLAIN, 0.8, tuple(int(c) ^ 1 for c in bgr), 1)
    _counter += 1
    cv2.imshow(WINDOW_NAME, img)
    cv2.waitKey(1)


def sample_center_bgr(frame, size=40):
    """Mean BGR of center region. Works with BGRA and BGR."""
    h, w = frame.shape[:2]
    cy, cx = h // 2, w // 2
    return frame[cy - size:cy + size, cx - size:cx + size, :3].mean(axis=(0, 1))


def drain_frames(engine, bgr, duration_s=1.0):
    """Consume frames for `duration_s`, continuously redrawing the window
    to keep WGC delivering frames. Returns center BGR of each frame."""
    results = []
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        fill_window(bgr)     # force new content → WGC delivers
        cv2.waitKey(10)
        pkt = engine.get_next_frame(50)
        if pkt is None:
            continue
        with pkt:
            results.append(sample_center_bgr(pkt.cpu_bgra))
    return results


@pytest.mark.capture
def test_color_cycle_live_and_recorded(tmp_path):
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, WINDOW_W, WINDOW_H)
    fill_window((128, 128, 128))
    time.sleep(0.5)

    try:
        engine = CaptureEngine(
            WindowTitleTarget(WINDOW_NAME),
            max_fps=10.0,
            record_width=WINDOW_W,
            record_height=WINDOW_H,
        )
        engine.start()

        # Warm up
        drain_frames(engine, (128, 128, 128), 0.5)

        # Start recording and cycle colors
        base = str(tmp_path / "color_test")
        engine.start_recording(base)

        live_results = []
        for name, bgr in COLORS:
            samples = drain_frames(engine, bgr, 1.0)
            if samples:
                live_results.append((name, bgr, samples[-1]))
            else:
                live_results.append((name, bgr, None))

        # Drain a few more frames to flush the pipeline
        drain_frames(engine, COLORS[-1][1], 0.3)

        engine.stop_recording()
        stats = engine.stats()
        engine.stop()

        print(f"\nFrames accepted: {stats.frames_accepted}")
        print(f"Frames recorded: {stats.frames_recorded}")

        # --- Verify live ---
        print("\n=== Live colors ===")
        for name, expected, actual in live_results:
            assert actual is not None, f"No frames captured for {name}"
            print(f"  {name:6s}: expected={expected}, "
                  f"got=[{actual[0]:.0f}, {actual[1]:.0f}, {actual[2]:.0f}]")
            diff = np.abs(np.array(expected, dtype=float) - actual)
            assert diff.max() < TOLERANCE, (
                f"Live {name}: max diff={diff.max():.0f}"
            )

        # --- Verify recorded MP4 ---
        mp4 = base + ".mp4"
        cap = cv2.VideoCapture(mp4)
        assert cap.isOpened()

        recorded = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            recorded.append(sample_center_bgr(frame, 20))
        cap.release()

        print(f"\n=== Recorded {len(recorded)} frames ===")
        assert len(recorded) >= len(COLORS), (
            f"Expected >= {len(COLORS)} recorded frames, got {len(recorded)}"
        )

        for name, expected_bgr, _ in live_results:
            found = any(
                np.abs(np.array(expected_bgr, dtype=float) - f).max() < TOLERANCE
                for f in recorded
            )
            print(f"  {name:6s}: {'FOUND' if found else 'MISSING'}")
            assert found, f"Color {name} not found in recording"

        print("\nColor cycle test passed!")

    finally:
        cv2.destroyAllWindows()
