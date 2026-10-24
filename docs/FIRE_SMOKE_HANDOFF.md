# Fire/smoke model handoff

Delivery date: 2026-10-24. Owner: AI 2. Training work is stopped at the user's
request; baseline_01 is the experimental integration candidate. No local model
load, target-camera AI validation or deployment approval is implied.

## Minimal repository package

`models/fire_smoke/` contains `manifest.yaml`, `classes.json`, `inference.yaml`,
`scenarios.yaml`, `MODEL_CARD.md`, `evaluation.json`, `training_args.yaml`,
`test_metrics.csv`, and the empty weight directory marker. Commit metadata and
this handoff only. The classes remain `0: smoke`, `1: fire`.

Get `runs/baseline_01/weights/best.pt` from the owner Drive link in the model card
and place it at `models/fire_smoke/weights/best.pt` on each Hub machine. `.pt` is
ignored and must not be force-added to Git. The manifest pins an expected hash;
verify it after downloading the trusted owner artifact. Do not substitute
baseline_02, last.pt, or a generic pretrained checkpoint.

The report and provenance are condensed into the model card and evaluation JSON.
Full datasets, run outputs, public clips and notebooks remain local/Drive assets,
not application source. Historical research source/docs/notebooks were archived
before cleanup to ignored `.data/fire_smoke_archive_20261024/research_archive.zip`
with a per-file checksum manifest. Original source ZIP and baseline dataset are
retained locally. This archive is a local recovery copy, not part of a Git clone.

## Recorded result

Baseline_01 validation best epoch 48: mAP50 0.69761, mAP50-95 0.39891 in training
CSV. Final best-checkpoint validation evaluation differs slightly and is recorded
separately in evaluation.json. Test: precision 0.7149016861, recall 0.6521950529,
mAP50 0.7016098589, mAP50-95 0.3968566750. Class values are rounded from the log.
Baseline_02 best validation mAP50-95 0.39575 did not improve the single-run result.
No significance or causal claim is made. Test and source-independence limitations
are explicit in the package. Rights review is unresolved; this is a prototype
handoff, not production clearance.

## Hub integration sequence (next owner: Hub + AI 2)

The latest team main pins Ultralytics 8.4.0 and fixes BGR NumPy input handling.
Install platform-appropriate PyTorch/torchvision in the application environment,
then the current `requirements-ai.lock`, and check package compatibility. Keep
CPU default initially; selecting CUDA must be explicit and tested on that host.
Do not transplant Colab's entire package list or claim Python 3.10 compatibility
before testing the actual package.

From repository root in PowerShell after environment setup and checkpoint copy:

```powershell
Get-FileHash models/fire_smoke/weights/best.pt -Algorithm SHA256
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.commands validate-model fire_smoke --mode metadata
.\.venv\Scripts\python.exe -m app.commands validate-model fire_smoke --mode runtime
.\.venv\Scripts\python.exe -m app.commands reload-model fire_smoke
```

On WSL use `.venv/bin/python` and `PYTHONPATH=backend` with the same command
arguments. Do not mix Windows and Linux virtual environments. Reload should be
requested only after successful trusted-weight runtime validation. Then test one
authorized local video before assigning the module to an authorized camera.
Keep observation, temporal confirmation and incident persistence separate.

Research boundary: the public house6 diagnostic found early visible flame misses;
normal target-camera recordings are unavailable. No private camera footage was
uploaded or automatically captured. Hub owns recording/integration and event
confirmation. AI 2 supplies this model, class map, provenance and evaluation.
