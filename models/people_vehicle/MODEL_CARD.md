# People and vehicle model card

Status: **baseline package** — official pretrained checkpoint, no team fine-tuning yet. Owner of the fine-tuned replacement: AI 1.

## Checkpoint

- Architecture: Ultralytics YOLO26s, task `detect`, input 640 (letterboxed by Ultralytics).
- Source: official Ultralytics release asset `yolo26s.pt` (tag v8.4.0), renamed to `weights/best.pt`. SHA-256 recorded in `manifest.yaml`.
- Training data: COCO (80 classes) by Ultralytics. `classes.json` mirrors all 80 checkpoint names exactly; `inference.yaml` keeps only person, bicycle, car, motorcycle, bus and truck.
- License: Ultralytics models are AGPL-3.0. A commercial or closed-source product needs an Ultralytics Enterprise License or a model with a permissive license. Raise this before claiming commercial deployment.

## Intended use and limits

- Operator review aid for zone entry, directional line crossing and dwell on authorized cameras. Not an identity system: track IDs are temporary and per camera.
- Not evaluated on the team's own camera angles yet. `evaluation.json` stays `NOT_PROVIDED` until event-level results on held-out clips exist.
- Known weak spots to measure: small/far objects, night IR footage, heavy occlusion, people partly hidden behind vehicles, low processing FPS (tracking IDs switch more when objects move far between processed frames).
