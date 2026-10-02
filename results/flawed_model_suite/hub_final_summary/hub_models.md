# Real Hugging Face models (single run each, descriptive)

| repo | status | fries | scoring | clean_acc | acc_drop | eod | harmful_recall | severe_fnr | benign_fpr | hash_check | llm_source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| unitary/unbiased-toxic-roberta | FINALIZED | 7.904 | scored | 0.915 | 0.012 | 0.093 | 0.733 | 0.145 | 0.040 | match | ['heuristic_fallback'] |
| unitary/toxic-bert | FINALIZED | 7.582 | scored | 0.868 | 0.010 | 0.174 | 0.423 | 0.355 | 0.021 | match | ['heuristic_fallback'] |
| martin-ha/toxic-comment-model | FINALIZED | 7.652 | scored | 0.890 | 0.012 | 0.063 | 0.522 | 0.298 | 0.018 | match | ['heuristic_fallback'] |
| s-nlp/roberta_toxicity_classifier | FINALIZED | 7.231 | scored | 0.927 | 0.022 | 0.085 | 0.765 | 0.089 | 0.033 | match | ['llm_v1'] |
| JungleLee/bert-toxic-comment-classification | FINALIZED | 7.154 | scored | 0.846 | 0.036 | 0.217 | 0.787 | 0.110 | 0.139 | match | ['heuristic_fallback'] |
| BunnyNoBugs/rubert-tiny2-russe-toxicity | FINALIZED | 6.200 | scored | 0.764 | 0.046 | 0.098 | 0.212 | 0.766 | 0.098 | match | ['heuristic_fallback'] |
| gravitee-io/distilbert-multilingual-toxicity-classifier | FINALIZED | 5.921 | scored | 0.784 | 0.137 | 0.167 | 0.638 | 0.280 | 0.180 | match | ['heuristic_fallback'] |
| textdetox/xlmr-large-toxicity-classifier | FINALIZED | 7.007 | scored | 0.805 | 0.054 | 0.242 | 0.777 | 0.156 | 0.188 | match | ['heuristic_fallback'] |
| gravitee-io/bert-small-toxicity | FINALIZED | 6.231 | scored | 0.808 | 0.079 | 0.123 | 0.515 | 0.383 | 0.119 | match | ['heuristic_fallback'] |
| citizenlab/distilbert-base-multilingual-cased-toxicity | FINALIZED | 7.104 | scored | 0.843 | 0.012 | 0.067 | 0.353 | 0.518 | 0.035 | match | ['heuristic_fallback'] |
| textdetox/xlmr-base-toxicity-classifier | FINALIZED | 6.607 | scored | 0.805 | 0.054 | 0.242 | 0.777 | 0.156 | 0.188 | match | ['heuristic_fallback'] |
| gravitee-io/bert-tiny-toxicity | FINALIZED | 6.563 | scored | 0.664 | 0.056 | 0.203 | 0.790 | 0.113 | 0.367 | match | ['heuristic_fallback'] |
| facebook/roberta-hate-speech-dynabench-r4-target | FINALIZED | 5.380 | scored | 0.783 | 0.072 | 0.167 | 0.153 | 0.837 | 0.059 | match | ['heuristic_fallback'] |
| Hate-speech-CNERG/dehatebert-mono-english | FINALIZED | 6.177 | scored | 0.802 | 0.001 | 0.127 | 0.148 | 0.812 | 0.035 | match | ['heuristic_fallback'] |
| pysentimiento/bert-it-hate-speech | FINALIZED | — | withheld | — | — | — | 0.023 | 0.972 | 0.015 | match | ['heuristic_fallback'] |
