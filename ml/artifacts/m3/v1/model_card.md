# Model card: M3 overturn-rate model (v1)

## What it does
Estimates P(IMR overturns the plan's decision) from case attributes, to give **context only** ("cases like this were overturned about X% of the time"). It is never used to advise against appealing (hard rule 9). The stats card shows the empirical rate with a Wilson 95% interval and N; the model estimate is shown only when it beats the empirical-Bayes baseline on Brier score and N ≥ 20.

Data: California Department of Managed Health Care, Independent Medical Review determinations (CC BY).

## Features and exclusions
Features: treatment_category, treatment_subcategory, diagnosis_category, diagnosis_subcategory, type, imr_type, year.

Excluded and why:
- `findings`: post-decision text that states the conclusion -> target leakage
- `days_to_adopt`: happens after the decision -> leakage
- `age_range`: sensitive attribute; used only for fairness slices
- `patient_gender`: sensitive attribute; used only for fairness slices

## Split
Time-based, same as M2: train 2001-2022, validation 2023, test [2024, 2025]. Sizes: {'train': 34481, 'validation': 2246, 'test': 5445}.

## Results
| Model | Validation Brier | Test ROC-AUC | Test Brier | Test log loss |
|---|---:|---:|---:|---:|
| Baseline: overall training rate | 0.2533 | 0.500 | 0.2543 | 0.7017 |
| Baseline: empirical-Bayes smoothed rate per treatment subcategory | 0.2067 | 0.705 | 0.2021 | 0.5890 |
| Logistic regression (one-hot) | 0.1997 | 0.723 | 0.1893 | 0.5594 |
| HistGradientBoosting (native categorical) | 0.1945 | 0.729 | 0.1882 | 0.5588 |

Selected by validation Brier: **hist_gradient_boosting**. Beats the EB baseline on test Brier: **True**.

The EB baseline shrinks each subcategory's rate toward the overall rate with a beta prior fitted by method of moments; small subcategories borrow strength from the whole dataset, which makes it a strong baseline.

## Calibration (test)
| Bin | N | Mean predicted | Observed |
|---|---:|---:|---:|
| 0.1-0.2 | 144 | 0.156 | 0.292 |
| 0.2-0.3 | 249 | 0.262 | 0.329 |
| 0.3-0.4 | 531 | 0.358 | 0.529 |
| 0.4-0.5 | 584 | 0.453 | 0.515 |
| 0.5-0.6 | 537 | 0.551 | 0.588 |
| 0.6-0.7 | 573 | 0.644 | 0.632 |
| 0.7-0.8 | 858 | 0.762 | 0.796 |
| 0.8-0.9 | 687 | 0.841 | 0.809 |
| 0.9-1.0 | 1271 | 0.936 | 0.887 |

## Performance by year (drift)
| Year | ROC-AUC | Brier |
|---|---:|---:|
| 2024 | 0.724 | 0.1977 |
| 2025 | 0.734 | 0.1787 |

## Fairness slices (test; age and gender are NOT model inputs)
### Age range
| Group | N | Observed | Mean predicted | Gap | Brier | FPR@0.5 | FNR@0.5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 to 10 | 237 | 0.654 | 0.584 | -0.070 | 0.2463 | 0.683 | 0.335 |
| 11 to 20 | 416 | 0.673 | 0.658 | -0.015 | 0.2128 | 0.618 | 0.204 |
| 21 to 30 | 521 | 0.745 | 0.698 | -0.047 | 0.1769 | 0.632 | 0.142 |
| 31 to 40 | 993 | 0.728 | 0.685 | -0.044 | 0.1661 | 0.511 | 0.152 |
| 41 to 50 | 1128 | 0.708 | 0.694 | -0.015 | 0.1817 | 0.565 | 0.149 |
| 51 to 64 | 1904 | 0.664 | 0.654 | -0.010 | 0.1956 | 0.463 | 0.223 |
| 65+ | 246 | 0.585 | 0.592 | +0.007 | 0.1764 | 0.373 | 0.236 |

### Gender
| Group | N | Observed | Mean predicted | Gap | Brier | FPR@0.5 | FNR@0.5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Female | 3113 | 0.692 | 0.684 | -0.008 | 0.1801 | 0.519 | 0.160 |
| Male | 2304 | 0.685 | 0.642 | -0.043 | 0.1993 | 0.521 | 0.230 |

Read the calibration gap per group: a positive gap means the model over-predicts overturns for that group. Because age and gender are excluded as features, any gap comes through correlated features (treatment and diagnosis mix differs by age). This is measured, not corrected; Phase B should review it before the estimate is shown to users.

## Limitations
- California, managed-care (DMHC) plans only; other states and plan types differ.
- Outcome base rates shift over time (see by-year table); retrain monthly.
- Context only; never advice.
