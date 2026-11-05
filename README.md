# MiMoCode Guard 1.3 — Data Expansion

This branch keeps Candidate A as the primary baseline and Candidate B as a comparison. TinyBrainBot is excluded.

## Kaggle CPU preparation commands

Clone this branch in a Kaggle notebook:

```bash
!git clone --depth 1 --branch mimocode-guard-1.3-data-expansion https://github.com/p5i6/mimocode-guard.git
%cd mimocode-guard
!pip -q install "datasets>=2.18,<4"
```

Audit the pinned upstream data:

```bash
!python tools/audit_v13_dataset.py --revision v1.5 --output v13_upstream_audit.json
```

After preparing `reviewed_supplement.jsonl` with the complete schema documented in `docs/V1.3_DATA_EXPANSION.md`, validate and build the train-only dataset:

```bash
!python tools/validate_v13_supplement.py --input reviewed_supplement.jsonl
!python tools/prepare_v13_dataset.py --supplement v13_supplement_train.jsonl --revision v1.5 --output /kaggle/working/mimocode_guard_v13_dataset
```

The builder refuses family or exact command overlap with frozen validation/test, adds supplement rows only to train, saves a DatasetDict and writes a SHA-256 manifest.

## Important training status

The existing `mimocode_guard_train.py` launcher still downloads the pinned trainer implementation, which loads the original upstream v1.5 dataset. It does **not yet consume** `/kaggle/working/mimocode_guard_v13_dataset`. Do not run the old launcher and call that an expanded-data experiment. The next engineering task is to patch the trainer's loader to accept the local DatasetDict, record its manifest hash, and prove the train/validation/test row counts before model fitting.

## Supplement schema

Each JSONL record requires: `command`, `shell`, `risk_level`, `risk_categories`, `reversible`, `requires_root`, `explanation`, `safer_alternative`, `source`, `provenance`, `derived_from`, `family_id`, and `reviewed: true`.

Family identifiers:
- hybrid: `hybrid:<derived_from>`
- generated: `generated:<seed-id>`
- open-source canonical command: `open_source:<sha256 of normalized command>`

Only human-reviewed labels are accepted. Use provenance that can be checked by another reviewer. Do not treat model-generated labels as ground truth. Do not put secrets or credentials in command examples.

## Safety

All commands are treated as inert text and are never executed. A Safe model prediction is never permission to execute a command. Keep deterministic policy checks and explicit approval for privileged actions.
