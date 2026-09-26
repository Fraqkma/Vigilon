import os
from pathlib import Path
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("VIGILON_DATA_DIR", ROOT / ".data"))
DATA.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA / 'vigilon.db'}")
SECRET_KEY = os.getenv("VIGILON_SECRET_KEY", "")
ENCRYPTION_KEY = os.getenv("VIGILON_ENCRYPTION_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("VIGILON_SECRET_KEY is missing. Run scripts/setup.ps1 or scripts/setup.sh.")
if not ENCRYPTION_KEY:
    raise RuntimeError("VIGILON_ENCRYPTION_KEY is missing. Run scripts/setup.ps1 or scripts/setup.sh.")
fernet = Fernet(ENCRYPTION_KEY.encode())
EVIDENCE_DIR = Path(os.getenv("VIGILON_EVIDENCE_DIR", DATA / "evidence"))
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR = Path(os.getenv("VIGILON_MEDIA_DIR", ROOT / "sample_data")).resolve()
HANDOFF_DIR = Path(os.getenv("VIGILON_HANDOFF_DIR", DATA / "frames"))
HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
