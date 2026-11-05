# MiMoCode Guard 1.3 — Data Expansion

This branch starts the data-expansion phase while preserving the original Candidate A baseline. Candidate B is retained for comparison; TinyBrainBot is excluded.

Read [the 1.3 data expansion plan](docs/V1.3_DATA_EXPANSION.md) before adding examples.

Validate only human-reviewed supplemental JSONL:

```bash
python tools/validate_v13_supplement.py --input reviewed_supplement.jsonl
```

This validator does not train a model. The existing pinned trainer still consumes the original `yannelli/cli-command-risk` v1.5 dataset. Do not claim supplemental rows were trained until a loader integration and run-manifest hash prove that they were.

Safety: commands are treated as inert text and are never executed. A Safe model prediction is never permission to execute a command. Keep deterministic policy checks and explicit approval for privileged actions.
