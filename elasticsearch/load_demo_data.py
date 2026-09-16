"""Load the demo data straight into Elasticsearch (no workers, no Redis).

Uses the same ingestion code as the workers:
  policy .txt   -> sections + metadata + vectors -> payer-policies
  FHIR bundles  -> flat event rows               -> patient-events

    python elasticsearch/load_demo_data.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

from ingestion.fhir_flattener import flatten_bundle  # noqa: E402
from ingestion.indexers import index_events, index_policy_chunks  # noqa: E402
from ingestion.policy_parser import build_chunks  # noqa: E402
from shared.config import ROOT  # noqa: E402

DATA = ROOT / "data"

for policy_file in sorted((DATA / "policies").glob("*.txt")):
    result = index_policy_chunks(build_chunks(policy_file))
    print(f"policy   {policy_file.name}: {result}")

for bundle_file in sorted((DATA / "fhir").glob("*.bundle.json")):
    patient_id, rows, warnings = flatten_bundle(json.loads(bundle_file.read_text()), bundle_file.name)
    result = index_events(patient_id, rows)
    print(f"patient  {bundle_file.name}: {result['events']} events" + (f", warnings: {warnings}" if warnings else ""))
