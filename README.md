# MiMoCode Guard 1.1

CPU-first command-risk classification training and inference.

## Run on Kaggle

1. Enable Internet in the notebook settings. No GPU is required.
2. Download the launcher:

```bash
wget -O mimocode_guard_train.py https://raw.githubusercontent.com/p5i6/mimocode-guard/main/mimocode_guard_train.py
```

3. Install missing Python packages and start training:

```bash
python mimocode_guard_train.py --install-missing-deps
```

The launcher retrieves the version-pinned payload fragments from this repository, verifies the extracted trainer SHA-256, and runs it. The readable implementation is extracted beside the launcher automatically.

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

This is an experimental risk classifier, not a shell sandbox or authorization system. **Never use a model's `safe` prediction to authorize execution or grant root access.** Keep deterministic policy checks, explicit approval for privileged actions, and audit logging. Commands in the training dataset are treated as text and are never executed by the trainer.

## Dataset

[Ryan Yannelli — CLI Command Risk](https://huggingface.co/datasets/yannelli/cli-command-risk), licensed CC BY 4.0. The trainer expects revision `v1.5` by default and uses only command text, shell name, and the risk label for model development.
