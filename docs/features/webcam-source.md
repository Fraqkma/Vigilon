# Local webcam source

Branch: `feature/webcam-source` (based on `main`, independent). Area: compatibility.

## Why

The team has one RTSP camera. A USB or built-in webcam lets anyone test rules, zones, alerts and AI modules
on their own laptop with a live picture, without the RTSP camera and without fake (SIMULATED) frames.

## What it adds

- **Live Monitoring → Add camera → Source type: Local webcam (worker computer)**, with a device index:
  `0` is the first camera, `1` the second, and so on, up to `9`. Leaving it blank means `0`.
- The ingestion worker opens the device with OpenCV (DirectShow on Windows), keeps a one-frame buffer for low
  latency, and publishes previews exactly like an RTSP camera. Browsers never access the webcam directly.
- The connectivity test and live AI module assignment accept webcams as well as RTSP/RTSPS.
- Webcam frames are real camera input. They are not labelled SIMULATED, and simulated scenarios cannot be
  enabled on them.

## Rules (security)

- Only an integer from `0` to `9` is accepted. Device paths (`/dev/video0`), URLs and any other text return 422.
- Creating or changing a camera stays admin-only.
- `AGENTS.md` and `docs/CAMERA_COMPATIBILITY.md` are updated: live modules may be assigned to RTSP/RTSPS or
  local webcam sources.

## Code

- `backend/app/webcam_adapter.py`: `parse_webcam_index` and `WebcamAdapter` (same `open/read/close` interface
  as `OpenCVAdapter`).
- `backend/app/main.py`: the source type is accepted in create, update, connectivity test and module assignment.
- `backend/app/worker.py`: `SourceRunner.adapter()` builds a `WebcamAdapter`.
- `frontend/app.js`: the webcam option and device-index hint in the camera form, and the module assignment
  panel for webcams.

## Limits

- Works only when the worker runs on the computer the webcam is plugged into. It does not work inside Docker
  Desktop, which has no access to host webcams on Windows or macOS.
- Not tested against physical webcam hardware in CI. To try it, run the worker natively, add a webcam source
  with index `0`, then press **Test connection**.

## Tests

`backend/tests/test_webcam_source.py`:

- index validation, including path and injection strings
- create with an explicit or default index
- 422 for bad input or a simulated scenario
- assignment gate (409 without a ready module)
- admin only
- the worker builds the adapter without opening the device
