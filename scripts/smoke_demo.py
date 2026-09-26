"""Exercise a running local API + worker without accessing external cameras."""
import json, os, sys, time
from pathlib import Path
from dotenv import dotenv_values
import httpx

env=dotenv_values(Path(__file__).resolve().parents[1]/".env")
with httpx.Client(base_url=os.getenv("VIGILON_URL","http://127.0.0.1:8000"),timeout=8) as client:
    health=client.get("/api/health"); health.raise_for_status()
    login=client.post("/api/auth/login",json={"username":env.get("VIGILON_ADMIN_USERNAME","admin"),"password":env["VIGILON_ADMIN_PASSWORD"]}); login.raise_for_status()
    overview=client.get("/api/overview"); overview.raise_for_status()
    source=next((c for c in overview.json()["cameras"] if c["simulated"]),None)
    if not source: raise SystemExit("No simulated source found; run seed-demo first.")
    deadline=time.time()+12; incident=None; preview=None
    while time.time()<deadline:
        preview=client.get(f"/api/cameras/{source['id']}/preview")
        incidents=client.get("/api/incidents").json()
        incident=next((i for i in incidents if i["camera_id"]==source["id"] and i["status"] in ("NEW","ACKNOWLEDGED")),None)
        if preview.status_code==200 and incident: break
        time.sleep(.3)
    if not preview or preview.status_code!=200: raise SystemExit("Worker preview did not become available.")
    if preview.headers.get("x-simulation")!="SIMULATED": raise SystemExit("Preview simulation marker missing.")
    if not incident: raise SystemExit("No incident appeared from the selected demo scenario.")
    evidence=client.get(f"/api/incidents/{incident['id']}/evidence"); evidence.raise_for_status()
    if evidence.content[:2]!=b"\xff\xd8": raise SystemExit("Incident snapshot is not a JPEG.")
    if incident["status"]=="NEW":
        client.post(f"/api/incidents/{incident['id']}/action",json={"status":"ACKNOWLEDGED","note":"Local demo verification"}).raise_for_status()
    client.post(f"/api/incidents/{incident['id']}/action",json={"status":"RESOLVED","note":"Local demo verification"}).raise_for_status()
    saved=next(i for i in client.get("/api/incidents").json() if i["id"]==incident["id"])
    assert saved["status"]=="RESOLVED" and saved["simulated"] and len(saved["history"])>=1
    print(json.dumps({"api":"healthy","worker":overview.json()["worker"],"source":source["name"],"preview":"JPEG SIMULATED","incident":saved["event_type"],"status":saved["status"],"evidence":"JPEG","history_entries":len(saved["history"])}))
