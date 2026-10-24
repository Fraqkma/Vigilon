"""Stdlib tests; no model or camera is loaded."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.status_io import write_status


class StatusIOTests(unittest.TestCase):
    def test_worker_telemetry_failure_does_not_escape_into_inference_job(self):
        from app.ai_hub import report_worker_status
        with patch("app.ai_hub.write_status", side_effect=PermissionError("locked")):
            with self.assertLogs("app.ai_hub", level="WARNING") as logs:
                report_worker_status(None, module_id="fire_smoke", status="RUNNING")
        self.assertIn("module_status_publish_failed", logs.output[0])

    def test_transient_windows_sharing_failure_retries(self):
        import os
        replace = os.replace
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "status.json"
            with patch("app.status_io.os.replace") as mocked:
                # Perform the real replace on the successful retry.
                def attempt(source, destination):
                    if mocked.call_count == 1:
                        raise PermissionError()
                    replace(source, destination)
                mocked.side_effect = attempt
                with patch("app.status_io.time.sleep"):
                    write_status(target, {"processed": 899})
                self.assertEqual(mocked.call_count, 2)
            self.assertEqual(json.loads(target.read_text()), {"processed": 899})
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_persistent_denial_preserves_previous_status_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "status.json"
            target.write_text('{"processed": 1}')
            with patch("app.status_io.os.replace", side_effect=PermissionError()) as mocked:
                with patch("app.status_io.time.sleep"), self.assertRaises(PermissionError):
                    write_status(target, {"processed": 899})
                self.assertEqual(mocked.call_count, 4)
            self.assertEqual(json.loads(target.read_text()), {"processed": 1})
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_writers_get_distinct_temporary_paths(self):
        import os
        replace = os.replace
        paths = []
        def publish(source, destination):
            paths.append(source)
            replace(source, destination)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "status.json"
            with patch("app.status_io.os.replace", side_effect=publish):
                write_status(target, {"processed": 1})
                write_status(target, {"processed": 2})
            self.assertNotEqual(paths[0], paths[1])


if __name__ == "__main__":
    unittest.main()
