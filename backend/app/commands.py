import argparse, os
from argon2 import PasswordHasher
from .db import bootstrap, Session, Camera, Rule

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("migrate"); b=sub.add_parser("bootstrap-admin"); b.add_argument("--username",default=os.getenv("VIGILON_ADMIN_USERNAME","admin")); b.add_argument("--password",default=os.getenv("VIGILON_ADMIN_PASSWORD")); s=sub.add_parser("seed-demo"); s.add_argument("--scenario",choices=["normal","obstruction","person_down","smoke_fire"],default="obstruction")
    args=p.parse_args()
    if args.command=="migrate":
        from alembic import command
        from alembic.config import Config
        backend=__import__("pathlib").Path(__file__).resolve().parents[1]
        config=Config(str(backend/"alembic.ini"))
        config.set_main_option("script_location",str(backend/"migrations"))
        command.upgrade(config,"head")
        print("Database migrations applied.")
    elif args.command=="bootstrap-admin":
        if not args.password: raise SystemExit("Set VIGILON_ADMIN_PASSWORD in .env before bootstrapping.")
        bootstrap(args.username,args.password,PasswordHasher().hash)
        print(f"Administrator {args.username!r} is ready (existing users are unchanged).")
    else:
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
if __name__=="__main__": main()
