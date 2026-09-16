#!/usr/bin/env python3
"""Write the demo patients as FHIR R4 bundles (what a hospital would send).

Same four stories as before:
  P-1042  knee claim; 4 honest months of PT + 2 PT visits BACKDATED on 2026-06-20
  P-4455  knee claim that meets every rule
  P-2087  Type 2 diabetes (E11.9)  | near-identical pair
  P-3311  Type 1 diabetes (E10.9)  |

Bi-temporal dates in FHIR:
  clinical date  -> onsetDateTime / performedDateTime / effectiveDateTime / authoredOn / period.start / date
  recorded date  -> meta.lastUpdated (plus recordedDate / issued where R4 has them)

    python3 data/fhir/build_demo_bundles.py
"""
import base64
import json
from pathlib import Path

OUT_DIR = Path(__file__).parent

ICD10 = "http://hl7.org/fhir/sid/icd-10-cm"
CPT = "http://www.ama-assn.org/go/cpt"
LOINC = "http://loinc.org"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"


class Bundle:
    def __init__(self, patient_id, birth_date, gender):
        self.patient_id = patient_id
        self.entries = [{"resourceType": "Patient", "id": patient_id, "birthDate": birth_date, "gender": gender}]

    def _add(self, resource, recorded, note):
        n = sum(1 for e in self.entries if e["resourceType"] == resource["resourceType"]) + 1
        resource["id"] = f"{self.patient_id.lower()}-{resource['resourceType'].lower()}-{n:02d}"
        resource["meta"] = {"lastUpdated": f"{recorded}T09:00:00Z"}
        resource["subject"] = {"reference": f"Patient/{self.patient_id}"}
        if note:
            resource["note"] = [{"text": note}]
        self.entries.append(resource)

    def condition(self, code, display, onset, recorded=None, note=None):
        self._add({"resourceType": "Condition",
                   "clinicalStatus": {"coding": [{"code": "active"}]},
                   "code": {"coding": [{"system": ICD10, "code": code, "display": display}]},
                   "onsetDateTime": onset, "recordedDate": recorded or onset}, recorded or onset, note)

    def procedure(self, code, display, performed, recorded=None, note=None):
        self._add({"resourceType": "Procedure", "status": "completed",
                   "code": {"coding": [{"system": CPT, "code": code, "display": display}]},
                   "performedDateTime": performed}, recorded or performed, note)

    def observation(self, code, display, effective, value, unit, recorded=None, note=None):
        self._add({"resourceType": "Observation", "status": "final",
                   "code": {"coding": [{"system": LOINC, "code": code, "display": display}]},
                   "effectiveDateTime": effective, "issued": f"{recorded or effective}T09:00:00Z",
                   "valueQuantity": {"value": value, "unit": unit}}, recorded or effective, note)

    def medication(self, code, display, authored, status="active", recorded=None, note=None):
        self._add({"resourceType": "MedicationRequest", "status": status, "intent": "order",
                   "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": code, "display": display}]},
                   "authoredOn": authored}, recorded or authored, note)

    def encounter(self, code, display, start, recorded=None):
        self._add({"resourceType": "Encounter", "status": "finished",
                   "type": [{"coding": [{"system": CPT, "code": code, "display": display}]}],
                   "period": {"start": start}}, recorded or start, None)

    def document(self, code, display, date, text, recorded=None):
        self._add({"resourceType": "DocumentReference", "status": "current",
                   "type": {"coding": [{"system": LOINC, "code": code, "display": display}]},
                   "date": f"{date}T09:00:00Z",
                   "content": [{"attachment": {"contentType": "text/plain",
                                               "data": base64.b64encode(text.encode()).decode()}}]},
                  recorded or date, None)

    def write(self):
        bundle = {"resourceType": "Bundle", "type": "collection",
                  "entry": [{"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in self.entries]}
        path = OUT_DIR / f"{self.patient_id}.bundle.json"
        path.write_text(json.dumps(bundle, indent=2) + "\n")
        print(f"  {path.name:<22} {len(self.entries) - 1:>2} resources + Patient")


PT = ("97110", "Therapeutic exercise, each 15 minutes")
MRI = ("73721", "MRI, lower extremity joint, without contrast")
ARTHRO = ("29881", "Arthroscopy, knee, surgical; with meniscectomy (medial OR lateral)")
BMI = ("39156-5", "Body mass index (BMI) [Ratio]")
A1C = ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood")
INSULIN = ("274783", "Insulin Glargine 100 UNT/ML Injection")

print("writing FHIR bundles:")

# ---------------------------------------------------------------- P-1042
b = Bundle("P-1042", "1968-04-12", "female")
b.condition("I48.91", "Unspecified atrial fibrillation", "2024-08-12")
b.medication("855332", "Warfarin Sodium 5 MG Oral Tablet", "2024-08-15",
             note="Warfarin 5mg daily for atrial fibrillation. INR goal 2.0-3.0.")
b.condition("M17.11", "Unilateral primary osteoarthritis, right knee", "2025-11-03",
            note="Orthopedic consultation. Right knee pain, worse with stairs. Radiographs show "
                 "medial joint space narrowing. Kellgren-Lawrence grade 3.")
b.encounter("99204", "Office visit, new patient", "2025-11-03")
for d in ["2026-01-12", "2026-01-26", "2026-02-09", "2026-02-23",
          "2026-03-09", "2026-03-23", "2026-04-06", "2026-04-20"]:
    b.procedure(*PT, d)
# >>> BACKDATED: performed Nov/Dec 2025, entered into the record 2026-06-20 (after the 06-01 surgery)
b.procedure(*PT, "2025-11-17", recorded="2026-06-20", note="Late entry. Supervised therapeutic exercise, right knee.")
b.procedure(*PT, "2025-12-15", recorded="2026-06-20", note="Late entry. Supervised therapeutic exercise, right knee.")
b.observation(*BMI, "2026-03-09", 34.2, "kg/m2")
b.procedure(*MRI, "2026-05-04", recorded="2026-05-05",
            note="MRI right knee: full-thickness cartilage loss medial femoral condyle. "
                 "Complex tear posterior horn medial meniscus.")
b.document("11506-3", "Progress note", "2026-04-20",
           "Patient continues to report persistent right knee pain despite structured physical "
           "therapy. Antalgic gait. Failed conservative management. Discussed arthroscopic partial meniscectomy.")
b.procedure(*ARTHRO, "2026-06-01")
b.medication("1092398", "Ketorolac Tromethamine 30 MG/ML Injection", "2026-06-01",
             note="Toradol 30mg IM post-operatively for pain control.")
b.write()

# ---------------------------------------------------------------- P-4455
b = Bundle("P-4455", "1979-09-30", "male")
b.condition("M23.221", "Derangement of posterior horn of medial meniscus, right knee", "2025-08-19",
            note="Medial joint line tenderness, positive McMurray. Suspect medial meniscal tear.")
for d in ["2025-09-08", "2025-09-29", "2025-10-20", "2025-11-10",
          "2025-12-15", "2026-01-19", "2026-02-16", "2026-03-16"]:
    b.procedure(*PT, d)
b.observation(*BMI, "2026-02-16", 28.7, "kg/m2")
b.procedure(*MRI, "2026-04-02", note="MRI right knee: displaced bucket-handle tear of the medial meniscus.")
b.procedure(*ARTHRO, "2026-05-11")
b.write()

# ------------------------------------------------- P-2087 / P-3311 (the pair)
b = Bundle("P-2087", "1961-02-02", "male")
b.condition("E11.9", "Type 2 diabetes mellitus without complications", "2025-03-14",
            note="Type 2 diabetes mellitus, poorly controlled. Metformin and basal insulin.")
b.observation(*A1C, "2026-05-20", 9.2, "%")
b.medication(*INSULIN, "2025-09-01")
b.write()

b = Bundle("P-3311", "1994-07-21", "female")
b.condition("E10.9", "Type 1 diabetes mellitus without complications", "2019-06-02",
            note="Type 1 diabetes mellitus, on multiple daily injections.")
b.observation(*A1C, "2026-05-18", 7.4, "%")
b.medication(*INSULIN, "2019-06-05")
b.write()
