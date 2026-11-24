# DSPy: hand-written vs optimized extraction prompt

Cheap tier `gpt-4.1-mini`. Optimized on 40 synthetic training letters; scored on 60 gold letters (mean exact-match accuracy over 8 fields). Optimization took 148 s. Spend: $0.025 (session `dspy`).

| Program | Gold field accuracy |
|---|---:|
| hand-written prompt (production intake_extract 2.0.0, LangChain structured output + grounding merge) | 1.000 |
| DSPy Predict, zero-shot (same fields, no optimization) | 0.977 |
| DSPy Predict, optimized (BootstrapFewShotWithRandomSearch, 3 demos) | 0.998 |

The production path also merges model answers over the deterministic extractor and rejects quotes that are not in the letter, which DSPy's programs do not do; the comparison shows what prompt optimization alone buys.
