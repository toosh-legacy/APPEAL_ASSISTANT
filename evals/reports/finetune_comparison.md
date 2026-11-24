# Fine-tuning experiment: extraction + classification

200 gold letters (synthetic, two layouts; none used for labeling). The strong model (gpt-4.1) labeled 295 synthetic training letters (tokenized; its category matched the generator's truth on 94.6%) and a 300-example fine-tuning JSONL was built (~265k training tokens, ~$1.33 for 2 epochs on gpt-4.1-mini), but OpenAI refused to create the training job:

> OpenAI is winding down the fine-tuning platform and your organization is no longer able to create new fine-tuning training jobs. (403 `training_not_available`, 2026-11-24)

So the fine-tuned row is absent; the labeled set is kept in `var/finetune/` for when fine-tuning is available again. Inference cost is LiteLLM's price for the calls actually made.

| System | Extraction (mean field accuracy) | Classification macro-F1 | Cost per 1,000 cases | p50 latency |
|---|---:|---:|---:|---:|
| scikit-learn M1 + rule extractor | 1.000 | 0.839 | $0.00 | 0.04 s |
| prompted cheap (gpt-4.1-mini) | 0.993 | 0.944 | $0.45 | 1.46 s |
| prompted strong (gpt-4.1) | 0.989 | 0.940 | $2.24 | 1.04 s |

Per-field accuracy:

| System | insurer | plan_type | state | service | date_of_service | notice_date | denial_reason | denial_codes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| scikit-learn M1 + rule extractor | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| prompted cheap (gpt-4.1-mini) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.945 | 1.000 |
| prompted strong (gpt-4.1) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.915 | 1.000 |

Experiment spend (session `finetune`): $1.21 of the $10 cap.

Caveat: the gold letters come from the same generator family as the training letters (plus one unseen EOB layout), so all systems look better here than they would on real letters.
