# External Hub validation — descriptive audit profiles (2026-10-03)

Descriptive only. **No ranking and no trustworthy/untrustworthy label**: there is no ground truth for
these models, and the FRIES numbers are TrustLens's own outputs, reproduced as reported. Models are
listed in selection order. Methodology unchanged; see `README.md` for the protocol.

## unitary/toxic-bert @ `4d6c22e74ba2`

Selected for: widely used multi-label Jigsaw classifier (BERT-base); toxicity head of a 6-label output.

- run status FINALIZED; revision evaluated `4d6c22e74ba2fdd26bc4f7238f50766b045a0d94`; engine llm_v1 (LEGACY_HEURISTIC_OSD_V1); FRIES withheld

| dimension | probe | aspect scoring | risks | gaps | O/S/D (source) | key evidence |
|---|---|---|---|---|---|---|
| FAIRNESS | EVALUATED | mapping_blocked | [] | None | None/None/None (None) | `{"n_evaluated":3000,"equal_opportunity_difference":0.174373,"eopp_ci":{"B":1000,"point":0.174373,"method":"bootstrap_percentile","ci_lower":0.098208,"ci_upper":0.251766},"equalized_odds_difference":0.174373,"eo_ci":{"B":1000,"point":0.174373,"method":"bootstrap_percentile","ci_lower":0.098208,"ci_upper":0.251766},"demographic_parity_difference":0.283159,"label_rate_gap":0.504795,"excess_dpd":0.0,"subgroup_f1_spread":0.203006,"fairness_finding":"INSUFFICIENT_EVIDENCE"}` |
| ROBUSTNESS | EVALUATED | no_material_risk | [] | None | 9/9/8 (None) | `{"n_evaluated":3000,"clean_accuracy":0.8677,"robust_accuracy":0.858,"accuracy_drop":0.009667,"attack_success_rate":0.0263,"perturbation_coverage":1.0,"max_changes":3}` |
| SAFETY | EVALUATED | disclosure_gap | [] | ['S-GOV-DISCLOSURE-GAP'] | 7/7/8 (None, groq) | `{"severe_fnr":0.3546099290780142,"fnr_ratio":0.6149305128520477,"coverage_ratio":0.0,"checks_present":0,"high_impact_claims":[],"behavior":{"status":"EVALUATED","severe_n":282,"severe_fnr":0.3546099290780142,"severe_fnr_ci":[0.30106949450248865,0.412058335736357],"overall_fnr":0.5766666666666667,"harmful_recall":0.42333333333333334,"benign_fpr":0.02125,"fnr_ratio":0.6149305128520477}}` |
| INTEGRITY | EVALUATED | no_material_risk | [] | [] | 9/9/9 (llm_v1, groq) | `{"identity":{"hash_comparison":"match"},"artifact_verification_status":"VERIFIED"}` |
| EXPLAINABILITY | EVALUATED | disclosure_gap | [] | ['E-DOC-INCOMPLETE'] | 4/5/5 (llm_v1, groq) | `{"coverage_ratio":0.6,"sections_present":3,"contradictions":[],"card_chars":11095,"documentation_source":{"content_length":11141,"retrieval_error":null,"retrieval_status":"ok","source_model_ref":"unitary/toxic-bert","documentation_url":"https://huggingface.co/unitary/toxic-bert/blob/4d6c22e74ba2fdd26bc4f7238f50766b045a0d94/README.md","source_model_revision":"4d6c22e74ba2fdd26bc4f7238f50766b045a0d94","documentation_revision":"4d6c22e74ba2fdd26bc4f7238f50766b045a0d94","documentation_source_type":"model_card","documentation_content_hash":"sha256:e209e453eb09581e0651cf4d923019fa5acb4f2d4a555a32c87aeb816f4e4239"}}` |

FRIES as reported: None; per dimension `null`

## unitary/unbiased-toxic-roberta @ `36295dd80b42`

Selected for: multi-label model trained on Civil Comments with identity-bias mitigation (fairness-relevant claim).

- run status FINALIZED; revision evaluated `36295dd80b422dc49f40052021430dae76241adc`; engine llm_v1 (LEGACY_HEURISTIC_OSD_V1); FRIES scored

| dimension | probe | aspect scoring | risks | gaps | O/S/D (source) | key evidence |
|---|---|---|---|---|---|---|
| FAIRNESS | EVALUATED | risk_detected | ['F-FAIR-EOPP'] | None | 8/8/8 (None) | `{"n_evaluated":3000,"equal_opportunity_difference":0.092544,"eopp_ci":{"B":1000,"point":0.092544,"method":"bootstrap_percentile","ci_lower":0.020169,"ci_upper":0.161874},"equalized_odds_difference":0.092544,"eo_ci":{"B":1000,"point":0.092544,"method":"bootstrap_percentile","ci_lower":0.054503,"ci_upper":0.162275},"demographic_parity_difference":0.349871,"label_rate_gap":0.504795,"excess_dpd":0.0,"subgroup_f1_spread":0.025209,"fairness_finding":"FAIRNESS_RISK"}` |
| ROBUSTNESS | EVALUATED | no_material_risk | [] | None | 8/8/8 (None) | `{"n_evaluated":3000,"clean_accuracy":0.9147,"robust_accuracy":0.903,"accuracy_drop":0.011667,"attack_success_rate":0.024,"perturbation_coverage":1.0,"max_changes":3}` |
| SAFETY | EVALUATED | disclosure_gap | [] | ['S-GOV-DISCLOSURE-GAP'] | 9/9/8 (heuristic_fallback) | `{"severe_fnr":0.1453900709219858,"fnr_ratio":0.5452127659574467,"coverage_ratio":0.0,"checks_present":0,"high_impact_claims":[],"behavior":{"status":"EVALUATED","severe_n":282,"severe_fnr":0.1453900709219858,"severe_fnr_ci":[0.10901456205816892,0.19129721901218608],"overall_fnr":0.26666666666666666,"harmful_recall":0.7333333333333334,"benign_fpr":0.04,"fnr_ratio":0.5452127659574467}}` |
| INTEGRITY | EVALUATED | no_material_risk | [] | [] | 9/9/8 (heuristic_fallback) | `{"identity":{"hash_comparison":"match"},"artifact_verification_status":"VERIFIED"}` |
| EXPLAINABILITY | EVALUATED | disclosure_gap | [] | ['E-DOC-INCOMPLETE'] | 6/6/6 (heuristic_fallback) | `{"coverage_ratio":0.6,"sections_present":3,"contradictions":[],"card_chars":11088,"documentation_source":{"content_length":11134,"retrieval_error":null,"retrieval_status":"ok","source_model_ref":"unitary/unbiased-toxic-roberta","documentation_url":"https://huggingface.co/unitary/unbiased-toxic-roberta/blob/36295dd80b422dc49f40052021430dae76241adc/README.md","source_model_revision":"36295dd80b422dc49f40052021430dae76241adc","documentation_revision":"36295dd80b422dc49f40052021430dae76241adc","documentation_source_type":"model_card","documentation_content_hash":"sha256:5ab17611a1ae299c3ea19b0813ae6f16e571ed472bb08282303eb7386d31bc3f"}}` |

FRIES as reported: 7.8614; per dimension `{"SAFETY": 8.6535, "FAIRNESS": 8.0, "INTEGRITY": 8.6535, "ROBUSTNESS": 8.0, "EXPLAINABILITY": 6.0}`

## s-nlp/roberta_toxicity_classifier @ `048c25bb1e19`

Selected for: binary RoBERTa-large classifier from a research group (Jigsaw data).

- run status FINALIZED; revision evaluated `048c25bb1e199b98802784f96325f4840f22145d`; engine llm_v1 (LEGACY_HEURISTIC_OSD_V1); FRIES scored

| dimension | probe | aspect scoring | risks | gaps | O/S/D (source) | key evidence |
|---|---|---|---|---|---|---|
| FAIRNESS | EVALUATED | no_material_risk | [] | None | 8/8/8 (None) | `{"n_evaluated":3000,"equal_opportunity_difference":0.018767,"eopp_ci":{"B":1000,"point":0.018767,"method":"bootstrap_percentile","ci_lower":0.000967,"ci_upper":0.090623},"equalized_odds_difference":0.085486,"eo_ci":{"B":1000,"point":0.085486,"method":"bootstrap_percentile","ci_lower":0.048634,"ci_upper":0.126832},"demographic_parity_difference":0.41279,"label_rate_gap":0.504795,"excess_dpd":0.0,"subgroup_f1_spread":0.068946,"fairness_finding":"NO_MATERIAL_DISPARITY"}` |
| ROBUSTNESS | EVALUATED | no_material_risk | [] | None | 4/4/8 (None) | `{"n_evaluated":3000,"clean_accuracy":0.927,"robust_accuracy":0.9047,"accuracy_drop":0.022333,"attack_success_rate":0.0313,"perturbation_coverage":1.0,"max_changes":3}` |
| SAFETY | EVALUATED | disclosure_gap | [] | ['S-GOV-DISCLOSURE-GAP'] | 9/9/8 (heuristic_fallback) | `{"severe_fnr":0.08865248226950355,"fnr_ratio":0.3772446054021428,"coverage_ratio":0.25,"checks_present":1,"high_impact_claims":[],"behavior":{"status":"EVALUATED","severe_n":282,"severe_fnr":0.08865248226950355,"severe_fnr_ci":[0.060768378297487255,0.1275932877441246],"overall_fnr":0.235,"harmful_recall":0.765,"benign_fpr":0.0325,"fnr_ratio":0.3772446054021428}}` |
| INTEGRITY | EVALUATED | no_material_risk | [] | [] | 9/9/8 (heuristic_fallback) | `{"identity":{"hash_comparison":"match"},"artifact_verification_status":"VERIFIED"}` |
| EXPLAINABILITY | EVALUATED | disclosure_gap | [] | ['E-DOC-INCOMPLETE'] | 2/2/2 (heuristic_fallback) | `{"coverage_ratio":0.2,"sections_present":1,"contradictions":[],"card_chars":3424,"documentation_source":{"content_length":3428,"retrieval_error":null,"retrieval_status":"ok","source_model_ref":"s-nlp/roberta_toxicity_classifier","documentation_url":"https://huggingface.co/s-nlp/roberta_toxicity_classifier/blob/048c25bb1e199b98802784f96325f4840f22145d/README.md","source_model_revision":"048c25bb1e199b98802784f96325f4840f22145d","documentation_revision":"048c25bb1e199b98802784f96325f4840f22145d","documentation_source_type":"model_card","documentation_content_hash":"sha256:b7dc818b84eea5bc5a80b85d9baf537bf1bced13e1252ee59630f67a30127dd0"}}` |

FRIES as reported: 6.4693; per dimension `{"SAFETY": 8.6535, "FAIRNESS": 8.0, "INTEGRITY": 8.6535, "ROBUSTNESS": 5.0397, "EXPLAINABILITY": 2.0}`

## martin-ha/toxic-comment-model @ `9842c08b35a4`

Selected for: small binary DistilBERT fine-tune by an individual author; no license in card metadata.

- run status FINALIZED; revision evaluated `9842c08b35a4687e7b211187d676986c8c96256d`; engine llm_v1 (LEGACY_HEURISTIC_OSD_V1); FRIES scored

| dimension | probe | aspect scoring | risks | gaps | O/S/D (source) | key evidence |
|---|---|---|---|---|---|---|
| FAIRNESS | EVALUATED | disparity_observed | [] | None | 9/9/8 (None) | `{"n_evaluated":3000,"equal_opportunity_difference":0.06286,"eopp_ci":{"B":1000,"point":0.06286,"method":"bootstrap_percentile","ci_lower":0.004773,"ci_upper":0.143969},"equalized_odds_difference":0.06286,"eo_ci":{"B":1000,"point":0.06286,"method":"bootstrap_percentile","ci_lower":0.033413,"ci_upper":0.143969},"demographic_parity_difference":0.299028,"label_rate_gap":0.504795,"excess_dpd":0.0,"subgroup_f1_spread":0.078553,"fairness_finding":"DISPARITY_OBSERVED"}` |
| ROBUSTNESS | EVALUATED | no_material_risk | [] | None | 8/8/8 (None) | `{"n_evaluated":3000,"clean_accuracy":0.8903,"robust_accuracy":0.8783,"accuracy_drop":0.012,"attack_success_rate":0.0257,"perturbation_coverage":1.0,"max_changes":3}` |
| SAFETY | EVALUATED | disclosure_gap | [] | ['S-GOV-DISCLOSURE-GAP'] | 8/8/8 (heuristic_fallback) | `{"severe_fnr":0.2978723404255319,"fnr_ratio":0.6227296315516346,"coverage_ratio":0.25,"checks_present":1,"high_impact_claims":[],"behavior":{"status":"EVALUATED","severe_n":282,"severe_fnr":0.2978723404255319,"severe_fnr_ci":[0.24750214520734554,0.3536755700027568],"overall_fnr":0.47833333333333333,"harmful_recall":0.5216666666666667,"benign_fpr":0.0175,"fnr_ratio":0.6227296315516346}}` |
| INTEGRITY | EVALUATED | disclosure_gap | [] | ['I-INT-LICENSE-UNDISCLOSED'] | 8/8/8 (heuristic_fallback) | `{"identity":{"hash_comparison":"match"},"artifact_verification_status":"VERIFIED"}` |
| EXPLAINABILITY | EVALUATED | disclosure_gap | [] | ['E-DOC-INCOMPLETE'] | 6/6/6 (heuristic_fallback) | `{"coverage_ratio":0.6,"sections_present":3,"contradictions":[],"card_chars":3184,"documentation_source":{"content_length":3184,"retrieval_error":null,"retrieval_status":"ok","source_model_ref":"martin-ha/toxic-comment-model","documentation_url":"https://huggingface.co/martin-ha/toxic-comment-model/blob/9842c08b35a4687e7b211187d676986c8c96256d/README.md","source_model_revision":"9842c08b35a4687e7b211187d676986c8c96256d","documentation_revision":"9842c08b35a4687e7b211187d676986c8c96256d","documentation_source_type":"model_card","documentation_content_hash":"sha256:65856ba28d1792de2497cdd887a46cdde0353e85e449a5e7a955a54f8b861e5e"}}` |

FRIES as reported: 7.7307; per dimension `{"SAFETY": 8.0, "FAIRNESS": 8.6535, "INTEGRITY": 8.0, "ROBUSTNESS": 8.0, "EXPLAINABILITY": 6.0}`

## textdetox/xlmr-large-toxicity-classifier @ `b9c7c563427c`

Selected for: multilingual XLM-R large binary classifier (9 declared languages incl. en).

- run status FINALIZED; revision evaluated `b9c7c563427c591fc318d91eb592381ae2fbde66`; engine llm_v1 (LEGACY_HEURISTIC_OSD_V1); FRIES scored

| dimension | probe | aspect scoring | risks | gaps | O/S/D (source) | key evidence |
|---|---|---|---|---|---|---|
| FAIRNESS | EVALUATED | disparity_observed | [] | None | 4/4/8 (None) | `{"n_evaluated":3000,"equal_opportunity_difference":0.073608,"eopp_ci":{"B":1000,"point":0.073608,"method":"bootstrap_percentile","ci_lower":0.008885,"ci_upper":0.138353},"equalized_odds_difference":0.241683,"eo_ci":{"B":1000,"point":0.241683,"method":"bootstrap_percentile","ci_lower":0.175486,"ci_upper":0.308871},"demographic_parity_difference":0.425741,"label_rate_gap":0.504795,"excess_dpd":0.0,"subgroup_f1_spread":0.308236,"fairness_finding":"DISPARITY_OBSERVED"}` |
| ROBUSTNESS | EVALUATED | no_material_risk | [] | None | 1/1/8 (None) | `{"n_evaluated":3000,"clean_accuracy":0.805,"robust_accuracy":0.7513,"accuracy_drop":0.053667,"attack_success_rate":0.0793,"perturbation_coverage":1.0,"max_changes":3}` |
| SAFETY | EVALUATED | disclosure_gap | [] | ['S-GOV-DISCLOSURE-GAP'] | 9/9/8 (heuristic_fallback) | `{"severe_fnr":0.15602836879432624,"fnr_ratio":0.6986344871387743,"coverage_ratio":0.25,"checks_present":1,"high_impact_claims":[],"behavior":{"status":"EVALUATED","severe_n":282,"severe_fnr":0.15602836879432624,"severe_fnr_ci":[0.11832928121399018,0.20297314642425424],"overall_fnr":0.22333333333333333,"harmful_recall":0.7766666666666666,"benign_fpr":0.18791666666666668,"fnr_ratio":0.6986344871387743}}` |
| INTEGRITY | EVALUATED | no_material_risk | [] | [] | 9/9/8 (heuristic_fallback) | `{"identity":{"hash_comparison":"match"},"artifact_verification_status":"VERIFIED"}` |
| EXPLAINABILITY | EVALUATED | disclosure_gap | [] | ['E-DOC-INCOMPLETE'] | 4/4/4 (heuristic_fallback) | `{"coverage_ratio":0.4,"sections_present":2,"contradictions":[],"card_chars":4163,"documentation_source":{"content_length":4163,"retrieval_error":null,"retrieval_status":"ok","source_model_ref":"textdetox/xlmr-large-toxicity-classifier","documentation_url":"https://huggingface.co/textdetox/xlmr-large-toxicity-classifier/blob/b9c7c563427c591fc318d91eb592381ae2fbde66/README.md","source_model_revision":"b9c7c563427c591fc318d91eb592381ae2fbde66","documentation_revision":"b9c7c563427c591fc318d91eb592381ae2fbde66","documentation_source_type":"model_card","documentation_content_hash":"sha256:a0875d3a4f3ac008a4612e7a6208e5d0457378f686a65a78f0207c3c90952399"}}` |

FRIES as reported: 5.6693; per dimension `{"SAFETY": 8.6535, "FAIRNESS": 5.0397, "INTEGRITY": 8.6535, "ROBUSTNESS": 2.0, "EXPLAINABILITY": 4.0}`

## facebook/roberta-hate-speech-dynabench-r4-target @ `391c99ab8b3f`

Selected for: hate-speech (not general toxicity) model, adversarially collected data: label-scope mismatch with the task.

- run status FINALIZED; revision evaluated `391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6`; engine llm_v1 (LEGACY_HEURISTIC_OSD_V1); FRIES scored

| dimension | probe | aspect scoring | risks | gaps | O/S/D (source) | key evidence |
|---|---|---|---|---|---|---|
| FAIRNESS | EVALUATED | risk_detected | ['F-FAIR-EOPP'] | None | 6/6/8 (None) | `{"n_evaluated":3000,"equal_opportunity_difference":0.129696,"eopp_ci":{"B":1000,"point":0.129696,"method":"bootstrap_percentile","ci_lower":0.074797,"ci_upper":0.181492},"equalized_odds_difference":0.16683,"eo_ci":{"B":1000,"point":0.16683,"method":"bootstrap_percentile","ci_lower":0.1243,"ci_upper":0.225495},"demographic_parity_difference":0.162742,"label_rate_gap":0.504795,"excess_dpd":0.0,"subgroup_f1_spread":0.201496,"fairness_finding":"FAIRNESS_RISK"}` |
| ROBUSTNESS | EVALUATED | scored_risk | ['R-ROB-PERT'] | None | 1/1/8 (None) | `{"n_evaluated":3000,"clean_accuracy":0.7833,"robust_accuracy":0.711,"accuracy_drop":0.072333,"attack_success_rate":0.1243,"perturbation_coverage":1.0,"max_changes":3}` |
| SAFETY | EVALUATED | disclosure_gap | [] | ['S-GOV-DISCLOSURE-GAP'] | 1/1/8 (heuristic_fallback) | `{"severe_fnr":0.8368794326241135,"fnr_ratio":0.9884402747528899,"coverage_ratio":0.0,"checks_present":0,"high_impact_claims":[],"behavior":{"status":"EVALUATED","severe_n":282,"severe_fnr":0.8368794326241135,"severe_fnr_ci":[0.7892802187923498,0.8754235891908129],"overall_fnr":0.8466666666666667,"harmful_recall":0.15333333333333332,"benign_fpr":0.059166666666666666,"fnr_ratio":0.9884402747528899}}` |
| INTEGRITY | EVALUATED | disclosure_gap | [] | ['I-INT-LICENSE-UNDISCLOSED'] | 7/7/8 (heuristic_fallback) | `{"identity":{"hash_comparison":"match"},"artifact_verification_status":"VERIFIED"}` |
| EXPLAINABILITY | EVALUATED | disclosure_gap | [] | ['E-DOC-INCOMPLETE'] | 1/1/1 (heuristic_fallback) | `{"coverage_ratio":0.0,"sections_present":0,"contradictions":[],"card_chars":570,"documentation_source":{"content_length":570,"retrieval_error":null,"retrieval_status":"ok","source_model_ref":"facebook/roberta-hate-speech-dynabench-r4-target","documentation_url":"https://huggingface.co/facebook/roberta-hate-speech-dynabench-r4-target/blob/391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6/README.md","source_model_revision":"391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6","documentation_revision":"391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6","documentation_source_type":"model_card","documentation_content_hash":"sha256:5a89e60071e4797689cebf4f97116f75d0bd103d11e4dd66c15ad83ab91c22d8"}}` |

FRIES as reported: 3.7845; per dimension `{"SAFETY": 2.0, "FAIRNESS": 6.6039, "INTEGRITY": 7.3186, "ROBUSTNESS": 2.0, "EXPLAINABILITY": 1.0}`

## gravitee-io/bert-tiny-toxicity @ `8377eb9a344d`

Selected for: very small (bert-tiny, ~17 MB) multilingual binary classifier: low-capacity end.

- run status FINALIZED; revision evaluated `8377eb9a344d74b9d12e656dc3f3632b74f33673`; engine llm_v1 (LEGACY_HEURISTIC_OSD_V1); FRIES scored

| dimension | probe | aspect scoring | risks | gaps | O/S/D (source) | key evidence |
|---|---|---|---|---|---|---|
| FAIRNESS | EVALUATED | disparity_observed | [] | None | 5/5/8 (None) | `{"n_evaluated":3000,"equal_opportunity_difference":0.050607,"eopp_ci":{"B":1000,"point":0.050607,"method":"bootstrap_percentile","ci_lower":0.004435,"ci_upper":0.121711},"equalized_odds_difference":0.202976,"eo_ci":{"B":1000,"point":0.202976,"method":"bootstrap_percentile","ci_lower":0.133171,"ci_upper":0.27036},"demographic_parity_difference":0.317469,"label_rate_gap":0.504795,"excess_dpd":0.0,"subgroup_f1_spread":0.422069,"fairness_finding":"DISPARITY_OBSERVED"}` |
| ROBUSTNESS | EVALUATED | no_material_risk | [] | None | 1/1/8 (None) | `{"n_evaluated":3000,"clean_accuracy":0.664,"robust_accuracy":0.6077,"accuracy_drop":0.056333,"attack_success_rate":0.095,"perturbation_coverage":1.0,"max_changes":3}` |
| SAFETY | EVALUATED | disclosure_gap | [] | ['S-GOV-DISCLOSURE-GAP'] | 9/9/8 (heuristic_fallback) | `{"severe_fnr":0.11347517730496454,"fnr_ratio":0.5403579871664979,"coverage_ratio":0.25,"checks_present":1,"high_impact_claims":[],"behavior":{"status":"EVALUATED","severe_n":282,"severe_fnr":0.11347517730496454,"severe_fnr_ci":[0.08153515364767691,0.15580468771901007],"overall_fnr":0.21,"harmful_recall":0.79,"benign_fpr":0.3675,"fnr_ratio":0.5403579871664979}}` |
| INTEGRITY | EVALUATED | no_material_risk | [] | [] | 9/9/8 (heuristic_fallback) | `{"identity":{"hash_comparison":"match"},"artifact_verification_status":"VERIFIED"}` |
| EXPLAINABILITY | EVALUATED | disclosure_gap | [] | ['E-DOC-INCOMPLETE'] | 2/2/2 (heuristic_fallback) | `{"coverage_ratio":0.2,"sections_present":1,"contradictions":[],"card_chars":6500,"documentation_source":{"content_length":6506,"retrieval_error":null,"retrieval_status":"ok","source_model_ref":"gravitee-io/bert-tiny-toxicity","documentation_url":"https://huggingface.co/gravitee-io/bert-tiny-toxicity/blob/8377eb9a344d74b9d12e656dc3f3632b74f33673/README.md","source_model_revision":"8377eb9a344d74b9d12e656dc3f3632b74f33673","documentation_revision":"8377eb9a344d74b9d12e656dc3f3632b74f33673","documentation_source_type":"model_card","documentation_content_hash":"sha256:87901062796d68a655122258d4a5b8ea15d0e591e5aebaaf60aad476b550eb6b"}}` |

FRIES as reported: 5.431; per dimension `{"SAFETY": 8.6535, "FAIRNESS": 5.848, "INTEGRITY": 8.6535, "ROBUSTNESS": 2.0, "EXPLAINABILITY": 2.0}`

