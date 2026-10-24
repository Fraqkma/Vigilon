# Fire and smoke model card

Owner: AI 2. Delivery candidate: **baseline_01**, YOLO26s detection, fine-tuned
from pretrained `yolo26s.pt` for 50 epochs at input 640, batch 4, seed 42.
Classes are exactly `0=smoke`, `1=fire`; darkness is out of scope.

## Checkpoint and integrity

Download the owner's trusted checkpoint from
[baseline_01 best.pt](https://drive.google.com/file/d/1AODnz0vKVtCMAnK1BVCy0RndHtOuCNoh/view)
and place it at `models/fire_smoke/weights/best.pt`. Do not commit weights to Git.
Expected SHA-256 from the successful Colab video-test environment:
`685874db1eb4ea3c049b17e8bf6970830603c8eaba93478cf2a67f1da5801cc6`.
This checkout has not downloaded or locally verified that checkpoint. Check its
hash after transfer and run Hub validation before use. A matching hash checks
integrity, not artifact trust. Baseline_02 was not selected because its best
validation mAP50-95 was slightly lower in the single observed run.

## Data and evaluation

D-Fire Kaggle version 1, experimental regrouped baseline_v1: 15,025 train /
3,220 validation / 3,219 test images. Original-resolution images were used;
known similarity components stayed in one partition and all AoF images were
conservatively assigned to train. These components are not verified clip/site
identities. Source independence and semantic annotation review remain incomplete.
Dataset collection declares CC0 but original-provider media terms and web-image
provenance remain unresolved. This is not a rights-cleared production dataset.

Test precision 0.714902, recall 0.652195, mAP50 0.701610, mAP50-95 0.396857.
Fire recall is only 0.573 (rounded logged value). Full conditions, per-class
metrics and repaired JPEG filenames are in `evaluation.json`. Scores are image
object-detection metrics, not event-level safety or alarm performance.

## Runtime and limitations

Observed training/inference environment: Ultralytics 8.4.0, Python 3.13.15,
PyTorch 2.11.0+cu130, NVIDIA RTX PRO 6000 Blackwell Server Edition on Colab.
`tested_versions` records this Ultralytics evidence only. Windows/WSL CPU/CUDA
Hub runtime, target hardware throughput, and target-camera AI integration are
**not validated**. Use the Hub's platform-appropriate runtime dependencies;
do not install the entire Colab package list into the application environment.

Current inference config preserves input 640, confidence 0.25 and CPU default.
These settings are initial integration settings, not calibrated alarm thresholds.
Keep temporal confirmation and incident decisions in Hub-owned scenario rules.

Public-video exploratory testing exposed misses on visible small/window flames,
including a miniature-house clip, and possible smoke false positives. Increasing
inference input to 960 or using a post-selected ROI did not fix that clip.
Private target-camera normal clips and camera-hour false-alert evaluation are
not available. No certified fire-system replacement or deployment-readiness claim.
