import enum
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .core import DATABASE_URL

class Base(DeclarativeBase): pass
class Role(str, enum.Enum): ADMIN="ADMIN"; OPERATOR="OPERATOR"
class IncidentStatus(str, enum.Enum): NEW="NEW"; ACKNOWLEDGED="ACKNOWLEDGED"; RESOLVED="RESOLVED"; FALSE_ALARM="FALSE_ALARM"
def now(): return datetime.now(timezone.utc)
engine=create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"check_same_thread":False} if DATABASE_URL.startswith("sqlite") else {})
Session=sessionmaker(engine, expire_on_commit=False)

class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True); username: Mapped[str]=mapped_column(String(80),unique=True); password_hash: Mapped[str]=mapped_column(String(300)); role: Mapped[Role]=mapped_column(Enum(Role)); active: Mapped[bool]=mapped_column(Boolean,default=True)
class Camera(Base):
    __tablename__="cameras"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(120)); location: Mapped[str]=mapped_column(String(160),default=""); source_type: Mapped[str]=mapped_column(String(20),default="synthetic"); connection: Mapped[str]=mapped_column(Text,default=""); enabled: Mapped[bool]=mapped_column(Boolean,default=True); simulated: Mapped[bool]=mapped_column(Boolean,default=True); scenario: Mapped[str]=mapped_column(String(32),default="normal"); processing_fps: Mapped[int]=mapped_column(Integer,default=2); resize_limit: Mapped[int]=mapped_column(Integer,default=1280); timeout_seconds: Mapped[int]=mapped_column(Integer,default=5); reconnect_min_seconds: Mapped[int]=mapped_column(Integer,default=1); reconnect_max_seconds: Mapped[int]=mapped_column(Integer,default=30); status: Mapped[str]=mapped_column(String(24),default="OFFLINE"); error_category: Mapped[str]=mapped_column(String(48),default=""); last_frame: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); reconnects: Mapped[int]=mapped_column(Integer,default=0); processed: Mapped[int]=mapped_column(Integer,default=0); dropped: Mapped[int]=mapped_column(Integer,default=0); secret: Mapped[str]=mapped_column(Text,default="")
class Rule(Base):
    __tablename__="rules"
    id: Mapped[int]=mapped_column(primary_key=True); camera_id: Mapped[int]=mapped_column(ForeignKey("cameras.id")); event_type: Mapped[str]=mapped_column(String(32)); enabled: Mapped[bool]=mapped_column(Boolean,default=True); min_duration: Mapped[int]=mapped_column(Integer,default=2); cooldown: Mapped[int]=mapped_column(Integer,default=30); zone: Mapped[dict]=mapped_column(JSON,default=dict); config: Mapped[dict]=mapped_column(JSON,default=dict)
class Incident(Base):
    __tablename__="incidents"
    id: Mapped[int]=mapped_column(primary_key=True); camera_id: Mapped[int]=mapped_column(ForeignKey("cameras.id")); rule_id: Mapped[int]=mapped_column(ForeignKey("rules.id")); event_type: Mapped[str]=mapped_column(String(32)); status: Mapped[IncidentStatus]=mapped_column(Enum(IncidentStatus),default=IncidentStatus.NEW); severity: Mapped[str]=mapped_column(String(16),default="HIGH"); simulated: Mapped[bool]=mapped_column(Boolean,default=False); first_seen: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); last_seen: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); snapshot: Mapped[str]=mapped_column(String(160)); metadata_json: Mapped[dict]=mapped_column(JSON,default=dict); config_snapshot: Mapped[dict]=mapped_column(JSON,default=dict); evidence_expired: Mapped[bool]=mapped_column(Boolean,default=False)
class Transition(Base):
    __tablename__="transitions"
    id: Mapped[int]=mapped_column(primary_key=True); incident_id: Mapped[int]=mapped_column(ForeignKey("incidents.id")); actor_id: Mapped[int]=mapped_column(ForeignKey("users.id")); from_status: Mapped[str]=mapped_column(String(20)); to_status: Mapped[str]=mapped_column(String(20)); note: Mapped[str]=mapped_column(String(500),default=""); at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Notification(Base):
    __tablename__="notifications"
    id: Mapped[int]=mapped_column(primary_key=True); incident_id: Mapped[int]=mapped_column(ForeignKey("incidents.id")); kind: Mapped[str]=mapped_column(String(32)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); read: Mapped[bool]=mapped_column(Boolean,default=False)
class Lease(Base):
    __tablename__="worker_lease"
    id: Mapped[int]=mapped_column(primary_key=True); owner: Mapped[str]=mapped_column(String(80)); expires: Mapped[datetime]=mapped_column(DateTime(timezone=True))

def init_db(): Base.metadata.create_all(engine)
def bootstrap(username,password,hasher):
    with Session.begin() as db:
        if db.scalar(select(User).where(User.username==username)) is None:
            db.add(User(username=username,password_hash=hasher(password),role=Role.ADMIN))
