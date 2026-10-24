# Control Center API contracts

All routes are same-origin under `/api`, require the existing signed session cookie for reads, and retain existing CSRF checks for mutations. Floor plan, placement and camera-context mutations require `ADMIN`. Incident actions retain current operator permissions and server transition checks. No camera source URL or credential is returned by these contracts.

## Plans and camera placements

- `GET /api/plans` returns `[{id,name,location_label,has_image,image_width,image_height,revision,placements:[{camera_id,x,y}]}]`.
- `POST /api/plans` (`ADMIN`) accepts `{"name":"North Wing","location_label":"Building A · Level 2"}` and returns the created shape with HTTP 201.
- `PATCH /api/plans/{id}` (`ADMIN`) accepts the same name/location fields and returns the updated plan. Unknown ID returns 404.
- `POST /api/plans/{id}/image?revision={n}&placement_policy=keep|clear` (`ADMIN`) accepts raw PNG/JPEG bytes with `Content-Type: image/png` or `image/jpeg`; maximum 8 MiB and 20 megapixels. Unsupported/undecodable image is 415; oversize is 413; stale revision is 409; missing plan is 404. Storage names are generated. `keep` preserves normalized positions for operator review; `clear` removes the selected plan's placements. Image access is `GET /api/plans/{id}/image` with an authenticated private/no-store response.
- `PUT /api/plans/{id}/placements` (`ADMIN`) accepts `{"revision":1,"placements":[{"camera_id":12,"x":0.25,"y":0.75}]}` and atomically replaces the plan's complete placement set. Coordinates are finite normalized values in `[0,1]`; each camera may be placed once and each camera has at most one plan placement. Unknown cameras and duplicates return 422. A stale plan revision or a camera already placed on another plan returns 409. Camera IDs refer to existing camera records.
- `DELETE /api/plans/{id}` (`ADMIN`) returns 204 and removes its image and placements, while preserving camera and incident records. Replacing plan image preserves normalized coordinates.
- Plan names are labels and may repeat; camera placements are unique across all plans. Revision increments on placement-set save and image replacement. Saving a placement list does not relocate cameras from another plan.

## Optional camera context

- `PUT /api/cameras/{camera_id}/context` (`ADMIN`) accepts nullable/omitted strings: `manufacturer` (120), `model` (120), `specifications` (500), `responsible_contact` (200), and `response_notes` (1000). Empty strings clear a value. Returns the current camera shape; unknown camera returns 404.
- Existing `GET /api/cameras` adds these nullable fields compatibly. `location` remains the camera's existing configured location. A plan's `location_label` is separate context; responsible contact is not incident assignment.

## Reused event contracts

- `GET /api/incidents?limit=50&status=NEW&camera_id=12` uses existing bounded pagination/filter contracts.
- `POST /api/incidents/{id}/action` with `{"status":"ACKNOWLEDGED|RESOLVED|FALSE_ALARM","note":"..."}` writes existing transition/audit history and applies the server's current legal-transition rules. Acknowledge is not resolution.
- `GET /api/incidents/{id}/evidence` serves the historical authenticated snapshot. A missing/expired snapshot is an evidence error, independent from current camera health.
- `GET /api/cameras/{id}/preview` remains the worker-published preview route. Camera health and frame freshness are separate fields.

## Errors and authority

Authentication errors are 401, insufficient role is 403, invalid values/references are 422, missing entities are 404, and existing incident transition conflicts are 409. Incidents remain authoritative in the `incidents` table; plan metadata never creates event records. All timestamps returned by existing incident/camera contracts are canonical UTC; this feature formats them locally for display.
