"""Deterministic geometry and per-session temporal scenario rules."""
from __future__ import annotations
from dataclasses import dataclass, field


def point_in_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    x, y = point; inside = False
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / ((b[1] - a[1]) or 1e-12) + a[0]: inside = not inside
    return inside


def signed_side(point, line):
    (x1, y1), (x2, y2) = line
    return (x2-x1)*(point[1]-y1) - (y2-y1)*(point[0]-x1)


@dataclass
class TrackState:
    inside: bool
    first_seen: float
    last_seen: float
    last_point: tuple[float, float]
    inside_since: float | None = None
    entry_eligible: bool = False
    emitted: set[str] = field(default_factory=set)
    line_side: dict[str, int] = field(default_factory=dict)


class ScenarioEvaluator:
    """State is owned by one source/job session. Input time is monotonic or media time."""
    def __init__(self, grace: float = 1.0, cooldown: float = 10.0):
        self.grace, self.cooldown = grace, cooldown
        self.tracks: dict[str, TrackState] = {}; self.last_event: dict[str, float] = {}

    def reset(self): self.tracks.clear(); self.last_event.clear()

    def update(self, track_id: str, anchor: tuple[float, float], timestamp: float, zone: list[list[float]] | None = None,
               line: list[list[float]] | None = None, direction: str = "A_TO_B", dwell_seconds: float | None = None,
               minimum: float = 0, event_prefix: str = "event", hysteresis: float = 0) -> list[dict]:
        inside = point_in_polygon(anchor, zone) if zone else True
        state = self.tracks.get(track_id); events=[]
        if state and timestamp < state.last_seen:
            self.tracks.pop(track_id, None); state=None
        if state and timestamp-state.last_seen > self.grace:
            self.tracks.pop(track_id, None); state=None
        if not state:
            state=TrackState(inside,timestamp,timestamp,anchor,timestamp if inside else None,False); self.tracks[track_id]=state
        previous_inside=state.inside
        if zone and inside and not previous_inside:
            state.inside_since=timestamp;state.entry_eligible=True
        elif zone and not inside:
            state.inside_since=None;state.entry_eligible=False
        if zone and inside and state.entry_eligible and "entry" not in state.emitted and timestamp-(state.inside_since or timestamp) >= minimum:
            event=self._emit(f"{event_prefix}:entry:{track_id}","ENTRY",timestamp,track_id)
            if event: events.append(event)
            state.emitted.add("entry")
        if line:
            side=signed_side(anchor,line); (x1,y1),(x2,y2)=line
            distance=side/max(((x2-x1)**2+(y2-y1)**2)**0.5,1e-12)
            sign=1 if distance>hysteresis else -1 if distance < -hysteresis else 0
            old=state.line_side.get(event_prefix)
            if sign and old and sign != old:
                moving=direction=="A_TO_B" and old<0<sign or direction=="B_TO_A" and old>0>sign
                if moving:
                    event=self._emit(f"{event_prefix}:cross:{track_id}","LINE_CROSSING",timestamp,track_id)
                    if event: events.append(event)
            if sign:state.line_side[event_prefix]=sign
        if dwell_seconds is not None and inside and state.inside_since is not None and timestamp-state.inside_since >= max(minimum,dwell_seconds) and "dwell" not in state.emitted:
            event=self._emit(f"{event_prefix}:dwell:{track_id}","DWELL",timestamp,track_id)
            if event: events.append(event)
            state.emitted.add("dwell")
        state.inside=inside;state.last_seen=timestamp;state.last_point=anchor
        return events

    def _emit(self,key,kind,at,track):
        if at-self.last_event.get(key,-1e30)<self.cooldown:return None
        self.last_event[key]=at
        return {"event_key":key,"kind":kind,"timestamp":at,"track_id":track,"simulated":False}
