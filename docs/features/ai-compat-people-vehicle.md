# AI compatibility fixes: people/vehicle package, tracking, RTSP freshness

Branch: `fix/ai-compat-people-vehicle` (based on `main`, independent). Areas: compatibility and AI.

## Problems found while testing on the team setup

1. **ByteTrack could not start offline.** The people/vehicle `tracker.yaml` uses ByteTrack, which imports `lap`.
   `lap` was missing from `requirements-ai.lock`, so Ultralytics tried to `pip install` it at runtime. That
   fails without internet or permission, and the module stays unusable.
2. **Duplicate or wrong events.** One `ScenarioEvaluator.update()` call can return ENTRY, LINE_CROSSING and DWELL
   candidates together. Every scenario published any candidate, so a ZONE_ENTRY rule also produced a timer-based
   DWELL event under its own name. Untracked boxes (no `track_id`) all shared one state key and could trigger
   entry or crossing for the wrong object.
3. **"Fresh" RTSP frames were seconds old.** The worker slept between reads, so packets queued up inside FFmpeg.
   UDP transport also dropped packets, which causes HEVC "Could not find ref with POC" warnings.
4. **Windows preview errors.** `os.replace` fails while the API process has the preview JPEG open, which skipped
   the frame and AI for that frame.

## Fixes

- `requirements-ai.lock`: `lap==0.5.13`.
- `backend/app/scenario_rules.py`:
  - `keep_candidate`: each event type publishes only its own kind.
  - `dwell_for`: the dwell timer applies only to DWELL and presence events.
  - `needs_track`: track-based rules ignore untracked boxes.
  - These are used in LIVE (`worker.py`), FILE jobs (`file_jobs.py`) and the CLI (`commands.py`), so all three
    behave the same way.
- `backend/app/adapters.py` and `worker.py`:
  - RTSP over TCP by default. An operator-set `OPENCV_FFMPEG_CAPTURE_OPTIONS` still takes precedence.
  - Live RTSP is drained at the camera's frame rate with `grab()`, and only one frame per processing slot is
    converted with `retrieve()`.
  - The file and synthetic paths are unchanged.
- `worker.py`: preview and manifest writes retry briefly on a Windows `PermissionError`.
- `models/people_vehicle/`: metadata now matches the official COCO-pretrained YOLO26 baseline:
  - COCO classes person, bicycle, car, motorcycle, bus and truck
  - `conf 0.35`
  - `device: cpu`, which works on every team PC
  - `tested_versions ["8.4.0"]`
  - The official sha256 values are kept as comments, ready to pin on the demo machine.
  - The weights (`.pt`) are not in Git.

## Tests

- `backend/tests/test_scenario_event_kinds.py`:
  - zone entry publishes one ENTRY and no DWELL
  - line crossing publishes only the crossing
  - DWELL waits for its own seconds
  - fire/smoke presence still confirms through the timer
  - untracked boxes are skipped only for track rules
- `backend/tests/test_rtsp_drain.py`: RTSP drains at the stream rate and emits at the processing rate.
- `backend/tests/test_preview_handoff.py`: a locked manifest is retried, and a locked old JPEG is tolerated.

Run the backend tests before placing real `.pt` weights. Three existing AI Hub tests expect `MISSING_WEIGHTS`.
