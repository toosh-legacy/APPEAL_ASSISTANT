# ML report (latest)

| Model | Version | Primary metric | Value | Previous (baseline) |
|---|---|---|---:|---:|
| m1 | v1 | gold macro-F1 | 0.8392 | 0.8435 |
| m2 | v1 | test macro-F1 (shortcuts removed) | 0.9772 | 0.9772 |
| m3 | v1 | test Brier (selected model) | 0.1882 | 0.1882 |

## m1

- Selected: logreg; validation macro-F1 {'linear_svm_calibrated': 1.0, 'logreg': 1.0}
- Gold macro-F1 0.839; ECE OOF 0.0339, gold 0.0847
- Ask-user threshold 0.70; gold coverage 82.5%, accuracy when answered 0.8909090909090909
- Ablation without codes: gold macro-F1 0.733

## m2

- tfidf_lr: validation 0.969, test 0.965
- tfidf_lr_shortcuts_removed: validation 0.969, test 0.977
- embeddings_lr: validation 0.672, test 0.720
- Majority baseline test macro-F1 0.307; split {'excluded_partial_years': [2026], 'test_years': [2024, 2025], 'train_years': '2001-2022', 'validation_year': 2023}

## m3

- baseline_overall_rate: test ROC-AUC 0.500, Brier 0.2543, log loss 0.7017
- baseline_eb_smoothed_subcategory: test ROC-AUC 0.705, Brier 0.2021, log loss 0.5890
- logreg_onehot: test ROC-AUC 0.723, Brier 0.1893, log loss 0.5594
- hist_gradient_boosting: test ROC-AUC 0.729, Brier 0.1882, log loss 0.5588
- Selected hist_gradient_boosting; beats EB baseline on Brier: True

Model cards: `ml/artifacts/<model>/<version>/model_card.md`.
