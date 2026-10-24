# Event action: enlarge the selected event, then choose the action

Branch: `feature/event-action-evidence` (based on `main`, independent of the other feature branches).
MVP items: acknowledge / resolve, with evidence the operator can actually read.

## What it changes

In Control Center, selecting an item in the **Event list** fills the **Event action** panel:

1. The snapshot is shown larger (up to 240 px in the panel, 58 % of the screen height when the panel is
   expanded) with the detected area outlined and labelled, for example `SIMULATED SMOKE FIRE` or
   `person 82%`.
2. Clicking the snapshot, or **Enlarge & choose action**, opens a review dialog with:
   - the same event enlarged, using most of the screen
   - the facts: camera, first and last seen, status, confidence
   - the actions: **Acknowledge**, **Resolve**, **False alarm** and the operator note
   - the operator history
3. Choosing an action in the dialog saves it and closes the dialog. Esc, **Close** or a click on the dimmed
   background closes without acting.

The note typed in the panel is carried into the dialog and back, so nothing typed is lost. Control Center's
7 s refresh pauses while the dialog is open, so the image does not jump while someone is reviewing it.

## How

- `frontend/features/incidents.js`:
  - `renderDetail` adds the zoomable evidence and the review `<dialog>`. The actions keep the existing
    `data-action` / `data-action-note` contract, so `control-center.js` is unchanged.
  - New `evidenceBox(incident)` returns the detected area, normalised `[x1,y1,x2,y2]`, or `null` when it
    cannot be placed honestly.
  - New `renderEvidence(incident, esc)` is the read-only view for other pages, such as Event Logs.
  - The click and input wiring is delegated once, so it survives every Control Center re-render.
  - The file loads `features/incidents.css` itself.
- The box is drawn with percentage positions inside a wrapper the size of the image (no canvas), so it stays
  aligned at every size.
- `backend/app/services/incident_service.py` also stores `frame_size: [width, height]` in incident metadata.
  Real detections store pixel `xyxy`, and the frame size is what turns that into a position on the picture.
  Older incidents without it show "No detection box recorded" instead of a guessed box.

## Tests

- `frontend/features/incidents.test.js` (`node --test`):
  - box from normalised or pixel geometry
  - no box without a frame size, or for a broken box
  - the same actions in the panel and the dialog
  - escaping
  - terminal and no-snapshot states
- `backend/tests/test_event_action.py`: `frame_size` is recorded and returned by `/api/incidents`.

## Possible follow-up

To open the review dialog immediately on every click in the Event list, add one `showModal()` call in the
Event list click handler in `control-center.js`. It was left out so a quick scan of the list stays one click
per item.
