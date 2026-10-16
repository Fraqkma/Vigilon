"""Local, explicit model package catalog and Ultralytics detection runtime."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = Path(os.getenv("VIGILON_MODEL_DIR", ROOT / "models")).expanduser().resolve()
HANDOFF_ROOT = Path(os.getenv("VIGILON_HANDOFF_DIR", ROOT / ".data" / "frames")).expanduser().resolve()
BUILTINS = {"people_vehicle", "fire_smoke"}
STATUSES = {"MISSING_WEIGHTS", "INVALID_CONFIG", "UNSUPPORTED_MODEL", "DEPENDENCY_MISSING", "READY", "LOADING", "RUNNING", "ERROR", "DISABLED"}


class PackageError(ValueError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def _mapping(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PackageError("INVALID_CONFIG", f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise PackageError("INVALID_CONFIG", f"{path.name} must contain a YAML mapping")
    return value


def _contained(base: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise PackageError("INVALID_CONFIG", f"{label} path is required")
    result = (base / relative).resolve()
    if not result.is_relative_to(base.resolve()):
        raise PackageError("INVALID_CONFIG", f"{label} path escapes the model package")
    return result


@dataclass
class ModelPackage:
    module_id: str
    directory: Path
    manifest: dict
    inference: dict
    classes: dict[int, str]
    original_classes: dict[int, str]
    scenarios: dict
    scenario_defaults: dict
    tracker: dict | None
    weights: Path
    status: str
    error: str | None = None
    runtime: Any = None
    lock: threading.RLock = field(default_factory=threading.RLock)
    latency_ms: float = 0.0
    processed: int = 0
    trackers: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {"module_id": self.module_id, "package_version": self.manifest.get("package_version"),
                "adapter_id": self.manifest.get("adapter_id"), "status": self.status, "error": self.error,
                "weights_path": str(self.weights), "metadata_valid": self.status not in ("INVALID_CONFIG",),
                "runtime_validated": self.status in ("READY", "RUNNING"),
                "supported_events": self.manifest.get("supported_events", []),
                "latency_ms": round(self.latency_ms, 2), "processed": self.processed}


def package_directory(module_id: str) -> Path:
    if module_id not in BUILTINS:
        raise PackageError("INVALID_CONFIG", f"Unknown built-in module {module_id!r}")
    root = MODEL_ROOT.resolve()
    directory = (root / module_id).resolve()
    if not directory.is_relative_to(root):
        raise PackageError("INVALID_CONFIG", "Model package path escapes model root")
    return directory


def inspect_package(module_id: str) -> ModelPackage:
    directory = package_directory(module_id)
    manifest_path = directory / "manifest.yaml"
    manifest = _mapping(manifest_path)
    required = {"schema_version", "module_id", "package_version", "adapter_id", "task", "runtime", "weights", "inference", "classes", "scenarios", "supported_events", "model_card", "evaluation"}
    missing = sorted(required - manifest.keys())
    if missing:
        raise PackageError("INVALID_CONFIG", "manifest missing: " + ", ".join(missing))
    if manifest["schema_version"] != 1 or manifest["module_id"] != module_id or manifest["task"] != "detect":
        raise PackageError("INVALID_CONFIG", "schema_version/module_id/task must identify a schema-1 detection package")
    allowed = {"people_vehicle": "vigilon.ultralytics.people_vehicle", "fire_smoke": "vigilon.ultralytics.fire_smoke"}
    if manifest["adapter_id"] != allowed[module_id]:
        raise PackageError("INVALID_CONFIG", "adapter_id does not match the reviewed built-in adapter")
    runtime=manifest["runtime"]
    if not isinstance(runtime,dict) or set(runtime)-{"framework","tested_versions","minimum_version"} or runtime.get("framework")!="ultralytics" or not isinstance(runtime.get("tested_versions"),list) or not isinstance(runtime.get("minimum_version"),str):
        raise PackageError("INVALID_CONFIG", "runtime must declare ultralytics, minimum_version, and tested_versions")
    if not isinstance(manifest["package_version"],str) or not manifest["package_version"] or not isinstance(manifest["supported_events"],list) or not manifest["supported_events"] or any(not isinstance(event,str) or not event for event in manifest["supported_events"]) or len(set(manifest["supported_events"]))!=len(manifest["supported_events"]):
        raise PackageError("INVALID_CONFIG", "package_version and unique supported_events are required")
    versions=[runtime["minimum_version"],*runtime["tested_versions"]]
    if any(not isinstance(version,str) or not re.fullmatch(r"\d+(?:\.\d+)*(?:[a-zA-Z0-9.+-]*)",version) for version in versions):
        raise PackageError("INVALID_CONFIG", "runtime versions must be valid version strings")
    files = {}
    for key in ("weights", "inference", "classes", "scenarios", "model_card", "evaluation"):
        value = manifest[key]
        rel = value.get("path") if isinstance(value, dict) else value
        files[key] = _contained(directory, rel, key)
    tracker = None
    if manifest.get("tracker"):
        if not isinstance(manifest["tracker"],dict):raise PackageError("INVALID_CONFIG","tracker must be a package-relative path mapping")
        tracker_path = _contained(directory, manifest["tracker"].get("path"), "tracker")
        tracker = _mapping(tracker_path)
    for key in ("model_card", "evaluation"):
        if not files[key].is_file():
            raise PackageError("INVALID_CONFIG", f"{key} file is missing: {files[key].name}")
    try:
        evaluation=json.loads(files["evaluation"].read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:raise PackageError("INVALID_CONFIG",f"evaluation.json must be valid JSON: {exc}") from exc
    if not isinstance(evaluation,dict) or evaluation.get("status") not in ("NOT_PROVIDED","PROVIDED"):
        raise PackageError("INVALID_CONFIG","evaluation.json status must be NOT_PROVIDED or PROVIDED")
    infer = _mapping(files["inference"])
    if set(infer) - {"imgsz", "conf", "iou", "classes", "device", "allow_cpu_fallback"}:
        raise PackageError("INVALID_CONFIG", "inference.yaml has unsupported fields")
    if not isinstance(infer.get("imgsz"), int) or not 32 <= infer["imgsz"] <= 4096 or not 0 < float(infer.get("conf", 0)) < 1 or not 0 < float(infer.get("iou", 0)) <= 1:
        raise PackageError("INVALID_CONFIG", "imgsz, conf, or iou is outside supported bounds")
    if infer.get("device") not in ("cpu", "cuda", "auto") or not isinstance(infer.get("allow_cpu_fallback"), bool):
        raise PackageError("INVALID_CONFIG", "device must be cpu/cuda/auto and allow_cpu_fallback a boolean")
    if infer.get("classes") is not None and (not isinstance(infer["classes"],list) or any(not isinstance(x,int) or isinstance(x,bool) for x in infer["classes"])):
        raise PackageError("INVALID_CONFIG", "inference classes must be null or a list of checkpoint class IDs")
    try:
        classes_json = json.loads(files["classes"].read_text(encoding="utf-8"))
        classes = {int(k): str(v["label"] if isinstance(v, dict) else v) for k, v in classes_json.items()}
        original_classes = {int(k): str(v.get("original_name", v["label"]) if isinstance(v, dict) else v) for k, v in classes_json.items()}
    except Exception as exc:
        raise PackageError("INVALID_CONFIG", f"classes.json must map integer IDs to labels: {exc}") from exc
    labels = list(classes.values())
    if not classes or len(set(labels)) != len(labels) or any(not x for x in labels):
        raise PackageError("INVALID_CONFIG", "classes.json must contain unique nonempty labels")
    if infer.get("classes") is not None and not set(infer["classes"])<=set(classes):
        raise PackageError("INVALID_CONFIG", "inference classes contains an ID missing from classes.json")
    scenarios = _mapping(files["scenarios"])
    if set(scenarios) - {"scenarios", "defaults"} or not isinstance(scenarios.get("scenarios"), dict):
        raise PackageError("INVALID_CONFIG", "scenarios.yaml requires a scenarios mapping")
    defaults=scenarios.get("defaults",{})
    allowed_defaults={"anchor","minimum_observation_seconds","disappearance_grace_seconds","cooldown_seconds","aggregation"}
    if not isinstance(defaults,dict) or set(defaults)-allowed_defaults or defaults.get("anchor","bottom_center") not in ("bottom_center","center") or defaults.get("aggregation","per_camera_event")!="per_camera_event":
        raise PackageError("INVALID_CONFIG", "scenario defaults contain unsupported fields or anchor")
    for numeric in ("minimum_observation_seconds","disappearance_grace_seconds","cooldown_seconds"):
        if numeric in defaults and (isinstance(defaults[numeric],bool) or not isinstance(defaults[numeric],(int,float)) or not math.isfinite(defaults[numeric]) or defaults[numeric]<0):raise PackageError("INVALID_CONFIG",f"scenario defaults have invalid {numeric}")
    allowed_scenario={"event_type","required_classes","class_mode","minimum_observation_seconds","disappearance_grace_seconds","cooldown_seconds","first_appearance_inside","direction","hysteresis_pixels","dwell_seconds"}
    declared = set(manifest["supported_events"])
    for name, cfg in scenarios["scenarios"].items():
        if not isinstance(cfg, dict) or set(cfg)-allowed_scenario or cfg.get("event_type") not in declared or not set(cfg.get("required_classes", [])) <= set(labels) or not cfg.get("required_classes") or cfg.get("class_mode","any") not in ("any","all") or cfg.get("direction","A_TO_B") not in ("A_TO_B","B_TO_A") or cfg.get("first_appearance_inside","ignore")!="ignore":
            raise PackageError("INVALID_CONFIG", f"scenario {name!r} has unsupported event or class requirements")
        for numeric in ("minimum_observation_seconds","disappearance_grace_seconds","cooldown_seconds","hysteresis_pixels","dwell_seconds"):
            if numeric in cfg and (isinstance(cfg[numeric],bool) or not isinstance(cfg[numeric],(float,int)) or not math.isfinite(cfg[numeric]) or cfg[numeric]<0):raise PackageError("INVALID_CONFIG",f"scenario {name!r} has invalid {numeric}")
    if tracker is not None:
        allowed_tracker={"tracker_type","track_high_thresh","track_low_thresh","new_track_thresh","track_buffer","match_thresh","fuse_score"}
        if set(tracker)-allowed_tracker or tracker.get("tracker_type")!="bytetrack" or not 0<=float(tracker.get("track_low_thresh",-1))<=float(tracker.get("track_high_thresh",-1))<=1 or not 0<=float(tracker.get("new_track_thresh",-1))<=1 or not 0<=float(tracker.get("match_thresh",-1))<=1 or not isinstance(tracker.get("track_buffer"),int) or not isinstance(tracker.get("fuse_score"),bool):
            raise PackageError("INVALID_CONFIG", "tracker.yaml does not match the supported ByteTrack schema")
    weights = files["weights"]
    expected = manifest["weights"].get("sha256") if isinstance(manifest["weights"], dict) else None
    if expected is not None and (not isinstance(expected,str) or not re.fullmatch(r"[0-9a-fA-F]{64}",expected)):
        raise PackageError("INVALID_CONFIG", "weights sha256 must be a 64-character hexadecimal digest")
    if not weights.is_file():
        return ModelPackage(module_id, directory, manifest, infer, classes, original_classes, scenarios["scenarios"], scenarios.get("defaults",{}), tracker, weights, "MISSING_WEIGHTS", "Place the team-approved detection checkpoint at this path.")
    if expected:
        hasher=hashlib.sha256()
        with weights.open("rb") as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b""):hasher.update(chunk)
        digest = hasher.hexdigest()
        if digest.lower() != expected.lower():
            raise PackageError("INVALID_CONFIG", "weights SHA-256 does not match manifest")
    return ModelPackage(module_id, directory, manifest, infer, classes, original_classes, scenarios["scenarios"], scenarios.get("defaults",{}), tracker, weights, "LOADING")


class UltralyticsDetectionAdapter:
    """Detection-only adapter. One model runtime is shared under a lock."""
    def __init__(self, package: ModelPackage): self.package = package

    def load(self) -> ModelPackage:
        p = self.package
        if p.status == "MISSING_WEIGHTS": return p
        try:
            import ultralytics
            from ultralytics import YOLO
            from packaging.version import Version
        except ImportError:
            p.status, p.error = "DEPENDENCY_MISSING", "Install the optional AI runtime from requirements-ai.lock"
            return p
        try:
            minimum=Version(str(p.manifest.get("runtime",{}).get("minimum_version","0")))
            installed=Version(str(getattr(ultralytics,"__version__","0")))
            if installed < minimum:
                raise PackageError("DEPENDENCY_MISSING",f"Ultralytics {minimum} or newer is required; found {installed}")
            import numpy as np
            model = YOLO(str(p.weights))
            if getattr(model, "task", None) != "detect":
                raise PackageError("UNSUPPORTED_MODEL", f"Checkpoint task is {getattr(model, 'task', 'unknown')!r}; only detect is supported")
            names = model.names
            names = {int(k): str(v) for k, v in names.items()} if isinstance(names, dict) else dict(enumerate(map(str, names)))
            if names != p.original_classes:
                raise PackageError("INVALID_CONFIG", f"Checkpoint class map {names} does not match classes.json original_name mapping {p.original_classes}")
            device = p.inference.get("device", "cpu")
            if device == "auto": device = "cuda" if self._cuda_available() else "cpu"
            if device == "cuda" and not self._cuda_available():
                if p.inference.get("allow_cpu_fallback"): device = "cpu"
                else: raise PackageError("DEPENDENCY_MISSING", "CUDA requested but unavailable; install a CUDA-enabled PyTorch build or allow CPU fallback")
            model.predict(np.zeros((64, 64, 3), dtype=np.uint8), imgsz=p.inference["imgsz"], conf=p.inference["conf"], iou=p.inference["iou"], device=device, verbose=False)
            p.inference = {**p.inference, "device": device}
            p.runtime, p.status, p.error = (model, "READY", None)
        except PackageError as exc: p.status, p.error = exc.status, str(exc)
        except Exception as exc: p.status, p.error = "UNSUPPORTED_MODEL", f"Could not load detection checkpoint: {type(exc).__name__}: {exc}"
        return p

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
            return bool(torch.cuda.is_available())
        except ImportError: return False

    def detect(self, image, session_id: str, source_id: int) -> list[dict]:
        import time
        p = self.package
        if p.status not in ("READY", "RUNNING") or p.runtime is None: return []
        import cv2
        import numpy as np
        bgr = np.asarray(image)
        if bgr.ndim == 3 and bgr.shape[2] == 3: rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        else: raise ValueError("Expected a three-channel BGR frame")
        conf = p.inference["conf"]; iou = p.inference["iou"]
        selected = p.inference.get("classes")
        started = time.perf_counter()
        with p.lock:
            result = p.runtime.predict(rgb, imgsz=p.inference["imgsz"], conf=conf, iou=iou, classes=selected, device="cpu" if p.inference.get("device") == "auto" else p.inference.get("device", "cpu"), verbose=False)[0]
            boxes = result.boxes
            rows = []
            if boxes is not None:
                xyxy = boxes.xyxy.cpu().numpy(); ids = boxes.cls.int().cpu().tolist(); scores = boxes.conf.cpu().tolist()
                track_ids = {}
                if p.tracker is not None and len(ids):
                    # One BYTETracker per (job/source), never shared across cameras.
                    from types import SimpleNamespace
                    from ultralytics.trackers.byte_tracker import BYTETracker
                    tracker = p.trackers.get((session_id, source_id))
                    if tracker is None:
                        tracker = BYTETracker(SimpleNamespace(**p.tracker), frame_rate=30)
                        p.trackers[(session_id, source_id)] = tracker
                    tracked = tracker.update(boxes.cpu().numpy(), result.orig_img)
                    for row in tracked:
                        if len(row) >= 8: track_ids[int(row[7])] = int(row[4])
                for index, (coords, class_id, score) in enumerate(zip(xyxy, ids, scores)):
                    label = p.classes.get(int(class_id))
                    if label is None: continue
                    rows.append({"source_id": source_id, "session_id": session_id, "label": label, "class_id": int(class_id), "class_name": p.original_classes[class_id], "score": float(score), "xyxy": [float(x) for x in coords], "track_id": track_ids.get(index), "coordinate_space": "original_pixels", "simulated": False, "module_id": p.module_id})
            p.latency_ms = (time.perf_counter() - started) * 1000; p.processed += 1; p.status = "RUNNING"
            return rows


class AIHub:
    def __init__(self): self.packages: dict[str, ModelPackage] = {}; self.sessions: dict[tuple[str, int], dict] = {}; self.lock = threading.RLock()
    def list(self) -> list[dict]:
        out=[]
        for module in sorted(BUILTINS):
            try:
                package=self.packages.get(module)
                if package is None: package=inspect_package(module)
                row=package.public()
                status_file=HANDOFF_ROOT/f"module-status-{module}.json"
                if status_file.is_file():
                    try:
                        worker=json.loads(status_file.read_text(encoding="utf-8"))
                        row.update({k:worker[k] for k in ("status","error","runtime_validated","latency_ms","processed","package_version","weights_path") if k in worker})
                        row["worker_status"]=worker.get("status")
                    except (OSError,ValueError): pass
                out.append(row)
            except PackageError as exc: out.append({"module_id":module,"status":exc.status,"error":str(exc),"runtime_validated":False})
        return out
    def validate(self, module_id: str, runtime: bool = False) -> ModelPackage:
        package=inspect_package(module_id)
        if runtime and package.status != "MISSING_WEIGHTS": package=UltralyticsDetectionAdapter(package).load()
        return package
    def reload(self, module_id: str) -> ModelPackage:
        with self.lock:
            package=self.validate(module_id, runtime=True)
            if package.status in ("READY", "RUNNING"):
                old=self.packages.get(module_id)
                if old:
                    with old.lock: old.runtime=None
                self.packages[module_id]=package
            else: self.packages[module_id]=package
            return package
    def activate(self,module_id:str):
        package=self.packages.get(module_id)
        if not package: package=self.reload(module_id)
        return package
    def detect(self,module_id:str,image,session_id:str,source_id:int):
        package=self.activate(module_id)
        self.sessions.setdefault((session_id,source_id),{})
        return UltralyticsDetectionAdapter(package).detect(image,session_id,source_id)
    def close_session(self,session_id:str):
        with self.lock:
            self.sessions={key:value for key,value in self.sessions.items() if key[0]!=session_id}
            for package in self.packages.values():
                with package.lock:package.trackers={key:value for key,value in package.trackers.items() if key[0]!=session_id}
    def close(self):
        with self.lock:
            for p in self.packages.values():
                with p.lock: p.runtime=None; p.trackers.clear()
            self.sessions.clear()


hub = AIHub()


def report_worker_status(package: ModelPackage | None, module_id: str | None = None, status: str | None = None, error: str | None = None) -> None:
    module=module_id or (package.module_id if package else None)
    if not module:return
    HANDOFF_ROOT.mkdir(parents=True,exist_ok=True)
    body=package.public() if package else {"module_id":module,"runtime_validated":False,"latency_ms":0,"processed":0}
    body.update({"status":status or body.get("status","ERROR"),"error":error if error is not None else body.get("error")})
    target=HANDOFF_ROOT/f"module-status-{module}.json";temp=target.with_suffix(".tmp")
    temp.write_text(json.dumps(body),encoding="utf-8");temp.replace(target)
