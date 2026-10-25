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
    for name in ai_hub.BUILTINS:
        shutil.copytree(ai_hub.ROOT/"models"/name,root/name,ignore=shutil.ignore_patterns("*.pt","*.pth","*.onnx","*.engine"))
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
    monkeypatch.setitem(sys.modules,"ultralytics",types.SimpleNamespace(__version__="8.4.0",YOLO=FakeYOLO))
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
    monkeypatch.setitem(sys.modules,"ultralytics",types.SimpleNamespace(__version__="8.4.0",YOLO=FakeYOLO))
    package=inspect_package("people_vehicle")
    assert UltralyticsDetectionAdapter(package).load().status=="UNSUPPORTED_MODEL"
    FakeYOLO.task="detect";FakeYOLO.names={0:"other"}
    package=inspect_package("people_vehicle")
    loaded=UltralyticsDetectionAdapter(package).load()
    assert loaded.status=="INVALID_CONFIG" and "class map" in loaded.error


def test_predict_receives_original_bgr_without_channel_swap(tmp_path,monkeypatch):
    folder=package_copy(tmp_path,monkeypatch)
    (folder/"manifest.yaml").write_text((folder/"manifest.yaml").read_text().replace("tracker: {path: tracker.yaml}","tracker: null"),encoding="utf-8")
    (folder/"weights"/"best.pt").write_bytes(b"temporary mocked checkpoint")
    import numpy as np

    class Result:
        boxes=None
    class FakeYOLO:
        task="detect"
        def __init__(self,path): self.names={int(k):v for k,v in json.loads((folder/"classes.json").read_text()).items()};self.images=[]
        def predict(self,image,**kwargs): self.images.append(image.copy());return [Result()]
    monkeypatch.setitem(sys.modules,"ultralytics",types.SimpleNamespace(__version__="8.4.0",YOLO=FakeYOLO))
    package=UltralyticsDetectionAdapter(inspect_package("people_vehicle")).load()
    assert package.status=="READY"
    image=np.zeros((4,5,3),dtype=np.uint8)
    image[:]=(11,73,241)  # distinct B, G, R values expose red/blue swapping
    UltralyticsDetectionAdapter(package).detect(image,"session",1)
    np.testing.assert_array_equal(package.runtime.images[-1],image)


def test_bytetrack_84_update_maps_returned_detection_index(tmp_path,monkeypatch):
    folder=package_copy(tmp_path,monkeypatch)
    (folder/"weights"/"best.pt").write_bytes(b"temporary mocked checkpoint")
    import numpy as np

    class ArrayView:
        def __init__(self,value): self.value=np.asarray(value)
        def cpu(self): return self
        def numpy(self): return self.value
        def int(self): return self
        def tolist(self): return self.value.tolist()
    class Boxes:
        xyxy=ArrayView([[1,2,30,40]])
        cls=ArrayView([0])
        conf=ArrayView([0.91])
        def __len__(self): return 1
        def cpu(self): return ArrayView([[1,2,30,40,0.91,0]])
    image=np.zeros((50,60,3),dtype=np.uint8);image[:]=(7,89,233)
    class Result:
        boxes=Boxes()
        orig_img=image
    class FakeYOLO:
        task="detect"
        def __init__(self,path): self.names={int(k):v for k,v in json.loads((folder/"classes.json").read_text()).items()}
        def predict(self,*args,**kwargs): return [Result()]
    instances=[]
    class FakeBYTETracker:
        def __init__(self,args,frame_rate): self.args=args;self.frame_rate=frame_rate;instances.append(self)
        def update(self,results,img):
            self.results=results;self.image=img
            return np.asarray([[1,2,30,40,73,0.91,0,0]],dtype=float)
    trackers=types.ModuleType("ultralytics.trackers")
    byte_tracker=types.ModuleType("ultralytics.trackers.byte_tracker")
    byte_tracker.BYTETracker=FakeBYTETracker
    monkeypatch.setitem(sys.modules,"ultralytics",types.SimpleNamespace(__version__="8.4.0",YOLO=FakeYOLO))
    monkeypatch.setitem(sys.modules,"ultralytics.trackers",trackers)
    monkeypatch.setitem(sys.modules,"ultralytics.trackers.byte_tracker",byte_tracker)
    package=UltralyticsDetectionAdapter(inspect_package("people_vehicle")).load()
    rows=UltralyticsDetectionAdapter(package).detect(image,"session",1)
    assert rows[0]["track_id"]==73
    assert instances[0].frame_rate==30
    assert instances[0].results.shape==(1,6)
    np.testing.assert_array_equal(instances[0].image,image)
