from ..db import Notification

def record_incident_created(db,incident_id):
    """Persist one deduplicated in-app incident notification."""
    db.add(Notification(incident_id=incident_id,kind="INCIDENT_CREATED"))
