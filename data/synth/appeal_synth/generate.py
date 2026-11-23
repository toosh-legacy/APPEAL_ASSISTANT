"""D4: deterministic synthetic denial-letter generator.

Every identifier is unmistakably fake (hard rule 8): Testperson names, ZZTEST member IDs, 555-01xx
phones, "123 Example St" addresses, fictional insurers. Gold letters use a *different* template family
and phrasing bank than train/validation letters, to measure generalization rather than memorization.

Gold has two families: 120 "gold" letters (notice layout) and, since Phase B, 80 "eob" letters: an
Explanation-of-Benefits layout with a claim table, different field labels, spelled-out dates and its own
plan/reason phrasings. The eob family was written without looking at the extraction rules, so it tests
whether extraction generalizes to a layout its author did not design it for.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from appeal_core.deadlines import compute_deadlines

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "processed" / "letters"
GOLD_DIR = ROOT / "evals" / "gold"

FIRST = ["Jordan", "Alex", "Casey", "Riley", "Morgan", "Taylor", "Jamie", "Avery", "Quinn", "Rowan", "Skyler", "Drew"]
LAST = ["Testperson", "Sampleton", "Exampleby", "Fakename", "Placeholder", "Demoson", "Mockridge", "Testwell"]
INSURERS = [
    "Example Health Plan",
    "Sample Mutual Insurance Co.",
    "Placeholder Care Network",
    "Demo Benefits Trust",
    "Fictional Health Partners",
    "Testcare Insurance Company",
]
STATES = ["CA", "TX", "NY", "FL", "IL", "WA", "OH", "GA", "AZ", "CO"]

# Plain-language service phrases mapped onto the real DMHC treatment / diagnosis vocabulary (D1).
SERVICES = [
    ("MRI of the lumbar spine", "Diag Imag & Screen", "MRI", "Orth/Musculoskeletal"),
    ("MRI of the brain", "Diag Imag & Screen", "MRI", "CNS/Neuromusc Dis"),
    ("CT scan of the abdomen", "Diag Imag & Screen", "CT Scan", "Digestive System/GI"),
    ("PET scan", "Diag Imag & Screen", "PET Scan", "Cancer"),
    ("genetic testing", "Diag Imag & Screen", "Genetic/Genomic Test", "Genetic Diseases"),
    ("screening mammogram", "Diag Imag & Screen", "Mammography", "Cancer"),
    ("residential treatment program", "Mental Health", "RTC", "Mental Disorder"),
    ("partial hospitalization program", "Mental Health", "Partial Hospital", "Mental Disorder"),
    ("intensive outpatient program", "Mental Health", "Intensive Outpt Prog", "Mental Disorder"),
    ("transcranial magnetic stimulation", "Elect/Therm/Radfreq", "TMS", "Mental Disorder"),
    ("outpatient physical therapy", "Rehab/Svc - Outpt", "Physical Therapy", "Orth/Musculoskeletal"),
    ("speech therapy", "Rehab/Svc - Outpt", "Speech Therapy", "CNS/Neuromusc Dis"),
    ("applied behavior analysis therapy", "Autism Related Tx", "Appld Behav Analysis", "Autism Spectrum"),
    ("knee injection (viscosupplementation)", "Pain Management", "Viscosupp Injection", "Orth/Musculoskeletal"),
    ("nerve block injection", "Pain Management", "Nerve Block", "Chron Pain Synd"),
    ("radiofrequency ablation", "Elect/Therm/Radfreq", "Radiofreq Ablat", "Chron Pain Synd"),
    ("spinal fusion surgery", "Orthopedic Proc", "Fusion", "Orth/Musculoskeletal"),
    ("artificial disc replacement", "Orthopedic Proc", "Artificial Disc Repl", "Orth/Musculoskeletal"),
    ("proton beam therapy", "Cancer Care", "Proton Beam", "Cancer"),
    ("chemotherapy", "Cancer Care", "Chemotherapy", "Cancer"),
    ("gastric bypass surgery", "Gen Surg Proc", "Gastric Bypass", "Morbid Obesity"),
    ("weight-loss medication", "Pharmacy", "Weight Control", "Endocrine/Metabolic"),
    ("biologic medication for arthritis", "Pharmacy", "Biologics", "Immuno Disorders"),
    ("IVIG infusion therapy", "Pharmacy", "IVIG Therapy", "Immuno Disorders"),
    ("Botox injections for migraine", "Pharmacy", "Botox Injection", "CNS/Neuromusc Dis"),
    ("continuous glucose monitor", "DME", "Other", "Endocrine/Metabolic"),
    ("power wheelchair", "DME", "Other", "CNS/Neuromusc Dis"),
    ("emergency room visit", "Emergency/Urg Care", "Emergency Room", "Trauma/Injuries"),
    ("inpatient hospital admission", "Acute Med Svc Inpt", "Admission", "Cardiac/Circ Problem"),
    ("skilled nursing facility stay", "Rehab/Svcs SNF Inpt", "Inpt Admission", "Orth/Musculoskeletal"),
    ("acupuncture", "Alternative Tx", "Acupuncture", "Chron Pain Synd"),
    ("breast reconstruction surgery", "Reconstr/Plast Proc", "Other", "Cancer"),
]

PLAN_PHRASES = {
    "train": {
        "employer_self_funded": "This is a self-funded group health plan sponsored by your employer and governed by ERISA.",
        "employer_fully_insured": "Your coverage is an insured group health plan provided through your employer.",
        "individual_marketplace": "Your coverage is an individual health plan purchased through the Health Insurance Marketplace.",
        "medicare_advantage": "You are enrolled in a Medicare Advantage plan.",
        "medicaid_managed_care": "You are enrolled in a Medicaid managed care plan.",
    },
    "gold": {
        "employer_self_funded": "Plan type: Employer self-funded (ERISA) group plan",
        "employer_fully_insured": "Plan type: Employer group plan (fully insured)",
        "individual_marketplace": "Plan type: Individual / Marketplace (ACA) coverage",
        "medicare_advantage": "Plan type: Medicare Advantage (Part C)",
        "medicaid_managed_care": "Plan type: Medicaid managed care (state program)",
    },
    "eob": {
        "employer_self_funded": "Coverage: group health benefits through your employer (self-insured, ERISA plan)",
        "employer_fully_insured": "Coverage: employer group insurance policy",
        "individual_marketplace": "Coverage: individual policy bought on the ACA marketplace",
        "medicare_advantage": "Coverage: Medicare Advantage HMO",
        "medicaid_managed_care": "Coverage: state Medicaid program, managed care plan",
    },
}

# Reason phrasings per category. "train" and "gold" banks are disjoint.
REASONS = {
    "train": {
        "medical_necessity": [
            "We reviewed the request for {service} and determined it is not medically necessary based on the information provided.",
            "The requested {service} does not meet our medical necessity criteria for your condition.",
            "Our medical reviewer found that {service} is not medically necessary at this time because conservative treatment has not been documented.",
        ],
        "prior_authorization": [
            "The claim for {service} was denied because prior authorization was not obtained before the service was provided.",
            "{service} requires precertification under your plan, and no approval was on file.",
            "We did not receive a prior authorization request for {service} before the date of service.",
        ],
        "out_of_network": [
            "The claim for {service} was denied because the provider is not in your plan's network.",
            "{service} was provided by an out-of-network provider and your plan does not cover out-of-network services except in emergencies.",
            "Your plan only covers {service} when provided by a participating (in-network) provider.",
        ],
        "coding_billing_error": [
            "The claim for {service} was denied because the procedure code is inconsistent with the diagnosis billed.",
            "The claim was submitted with missing or invalid billing information and cannot be processed.",
            "This claim appears to be a duplicate of a claim already processed.",
        ],
        "experimental_investigational": [
            "{service} is considered experimental or investigational for your condition and is not covered.",
            "The requested {service} is investigational because there is insufficient evidence of its effectiveness for your diagnosis.",
            "Our policy considers {service} experimental for this use.",
        ],
        "not_covered_benefit": [
            "{service} is not a covered benefit under your plan.",
            "Your plan excludes coverage for {service}.",
            "The charges for {service} are not covered under the terms of your benefit plan.",
        ],
        "timely_filing": [
            "The claim for {service} was received after the filing deadline and is denied for untimely filing.",
            "This claim was not submitted within the time limit required by your plan.",
            "The time limit for filing this claim has expired.",
        ],
        "other_unclear": [
            "Your claim for {service} has been denied. Please contact Member Services for more information.",
            "After review, we are unable to approve payment for {service}.",
            "The claim for {service} was not approved.",
        ],
    },
    "gold": {
        "medical_necessity": [
            "Based on the clinical records submitted, {service} is not considered medically appropriate; less intensive treatment options should be tried first.",
            "Coverage for {service} is denied: the documentation does not support that this level of care is medically required.",
        ],
        "prior_authorization": [
            "Payment for {service} is denied. The service needed advance approval from the plan, which was not requested.",
            "No pre-service approval (authorization) was found for {service}; the plan requires one for this service.",
        ],
        "out_of_network": [
            "{service} was received from a non-participating provider. Benefits are limited to in-network care for this service.",
            "The treating facility is outside the plan network, so {service} is not payable at the in-network level.",
        ],
        "coding_billing_error": [
            "The billed procedure code and modifier do not match; the provider must correct and resubmit the claim for {service}.",
            "The claim for {service} lacks required information (diagnosis pointer) and was rejected.",
        ],
        "experimental_investigational": [
            "The plan considers {service} unproven for this diagnosis; current medical literature does not establish its effectiveness.",
            "{service} remains under clinical study for this indication and is excluded as investigational.",
        ],
        "not_covered_benefit": [
            "The plan's Evidence of Coverage lists {service} as an exclusion.",
            "{service} falls outside the benefits included in your policy.",
        ],
        "timely_filing": [
            "The provider submitted the claim for {service} beyond the plan's claim submission period.",
            "Claim received too late: the submission window for {service} had closed.",
        ],
        "other_unclear": [
            "Benefits for {service} cannot be provided. See the explanation of benefits for details.",
            "We have made an adverse determination regarding {service}.",
        ],
    },
    "eob": {
        "medical_necessity": [
            "The plan's physician reviewer decided {service} was not needed for your condition at this time.",
            "{service} does not meet the plan's guidelines for medical need based on the records we received.",
        ],
        "prior_authorization": [
            "{service} must be approved by the plan before you receive it. We have no record of an approval.",
            "The provider did not get the plan's OK in advance for {service}.",
        ],
        "out_of_network": [
            "The provider who performed {service} does not have a contract with the plan.",
            "{service} was performed by a provider outside your plan's network; your plan has no out-of-network benefits.",
        ],
        "coding_billing_error": [
            "The provider billed {service} with a code that does not match the diagnosis. Ask the provider to send a corrected claim.",
            "Information needed to process {service} was missing from the claim the provider sent.",
        ],
        "experimental_investigational": [
            "The plan does not pay for {service} for this condition because it is still considered experimental.",
            "{service} has not been shown to work for this diagnosis and is treated as investigational.",
        ],
        "not_covered_benefit": [
            "Your plan does not include {service} as a benefit.",
            "{service} is excluded from coverage under your plan documents.",
        ],
        "timely_filing": [
            "The provider sent the claim for {service} after the deadline for submitting claims.",
            "The claim for {service} was filed late.",
        ],
        "other_unclear": [
            "This claim for {service} was not paid. Call us if you have questions.",
            "We are not able to pay for {service}.",
        ],
    },
}

CODE_FOR = {
    "medical_necessity": ["CO-50"],
    "prior_authorization": ["CO-197", "CO-15"],
    "out_of_network": ["CO-242"],
    "coding_billing_error": ["CO-16", "CO-4", "CO-11", "CO-18"],
    "experimental_investigational": ["CO-55"],
    "not_covered_benefit": ["CO-96", "CO-204"],
    "timely_filing": ["CO-29"],
    "other_unclear": [],
}

APPEAL_PARAGRAPH = {
    "train": "You have the right to appeal this decision. To appeal, send a written request to the address below. See the enclosed notice of your appeal rights for deadlines and how to request an external review.",
    "gold": "APPEAL RIGHTS: If you disagree with this decision you may ask us to look at it again. Instructions and time limits are on the attached page.",
    "eob": "Your right to appeal: you or someone you choose can ask the plan to review this decision. Send your request in writing to the plan address on this statement. Keep a copy for your records.",
}


def _fmt_date(d: date, style: int) -> str:
    if style == 0:
        return d.strftime("%B %d, %Y").replace(" 0", " ")
    if style == 1:
        return d.strftime("%m/%d/%Y")
    return d.strftime("%Y-%m-%d")


def make_letter(rng: random.Random, split: str, idx: int, category: str | None = None, family: str | None = None) -> dict:
    family = family or ("gold" if split == "gold" else "train")
    category = category or rng.choice(list(REASONS["train"]))
    plan_type = rng.choice(list(PLAN_PHRASES["train"]))
    state = rng.choice(STATES)
    insurer = rng.choice(INSURERS)
    service, tcat, tsub, dcat = rng.choice(SERVICES)
    first, last = rng.choice(FIRST), rng.choice(LAST)
    name = f"{first} {last}"
    member_id = f"ZZTEST{rng.randint(100000, 999999)}"
    claim = f"CLM-{rng.randint(10, 99)}-{rng.randint(1000000, 9999999)}"
    phone = f"555-01{rng.randint(0, 99):02d}"
    dos = date(2025, 1, 1) + timedelta(days=rng.randint(0, 300))
    notice = dos + timedelta(days=rng.randint(10, 60))
    codes = []
    if CODE_FOR[category] and rng.random() < 0.6:
        codes = [rng.choice(CODE_FOR[category])]
    reason = rng.choice(REASONS[family][category]).format(service=service)
    reason = reason[0].upper() + reason[1:]
    ds = rng.randint(0, 2)
    plan_sentence = PLAN_PHRASES[family][plan_type]

    if family == "eob":
        billed = rng.randint(80, 9000)
        lines = [
            "EXPLANATION OF BENEFITS - THIS IS NOT A BILL",
            insurer,
            f"Questions? Call {phone} (TTY 711), Monday to Friday",
            "",
            f"Statement date  {_fmt_date(notice, 0)}",
            f"Patient  {name}",
            f"Member number  {member_id}",
            f"Claim ID  {claim}",
            f"State of residence  {state}",
            plan_sentence,
            "",
            "CLAIM DETAIL",
            "Date of service | What you received | Billed | Plan paid | You may owe",
            f"{_fmt_date(dos, 0)} | {service} | ${billed:,}.00 | $0.00 | ${billed:,}.00",
            "",
            "Why this claim was not paid",
            reason,
        ]
        if codes:
            lines.append(f"Remark code {codes[0]}")
        lines += ["", APPEAL_PARAGRAPH["eob"], "", f"{insurer} Claims Review, 123 Example St, Testville, {state} 00000"]
    elif family == "train":
        lines = [
            insurer.upper(),
            "Member Services: " + phone,
            "",
            _fmt_date(notice, ds),
            "",
            name,
            "123 Example St",
            f"Testville, {state} 00000",
            "",
            f"Member ID: {member_id}",
            f"Claim Number: {claim}",
            f"Date of Service: {_fmt_date(dos, ds)}",
            f"Service: {service}",
            "",
            f"Dear {name},",
            "",
            "NOTICE OF ADVERSE BENEFIT DETERMINATION",
            "",
            f"We have reviewed the claim listed above. {plan_sentence}",
            "",
            "Reason for denial: " + reason,
        ]
        if codes:
            lines.append(f"Denial code: {codes[0]}")
        lines += ["", APPEAL_PARAGRAPH["train"], "", "Sincerely,", "Utilization Management Department", f"{insurer}"]
    else:
        lines = [
            f"{insurer} | Appeals & Grievances | Tel {phone}",
            "-" * 40,
            f"Notice date: {_fmt_date(notice, ds)}",
            f"RE: {name}    Subscriber #: {member_id}",
            f"Reference no. {claim}",
            f"Service date {_fmt_date(dos, ds)} - Item/service: {service}",
            f"Coverage state: {state}",
            plan_sentence,
            "",
            "Summary of our decision",
            reason,
        ]
        if codes:
            lines.append(f"Adjustment reason code(s): {', '.join(codes)}")
        lines += ["", APPEAL_PARAGRAPH["gold"], "", f"{insurer}", "123 Example St, Suite 100", f"Testville, {state} 00000"]

    # layout noise: random extra blank lines / page footer
    if rng.random() < 0.4:
        lines.insert(rng.randint(1, len(lines) - 1), "")
    if rng.random() < 0.3:
        lines.append(f"Page 1 of 1   Form {rng.randint(100, 999)}-{rng.choice('ABC')}")
    text = "\n".join(lines)

    deadlines = compute_deadlines(plan_type, notice)
    primary = next((d for d in deadlines if d["kind"] == "internal_appeal"), None)
    return {
        "id": f"{split}-{idx:05d}",
        "split": split,
        "family": family,
        "text": text,
        "label": {
            "category": category,
            "plan_type": plan_type,
            "fields": {
                "insurer": insurer,
                "plan_type": plan_type,
                "state": state,
                "claim_number": claim,
                "member_id": member_id,
                "service": service,
                "date_of_service": dos.isoformat(),
                "notice_date": notice.isoformat(),
                "denial_codes": codes,
                "member_name": name,
            },
            "reason_text": reason,
            "treatment_category": tcat,
            "treatment_subcategory": tsub,
            "diagnosis_category": dcat,
            "deadline": primary["due_date"] if primary else None,
            "deadline_rule": primary["rule_id"] if primary else None,
        },
        "identifiers": [name, member_id, claim, phone],
    }


EOB_GOLD = 80


def generate(seed: int = 20251123) -> dict[str, int]:
    sizes = {"train": 3000, "validation": 500, "gold": 120}
    out: dict[str, int] = {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    cats = list(REASONS["train"])
    for split, n in sizes.items():
        rng = random.Random(f"{seed}-{split}")
        letters = []
        for i in range(n):
            # gold: balanced categories (15 each)
            cat = cats[i % len(cats)] if split == "gold" else None
            letters.append(make_letter(rng, split, i, cat))
        if split == "gold":
            # second gold family (Phase B): own RNG stream so the first 120 letters stay identical
            rng2 = random.Random(f"{seed}-gold-eob")
            for j in range(EOB_GOLD):
                letters.append(make_letter(rng2, split, n + j, cats[j % len(cats)], family="eob"))
            out["gold_eob"] = EOB_GOLD
        path = (GOLD_DIR / "letters.jsonl") if split == "gold" else (OUT_DIR / f"{split}.jsonl")
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for letter in letters:
                f.write(json.dumps(letter, ensure_ascii=False) + "\n")
        out[split] = len(letters)
    return out


if __name__ == "__main__":
    print(generate())
