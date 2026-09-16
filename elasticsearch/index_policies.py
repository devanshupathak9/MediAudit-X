"""Read policy .txt files, split into sections, extract metadata, embed, index.

Everything comes from the policy text itself (no criteria JSON).
Metadata is extracted with regex, so codes and numbers are never guessed.
Embedding and storage go through LangChain (ElasticsearchStore).

    python index_policies.py
"""
import re

from langchain_elasticsearch import ElasticsearchStore

from embedder import MODEL_NAME, get_embeddings
from es_client import DATA_DIR, es

INDEX = "payer-policies"
POLICY_DIR = DATA_DIR / "policies"

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


def build_chunks(policy_file) -> list[dict]:
    """One dict per section: the raw English text + its metadata."""
    raw = policy_file.read_bytes()
    policy = policy_metadata(raw.decode("utf-8"))

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


if __name__ == "__main__":
    saved_model = es.indices.get_mapping(index=INDEX)[INDEX]["mappings"].get("_meta", {}).get("embedding_model")
    if saved_model != MODEL_NAME:
        raise SystemExit(f"Index was created for {saved_model!r} but .env selects {MODEL_NAME!r}. "
                         f"Run create_indices.py first.")

    embeddings = get_embeddings()
    store = ElasticsearchStore(index_name=INDEX, client=es, embedding=embeddings,
                               query_field="chunk_text", vector_query_field="chunk_vector")

    for policy_file in sorted(POLICY_DIR.glob("*.txt")):
        chunks = build_chunks(policy_file)
        meta = [c["metadata"] for c in chunks]

        # Store the raw English, but embed title + section + text:
        # "less than 40.0 kg/m2" alone means little to the model.
        texts_to_embed = [f"{m['title']}. Section {m['section_no']} {m['section_title']}. {c['text']}"
                          for c, m in zip(chunks, meta)]
        vectors = embeddings.embed_documents(texts_to_embed)

        store.add_embeddings(
            text_embeddings=list(zip([c["text"] for c in chunks], vectors)),
            metadatas=meta,
            ids=[m["chunk_id"] for m in meta],
            create_index_if_not_exists=False,  # create_indices.py owns the mapping
        )

        print(f"\n{policy_file.name}: indexed {len(chunks)} chunks with {MODEL_NAME}")
        for m in meta:
            extras = {k: m[k] for k in ("cpt_codes_mentioned", "icd_codes_mentioned", "duration_months",
                                        "duration_days", "threshold_value") if m[k]}
            print(f"  {m['chunk_id']}  §{m['section_no']:<4} {m['chunk_type']:<15} {extras}")
