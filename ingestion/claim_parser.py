"""Claim preprocessing: validate the claim before anything is indexed.

Guardrail: bad input is rejected here, with a reason, instead of producing a
confident-looking decision later.
"""
import re
from datetime import date

CPT = re.compile(r"^\d{5}$")
ICD10 = re.compile(r"^[A-Z]\d{2}(\.\w{1,4})?$")
REQUIRED = ("claim_id", "patient_id", "payer", "cpt", "icd", "date_of_service")


class ClaimRejected(ValueError):
    """The claim is incomplete or malformed."""


def parse_claim(claim: dict) -> dict:
    missing = [k for k in REQUIRED if not claim.get(k)]
    if missing:
        raise ClaimRejected(f"missing fields: {missing}")
    if not CPT.match(claim["cpt"]):
        raise ClaimRejected(f"cpt {claim['cpt']!r} is not a 5-digit CPT code")
    bad_icd = [c for c in claim["icd"] if not ICD10.match(c)]
    if bad_icd:
        raise ClaimRejected(f"invalid ICD-10 codes: {bad_icd}")
    try:
        dos = date.fromisoformat(claim["date_of_service"])
    except ValueError as e:
        raise ClaimRejected(f"date_of_service {claim['date_of_service']!r} is not YYYY-MM-DD") from e
    if dos > date.today():
        raise ClaimRejected(f"date_of_service {dos} is in the future")

    return {
        "claim_id": claim["claim_id"],
        "patient_id": claim["patient_id"],
        "payer": claim["payer"],
        "cpt": claim["cpt"],
        "icd": list(claim["icd"]),
        "date_of_service": dos.isoformat(),
        "billed_amount": claim.get("billed_amount"),
    }
