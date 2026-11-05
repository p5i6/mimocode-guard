#!/usr/bin/env python3
"""Build a DatasetDict with reviewed additions in train only; keep eval splits byte-stable."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import shutil
from pathlib import Path

from datasets import Dataset, DatasetDict, concatenate_datasets, load_dataset, load_from_disk


def normalise_command(value) -> str:
    return " ".join(str(value or "").split())


def family_of(row) -> str:
    source = str(row.get("source") or "").strip()
    if source == "hybrid":
        return "hybrid:" + str(row.get("derived_from") or "").strip()
    if source == "generated":
        identifier = str(row.get("id") or "").strip()
        stub = re.sub(r"-(?:bash|zsh|sh|dash|fish)-[0-9a-f]{12}$", "", identifier)
        return "generated:" + stub
    if source == "open_source":
        command = normalise_command(row.get("command"))
        return "open_source:" + hashlib.sha256(command.encode("utf-8")).hexdigest()
    return "unknown:" + str(row.get("id") or "").strip()


def rows_sha256(split) -> str:
    digest = hashlib.sha256()
    for row in split:
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supplement", default="v13_supplement_train.jsonl")
    parser.add_argument("--dataset", default="yannelli/cli-command-risk")
    parser.add_argument("--revision", default="v1.5")
    parser.add_argument("--output", default="mimocode_guard_v13_dataset")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    supplement_path = Path(args.supplement)
    if not supplement_path.is_file():
        parser.error("validated supplement not found: " + str(supplement_path))
    raw_supplement = supplement_path.read_bytes()
    rows = [json.loads(line) for line in raw_supplement.decode("utf-8-sig").splitlines() if line.strip()]
    if not rows:
        parser.error("supplement contains no rows")

    upstream = load_dataset(args.dataset, revision=args.revision)
    required_splits = {"train", "validation", "test"}
    missing = required_splits - set(upstream.keys())
    if missing:
        raise RuntimeError("upstream dataset missing splits: " + ", ".join(sorted(missing)))

    frozen_families = set()
    frozen_commands = set()
    baseline_commands = set()
    baseline_ids = set()

    for split_name in ("train", "validation", "test"):
        for row in upstream[split_name]:
            command_key = (str(row.get("shell") or "").lower(), normalise_command(row.get("command")))
            if command_key[1]:
                baseline_commands.add(command_key)
            if row.get("id") is not None:
                baseline_ids.add(str(row["id"]))
            if split_name in ("validation", "test"):
                frozen_families.add(family_of(row))
                if command_key[1]:
                    frozen_commands.add(command_key)
            else:
                pass

    supplemental_commands = set()
    supplemental_ids = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise RuntimeError(f"supplement row {index} is not an object")
        family_id = str(row.get("family_id") or "").strip()
        command = normalise_command(row.get("command"))
        shell = str(row.get("shell") or "").lower().strip()
        label = str(row.get("risk_level") or "").lower().strip()
        if not family_id or not command or not shell or not label:
            raise RuntimeError(f"supplement row {index} has an empty required field")

        if family_id in frozen_families:
            raise RuntimeError(f"supplement row {index} family overlaps frozen validation/test: {family_id}")
        command_key = (shell, command)
        if command_key in frozen_commands:
            raise RuntimeError(f"supplement row {index} command overlaps frozen validation/test")
        if command_key in baseline_commands:
            raise RuntimeError(f"supplement row {index} duplicates an existing upstream command")
        if command_key in supplemental_commands:
            raise RuntimeError(f"supplement row {index} duplicates another supplement command")
        supplemental_commands.add(command_key)

        digest = hashlib.sha256(command.encode("utf-8")).hexdigest()[:12]
        proposed_id = f"{family_id.replace(':', '-')}-{shell}-{digest}"
        if proposed_id in baseline_ids or proposed_id in supplemental_ids:
            raise RuntimeError(f"supplement row {index} creates a duplicate record id")
        supplemental_ids.add(proposed_id)

    additions = []
    for row in rows:
        source = row["source"]
        shell = row["shell"]
        command = row["command"]
        digest = hashlib.sha256(normalise_command(command).encode("utf-8")).hexdigest()[:12]
        if row["source"] == "hybrid":
            family_stub = row["derived_from"]
        elif row["source"] == "generated":
            family_stub = row["family_id"].split(":", 1)[1]
        else:
            family_stub = "os-" + row["provenance"]
        proposed_id = f"{family_stub}-{shell}-{digest}"

        values = {
            "id": proposed_id,
            "command": command,
            "shell": shell,
            "risk_level": row["risk_level"],
            "risk_categories": row["risk_categories"],
            "reversible": row["reversible"],
            "requires_root": row["requires_root"],
            "explanation": row["explanation"],
            "safer_alternative": row["safer_alternative"],
            "source": source,
            "provenance": row["provenance"],
            "derived_from": row["derived_from"],
            "split": "train",
        }
        # Match the upstream schema exactly; this prevents feature mismatch on concatenate.
        additions.append({column: values.get(column) for column in upstream["train"].column_names})

    extra = Dataset.from_list(additions, features=upstream["train"].features)
    merged_train = concatenate_datasets([upstream["train"], extra])
    output = Path(args.output)
    if output.exists():
        if not args.overwrite:
            raise FileExistsError(f"output already exists; pass --overwrite to replace it: {output}")
        shutil.rmtree(output)

    validation_before = rows_sha256(upstream["validation"])
    test_before = rows_sha256(upstream["test"])
    dataset_dict = DatasetDict({
        "train": merged_train,
        "validation": upstream["validation"],
        "test": upstream["test"],
    })
    dataset_dict.save_to_disk(str(output))

    # Reload and verify the frozen splits at the persisted boundary, not just in memory.
    reloaded = load_from_disk(str(output))
    validation_after = rows_sha256(reloaded["validation"])
    test_after = rows_sha256(reloaded["test"])
    validation_unchanged = validation_before == validation_after
    test_unchanged = test_before == test_after
    if not validation_unchanged or not test_unchanged:
        raise RuntimeError("persisted validation/test content differs from the upstream frozen split")

    manifest = {
        "dataset": args.dataset,
        "revision": args.revision,
        "train_before": len(upstream["train"]),
        "supplement_rows_added": len(additions),
        "train_after": len(reloaded["train"]),
        "validation_rows_unchanged": len(reloaded["validation"]),
        "test_rows_unchanged": len(reloaded["test"]),
        "validation_sha256_before": validation_before,
        "validation_sha256_after": validation_after,
        "test_sha256_before": test_before,
        "test_sha256_after": test_after,
        "validation_test_unchanged": validation_unchanged and test_unchanged,
        "supplement_sha256": hashlib.sha256(raw_supplement).hexdigest(),
        "dataset_saved_to": str(output),
        "commands_executed": False,
    }
    manifest_path = Path(str(output) + "_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
