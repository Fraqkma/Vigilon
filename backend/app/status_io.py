"""Atomic publication of replaceable module telemetry."""
import json
import os
import tempfile
import time
from pathlib import Path


def write_status(path: Path, body: dict) -> None:
    """Use independent temporary files and bounded Windows sharing retries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(body, stream)
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
