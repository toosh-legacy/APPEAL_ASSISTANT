# Reading level (Flesch-Kincaid grade)

Target: grade 6-8 (SPEC 21.6). Domain words users must learn anyway (Medicare Advantage, Medicaid, Marketplace, insurance, insurer, appeal, appealing, denial, California) are scored as 'plan'.

## Web pages

| Page | Grade | Strings |
|---|---:|---:|
| `apps/web/src/app/about/data/page.tsx` | 8.2 | 10 |
| `apps/web/src/app/admin/page.tsx` | 6.6 | 2 |
| `apps/web/src/app/cases/[id]/confirm/page.tsx` | 4.5 | 17 |
| `apps/web/src/app/cases/[id]/page.tsx` | 4.2 | 32 |
| `apps/web/src/app/insights/insurers/page.tsx` | 7.4 | 3 |
| `apps/web/src/app/page.tsx` | 5.4 | 14 |
| `apps/web/src/app/sources/[...chunkId]/page.tsx` | 6.2 | 3 |
| `apps/web/src/app/start/page.tsx` | 2.8 | 12 |

Hardest strings per page (grade > 8):

- `about/data/page.tsx` (18.2): , Independent Medical Review (IMR) Determinations, published on the California Health and Human Services Open Data Portal under a Creative Commons Attribution l
- `about/data/page.tsx` (12.8): Our rights summaries are written from the regulations above and marked as draft until a person reviews them against the cited paragraphs.
- `about/data/page.tsx` (9.9): Our denial-category model is trained on synthetic letters. Real letters vary; always check the category and facts.
- `cases/[id]/confirm/page.tsx` (14.4): ; const c = q.data; if (["RECEIVED", "EXTRACTING"].includes(c.status)) return (
- `cases/[id]/page.tsx` (10.4): This letter was made with our basic template because a service was unavailable.
- `cases/[id]/page.tsx` (10.2): Edit anything. Numbers in brackets open the exact source. Fill every
- `page.tsx` (14.3): Latest quality checks are published in the project&apos;s evaluation report.
- `page.tsx` (12.6): Federal regulations from the official eCFR (public domain).
- `page.tsx` (11.5): Real independent medical review decisions from the California Department of Managed Health Care (CC BY).

## Knowledge base (information only: legal content, rewrite during the human KB review)

| File | Grade |
|---|---:|
| `packages/kb/summaries/employer_plans.md` | 7.7 |
| `packages/kb/summaries/general_rights.md` | 7.7 |
| `packages/kb/summaries/individual_marketplace.md` | 6.7 |
| `packages/kb/summaries/medicaid_managed_care.md` | 7.2 |
| `packages/kb/summaries/medicare_advantage.md` | 11.5 |
| `packages/kb/summaries/surprise_billing.md` | 14.8 |
| `packages/kb/playbooks/coding_billing_error.yaml` | 7.0 |
| `packages/kb/playbooks/experimental_investigational.yaml` | 10.4 |
| `packages/kb/playbooks/medical_necessity.yaml` | 11.5 |
| `packages/kb/playbooks/not_covered_benefit.yaml` | 8.5 |
| `packages/kb/playbooks/other_unclear.yaml` | 5.5 |
| `packages/kb/playbooks/out_of_network.yaml` | 10.3 |
| `packages/kb/playbooks/prior_authorization.yaml` | 11.1 |
| `packages/kb/playbooks/timely_filing.yaml` | 6.0 |
