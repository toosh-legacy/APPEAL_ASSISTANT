# Model card: M2 IMR-type text classifier (v1)

## What it does
Predicts the DMHC IMR `Type` (Experimental/Investigational, Medical Necessity, Urgent Care) from text. Trained on the physician reviewers' `Findings` text of real California IMR decisions (California Department of Managed Health Care, CC BY). The Research agent uses it to choose which precedent pool fits the user's case.

## Split (time-based, never random)
Train: 2001-2022; validation: 2023; test: [2024, 2025] (the two most recent full years). Partial years excluded: [2026].
A random split would leak the future into the past: reviewer templates, wording and the mix of treatments change over the years (e.g. new drug classes, new boilerplate), so a random split overstates how well the model works on next year's cases. The time split mirrors deployment: train on the past, predict the future.

Sizes: {'train': 34481, 'validation': 2246, 'test': 5445}

## Results (macro-F1)
| Variant | Validation | Test | Test per-class recall |
|---|---:|---:|---|
| Majority-class baseline | - | 0.307 | |
| TF-IDF + logistic regression | 0.969 | 0.965 | Experimental/Investigational: 1.00, Medical Necessity: 1.00, Urgent Care: 0.81 |
| TF-IDF + LR, label-stating phrases removed (shortcut ablation) | 0.969 | 0.977 | Experimental/Investigational: 1.00, Medical Necessity: 1.00, Urgent Care: 0.88 |
| MiniLM embeddings + logistic regression | 0.672 | 0.720 | Experimental/Investigational: 0.86, Medical Necessity: 0.89, Urgent Care: 0.94 |

## Shortcut learning
Findings text often states the label in boilerplate ("...is not medically necessary...", "...is likely to be more beneficial than any available standard therapy..." for experimental cases). The full model can score highly just by spotting these phrases. The ablation removes them (regex in `m2.py`) and re-trains; the drop between the two rows measures how much the model relied on the shortcut. The **served** model is the shortcut-removed variant, because the user's denial text does not contain reviewer boilerplate.

**What the ablation showed:** removing the label-stating phrases did NOT lower test macro-F1 (0.965 -> 0.977). The shortcut is not only in those phrases: DMHC writes each IMR type with a different template (for example 'Nature of Statutory Criteria/Case Summary' sections and 'standard therapy' comparisons), so the remaining structure still gives the type away. The high score therefore measures template recognition more than clinical understanding. A stronger test (Phase B) trains only on the case-summary sentences before the reviewer's conclusion, or on the user's own denial wording.

## Limitations
- Trained on reviewer findings, applied to the user's redacted reason + service text: a domain shift. Used only to pick a precedent pool, never shown as a prediction.
- Urgent Care is a small class; its recall is noisy.
- California only.
