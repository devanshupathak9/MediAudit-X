"""FHIR preprocessing: FHIR R4 bundle -> one flat event row per clinical fact.

Every resource type hides its dates and codes in different places. This file is
the only place that knows those differences; everything downstream sees rows of
the same shape, so one ES|QL query can answer any timeline question.

Two dates per row (bi-temporal):
  event_time   when it clinically happened
  recorded_at  when it entered the record (recordedDate / issued / meta.lastUpdated)
"""
import base64

CODE_SYSTEMS = {
    "http://hl7.org/fhir/sid/icd-10-cm": "ICD10",
    "http://hl7.org/fhir/sid/icd-10": "ICD10",
    "http://www.ama-assn.org/go/cpt": "CPT",
    "http://loinc.org": "LOINC",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "RxNorm",
    "http://snomed.info/sct": "SNOMED",
}

# resourceType -> (event_type, where the code is, where the clinical date is)
RESOURCES = {
    "Condition":         ("diagnosis",   lambda r: r.get("code"),                        lambda r: r.get("onsetDateTime")),
    "Procedure":         ("procedure",   lambda r: r.get("code"),                        lambda r: r.get("performedDateTime") or (r.get("performedPeriod") or {}).get("start")),
    "Observation":       ("observation", lambda r: r.get("code"),                        lambda r: r.get("effectiveDateTime")),
    "MedicationRequest": ("medication",  lambda r: r.get("medicationCodeableConcept"),   lambda r: r.get("authoredOn")),
    "Encounter":         ("encounter",   lambda r: (r.get("type") or [None])[0],         lambda r: (r.get("period") or {}).get("start")),
    "DocumentReference": ("note",        lambda r: r.get("type"),                        lambda r: r.get("date")),
}


class BundleRejected(ValueError):
    """The upload is not a FHIR bundle we can use."""


def to_timestamp(value: str | None) -> str | None:
    """'2026-01-12' -> '2026-01-12T00:00:00Z'. Full timestamps pass through."""
    if not value:
        return None
    return value if "T" in value else f"{value}T00:00:00Z"


def first_coding(concept: dict | None) -> tuple[str | None, str | None, str | None]:
    """(code_system, code, display) of the first coding we recognise."""
    for coding in (concept or {}).get("coding", []):
        system = CODE_SYSTEMS.get(coding.get("system"))
        if system and coding.get("code"):
            return system, coding["code"], coding.get("display")
    return None, None, None


def note_text(resource: dict) -> str | None:
    parts = [n["text"] for n in resource.get("note", []) if n.get("text")]
    for content in resource.get("content", []):  # DocumentReference: base64 text attachment
        attachment = content.get("attachment", {})
        if attachment.get("contentType", "").startswith("text/") and attachment.get("data"):
            parts.append(base64.b64decode(attachment["data"]).decode("utf-8"))
    return "\n".join(parts) or None


def recorded_time(resource: dict) -> str | None:
    return to_timestamp(resource.get("recordedDate") or resource.get("issued")
                        or resource.get("meta", {}).get("lastUpdated"))


def flatten_bundle(bundle: dict, source_file: str) -> tuple[str, list[dict], list[str]]:
    """Return (patient_id, rows, warnings). Skipped resources are reported, never silently dropped."""
    if bundle.get("resourceType") != "Bundle":
        raise BundleRejected(f"{source_file}: resourceType is {bundle.get('resourceType')!r}, expected 'Bundle'")

    resources = [e.get("resource", {}) for e in bundle.get("entry", [])]
    patients = [r for r in resources if r.get("resourceType") == "Patient"]
    if len(patients) != 1:
        raise BundleRejected(f"{source_file}: expected exactly 1 Patient, found {len(patients)}")
    patient_id = patients[0]["id"]

    rows, warnings = [], []
    for r in resources:
        rtype = r.get("resourceType")
        if rtype == "Patient":
            continue
        where = f"{rtype}/{r.get('id')}"
        if rtype not in RESOURCES:
            warnings.append(f"skipped {where}: resource type not supported yet")
            continue

        # Guardrail: every row must belong to the bundle's patient.
        if r.get("subject", {}).get("reference") != f"Patient/{patient_id}":
            warnings.append(f"skipped {where}: subject is not Patient/{patient_id}")
            continue

        event_type, get_code, get_date = RESOURCES[rtype]
        code_system, code, display = first_coding(get_code(r))
        event_time = to_timestamp(get_date(r))

        if not code or not event_time:
            warnings.append(f"skipped {where}: missing {'code' if not code else 'clinical date'}")
            continue

        value = r.get("valueQuantity") or {}
        rows.append({
            "event_id": f"{patient_id}:{where}",
            "patient_id": patient_id,
            "encounter_id": (r.get("encounter") or {}).get("reference"),
            "event_type": event_type,
            "code_system": code_system,
            "code": code,
            "code_text": display,
            "note_text": note_text(r),
            "value_num": value.get("value"),
            "value_unit": value.get("unit"),
            "status": r.get("status"),
            "event_time": event_time,
            "event_end": None,
            "recorded_at": recorded_time(r) or event_time,
            "source_doc_id": source_file,
            "source_path": where,
        })
    return patient_id, rows, warnings
