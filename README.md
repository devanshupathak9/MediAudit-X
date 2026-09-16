# MediAudit-X

Checks whether a medical insurance claim meets the insurer's policy, and shows the exact evidence for every answer.

**How it works**

1. **Receives** the insurance policy, the patient's medical history (FHIR) and the claim.
2. **Indexes** them in Elasticsearch: policy sections with metadata and vectors, and the patient history as a timeline.
3. **Finds** the policy rules that apply to the claim, using exact code filters plus hybrid (keyword + vector) search.
4. **Checks** each rule against the patient's record *as of the date of service*, so notes added after the surgery don't count.
5. **Reports** approve / deny / pend, with citations pointing to the exact policy text and patient records.

The LLM only explains the result; searching, counting and the final decision are done by Elasticsearch and code.
