"""Regression: a scenario may only publish the candidate kind that matches its event type."""
from app.scenario_rules import ScenarioEvaluator, dwell_for, keep_candidate, needs_track

ZONE = [[0.6, 0], [1, 0], [1, 1], [0.6, 1]]   # right-hand 40% of the frame
LINE = [[0.5, 1], [0.5, 0]]                   # vertical line in the middle


def _walk(event_type, zone=None, line=None, config=None):
    """One track walks left -> right for 6 s at 10 FPS; return the events that would be published."""
    config = config or {}
    minimum = 1.0
    state = ScenarioEvaluator(grace=1, cooldown=10)
    published = []
    for i in range(60):
        t = i / 10
        anchor = (0.1 + i * 0.015, 0.9)       # x: 0.10 -> 0.985
        for c in state.update("7", anchor, t, zone=zone, line=line, dwell_seconds=dwell_for(event_type, config, minimum),
                              minimum=minimum, event_prefix=f"pv:{event_type}"):
            if keep_candidate(event_type, c):
                published.append(c["kind"])
    return published


def test_zone_entry_publishes_one_entry_and_no_dwell():
    assert _walk("ZONE_ENTRY", zone=ZONE) == ["ENTRY"]


def test_line_crossing_publishes_only_the_crossing():
    assert _walk("LINE_CROSSING", line=LINE) == ["LINE_CROSSING"]


def test_dwell_waits_for_dwell_seconds_not_the_entry():
    assert _walk("DWELL", zone=ZONE, config={"dwell_seconds": 30}) == []      # only ~2.6 s inside
    assert _walk("DWELL", zone=ZONE, config={"dwell_seconds": 2}) == ["DWELL"]


def test_presence_episode_still_confirms_through_timer():
    # fire/smoke has no zone/line: SMOKE_DETECTED confirms after the minimum observation time
    assert _walk("SMOKE_DETECTED") == ["DWELL"]


def test_untracked_boxes_are_skipped_only_for_track_rules():
    assert needs_track("LINE_CROSSING", True, None)
    assert not needs_track("LINE_CROSSING", True, 4)
    assert not needs_track("SMOKE_DETECTED", False, None)   # fire/smoke has no tracker by design
