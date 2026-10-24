"""Regression: a live RTSP reader drains every packet and converts only one frame per processing slot."""
import time
from types import SimpleNamespace

import numpy as np

from app import worker
from app.adapters import Frame


class FakeLiveStream:
    """Pretends to be a 50 FPS camera. grab() blocks for one frame interval like a real stream."""
    def __init__(self): self.grabbed = 0; self.retrieved = 0; self.closed = False
    def open(self): return True
    def grab(self):
        time.sleep(0.02); self.grabbed += 1; return True
    def retrieve(self):
        self.retrieved += 1
        return Frame(np.zeros((8, 8, 3), np.uint8), time.time(), 8, 8, self.grabbed)
    def read(self): raise AssertionError("live RTSP must not use the sleep-between-reads path")
    def close(self): self.closed = True


def _camera(source_type):
    return SimpleNamespace(id=1, source_type=source_type, last_frame=None, reconnects=0, processed=0, dropped=0,
                           processing_fps=5, reconnect_min_seconds=1, reconnect_max_seconds=2)


def test_rtsp_reader_drains_at_stream_rate_and_emits_at_processing_rate():
    stream = FakeLiveStream()
    runner = worker.SourceRunner(_camera("rtsp"))
    runner.adapter = lambda: stream
    runner.start(); time.sleep(1.0); runner.stop(); runner.join(3)

    assert stream.closed
    assert stream.grabbed >= 35                     # ~50 packets/s pulled, nothing left to back up
    assert 4 <= stream.retrieved <= 7               # ~5 conversions/s = processing_fps
    latest = runner.frames.get_nowait()
    assert stream.grabbed - latest.sequence <= 12   # queued frame is from the newest packets, not the backlog
