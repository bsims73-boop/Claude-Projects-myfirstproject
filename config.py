import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
RECEIPTS_FOLDER = BASE_DIR / "receipts"
DATABASE_PATH = BASE_DIR / "database" / "receipts.db"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")
MAX_IMAGE_SIZE_MB = float(os.getenv("MAX_IMAGE_SIZE_MB", "20"))
SAM_GOV_API_KEY = os.getenv("SAM_GOV_API_KEY", "")
SIMPLER_GRANTS_API_KEY = os.getenv("SIMPLER_GRANTS_API_KEY", "")
