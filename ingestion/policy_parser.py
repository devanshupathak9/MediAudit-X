"""Policy preprocessing: raw policy text -> section chunks with metadata.

Pure functions, no Elasticsearch. Metadata is extracted with regex, so codes and
numbers are copied from the text, never guessed. Byte offsets point at the exact
span of the original file, so every chunk is a verifiable citation.
"""
import hashlib
import re
from pathlib import Path

# A new chunk starts at "SECTION 2. ..." or at a numbered rule like "2.1 "
CHUNK_START = re.compile(rb"^(?:SECTION \d+\.|\d+\.\d+ )", re.MULTILINE)

# Section title -> chunk type
TYPE_BY_SECTION = {
    "SCOPE": "scope",
    "MEDICAL NECESSITY CRITERIA": "criteria_intro",
    "DOCUMENTATION STANDARDS": "documentation",
    "LIMITATIONS AND EXCLUSIONS": "exclusion",
    "CODING": "coding",
}

THRESHOLD_OPS = {"less than": "lt", "greater than": "gt", "at least": "gte", "no more than": "lte"}


def find(pattern, text):
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else None


def policy_metadata(text: str) -> dict:
    """Metadata that is true for the whole policy (copied onto every chunk)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    scope = find(r"(SECTION 1\..*?)SECTION 2\.", text) or ""
    return {
        "payer": lines[0],                                    # MERIDIAN HEALTH PLAN
        "policy_id": find(r"POLICY BULLETIN (\S+)", text),    # MHP-0673
        "title": lines[2],                                    # ARTHROSCOPIC SURGERY OF THE KNEE
        "version": find(r"Version ([\d.]+)", text),
        "supersedes": find(r"Supersedes ([\d.]+)", text),
        "effective_from": find(r"Effective (\d{4}-\d{2}-\d{2})", text),
        "effective_to": None,
        "applies_to_cpt": re.findall(r"\b\d{5}\b", scope),    # CPT codes listed in the Scope section
    }


def chunk_metadata(text: str) -> dict:
    """Metadata found inside this one section only."""
    threshold = re.search(r"(less than|greater than|at least|no more than)\s+(\d+(?:\.\d+)?)\s*(kg/m2|%|mg/dL)?", text)
    return {
        "cpt_codes_mentioned": sorted(set(re.findall(r"\b\d{5}\b", text))),
        "icd_codes_mentioned": sorted(set(re.findall(r"\b[A-Z]\d{2}\.\d{1,4}\b", text))),
        # "six (6) months" -> 6,  "forty-five (45) days" -> 45
        "duration_months": sorted({int(n) for n in re.findall(r"\((\d+)\)\s+months", text)}),
        "duration_days": sorted({int(n) for n in re.findall(r"\((\d+)\)\s+days", text)}),
        "threshold_op": THRESHOLD_OPS[threshold.group(1)] if threshold else None,
        "threshold_value": float(threshold.group(2)) if threshold else None,
        "threshold_unit": threshold.group(3) if threshold else None,
    }


def split_into_chunks(raw: bytes):
    """Yield (byte_start, byte_end, text). Offsets point at the exact text in the file."""
    starts = [0] + [m.start() for m in CHUNK_START.finditer(raw)]
    ends = starts[1:] + [len(raw)]
    for start, end in zip(starts, ends):
        piece = raw[start:end]
        stripped = piece.strip()
        if stripped:
            byte_start = start + (len(piece) - len(piece.lstrip()))
            yield byte_start, byte_start + len(stripped), stripped.decode("utf-8")


class PolicyRejected(ValueError):
    """The file does not look like a policy we can cite reliably."""


REQUIRED = ("policy_id", "version", "effective_from")


def build_chunks(policy_file: Path) -> list[dict]:
    """One dict per section: the raw English text + its metadata."""
    raw = policy_file.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise PolicyRejected(f"{policy_file.name}: not UTF-8 text") from e

    policy = policy_metadata(text)

    # Guardrail: refuse policies missing the fields that filters depend on.
    missing = [k for k in REQUIRED if not policy[k]]
    if missing:
        raise PolicyRejected(f"{policy_file.name}: could not find {missing} in the policy header")
    if not policy["applies_to_cpt"]:
        raise PolicyRejected(f"{policy_file.name}: no CPT codes found in SECTION 1 (scope)")

    policy["source_sha256"] = hashlib.sha256(raw).hexdigest()

    chunks = []
    section_title = "HEADER"
    for i, (byte_start, byte_end, text) in enumerate(split_into_chunks(raw)):
        first_line = text.split("\n", 1)[0]

        header = re.match(r"SECTION (\d+)\. (.+)", first_line)
        rule = re.match(r"(\d+\.\d+) ", first_line)
        if header:
            section_no, section_title = header.group(1), header.group(2).strip()
            chunk_type = TYPE_BY_SECTION.get(section_title, "other")
        elif rule:
            section_no, chunk_type = rule.group(1), "criterion"   # section_title stays the parent's
        else:
            section_no, chunk_type = "0", "header"

        chunks.append({
            "text": text,
            "metadata": {
                "chunk_id": f"{policy['policy_id']}::{i:02d}",
                **policy,
                "section_no": section_no,
                "section_title": section_title,
                "chunk_type": chunk_type,
                **chunk_metadata(text),
                "source_file": policy_file.name,
                "byte_start": byte_start,
                "byte_end": byte_end,
            },
        })
    return chunks

