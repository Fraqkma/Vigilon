import json
import shutil
import sys
import types
from pathlib import Path

import pytest

from app import ai_hub
from app.ai_hub import PackageError, inspect_package
from app.scenario_rules import ScenarioEvaluator, point_in_polygon
from app.ai_hub import UltralyticsDetectionAdapter


def package_copy(tmp_path, monkeypatch, module="people_vehicle"):
    root=tmp_path/"models";root.mkdir(parents=True)
    shutil.copytree(ai_hub.ROOT/"models"/module,root/module)
    monkeypatch.setattr(ai_hub,"MODEL_ROOT",root)
    return root/module


def test_canonical_packages_are_metadata_valid_but_missing_weights(tmp_path,monkeypatch):
    package_copy(tmp_path,monkeypatch)
    p=inspect_package("people_vehicle")
    assert p.status=="MISSING_WEIGHTS" and not p.weights.exists()
    assert p.classes[2]=="car" and p.manifest["task"]=="detect"


def test_manifest_and_package_escape_are_rejected(tmp_path,monkeypatch):
    folder=package_copy(tmp_path,monkeypatch)
    (folder/"manifest.yaml").write_text("schema_version: [",encoding="utf-8")
    with pytest.raises(PackageError,match="Cannot read manifest"):
        inspect_package("people_vehicle")
    folder=package_copy(tmp_path/"second",monkeypatch)
    manifest=(folder/"manifest.yaml").read_text(encoding="utf-8").replace("inference.yaml","../outside.yaml")
    (folder/"manifest.yaml").write_text(manifest,encoding="utf-8")
    with pytest.raises(PackageError,match="escapes"):
        inspect_package("people_vehicle")


def test_bad_inference_field_and_class_map_rejected(tmp_path,monkeypatch):
    folder=package_copy(tmp_path,monkeypatch)
    (folder/"inference.yaml").write_text("imgsz: 640\nconf: 0.25\niou: 0.45\ndevice: cpu\nallow_cpu_fallback: false\nmagic: true\n",encoding="utf-8")
    with pytest.raises(PackageError,match="unsupported fields"):
        inspect_package("people_vehicle")
    folder=package_copy(tmp_path/"second",monkeypatch)
    (folder/"classes.json").write_text(json.dumps({"0":"person","1":"person"}),encoding="utf-8")
    with pytest.raises(PackageError,match="unique"):
        inspect_package("people_vehicle")


def test_checksum_mismatch_is_reported(tmp_path,monkeypatch):
    folder=package_copy(tmp_path,monkeypatch)
    (folder/"weights").mkdir(exist_ok=True);(folder/"weights"/"best.pt").write_bytes(b"temporary test fixture")
    manifest=(folder/"manifest.yaml").read_text(encoding="utf-8").replace("sha256: null",'sha256: "' + "0"*64 + '"')
    (folder/"manifest.yaml").write_text(manifest,encoding="utf-8")
    with pytest.raises(PackageError,match="SHA-256"):
        inspect_package("people_vehicle")


def test_zone_line_and_dwell_rules_are_stateful_and_session_local():
    polygon=[[0,0],[1,0],[1,1],[0,1]]
    assert point_in_polygon((.5,.5),polygon)
    first=ScenarioEvaluator(grace=3,cooldown=2);second=ScenarioEvaluator()
    assert first.update("x",(-1,.5),0,zone=polygon)==[]
    assert first.update("x",(.1,.5),2,zone=polygon,minimum=1)==[]
    entry=first.update("x",(.1,.5),3,zone=polygon,minimum=1)
    assert entry and entry[0]["kind"]=="ENTRY"
    assert second.update("x",(.1,.5),3,zone=polygon)==[]
    line=[[0,.5],[1,.5]]
    first.update("x",(.5,.4),3.1,line=line,hysteresis=.01)
    assert first.update("x",(.5,.505),3.2,line=line,hysteresis=.01)==[]
    crossing=first.update("x",(.5,.6),4,line=line,hysteresis=.01)
    assert crossing and crossing[0]["kind"]=="LINE_CROSSING"
    evaluator=ScenarioEvaluator(grace=2);evaluator.update("person",(.5,.5),0,zone=polygon,dwell_seconds=1)
    dwell=evaluator.update("person",(.5,.5),1.1,zone=polygon,dwell_seconds=1)
    assert dwell and dwell[0]["kind"]=="DWELL"


def test_module_catalog_exposes_missing_weights_not_ready(tmp_path,monkeypatch):
    root=tmp_path/"models";root.mkdir()
    for name in ai_hub.BUILTINS: shutil.copytree(ai_hub.ROOT/"models"/name,root/name)
    monkeypatch.setattr(ai_hub,"MODEL_ROOT",root)
    catalog=ai_hub.AIHub().list()
    assert {m["status"] for m in catalog}=={"MISSING_WEIGHTS"}
    assert all(not m["runtime_validated"] for m in catalog)


def test_runtime_adapter_cpu_warmup_and_explicit_cuda_unavailable(tmp_path,monkeypatch):
    folder=package_copy(tmp_path,monkeypatch)
    (folder/"manifest.yaml").write_text((folder/"manifest.yaml").read_text().replace("tracker: {path: tracker.yaml}","tracker: null"),encoding="utf-8")
    (folder/"weights"/"best.pt").write_bytes(b"temporary mocked checkpoint")
    import json as json_lib
    names={int(k):v for k,v in json_lib.loads((folder/"classes.json").read_text()).items()}
    class FakeYOLO:
        task="detect"
        def __init__(self,path):self.names=names;self.calls=[]
        def predict(self,*args,**kwargs):self.calls.append(kwargs);return [object()]
    monkeypatch.setitem(sys.modules,"ultralytics",types.SimpleNamespace(__version__="8.3.0",YOLO=FakeYOLO))
    monkeypatch.setattr(UltralyticsDetectionAdapter,"_cuda_available",staticmethod(lambda:False))
    package=inspect_package("people_vehicle")
    loaded=UltralyticsDetectionAdapter(package).load()
    assert loaded.status=="READY" and loaded.runtime.calls[0]["device"]=="cpu"
    inference=(folder/"inference.yaml").read_text().replace("device: cpu","device: cuda")
    (folder/"inference.yaml").write_text(inference,encoding="utf-8")
    package=inspect_package("people_vehicle");loaded=UltralyticsDetectionAdapter(package).load()
    assert loaded.status=="DEPENDENCY_MISSING" and "CUDA requested" in loaded.error


def test_runtime_rejects_non_detection_task_and_wrong_checkpoint_names(tmp_path,monkeypatch):
    folder=package_copy(tmp_path,monkeypatch)
    (folder/"manifest.yaml").write_text((folder/"manifest.yaml").read_text().replace("tracker: {path: tracker.yaml}","tracker: null"),encoding="utf-8")
    (folder/"weights"/"best.pt").write_bytes(b"temporary mocked checkpoint")
    class FakeYOLO:
        task="segment";names={}
        def __init__(self,path):self.task=type(self).task;self.names=type(self).names
    monkeypatch.setitem(sys.modules,"ultralytics",types.SimpleNamespace(__version__="8.3.0",YOLO=FakeYOLO))
    package=inspect_package("people_vehicle")
    assert UltralyticsDetectionAdapter(package).load().status=="UNSUPPORTED_MODEL"
    FakeYOLO.task="detect";FakeYOLO.names={0:"other"}
    package=inspect_package("people_vehicle")
    loaded=UltralyticsDetectionAdapter(package).load()
    assert loaded.status=="INVALID_CONFIG" and "class map" in loaded.error
