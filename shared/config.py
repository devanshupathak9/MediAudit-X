"""Paths and settings shared by every worker. Values come from the root .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

MAPPINGS_DIR = ROOT / "elasticsearch" / "mappings"

# Where raw uploads, stored policies and reports live (gitignored)
STORAGE_DIR = ROOT / "storage"
JOBS_DIR = STORAGE_DIR / "jobs"          # one folder per submitted job
POLICY_STORE = STORAGE_DIR / "policies"  # original policy files, for citations

POLICY_INDEX = "payer-policies"
EVENTS_INDEX = "patient-events"
CLAIMS_INDEX = "claims"
