# Model packages

The repository-root packages are resolved independently of the current shell directory. `VIGILON_MODEL_DIR` may point to another package root. Add only team-approved Ultralytics detection checkpoints; `.pt` files execute deserialization code and must come from a trusted owner.

AI 1 places its checkpoint at `models/people_vehicle/weights/best.pt`; AI 2 uses `models/fire_smoke/weights/best.pt`. Before importing a checkpoint, complete that package's class map, scenario configuration, model card, evaluation record, and optionally SHA-256 in the manifest. Never overwrite a teammate's package with a generated template.

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.commands list-models
.\.venv\Scripts\python.exe -m app.commands validate-model people_vehicle --mode metadata
.\.venv\Scripts\python.exe -m app.commands validate-model people_vehicle --mode runtime
.\.venv\Scripts\python.exe -m app.commands reload-model people_vehicle
```

To create a separate, non-overwriting package template for a teammate, run `.\.venv\Scripts\python.exe -m app.commands init-model-package people_vehicle --destination .data\model-staging\people_vehicle`. The command refuses any existing destination and excludes weight/export artifacts. The canonical `models/people_vehicle` and `models/fire_smoke` templates are already present.

Repeat with `fire_smoke`. `reload-model` queues reload for the worker process through the shared handoff directory; the worker validates and warms the package at its next loop boundary. The API exposes `/api/ai/modules`; admin mutations require the existing session and same-origin protections. Visor's live assignment accepts configured RTSP/RTSPS sources. FILE jobs can be created from AI Hub in Visor or with `analyze-video`; input must be beneath `VIGILON_MEDIA_DIR`.

Install AI dependencies separately from the CPU demo with the platform-appropriate PyTorch build first, then `python -m pip install -r requirements-ai.lock`. CPU is the package default. CUDA is selected only when configured and available; otherwise loading fails unless CPU fallback is explicitly enabled. Model caches belong outside the model tree (`TORCH_HOME` may be set to a writable cache directory). No weights download automatically.

`hub-self-test` and generated demo scenarios are SIMULATED. They validate pipeline behavior and do not validate a trained model. `REAL_MODEL_VALIDATED` requires runtime validation against the actual trusted checkpoint. `CAMERA_VALIDATED` requires a separately authorized test with that camera/NVR; neither status is implied by file analysis.

In Compose, set `VIGILON_MODEL_DIR=/models` and mount `./models:/models:ro` into API and worker. Weights remain outside the image and read-only to those processes. Store caches, frame handoff and evidence in their separate writable volumes.
