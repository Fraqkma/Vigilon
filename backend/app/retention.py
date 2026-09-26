import os
from datetime import timedelta
from sqlalchemy import select
from .core import EVIDENCE_DIR
from .db import Incident, Session, now

def main():
    days=max(1,int(os.getenv("VIGILON_RETENTION_DAYS","30"))); cutoff=now()-timedelta(days=days); removed=0
    with Session.begin() as db:
        for incident in db.scalars(select(Incident).where(Incident.last_seen<cutoff,Incident.evidence_expired.is_(False))):
            path=EVIDENCE_DIR/incident.snapshot
            try: path.unlink(missing_ok=True);removed+=1
            finally: incident.evidence_expired=True
    print(f"Expired evidence references: {removed}; retention: {days} days")
if __name__=="__main__": main()
