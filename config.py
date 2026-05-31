import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FB_EMAIL = os.getenv("FB_EMAIL", "")
FB_PASSWORD = os.getenv("FB_PASSWORD", "")

HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

PROFILE_DIR = Path("profiles/facebook-profile")