import uuid
from datetime import timedelta
from ..core import EVIDENCE_DIR
from ..db import Incident, IncidentStatus, now
from .notification_service import record_incident_created

def persist_detection(db,camera,frame,snapshot_source,detection,rule):
    """Deduplicate an active event or persist a new snapshot-backed incident."""
    active=db.query(Incident).filter(Incident.camera_id==camera.id,Incident.rule_id==rule.id,Incident.status.in_([IncidentStatus.NEW,IncidentStatus.ACKNOWLEDGED])).order_by(Incident.id.desc()).first()
    if active:
        active.last_seen=now()
        return active
    cooling=db.query(Incident).filter(Incident.camera_id==camera.id,Incident.rule_id==rule.id,Incident.first_seen>now()-timedelta(seconds=rule.cooldown)).first()
    if cooling:return None
    snapshot=f"incident-{uuid.uuid4().hex}.jpg"
    (EVIDENCE_DIR/snapshot).write_bytes(snapshot_source.read_bytes())
    incident=Incident(camera_id=camera.id,rule_id=rule.id,event_type=detection.event_type,status=IncidentStatus.NEW,severity="HIGH",simulated=detection.simulated,snapshot=snapshot,metadata_json={"scenario":camera.scenario,"frame_sequence":frame.sequence,"captured_at":detection.captured_at,"geometry":detection.geometry,"detector_id":detection.detector_id,"detector_version":detection.detector_version,"confidence":detection.confidence,"metadata":detection.metadata},config_snapshot={"rule_id":rule.id,"minimum_duration_seconds":rule.min_duration,"zone":rule.zone})
    db.add(incident);db.flush();record_incident_created(db,incident.id)
    return incident
