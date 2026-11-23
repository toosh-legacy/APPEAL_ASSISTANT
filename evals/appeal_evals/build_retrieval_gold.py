"""Builds evals/gold/retrieval.jsonl.

Relevance is defined WITHOUT the retriever: a regulation/summary chunk is relevant if its text contains
all of the given phrases (within the given source), or it is a listed summary section; a precedent is
relevant if it matches metadata + text filters. Questions whose phrases resolve to nothing are dropped
and reported (so the set never contains unverifiable labels).
"""

from __future__ import annotations

import json
from pathlib import Path

from appeal_core.db import get_engine
from sqlalchemy import text

OUT = Path(__file__).resolve().parents[1] / "gold" / "retrieval.jsonl"
E, IND, MA, MD = "employer_self_funded", "individual_marketplace", "medicare_advantage", "medicaid_managed_care"

# (query, plan_type, source_id or None, [phrases...], [summary ids])
RULE_Q = [
    ("deadline to file internal appeal employer plan", E, "29cfr2560.503-1", ["at least 180 days following receipt"], ["sum:employer_plans#your-deadline-to-appeal"]),
    ("how many days do I have to appeal a denial from my job's health plan", E, "29cfr2560.503-1", ["at least 180 days following receipt"], ["sum:employer_plans#your-deadline-to-appeal"]),
    ("individual marketplace plan internal appeal rules", IND, "45cfr147.136", ["individual health insurance coverage must comply with all the requirements"], ["sum:individual_marketplace#your-deadline-to-appeal"]),
    ("how long do I have to request an external review", E, "45cfr147.136", ["within four months after the date of receipt"], ["sum:employer_plans#external-review"]),
    ("external review request four months marketplace plan", IND, "45cfr147.136", ["within four months after the date of receipt"], ["sum:individual_marketplace#external-review"]),
    ("Medicare Advantage reconsideration filing deadline", MA, "42cfr422.M", ["request for reconsideration must be filed within 60 calendar days"], ["sum:medicare_advantage#your-deadline-to-ask-for-reconsideration"]),
    ("how long to appeal Medicare Advantage organization determination", MA, "42cfr422.M", ["within 60 calendar days after receipt of the written organization determination notice"], []),
    ("Medicaid managed care appeal deadline", MD, "42cfr438.F", ["60 calendar days from the date on the adverse benefit determination notice"], ["sum:medicaid_managed_care#your-deadline-to-appeal"]),
    ("state fair hearing time limit medicaid", MD, "42cfr438.F", ["no less than 90 calendar days and no more than 120 calendar days"], ["sum:medicaid_managed_care#state-fair-hearing"]),
    ("urgent care appeal decision 72 hours employer plan", E, "29cfr2560.503-1", ["72 hours after receipt of the claimant's request for review"], ["sum:employer_plans#urgent-care-appeals"]),
    ("copies of documents relevant to my claim free of charge", E, "29cfr2560.503-1", ["free of charge", "copies of, all documents, records, and other information relevant"], ["sum:employer_plans#what-a-full-and-fair-review-includes"]),
    ("consult a health care professional with appropriate training on appeal", E, "29cfr2560.503-1", ["health care professional who has appropriate training and experience"], ["sum:employer_plans#medical-judgment-on-appeal"]),
    ("appeal review takes into account all comments documents records submitted", E, "29cfr2560.503-1", ["takes into account all comments, documents, records, and other information submitted"], []),
    ("emergency services without prior authorization out of network", E, "45cfr149.110", ["without the need for any prior authorization determination"], ["sum:surprise_billing#emergency-care-without-prior-approval"]),
    ("expedited reconsideration Medicare Advantage 72 hours", MA, "42cfr422.M", ["expedited reconsideration", "72 hours"], ["sum:medicare_advantage#expedited-fast-reconsideration"]),
    ("independent outside entity review when MA plan affirms denial", MA, "42cfr422.M", ["reviewed and resolved by an independent, outside entity"], ["sum:medicare_advantage#independent-review"]),
    ("continuation of benefits while medicaid appeal pending", MD, "42cfr438.F", ["continuation of benefits"], []),
    ("expedited appeal medicaid managed care timeframe", MD, "42cfr438.F", ["no longer than 72 hours after the MCO, PIHP, or PAHP receives the appeal"], ["sum:medicaid_managed_care#expedited-appeals"]),
    ("what must a denial notice say specific reason for adverse determination", E, "29cfr2560.503-1", ["specific reason or reasons for the adverse determination"], ["sum:general_rights#the-denial-notice-must-explain-itself"]),
    ("denial notice must include the denial code and its meaning", E, "45cfr147.136", ["denial code and its corresponding meaning"], []),
    ("post-service claim appeal decision 60 days", E, "29cfr2560.503-1", ["not later than 60 days after receipt by the plan of the claimant's request for review"], []),
    ("pre-service claim appeal decision 30 days group health plan", E, "29cfr2560.503-1", ["not later than 30 days after receipt by the plan of the claimant's request for review"], []),
    ("initial benefit determination urgent care claim 72 hours", E, "29cfr2560.503-1", ["not later than 72 hours after receipt of the claim by the plan"], []),
    ("plan must not defer to initial adverse determination on appeal", E, "29cfr2560.503-1", ["does not afford deference to the initial adverse benefit determination"], []),
    ("appeal decided by someone who did not make the initial decision", E, "29cfr2560.503-1", ["neither the individual who made the adverse benefit determination"], []),
    ("rescission of coverage counts as adverse benefit determination", IND, "45cfr147.136", ["rescission"], []),
    ("deemed exhausted internal appeals plan failed to follow rules", E, "45cfr147.136", ["deemed to have exhausted the internal claims and appeals process"], []),
    ("culturally and linguistically appropriate notices", IND, "45cfr147.136", ["culturally and linguistically appropriate"], []),
    ("expedited external review urgent medical condition", E, "45cfr147.136", ["expedited external review"], []),
    ("continued coverage pending outcome of appeal concurrent care", E, "45cfr147.136", ["continued coverage pending the outcome of an appeal"], []),
    ("standard reconsideration Medicare Advantage decision 30 days", MA, "42cfr422.M", ["standard reconsideration"], []),
    ("who may request reconsideration Medicare Advantage", MA, "42cfr422.M", ["parties to the organization determination"], []),
    ("Medicare Advantage ALJ hearing request 60 days", MA, "42cfr422.M", ["file a request for a hearing within 60 calendar days"], []),
    ("good cause extension for filing reconsideration late", MA, "42cfr422.M", ["good cause"], []),
    ("medicaid grievance filed at any time", MD, "42cfr438.F", ["may file a grievance with the MCO, PIHP, or PAHP at any time"], []),
    ("medicaid plan must provide notice of adverse benefit determination in writing", MD, "42cfr438.F", ["notice of adverse benefit determination"], []),
    ("medicaid appeal resolution standard timeframe 30 calendar days", MD, "42cfr438.F", ["30 calendar days"], []),
    ("surprise billing out-of-network provider at in-network facility", E, "45cfr149.120", ["nonparticipating provider", "participating health care facility"], ["sum:surprise_billing#out-of-network-providers-at-in-network-facilities"]),
    ("air ambulance out of network cost sharing", E, "45cfr149.130", ["air ambulance"], []),
    ("notice and consent to waive balance billing protections", E, "45cfr149.420", ["notice and consent"], []),
    ("emergency cost sharing same as in network", E, "45cfr149.110", ["cost-sharing requirement"], ["sum:surprise_billing#out-of-network-emergency-care"]),
    ("keep copies and send appeal in writing", E, None, [], ["sum:general_rights#keep-copies-and-send-in-writing"]),
]

# (query, filters) ; relevant = precedent chunks matching all filters
PREC_Q = [
    ("MRI lumbar spine medical necessity", {"treatment_subcategory": "MRI", "text_like": "%lumbar%"}),
    ("MRI of the brain headaches", {"treatment_subcategory": "MRI", "text_like": "%brain%"}),
    ("residential treatment center eating disorder", {"treatment_subcategory": "RTC", "text_like": "%eating disorder%"}),
    ("residential treatment substance use disorder", {"treatment_category": "Mental Health", "text_like": "%substance%"}),
    ("applied behavior analysis autism therapy hours", {"treatment_subcategory": "Appld Behav Analysis"}),
    ("proton beam therapy prostate cancer", {"treatment_subcategory": "Proton Beam", "text_like": "%prostate%"}),
    ("transcranial magnetic stimulation depression", {"treatment_subcategory": "TMS"}),
    ("gastric bypass bariatric surgery obesity", {"treatment_subcategory": "Gastric Bypass"}),
    ("IVIG immune globulin infusion", {"treatment_subcategory": "IVIG Therapy"}),
    ("genetic testing hereditary cancer BRCA", {"treatment_subcategory": "Genetic/Genomic Test", "text_like": "%BRCA%"}),
    ("viscosupplementation knee injection osteoarthritis", {"treatment_subcategory": "Viscosupp Injection"}),
    ("spinal fusion lumbar degenerative disc", {"treatment_subcategory": "Fusion"}),
    ("artificial disc replacement cervical", {"treatment_subcategory": "Artificial Disc Repl"}),
    ("PET scan cancer staging", {"treatment_subcategory": "PET Scan"}),
    ("speech therapy child developmental delay", {"treatment_subcategory": "Speech Therapy"}),
    ("physical therapy outpatient visits after surgery", {"treatment_subcategory": "Physical Therapy"}),
    ("Botox injections chronic migraine", {"treatment_subcategory": "Botox Injection", "text_like": "%migraine%"}),
    ("weight loss medication obesity", {"treatment_subcategory": "Weight Control"}),
    ("breast reduction surgery back pain", {"treatment_category": "Reconstr/Plast Proc", "text_like": "%reduction%"}),
    ("acupuncture chronic pain", {"treatment_subcategory": "Acupuncture"}),
    ("partial hospitalization program mental health", {"treatment_subcategory": "Partial Hospital"}),
    ("radiofrequency ablation back pain facet", {"treatment_subcategory": "Radiofreq Ablat"}),
    ("continuous glucose monitor diabetes", {"text_like": "%continuous glucose monitor%"}),
    ("experimental treatment clinical trial cancer drug", {"type": "Experimental/Investigational", "treatment_category": "Cancer Care"}),
]


def resolve_rules(c, source_id, phrases):
    if not phrases:
        return []
    sql = "SELECT id FROM kb_chunk WHERE source_kind='regulation'"
    params = {}
    if source_id:
        sql += " AND source_id = :sid"
        params["sid"] = source_id
    for i, p in enumerate(phrases):
        sql += f" AND lower(regexp_replace(coalesce(heading, '') || ' ' || text, '\\s+', ' ', 'g')) LIKE :p{i}"
        params[f"p{i}"] = f"%{p.lower()}%"
    return [r[0] for r in c.execute(text(sql + " ORDER BY id"), params)]


def resolve_prec(c, f):
    sql = "SELECT id FROM precedent_chunk WHERE true"
    params = {}
    for k, v in f.items():
        if k == "text_like":
            sql += " AND text ILIKE :tl"
            params["tl"] = v
        else:
            sql += f" AND {k} = :{k}"
            params[k] = v
    return [r[0] for r in c.execute(text(sql + " ORDER BY id"), params)]


def build() -> dict:
    out, dropped = [], []
    with get_engine().connect() as c:
        existing = {r[0] for r in c.execute(text("SELECT id FROM kb_chunk WHERE source_kind='summary'"))}
        for i, (q, pt, sid, phrases, sums) in enumerate(RULE_Q):
            rel = resolve_rules(c, sid, phrases) + [s for s in sums if s in existing]
            if not rel:
                dropped.append(q)
                continue
            out.append({"id": f"rq{i:02d}", "collection": "rules", "query": q, "plan_type": pt, "relevant": rel, "definition": {"source_id": sid, "phrases": phrases, "summaries": sums}})
        for i, (q, f) in enumerate(PREC_Q):
            rel = resolve_prec(c, f)
            if not rel:
                dropped.append(q)
                continue
            out.append({"id": f"pq{i:02d}", "collection": "precedents", "query": q, "relevant": rel, "definition": f})
    OUT.write_text("\n".join(json.dumps(o) for o in out) + "\n", encoding="utf-8")
    return {"questions": len(out), "rules": sum(o["collection"] == "rules" for o in out), "precedents": sum(o["collection"] == "precedents" for o in out), "dropped": dropped}


if __name__ == "__main__":
    print(build())
