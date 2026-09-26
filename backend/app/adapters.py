from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import ipaddress, os, socket, time
import cv2

@dataclass
class Frame:
    image: object
    captured_at: float
    width: int
    height: int
    sequence: int

class SourceAdapter(Protocol):
    def open(self): ...
    def read(self): ...
    def close(self): ...

class SyntheticAdapter:
    def __init__(self,scenario): self.scenario=scenario; self.seq=0
    def open(self): return True
    def read(self):
        from PIL import Image, ImageDraw
        self.seq+=1; im=Image.new("RGB",(960,540),(20,30,42)); d=ImageDraw.Draw(im)
        d.rectangle((24,24,936,516),outline=(70,100,120),width=2)
        d.text((40,40),"VIGILON  |  SYNTHETIC SOURCE",fill=(180,220,240))
        d.text((40,72),f"Scenario: {self.scenario.upper()}  |  Frame {self.seq}",fill=(120,190,230))
        if self.scenario=="obstruction":
            d.rectangle((220,270,740,380),fill=(240,150,35)); d.text((380,310),"SIMULATED OBSTRUCTION",fill="black")
        elif self.scenario=="person_down":
            d.ellipse((420,275,520,355),fill=(235,190,140)); d.line((470,315,650,315),fill=(60,160,240),width=30); d.text((365,390),"SIMULATED PERSON DOWN",fill=(255,150,100))
        elif self.scenario=="smoke_fire":
            d.ellipse((400,260,540,400),fill=(240,75,25)); d.ellipse((425,240,510,350),fill=(255,210,55)); d.text((380,420),"SIMULATED SMOKE / FIRE",fill=(255,150,100))
        return Frame(im,time.time(),im.width,im.height,self.seq)
    def close(self): pass

class OpenCVAdapter:
    def __init__(self,source_type,connection,media_root,timeout=5):
        self.source_type=source_type; self.connection=connection; self.media_root=media_root; self.timeout=timeout; self.cap=None
    def _validate(self):
        if self.source_type=="file":
            path=Path(self.connection).resolve()
            if not path.is_relative_to(self.media_root): raise ValueError("media_path_denied")
            if not path.is_file(): raise ValueError("media_file_missing")
            return str(path)
        from urllib.parse import urlsplit
        u=urlsplit(self.connection)
        if u.scheme not in ("rtsp","rtsps") or not u.hostname or not u.port: raise ValueError("rtsp_url_invalid")
        try: ip=ipaddress.ip_address(socket.gethostbyname(u.hostname))
        except OSError: raise ValueError("rtsp_host_unresolved")
        private_lan=(ipaddress.ip_network("10.0.0.0/8"),ipaddress.ip_network("172.16.0.0/12"),ipaddress.ip_network("192.168.0.0/16"))
        if not any(ip in network for network in private_lan): raise ValueError("rtsp_destination_not_private_lan")
        cidrs=os.getenv("VIGILON_ALLOWED_RTSP_CIDRS","10.0.0.0/8,172.16.0.0/12,192.168.0.0/16").split(",")
        if not any(ip in ipaddress.ip_network(c.strip(),strict=False) for c in cidrs): raise ValueError("rtsp_destination_denied")
        if u.port in (22,25,53,80,443,2375,3306,5432,6379,8080,9200): raise ValueError("rtsp_port_denied")
        return self.connection
    def open(self):
        self.cap=cv2.VideoCapture(self._validate(),cv2.CAP_FFMPEG,[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,self.timeout*1000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,self.timeout*1000])
        return self.cap.isOpened()
    def read(self):
        ok,image=self.cap.read()
        if not ok: return None
        h,w=image.shape[:2]; return Frame(image,time.time(),w,h,0)
    def close(self):
        if self.cap: self.cap.release(); self.cap=None
