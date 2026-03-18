import os, subprocess, tempfile
from memoir import CaptureEngine, MonitorTarget


def test_record_30_frames():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = os.path.join(tmpdir, "test_session")
        mp4 = base + ".mp4"

        engine = CaptureEngine(
            MonitorTarget(0),
            max_fps=10.0,
            record_width=1280,
            record_height=720,
        )
        engine.start()

        for i, pkt in enumerate(engine.frames()):
            pkt.release()
            if i >= 2:
                break

        info = engine.start_recording(base)
        print(f"Recording to: {info.video_path}")
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
        print(f"Stats: {stats}")
        assert stats.frames_recorded >= 30

        engine.stop()

        assert os.path.isfile(mp4), f"MP4 not found: {mp4}"
        sz = os.path.getsize(mp4)
        print(f"MP4 size: {sz} bytes")
        assert sz > 1000

        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-count_packets", "-show_entries",
                 "stream=nb_read_packets,codec_name,width,height",
                 "-of", "csv=p=0", mp4],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                print(f"ffprobe: {result.stdout.strip()}")
        except FileNotFoundError:
            print("ffprobe not found, skipping detailed verification")

        print("Recording test passed!")


if __name__ == "__main__":
    test_record_30_frames()
