#!/usr/bin/env python3
"""Hand-authored demo patients for MediAudit-X.

Real volume comes from Synthea later; these four exist because each one proves a
specific claim in the pitch, and Synthea will not generate them on demand.

  P-1042  knee arthroscopy claim. Four honest months of PT, plus TWO BACKDATED
          PT visits entered 19 days AFTER the surgery. Ignore `recorded_at` and
          the chart shows 6 months (approve). Respect it and the chart shows 4
          (deny). Also on warfarin -> post-op Toradol order is a safety hit.
  P-2087  Type 2 diabetes  (E11.9)  |  adversarial pair: near-identical text,
  P-3311  Type 1 diabetes  (E10.9)  |  one character apart, opposite coverage.
  P-4455  clean knee claim that genuinely meets all five criteria (approve path).

Emits one flat row per clinical event -- the shape every ES|QL template expects.

    python3 data/patients/build_demo_patients.py
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "demo-patients.events.jsonl"
rows: list[dict] = []


def ev(patient, etype, system, code, text, when, *, recorded=None, value=None,
       unit=None, note=None, status="completed", encounter=None, doc=None, page=1):
    """One clinical event. `recorded` defaults to `when` -- the honest case."""
    n = len(rows) + 1
    rows.append({
        "event_id": f"E-{n:04d}",
        "patient_id": patient,
        "encounter_id": encounter,
        "event_type": etype,
        "code_system": system,
        "code": code,
        "code_text": text,
        "note_text": note,
        "value_num": value,
        "value_unit": unit,
        "status": status,
        "event_time": f"{when}T09:00:00Z",
        "event_end": None,
        # THE bi-temporal axis. `recorded_at` is when it entered the record.
        "recorded_at": f"{recorded or when}T09:00:00Z",
        "source_doc_id": doc or f"chart-{patient}.pdf",
        "source_page": page,
        "byte_start": None,
        "byte_end": None,
    })


# ---------------------------------------------------------------- P-1042
# The headline case. Date of service 2026-06-01, CPT 29881, right knee.
P = "P-1042"

# Comorbidity + anticoagulant: sets up the drug-safety overlay.
ev(P, "diagnosis", "ICD10", "I48.91", "Unspecified atrial fibrillation", "2024-08-12", page=3)
ev(P, "medication", "RxNorm", "855332", "Warfarin Sodium 5 MG Oral Tablet",
   "2024-08-15", status="active", page=4,
   note="Warfarin 5mg daily for atrial fibrillation. INR goal 2.0-3.0. Managed by anticoagulation clinic.")

# C1: qualifying diagnosis, well before DOS.
ev(P, "diagnosis", "ICD10", "M17.11", "Unilateral primary osteoarthritis, right knee",
   "2025-11-03", encounter="ENC-1042-01", page=7,
   note="Orthopedic consultation. Right knee pain, insidious onset, worse with stairs. "
        "Weight-bearing radiographs show medial joint space narrowing. Kellgren-Lawrence grade 3.")
ev(P, "encounter", "CPT", "99204", "Office visit, new patient", "2025-11-03", encounter="ENC-1042-01", page=7)

# Conservative therapy, honestly documented: Jan-Apr 2026 = FOUR distinct months.
for d in ["2026-01-12", "2026-01-26", "2026-02-09", "2026-02-23",
          "2026-03-09", "2026-03-23", "2026-04-06", "2026-04-20"]:
    ev(P, "procedure", "CPT", "97110", "Therapeutic exercise, each 15 minutes", d, page=11)

# >>> THE BACKDATED ENTRIES <<<
# Claim denied 2026-06-10 for insufficient conservative therapy. On 2026-06-20 two
# PT encounters appear in the record, dated to Nov and Dec 2025 -- seven months
# earlier. Policy MHP-0673 section 3 explicitly disallows this.
ev(P, "procedure", "CPT", "97110", "Therapeutic exercise, each 15 minutes",
   "2025-11-17", recorded="2026-06-20", page=12,
   note="Late entry. Supervised therapeutic exercise, right knee.")
ev(P, "procedure", "CPT", "97110", "Therapeutic exercise, each 15 minutes",
   "2025-12-15", recorded="2026-06-20", page=12,
   note="Late entry. Supervised therapeutic exercise, right knee.")

# C5: BMI 34.2 -> under the 40.0 ceiling.
ev(P, "observation", "LOINC", "39156-5", "Body mass index (BMI) [Ratio]",
   "2026-03-09", value=34.2, unit="kg/m2", page=13)

# C3: imaging obtained AFTER the final therapy encounter (2026-04-20). Order holds.
ev(P, "procedure", "CPT", "73721", "MRI, lower extremity joint, without contrast",
   "2026-05-04", recorded="2026-05-05", page=15,
   note="MRI right knee: full-thickness cartilage loss medial femoral condyle. "
        "Complex tear posterior horn medial meniscus. Moderate joint effusion.")

ev(P, "note", "LOINC", "11506-3", "Progress note", "2026-04-20", page=14,
   note="Patient continues to report persistent right knee pain despite structured "
        "physical therapy. Antalgic gait. Failed conservative management. "
        "Discussed arthroscopic partial meniscectomy.")

# The claimed procedure itself.
ev(P, "procedure", "CPT", "29881", "Arthroscopy, knee, surgical; with meniscectomy (medial OR lateral)",
   "2026-06-01", encounter="ENC-1042-09", page=19)
# Post-op order that collides with warfarin.
ev(P, "medication", "RxNorm", "1092398", "Ketorolac Tromethamine 30 MG/ML Injection",
   "2026-06-01", status="active", encounter="ENC-1042-09", page=20,
   note="Toradol 30mg IM post-operatively for pain control.")

# ------------------------------------------------- P-2087 / P-3311 (the pair)
# Textually near-identical, financially opposite. `code` is a keyword field, so a
# term query separates them perfectly; a match query on `code_text` does not.
ev("P-2087", "diagnosis", "ICD10", "E11.9", "Type 2 diabetes mellitus without complications",
   "2025-03-14", page=2,
   note="Type 2 diabetes mellitus, poorly controlled. Metformin and basal insulin. "
        "Discussed continuous glucose monitoring.")
ev("P-2087", "observation", "LOINC", "4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood",
   "2026-05-20", value=9.2, unit="%", page=3)
ev("P-2087", "medication", "RxNorm", "274783", "Insulin Glargine 100 UNT/ML Injection",
   "2025-09-01", status="active", page=4)

ev("P-3311", "diagnosis", "ICD10", "E10.9", "Type 1 diabetes mellitus without complications",
   "2019-06-02", page=2,
   note="Type 1 diabetes mellitus, on multiple daily injections. "
        "Continuous glucose monitoring in place since diagnosis.")
ev("P-3311", "observation", "LOINC", "4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood",
   "2026-05-18", value=7.4, unit="%", page=3)
ev("P-3311", "medication", "RxNorm", "274783", "Insulin Glargine 100 UNT/ML Injection",
   "2019-06-05", status="active", page=4)

# ---------------------------------------------------------------- P-4455
# The approve path: same claim shape as P-1042, but genuinely compliant. Six
# distinct months, contemporaneously recorded, largest gap 35 days.
Q = "P-4455"
ev(Q, "diagnosis", "ICD10", "M23.221", "Derangement of posterior horn of medial meniscus, right knee",
   "2025-08-19", page=5,
   note="Medial joint line tenderness, positive McMurray. Suspect medial meniscal tear.")
for d in ["2025-09-08", "2025-09-29", "2025-10-20", "2025-11-10",
          "2025-12-15", "2026-01-19", "2026-02-16", "2026-03-16"]:
    ev(Q, "procedure", "CPT", "97110", "Therapeutic exercise, each 15 minutes", d, page=9)
ev(Q, "observation", "LOINC", "39156-5", "Body mass index (BMI) [Ratio]",
   "2026-02-16", value=28.7, unit="kg/m2", page=10)
ev(Q, "procedure", "CPT", "73721", "MRI, lower extremity joint, without contrast",
   "2026-04-02", page=12,
   note="MRI right knee: displaced bucket-handle tear of the medial meniscus.")
ev(Q, "procedure", "CPT", "29881", "Arthroscopy, knee, surgical; with meniscectomy (medial OR lateral)",
   "2026-05-11", page=14)

OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))

by_patient: dict[str, int] = {}
for r in rows:
    by_patient[r["patient_id"]] = by_patient.get(r["patient_id"], 0) + 1
backdated = [r for r in rows if r["recorded_at"] > r["event_time"]]
print(f"wrote {len(rows)} events -> {OUT}")
for pid, n in sorted(by_patient.items()):
    print(f"  {pid}  {n:>3} events")
print(f"  {len(backdated)} event(s) recorded after the fact "
      f"(the bi-temporal demo): {[r['event_id'] for r in backdated]}")
