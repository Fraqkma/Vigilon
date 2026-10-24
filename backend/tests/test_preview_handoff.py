"""Regression: a briefly locked handoff file (Windows PermissionError) must not drop the frame."""
from pathlib import Path

import numpy as np

from app import worker
from app.adapters import Frame


def test_locked_manifest_is_retried_and_old_jpeg_lock_is_tolerated(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "HANDOFF_DIR", tmp_path)
    real_replace, real_unlink = Path.replace, Path.unlink
    calls = {"replace": 0}

    def flaky_replace(self, target):
        # Simulate the API holding camera-9.json open for the first two attempts.
        if Path(target).suffix == ".json" and calls["replace"] < 2:
            calls["replace"] += 1
            raise PermissionError("locked by reader")
        return real_replace(self, target)

    def locked_unlink(self, missing_ok=False):
        raise PermissionError("jpeg being served")

    monkeypatch.setattr(Path, "replace", flaky_replace)
    image = np.zeros((72, 128, 3), dtype=np.uint8)
    for seq in range(1, 5):
        if seq == 4:
            monkeypatch.setattr(Path, "unlink", locked_unlink)   # cleanup of the oldest JPEG is blocked
        worker.write_preview(9, Frame(image, 0.0, 128, 72, seq), "real", 640)
    monkeypatch.setattr(Path, "unlink", real_unlink)

    assert calls["replace"] == 2                                   # retried, not raised
    assert '"sequence": 4' in (tmp_path / "camera-9.json").read_text()
    assert (tmp_path / "camera-9-4.jpg").is_file()
