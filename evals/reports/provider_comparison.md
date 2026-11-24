# Offline vs LLM provider (SPEC 21.4)

Intake-level suites on the gold letters. The LLM fills extraction fields; classification uses the extracted
reason/codes with the same M1 model, so differences there come from extraction. Letters are synthetic.
Fields are scored by exact match; `denial_reason` is compared with the whole reason passage of the template,
so a model that returns only the reason sentence (dropping a trailing line such as 'Call us if you have
questions.') counts as a miss. Model values for insurer, service and denial_reason are kept only when they
occur in the letter.

| Metric | offline | openai (gpt-4o-mini) |
|---|---:|---:|
| letters | 200 | 200 |
| extraction, mean field accuracy | 1.000 | 0.993 |
| extraction, notice layout (gold) | 1.000 | 0.994 |
| extraction, EOB layout | 1.000 | 0.991 |
|   insurer | 1.000 | 1.000 |
|   plan_type | 1.000 | 1.000 |
|   state | 1.000 | 1.000 |
|   claim_number | 1.000 | 1.000 |
|   member_id | 1.000 | 1.000 |
|   service | 1.000 | 1.000 |
|   date_of_service | 1.000 | 1.000 |
|   notice_date | 1.000 | 1.000 |
|   denial_reason | 1.000 | 0.930 |
|   denial_codes | 1.000 | 1.000 |
| classification macro-F1 | 0.845 | 0.845 |
| ask-user rate | 0.165 | 0.175 |
| deadlines exact | 1.000 | 1.000 |
| seconds per letter | 0.08 | 2.26 |
