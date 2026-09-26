from dataclasses import dataclass, field
from typing import Protocol

EVENT_TYPES={"PERSON_DOWN","OBSTRUCTION","SMOKE_FIRE"}

@dataclass(frozen=True)
class FrameContext:
    camera_id:int
    captured_at:str
    width:int
    height:int
    sequence:int

@dataclass(frozen=True)
class DetectionResult:
    camera_id:int
    captured_at:str
    frame_width:int
    frame_height:int
    event_type:str
    geometry:dict
    track_id:str|None
    detector_id:str
    detector_version:str
    confidence:float|None
    metadata:dict=field(default_factory=dict)
    simulated:bool=False

class DetectorPlugin(Protocol):
    detector_id:str
    version:str
    available:bool
    supported_event_types:set[str]
    def detect(self,context:FrameContext,scenario:str)->list[DetectionResult]: ...

class SimulatedScenarioPlugin:
    detector_id="vigilon.synthetic-scenarios"
    version="1"
    available=True
    supported_event_types=EVENT_TYPES
    scenarios={"obstruction":"OBSTRUCTION","person_down":"PERSON_DOWN","smoke_fire":"SMOKE_FIRE"}
    def detect(self,context:FrameContext,scenario:str)->list[DetectionResult]:
        event=self.scenarios.get(scenario)
        if not event:return []
        return [DetectionResult(context.camera_id,context.captured_at,context.width,context.height,event,{"type":"rectangle","normalized":[0.25,0.4,0.75,0.75]},None,self.detector_id,self.version,None,{"scenario":scenario,"source":"generated_fixture"},True)]

class UnavailableRealDetector:
    detector_id="vigilon.real-detector"
    version="unconfigured"
    available=False
    supported_event_types=set()
    def detect(self,context:FrameContext,scenario:str)->list[DetectionResult]:return []
