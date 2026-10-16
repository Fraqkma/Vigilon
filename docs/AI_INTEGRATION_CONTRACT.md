# AI integration contract

`Frame` in `app.adapters` contains image, UTC capture time, original dimensions, increasing sequence, timestamp origin, optional media time, and discontinuity marker. File `media_time` is seconds from the media timeline; live timestamps are capture wall time, while elapsed live rules use monotonic time.

`DetectionResult` in `app.detection` remains the event sink input. The Ultralytics adapter additionally yields a JSON-compatible observation with `source_id`, `session_id`, canonical `label`, original `class_id`/name, score, original-image pixel `xyxy`, optional track ID, module ID, and `simulated: false`. Scores are raw model scores, not calibrated probabilities. Synthetic plugin results retain `simulated: true`.

Package plugins do not write application tables. The worker maps observations through package scenarios to enabled application rules, applies temporal acceptance, pins the triggering frame by copying it into evidence persistence, then calls the existing incident service. Incident deduplication and notification remain application responsibilities. An operator's `RESOLVED` status does not claim scene clearance.

Representative JSON observation: `{"source_id":7,"session_id":"live-7","label":"person","class_id":0,"class_name":"person","score":0.83,"xyxy":[10,20,80,160],"coordinate_space":"original_pixels","track_id":14,"module_id":"people_vehicle","simulated":false}`. Values here illustrate shape only, not model performance.
