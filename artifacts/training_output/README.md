# MiMoCode Guard 1.1 Risk Classifier — CPU-first training run

- Dataset: `yannelli/cli-command-risk` revision `v1.5`
- Selected candidate by validation-only ranking: **A**
- Deployment status: **research_only_safety_targets_not_met**
- Maximum deploy bundle target: **10.0 MiB**
- Training device: CPU

| Candidate | Package MiB | Under limit | Test macro-F1 | Test Critical recall (argmax) | Test High+Critical recall (thresholded) |
|---|---:|---|---:|---:|---:|
| A + Critical head | 2.897 | True | 0.5618 | 0.6369 | 0.9458 |
| B Token-CNN | 1.376 | True | 0.4945 | 0.6433 | 0.7725 |

## Candidate A Critical specialist
- Validation Critical recall: 0.9758
- Validation Safe false-positive rate: 0.0084
- Validation noncritical false-positive rate: 0.1998
- Test Critical recall (threshold fixed on validation): 0.9949

Model selection uses validation metrics only; test metrics are report-only. A specialist flag is an additional review signal, not an automatic block/allow decision.

## Diagnostic artifacts
- `comparison.json`, `training_config.json`, `data_diagnostics.json`
- `error_analysis.json`, `calibration_report.json`
- `critical_false_safe.jsonl`, `critical_false_high.jsonl`, `safe_false_positive.jsonl`
- `critical_detector_misses.jsonl`, `critical_detector_false_positives.jsonl`

## Dataset attribution
Ryan Yannelli (2026), *CLI Command Risk*, Hugging Face Datasets, CC BY 4.0: https://huggingface.co/datasets/yannelli/cli-command-risk

## Safety limitations
This experimental classifier does not fully parse shell semantics and cannot prove a command is safe. A `safe` prediction must never authorize command execution. Keep deterministic policy rules, privileged-action confirmation, and audit logs. Never pass passwords, tokens, or credentials to the model.
