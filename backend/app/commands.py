import argparse, json, os, time
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("migrate"); b=sub.add_parser("bootstrap-admin"); b.add_argument("--username",default=os.getenv("VIGILON_ADMIN_USERNAME","admin")); b.add_argument("--password",default=os.getenv("VIGILON_ADMIN_PASSWORD")); s=sub.add_parser("seed-demo"); s.add_argument("--scenario",choices=["normal","obstruction","person_down","smoke_fire"],default="obstruction")
    sub.add_parser("list-models")
    t=sub.add_parser("init-model-package");t.add_argument("module_id");t.add_argument("--destination",required=True)
    v=sub.add_parser("validate-model");v.add_argument("module_id");v.add_argument("--mode",choices=["metadata","runtime"],default="metadata")
    r=sub.add_parser("reload-model");r.add_argument("module_id")
    a=sub.add_parser("analyze-video");a.add_argument("--input",required=True);a.add_argument("--modules",required=True,help="comma-separated built-in module IDs");a.add_argument("--output",required=True);a.add_argument("--session-id",default=None);a.add_argument("--scenario-config",default=None)
    st=sub.add_parser("hub-self-test");st.add_argument("--output",default=None)
    args=p.parse_args()
    if args.command=="migrate":
        from .db import Session
        from alembic import command
        from alembic.config import Config
        backend=__import__("pathlib").Path(__file__).resolve().parents[1]
        config=Config(str(backend/"alembic.ini"))
        config.set_main_option("script_location",str(backend/"migrations"))
        command.upgrade(config,"head")
        print("Database migrations applied.")
    elif args.command=="bootstrap-admin":
        from argon2 import PasswordHasher
        from .db import bootstrap
        if not args.password: raise SystemExit("Set VIGILON_ADMIN_PASSWORD in .env before bootstrapping.")
        bootstrap(args.username,args.password,PasswordHasher().hash)
        print(f"Administrator {args.username!r} is ready (existing users are unchanged).")
    elif args.command=="seed-demo":
        from .db import Session, Camera, Rule
        with Session.begin() as db:
            camera=db.query(Camera).filter_by(name="Demo entrance").first()
            if camera is None:
                camera=Camera(name="Demo entrance",location="Sample property · entrance",source_type="synthetic",connection="",enabled=True,simulated=True,scenario=args.scenario,processing_fps=2,resize_limit=960)
                db.add(camera);db.flush()
                for ev in ["OBSTRUCTION","PERSON_DOWN","SMOKE_FIRE"]: db.add(Rule(camera_id=camera.id,event_type=ev,enabled=ev=={"obstruction":"OBSTRUCTION","person_down":"PERSON_DOWN","smoke_fire":"SMOKE_FIRE"}[args.scenario],min_duration=2,cooldown=30,zone={"type":"polygon","points":[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]}))
            else:
                camera.scenario=args.scenario
                for rule in db.query(Rule).filter_by(camera_id=camera.id).all(): rule.enabled=rule.event_type=={"obstruction":"OBSTRUCTION","person_down":"PERSON_DOWN","smoke_fire":"SMOKE_FIRE"}.get(args.scenario)
        print(f"Synthetic demo source ready with {args.scenario!r}; every generated event is marked SIMULATED.")
    elif args.command in ("list-models","validate-model","reload-model","init-model-package"):
        from .ai_hub import hub, PackageError, BUILTINS
        if args.command=="list-models": print(json.dumps({"hub_status":"HUB_INFRA_READY","modules":hub.list()},indent=2))
        elif args.command=="init-model-package":
            import shutil
            from .ai_hub import ROOT
            if args.module_id not in BUILTINS:raise SystemExit("Unknown built-in module")
            source=(ROOT/"models"/args.module_id).resolve();destination=Path(args.destination).expanduser().resolve()
            if destination.exists():raise SystemExit(f"Refusing to overwrite existing destination: {destination}")
            if destination==source or source.is_relative_to(destination) or destination.is_relative_to(source):raise SystemExit("Destination may not contain or replace the canonical source template")
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(source,destination,ignore=shutil.ignore_patterns("*.pt","*.pth","*.onnx","*.engine"))
            print(json.dumps({"status":"TEMPLATE_CREATED","module_id":args.module_id,"destination":str(destination),"weights_copied":False}))
        elif args.command=="validate-model":
            try: print(json.dumps(hub.validate(args.module_id,args.mode=="runtime").public(),indent=2))
            except PackageError as exc: print(json.dumps({"module_id":args.module_id,"status":exc.status,"error":str(exc)},indent=2));raise SystemExit(2)
        else:
            if args.module_id not in BUILTINS: raise SystemExit("Unknown built-in module")
            from .core import HANDOFF_DIR
            target=HANDOFF_DIR/f"reload-{args.module_id}.json";temp=target.with_suffix(".tmp")
            temp.write_text(json.dumps({"module_id":args.module_id,"requested_at":time.time()}),encoding="utf-8");temp.replace(target)
            print(json.dumps({"module_id":args.module_id,"status":"RELOAD_QUEUED","runtime":"worker"}))
    elif args.command=="analyze-video":
        from .ai_hub import hub, PackageError, BUILTINS
        from .core import MEDIA_DIR
        from .adapters import OpenCVAdapter
        from .scenario_rules import ScenarioEvaluator
        modules=[x.strip() for x in args.modules.split(",") if x.strip()]
        if not modules or any(x not in BUILTINS for x in modules): raise SystemExit("--modules must list people_vehicle and/or fire_smoke")
        output=Path(args.output).expanduser().resolve();output.mkdir(parents=True,exist_ok=True)
        job=args.session_id or f"file-{int(time.time())}"
        overrides={}
        if args.scenario_config:
            overrides=json.loads(Path(args.scenario_config).read_text(encoding="utf-8"))
            if not isinstance(overrides,dict) or any(not isinstance(v,dict) or set(v)-{"zone","line","direction","minimum_observation_seconds","dwell_seconds","hysteresis_pixels"} for v in overrides.values()):raise SystemExit("scenario config must map scenario IDs to supported geometry/timing overrides")
            for name,cfg in overrides.items():
                if any(key in cfg and (isinstance(cfg[key],bool) or not isinstance(cfg[key],(int,float)) or cfg[key]<0 or cfg[key]!=cfg[key] or cfg[key]==float("inf")) for key in ("minimum_observation_seconds","dwell_seconds","hysteresis_pixels")):raise SystemExit(f"{name}: timing and hysteresis values must be finite and nonnegative")
                if "direction" in cfg and cfg["direction"] not in ("A_TO_B","B_TO_A"):raise SystemExit(f"{name}: direction must be A_TO_B or B_TO_A")
                if "line" in cfg and (not isinstance(cfg["line"],list) or len(cfg["line"])!=2 or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(x,(int,float)) or not 0<=x<=1 for x in p) for p in cfg["line"]) or cfg["line"][0]==cfg["line"][1]):raise SystemExit(f"{name}: line needs two distinct normalized endpoints")
                if "zone" in cfg:
                    z=cfg["zone"];pts=z.get("points") if isinstance(z,dict) else None
                    if not isinstance(pts,list) or len(pts)<3 or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(x,(int,float)) or not 0<=x<=1 for x in p) for p in pts):raise SystemExit(f"{name}: zone needs normalized polygon points")
                    area=abs(sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts)))/2)
                    if not area:raise SystemExit(f"{name}: zone has zero area")
        results={"job_id":job,"input":str(args.input),"status":"RUNNING","timestamp_origin":"media","modules":modules,"scenario_overrides":overrides,"frames":0,"detections":[],"events":[],"detections_truncated":False,"events_truncated":False}
        states={};first_seen={}
        target=output/f"{job}-results.json"; cancelled=False
        def save_results():
            temp=target.with_suffix(".tmp");temp.write_text(json.dumps(results,indent=2),encoding="utf-8");temp.replace(target)
        save_results()
        try:
            for module in modules:
                package=hub.reload(module)
                if package.status not in ("READY","RUNNING"):
                    raise RuntimeError(f"{module}: {package.status}: {package.error or 'unavailable'}")
            known={name for module in modules for name in hub.packages[module].scenarios}
            if set(overrides)-known:raise ValueError("unknown scenario IDs: " + ", ".join(sorted(set(overrides)-known)))
            source=OpenCVAdapter("file",args.input,MEDIA_DIR)
            if not source.open():raise RuntimeError("video_decode_failed")
            try:
                while True:
                    frame=source.read()
                    if frame is None:break
                    results["frames"]+=1; media_time=frame.media_time if frame.media_time is not None else (frame.sequence-1)/max(source.fps,1)
                    if results["frames"]%30==0:save_results()
                    for module in modules:
                        try:
                            package=hub.packages[module]
                            observations=hub.detect(module,frame.image,job,0)
                            present={item["label"] for item in observations}
                            for detection in observations:
                                if len(results["detections"])<50000:results["detections"].append({"media_time":media_time,"frame_id":frame.sequence,"detection":detection})
                                else:results["detections_truncated"]=True
                            for scenario_id,scenario in package.scenarios.items():
                                required=scenario.get("required_classes",[])
                                if scenario.get("class_mode","any")=="all" and not set(required)<=present:continue
                                for detection in observations:
                                    if detection["label"] not in required:continue
                                    config={**scenario,**overrides.get(scenario_id,{})};event_type=config["event_type"]
                                    track=str(detection["track_id"] if detection["track_id"] is not None else f"{detection['class_id']}")
                                    defaults=package.scenario_defaults;minimum=float(config.get("minimum_observation_seconds",defaults.get("minimum_observation_seconds",0)))
                                    xyxy=detection["xyxy"]
                                    if defaults.get("anchor","bottom_center")=="center":anchor=((xyxy[0]+xyxy[2])/2/frame.width,(xyxy[1]+xyxy[3])/2/frame.height)
                                    else:anchor=((xyxy[0]+xyxy[2])/2/frame.width,xyxy[3]/frame.height)
                                    grace=float(config.get("disappearance_grace_seconds",defaults.get("disappearance_grace_seconds",1)))
                                    cooldown=float(config.get("cooldown_seconds",defaults.get("cooldown_seconds",10)))
                                    key=(module,scenario_id)
                                    state=states.setdefault(key,ScenarioEvaluator(grace,cooldown))
                                    dwell=config.get("dwell_seconds",minimum)
                                    hysteresis=float(config.get("hysteresis_pixels",0))/max(frame.width,frame.height)
                                    candidates=state.update(track,anchor,media_time,zone=(config.get("zone") or {}).get("points"),line=config.get("line"),direction=config.get("direction","A_TO_B"),dwell_seconds=dwell,minimum=minimum,event_prefix=f"{module}:{scenario_id}",hysteresis=hysteresis)
                                    for candidate in candidates:
                                        if len(results["events"])<10000:results["events"].append({"media_time":media_time,"frame_id":frame.sequence,"event_type":event_type,"scenario_id":scenario_id,"candidate":candidate,"detection":detection,"simulated":False})
                                        else:results["events_truncated"]=True
                        except Exception as exc:
                            results["status"]="FAILED";results["error"]=f"{module}: {type(exc).__name__}: {exc}";raise
            finally:source.close()
            results["status"]="COMPLETED"
        except KeyboardInterrupt:
            results["status"]="CANCELLED";cancelled=True
        except Exception as exc:
            results["status"]="FAILED";results["error"]=str(exc)
        finally:
            save_results();hub.close()
        print(json.dumps({"result_file":str(target),"status":results["status"],"frames":results["frames"],"events":len(results["events"])}))
        if results["status"]!="COMPLETED":raise SystemExit(130 if cancelled else 2)
    else:
        from .detection import FrameContext, SimulatedScenarioPlugin
        from PIL import Image
        plugin=SimulatedScenarioPlugin();observations=[]
        for scenario in ("normal","obstruction","person_down","smoke_fire"):
            context=FrameContext(1,"2026-01-01T00:00:00Z",320,180,1)
            detections=plugin.detect(context,scenario)
            observations.extend({"scenario":scenario,"event_type":d.event_type,"simulated":d.simulated} for d in detections)
        report={"status":"SIMULATED_SELF_TEST_PASSED","real_model_validated":False,"camera_validated":False,"observations":observations}
        if args.output: Path(args.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
if __name__=="__main__": main()
