# Model handoff checklist

## AI 1: people and vehicles

- Put the approved Ultralytics detection checkpoint at `models/people_vehicle/weights/best.pt`.
- Align every numeric ID/name in `classes.json` to `model.names`; do not assume COCO IDs.
- Configure inference, ByteTrack, scenarios, aliases, zone/line needs, and tested runtime version.
- Complete `MODEL_CARD.md` with provenance, license, training details, limitations, and intended use.
- Complete `evaluation.json` with site/session split, event-level results, false alerts per camera-hour, delay, missed events, hardware, and runtime conditions. Do not enter estimates as results.
- Run metadata validation, trusted local runtime validation, then explicit worker reload. Test two authorized sources to check track isolation.

## AI 2: fire and smoke

- Put the approved Ultralytics detection checkpoint at `models/fire_smoke/weights/best.pt`.
- Align class IDs, labels and scenario requirements with `model.names`.
- Complete model card provenance/license, training details and limitations; record temporally evaluated scenarios and conditions.
- Run metadata validation, trusted local runtime validation, and explicit worker reload. Confirm fire/smoke episode gaps and cooldown on consented/licensed data.

## Shared release gate

Weights alone are not a package. Submit configuration, class mapping, provenance, license, runtime compatibility and evaluation together. Validate packages without changing Hub code. Runtime validation is not accuracy validation; file inference is not physical-camera validation. Only detection checkpoints are accepted by the built-in adapter. Another architecture needs a reviewed adapter. Preserve source files and never send footage or checkpoints to an unapproved service.
