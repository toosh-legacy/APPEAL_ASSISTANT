"""Generates packages/kb/playbooks/*.yaml. The YAML files are the source of truth once reviewed;
this script only exists to keep the eight playbooks structurally identical."""

from pathlib import Path

import yaml

HERE = Path(__file__).parent / "playbooks"
COMMERCIAL = ["employer_self_funded", "employer_fully_insured", "individual_marketplace"]

common_legal = [
    {
        "id": "full_fair_review",
        "text": "I am asking for a full and fair review of this decision that takes into account all comments, documents, records and other information I submit.",
        "needs": "full and fair review comments documents records information submitted",
        "plan_types": COMMERCIAL,
    },
    {
        "id": "documents_request",
        "text": "Please send me, free of charge, copies of all documents, records and other information relevant to my claim.",
        "needs": "free of charge copies documents records information relevant claim",
        "plan_types": COMMERCIAL,
    },
    {
        "id": "ma_reconsideration",
        "text": "I am requesting a reconsideration of this organization determination.",
        "needs": "request reconsideration organization determination",
        "plan_types": ["medicare_advantage"],
    },
    {
        "id": "medicaid_appeal",
        "text": "I am filing an appeal of this adverse benefit determination.",
        "needs": "appeal adverse benefit determination",
        "plan_types": ["medicaid_managed_care"],
    },
]
med_judgment = {
    "id": "medical_judgment_reviewer",
    "text": "Because this denial is based on a medical judgment, I ask that the appeal be decided in consultation with a health care professional who has appropriate training and experience in the field of medicine involved.",
    "needs": "medical judgment health care professional appropriate training experience field medicine",
    "plan_types": COMMERCIAL,
}
nsa = {
    "id": "nsa_emergency",
    "text": "Emergency services must be covered without the need for any prior authorization determination, even if the services are provided on an out-of-network basis.",
    "needs": "emergency services prior authorization determination out-of-network basis",
    "plan_types": COMMERCIAL,
}

books = {
    "medical_necessity": dict(
        label="Medical necessity",
        why="The plan says the service was not medically necessary for your condition.",
        usually_means="The plan's reviewer did not think the records showed you needed this service, or thought a different option should come first. These denials are often about missing or incomplete medical records.",
        facts=["My doctor recommended {service} to treat my condition.", "My treating clinician will provide a letter explaining why {service} is medically necessary for me."],
        legal=[med_judgment],
        evidence=["A letter of medical necessity from your treating clinician", "Office notes and test results that show your symptoms and history", "Records of treatments you already tried and how they worked", "Any clinical guidelines your clinician relies on"],
    ),
    "prior_authorization": dict(
        label="Prior authorization",
        why="The plan says approval was needed before the service and it was not obtained.",
        usually_means="Many plans require approval before certain services. Sometimes the approval was requested but not recorded, or the service was urgent.",
        facts=["I ask the plan to review whether prior authorization was required for {service} and whether it was requested.", "If prior authorization was required, I ask the plan to review the medical need for {service} now."],
        legal=[med_judgment],
        evidence=["Any authorization or reference numbers from your provider's office", "Dates and names from calls about the authorization", "Records showing whether the care was urgent", "A letter from your clinician about why the service was needed"],
    ),
    "out_of_network": dict(
        label="Out of network",
        why="The plan says the provider or facility was not in its network.",
        usually_means="The plan may pay less or nothing for out-of-network care. Federal surprise-billing rules can protect you for emergency care and for some care at in-network facilities.",
        facts=["I received {service} from a provider the plan says is out of network.", "I ask the plan to review whether federal protections for emergency or out-of-network care apply to this claim."],
        legal=[nsa],
        evidence=["Proof the care was an emergency, if it was", "Whether you chose the provider or were assigned one", "Network directory pages showing the provider, if listed", "Any consent forms you signed about out-of-network care"],
    ),
    "coding_billing_error": dict(
        label="Coding or billing error",
        why="The plan says the claim had a coding or billing problem.",
        usually_means="These denials are often fixed when the provider's office corrects and resubmits the claim.",
        facts=["I ask the plan to work with my provider to correct any coding or billing error on the claim for {service}.", "My provider's billing office will confirm the correct codes for {service}."],
        legal=[],
        evidence=["An itemized bill from the provider", "The explanation of benefits (EOB)", "A note from the billing office confirming the correct codes"],
    ),
    "experimental_investigational": dict(
        label="Experimental or investigational",
        why="The plan says the treatment is experimental or investigational.",
        usually_means="The plan thinks there is not enough evidence that the treatment works for your condition. Published studies and your clinician's explanation can matter a lot.",
        facts=["My doctor recommended {service} for my condition.", "My treating clinician will provide published medical evidence supporting {service} for my condition."],
        legal=[med_judgment],
        evidence=["A letter from your clinician explaining why this treatment fits you", "Published studies or guidelines supporting the treatment", "Records showing standard treatments you already tried"],
    ),
    "not_covered_benefit": dict(
        label="Not a covered benefit",
        why="The plan says your policy does not cover this service.",
        usually_means="The plan believes the service is excluded or not listed as a benefit. The exact wording of your plan documents matters.",
        facts=["I ask the plan to identify the specific plan provision it relied on to deny {service}.", "I ask the plan to review whether {service} is covered under my plan's terms."],
        legal=[],
        evidence=["Your plan's summary of benefits and coverage", "The plan document section the denial refers to", "A letter from your clinician describing the service"],
    ),
    "timely_filing": dict(
        label="Timely filing",
        why="The plan says the claim was sent after its filing deadline.",
        usually_means="Usually this is between the provider and the plan. Ask whether you can be billed for a claim the provider filed late.",
        facts=["I ask the plan to review the dates on which the claim for {service} was submitted.", "I ask the plan to confirm whether I can be billed for a claim denied for late filing."],
        legal=[],
        evidence=["Proof of when the claim was first sent (from the provider)", "Any earlier denials or letters about the claim"],
    ),
    "other_unclear": dict(
        label="Other or unclear",
        why="The reason for the denial is not clear from the letter.",
        usually_means="When a denial is unclear, start by asking the plan for the exact reason and the rule it used.",
        facts=["I ask the plan to explain the specific reason for denying {service}."],
        legal=[],
        evidence=["The full denial letter and explanation of benefits", "Notes from any calls with the plan"],
    ),
}

CLINICIAN = (
    "Dear {clinician}, my health plan denied coverage for {service} ({category_label}). I am appealing. "
    "Could you please write a letter of medical necessity that explains my diagnosis, the treatments I have tried, "
    "why {service} is appropriate for me, and any clinical guidelines or studies that support it? "
    "My appeal deadline is {deadline}. Thank you."
)

if __name__ == "__main__":
    HERE.mkdir(exist_ok=True)
    for cat, b in books.items():
        out = {"category": cat, "status": "needs_human_review", **b, "legal": common_legal + b["legal"], "clinician_request": CLINICIAN}
        (HERE / f"{cat}.yaml").write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
    print("wrote", len(books), "playbooks")
