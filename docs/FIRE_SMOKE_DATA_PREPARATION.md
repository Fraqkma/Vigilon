# Fire/smoke data preparation — AI 2

## Scope and handoff

Detect visible smoke and flames using a YOLO26s pretrained detection checkpoint, then fine-tune on approved task data. Darkness is deferred. AI 2 owns data, labels, training and detector evaluation. Hub owns source-frame preparation, temporal confirmation, zones and repeated-event handling. Application owns incident persistence.

Class order is fixed: `0: smoke`, `1: fire`. It must match CVAT export, dataset YAML, checkpoint names and `models/fire_smoke/classes.json`.

The intended source is 1280x720; model input target is `imgsz=640`. Preserve original dataset images. Training performs its own input preparation; do not permanently stretch source images into squares. Runtime preprocessing and exact tested dependency versions must be agreed with Hub before training a delivery checkpoint. The existing AI dependency pin is not a validated YOLO26 environment.

## Step 1: register and approve data

Copy `docs/templates/fire_smoke_sources.csv` into ignored `data/fire_smoke/source_registry.csv`. Record each source before importing it. Do not put private locations, credentials or footage into tracked documentation.

For each source record:

- Original URL or authorized local reference, owner and retrieval date.
- Dataset and underlying media rights, including training, redistribution and attribution conditions. An accessible download or repository code license alone does not establish media rights.
- Clip/site/session grouping, relevant classes and whether annotations exist.
- Approval status: `PENDING`, `APPROVED` or `REJECTED`. Only approved sources enter the dataset.

Use a separate private working tree under ignored `data/fire_smoke/`:

```text
source_registry.csv
raw/                    # Unmodified approved source media
annotations/            # CVAT exports and review records
splits/                 # Group-to-split assignments and image manifests
dataset/images/train/
dataset/images/val/
dataset/images/test/
dataset/labels/train/
dataset/labels/val/
dataset/labels/test/
```

These directories contain local data, not files to commit. No media or weights have been collected by creating this guide.

## Step 2: define and review labels

- `smoke`: visible smoke; box the visible plume, excluding clearly unrelated background. Include a partially visible plume when its identity is sufficiently clear.
- `fire`: visible flames; do not box the entire illuminated room, glow or unrelated reflection.
- Label both classes when both are visible. Apply one consistent policy to connected versus separate regions; review ambiguous examples together before scaling annotation.
- Uncertain smoke versus steam/dust examples require review, not invented certainty.
- Include reviewed negative frames with no target instances. Their YOLO labels are empty; do not add a `normal` class.
- Include difficult negatives such as steam, dust, orange lamps, reflections and screens. Verify that they actually contain no visible target before assigning empty labels.
- Review a small pilot batch together before annotating the full collection. Import class IDs explicitly; check the exported mapping instead of assuming CVAT order.

## Step 3: prevent data leakage

Assign splits by original clip/site/session before frame extraction or augmentation. All related frames and transformed copies stay in the same split. Group duplicate or republished copies together. Reserve whole unseen locations for testing where data permits.

A provisional 70/15/15 train/validation/test allocation is a planning aid, not an acceptance criterion. Count independent groups and class coverage as well as images; never break grouping to reach an exact ratio. Record assignments and seed. Use validation for tuning and keep test untouched until the selected run is evaluated.

## Step 4: pilot dataset gate

Before a full training run, verify:

- Rights and provenance are recorded for every included group.
- Class mapping is exactly smoke then fire.
- Boxes align with original images, with valid normalized YOLO coordinates.
- Missing/unreviewed labels are distinguishable from reviewed empty labels.
- Both target classes and representative negatives are covered; record missing conditions.
- No related group crosses splits.
- Dataset version, image/group counts, label policy and split manifest are recorded.

First milestone: an approved, reviewed pilot dataset and a reproducible GPU environment. No accuracy, capacity or real-model validation is claimed at this stage.

## Later delivery

Deliver trusted `best.pt` privately to `models/fire_smoke/weights/best.pt`, with the matching class map, inference configuration, tested runtime versions, completed model card and evaluation record. Keep weights and source media out of Git. Do not change Hub-owned scenario rules as part of data preparation.

Report per-class detection metrics and observed errors; evaluate episode false alerts, misses and delay jointly with Hub using its agreed temporal rules. Include hardware, resolution and throughput conditions. Do not stage unsafe fires to create training footage.
