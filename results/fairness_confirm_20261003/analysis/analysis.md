# L5 — L4.1 confirmatory fairness validation (seed 20261003)

Rule: v6-eod-fairness-risk-2026 / tl-fairness-binary-v1.2, unchanged (ε = 0.02, wide-CI 0.15, B = 1000).

| model | flip rate | n (g0/g1) | pos rate (g0/g1) | DPD | EOD | EOD CI | FPR gap | F1 spread | finding | risks | aspect | flagged | repeatable |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clean_control | 0.0 | 2500/500 | 0.1128/0.6360 | 0.3496 | 0.1057 | [0.0279, 0.1808] | 0.0755 | 0.1343 | INSUFFICIENT_EVIDENCE | [] | mapping_blocked | False | True |
| fairness_r020 | 0.2 | 2500/500 | 0.1128/0.6360 | 0.3812 | 0.1135 | [0.0331, 0.1889] | 0.0901 | 0.1379 | INSUFFICIENT_EVIDENCE | [] | mapping_blocked | False | True |
| fairness_r040 | 0.4 | 2500/500 | 0.1128/0.6360 | 0.4424 | 0.1673 | [0.0924, 0.2393] | 0.1416 | 0.1818 | FAIRNESS_RISK | ['F-FAIR-EOPP'] | risk_detected | True | True |
| fairness_r070 | 0.7 | 2500/500 | 0.1128/0.6360 | 0.5132 | 0.2049 | [0.1322, 0.2767] | 0.2522 | 0.2114 | FAIRNESS_RISK | ['F-FAIR-EOPP'] | risk_detected | True | True |
| fairness_r100 | 1.0 | 2500/500 | 0.1128/0.6360 | 0.5636 | 0.2056 | [0.1395, 0.2657] | 0.3472 | 0.2265 | FAIRNESS_RISK | ['F-FAIR-EOPP'] | risk_detected | True | True |
| reference_toxicbert_2label | control | 2500/500 | 0.1128/0.6360 | 0.2720 | 0.1451 | [0.0688, 0.2170] | 0.0373 | 0.1691 | FAIRNESS_RISK | ['F-FAIR-EOPP'] | risk_detected | True | True |

## Hypotheses (frozen criteria)

```json
{
  "H1": {
    "holds": false,
    "controls": [
      "clean_control",
      "reference_toxicbert_2label"
    ],
    "flagged_controls": [
      "reference_toxicbert_2label"
    ]
  },
  "H2": {
    "holds": true,
    "models": [
      "fairness_r040",
      "fairness_r070",
      "fairness_r100"
    ],
    "recall": 1.0,
    "flagged": {
      "fairness_r040": true,
      "fairness_r070": true,
      "fairness_r100": true
    }
  },
  "H3": {
    "holds": true,
    "spearman_rho": 1.0,
    "n_levels": 5,
    "levels": [
      [
        0.0,
        0.105714
      ],
      [
        0.2,
        0.113475
      ],
      [
        0.4,
        0.167269
      ],
      [
        0.7,
        0.204938
      ],
      [
        1.0,
        0.205607
      ]
    ],
    "adjacent_decreases": 0,
    "strictly_monotone": true
  },
  "H4": {
    "per_model": {
      "clean_control": {
        "insufficient_evidence": 3,
        "mapping_blocked": 3
      },
      "fairness_r020": {
        "insufficient_evidence": 3,
        "mapping_blocked": 3
      },
      "fairness_r040": {
        "insufficient_evidence": 0,
        "mapping_blocked": 0
      },
      "fairness_r070": {
        "insufficient_evidence": 0,
        "mapping_blocked": 0
      },
      "fairness_r100": {
        "insufficient_evidence": 0,
        "mapping_blocked": 0
      },
      "reference_toxicbert_2label": {
        "insufficient_evidence": 0,
        "mapping_blocked": 0
      }
    }
  }
}
```
