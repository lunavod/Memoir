import os, time
from memoir_capture import CaptureEngine, MonitorTarget

output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "recordings")
os.makedirs(output_dir, exist_ok=True)
base = os.path.join(output_dir, "monitor_10s")

engine = CaptureEngine(
    MonitorTarget(0),
    max_fps=10.0,
    record_width=1920,
    record_height=1080,
)
engine.start()

info = engine.start_recording(base)
print(f"Recording to: {info.video_path}")

start = time.time()
count = 0
for pkt in engine.frames():
    pkt.release()
    count += 1
    elapsed = time.time() - start
    if elapsed >= 10.0:
        break

engine.stop_recording()
engine.stop()

stats = engine.stats()
print(f"Recorded {stats.frames_recorded} frames in {time.time() - start:.1f}s")
print(f"Output: {os.path.abspath(info.video_path)}")
