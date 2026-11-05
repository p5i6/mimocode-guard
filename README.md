# MiMoCode Guard 1.2

CPU-first command-risk classification training and inference, with an integrated report-integrity gate.

## Run on Kaggle

1. Enable Internet in the notebook settings. No GPU is required.
2. Download the launcher:

```bash
wget -O mimocode_guard_train.py https://raw.githubusercontent.com/p5i6/mimocode-guard/mimocode-guard-1.2-audit/mimocode_guard_train.py
```

3. Install missing Python packages and start training:

```bash
python mimocode_guard_train.py --install-missing-deps
```

The launcher first audits the published reports in `artifacts/reports/`: it validates the four JSON reports, parses all five JSONL files, reconciles JSONL row counts against `error_analysis.json`, and writes `mimocode_guard_v12_audit/audit_summary.json`. A malformed report or row-count mismatch stops the run before training. If the audit passes, the launcher retrieves the pinned trainer payload, verifies its SHA-256, extracts the implementation beside the launcher, and runs it.

Report auditing requires Internet access. For an intentional offline reproduction only, set `MIMOCODE_SKIP_REPORT_AUDIT=1`; this bypasses the report gate and should not be used for a fresh model-selection run.

Default output:
- Kaggle: `/kaggle/working/mimocode_guard_output/`
- Other environments: `mimocode_guard_output/` beside the script

## Local inference

After training Candidate A:

```bash
python mimocode_guard_train.py --predict "git status --short" --candidate A
```

To point to a different exported model bundle, pass `--bundle PATH`.

## Safety

This is an experimental risk classifier, not a shell sandbox or authorization system. **Never use a model's `safe` prediction to authorize execution or grant root access.** Keep deterministic policy checks, explicit approval for privileged actions, and audit logging. Commands in the training dataset are treated as text and are never executed by the trainer. Test split metrics remain report-only and must not guide model or threshold selection.

## Dataset

[Ryan Yannelli — CLI Command Risk](https://huggingface.co/datasets/yannelli/cli-command-risk), licensed CC BY 4.0. The trainer expects revision `v1.5` by default and uses only command text, shell name, and the risk label for model development.