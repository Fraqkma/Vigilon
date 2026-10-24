# Device photo in Device details

Branch: `feature/device-image` (needs `feature/registry-navigation`). MVP item: camera management.

## What it adds

- The Control Center **Device details** panel shows a rough photo of the selected camera, so an operator can
  recognise the device on site. Clicking the photo opens it at full size.
- Admins see **Add photo** / **Replace photo** and **Remove**. Operators see the photo only.
- Without a photo, the panel shows "No device photo".

## API

- `GET /api/cameras/{id}/device-image`: any signed-in user. Returns 404 when the camera has no photo.
- `POST /api/cameras/{id}/device-image`: admin only. The raw PNG or JPEG is the request body (≤ 8 MiB,
  ≤ 20 megapixels), the same rules as floor-plan images. The image is decoded, EXIF-rotated, shrunk to at
  most 1280 px and re-encoded. Re-encoding also strips EXIF data such as GPS position or phone model.
  Returns `{camera_id, device_image_version}`.
- `DELETE /api/cameras/{id}/device-image`: admin only. Returns 204.
- `GET /api/cameras` now includes `device_image_version` for each camera: the file time in ms, or `null`.
  The browser adds it to the image URL (`?v=`), so a replaced photo is never shown from cache.

Mutations keep the existing same-origin check. A missing camera returns 404, a non-admin 403, and a file that
is not a decodable PNG or JPEG 415.

## Storage

Photos are stored as `<data dir>/device-images/camera-<id>.jpg|png`, next to evidence and floor plans in the
git-ignored data folder. There is no database column and no migration. The write goes to a temporary file
and is then renamed, so a reader never sees a half-written photo.

## Frontend

- `frontend/features/devices.js`:
  - `renderDevice(camera, expanded, esc, formatTime, isAdmin)` adds the photo block.
  - Upload and removal are delegated listeners, so they survive Control Center re-renders.
  - A short-lived override shows the new photo immediately until the next refresh returns the new version.
  - The file loads `features/devices.css` itself.
- `control-center.js`: one call site passes `me.role === 'ADMIN'` to `renderDevice`.

## Limits

- One photo per camera.
- There is no camera delete endpoint today. If one is added, it should also delete `camera-<id>.*`.

## Tests

`backend/tests/test_device_image.py` covers:

- upload, replace and remove
- operators can view
- shrink to 1280 px
- EXIF stripped
- PNG replaces JPEG
- `device_image_version` in `/api/cameras`
- rejection cases: 415, 413, 404, 403, 401, and cross-origin
