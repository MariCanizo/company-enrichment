from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", PROJECT_ROOT / "output"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

MOCK_LLM = os.getenv("MOCK_LLM", "true").lower() in ("1", "true", "yes")
MOCK_SEARCH = os.getenv("MOCK_SEARCH", "true").lower() in ("1", "true", "yes")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "3"))

USER_AGENT = (
    "Mozilla/5.0 (compatible; CompanyEnrichmentBot/0.1; +https://example.local/bot)"
)
