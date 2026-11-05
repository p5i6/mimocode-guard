#!/usr/bin/env python3
"""Audit upstream or locally expanded CLI Command Risk splits. No commands run."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

from datasets import load_dataset, load_from_disk

LABELS = {"safe", "low", "moderate", "high", "critical"}


def normalise_command(value) -> str:
    return " ".join(str(value or "").split())


def family_of(row) -> str:
    source = str(row.get("source") or "").strip()
    if source == "hybrid":
        return "hybrid:" + str(row.get("derived_from") or "").strip()
    if source == "generated":
        identifier = str(row.get("id") or "").strip()
        return "generated:" + re.sub(r"-(?:bash|zsh|sh|dash|fish)-[0-9a-f]{12}$", "", identifier)
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
    parser.add_argument("--dataset", default="yannelli/cli-command-risk")
    parser.add_argument("--revision", default="v1.5")
    parser.add_argument("--local-dataset", default=None)
    parser.add_argument("--output", default="v13_dataset_audit.json")
    parser.add_argument("--skip-reference-check", action="store_true",
                        help="skip remote v1.5 validation/test comparison (not recommended)")
    args = parser.parse_args()

    is_local = bool(args.local_dataset)
    if is_local:
        local_path = Path(args.local_dataset)
        if not local_path.is_dir():
            parser.error("local dataset directory not found: " + str(local_path))
        dataset = load_from_disk(str(local_path))
    else:
        dataset = load_dataset(args.dataset, revision=args.revision)

    required_splits = {"train", "validation", "test"}
    missing = required_splits - set(dataset.keys())
    if missing:
        raise RuntimeError("dataset missing splits: " + ", ".join(sorted(missing)))

    report = {
        "dataset": args.dataset,
        "revision": args.revision,
        "dataset_kind": "local_expanded" if is_local else "upstream",
        "local_dataset": args.local_dataset,
        "splits": {},
        "cross_split_families": [],
        "cross_split_commands": [],
        "commands_executed": False,
    }
    family_splits = collections.defaultdict(set)
    command_splits = collections.defaultdict(set)
    family_labels = collections.defaultdict(set)
    any_unknown_labels = 0

    for split_name in ("train", "validation", "test"):
        counts = collections.Counter()
        source_counts = collections.Counter()
        for row in dataset[split_name]:
            label = str(row.get("risk_level") or "unknown").lower()
            counts[label] += 1
            source_counts[str(row.get("source") or "unknown")] += 1
            if label not in LABELS:
                any_unknown_labels += 1
            family_id = family_of(row)
            family_splits[family_id].add(split_name)
            family_labels[family_id].add(label)
            command = normalise_command(row.get("command"))
            shell = str(row.get("shell") or "").lower()
            if command:
                command_splits[(shell, command)].add(split_name)

        report["splits"][split_name] = {
            "rows": len(dataset[split_name]),
            "risk_level_counts": dict(sorted(counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "critical_share": counts["critical"] / max(1, len(dataset[split_name])),
            "unknown_label_rows": sum(count for label, count in counts.items() if label not in LABELS),
            "content_sha256": rows_sha256(dataset[split_name]),
        }

    report["cross_split_families"] = [
        {"family_id": family_id, "splits": sorted(splits)}
        for family_id, splits in family_splits.items() if len(splits) > 1
    ][:500]
    report["cross_split_family_count"] = sum(len(splits) > 1 for splits in family_splits.values())
    report["cross_split_commands"] = [
        {
            "shell": key[0],
            "command_sha256": hashlib.sha256(key[1].encode("utf-8")).hexdigest(),
            "splits": sorted(splits),
        }
        for key, splits in command_splits.items() if len(splits) > 1
    ][:500]
    report["cross_split_command_count"] = sum(len(splits) > 1 for splits in command_splits.values())
    report["families_with_multiple_labels"] = sum(len(labels) > 1 for labels in family_labels.values())
    report["unknown_label_rows_total"] = any_unknown_labels
    report["family_leakage_free"] = report["cross_split_family_count"] == 0
    report["exact_command_leakage_free"] = report["cross_split_command_count"] == 0

    if is_local and not args.skip_reference_check:
        reference = load_dataset(args.dataset, revision=args.revision)
        reference_hashes = {
            split: rows_sha256(reference[split]) for split in ("validation", "test")
        }
        report["reference_comparison"] = {}
        for split in ("validation", "test"):
            local_hash = report["splits"][split]["content_sha256"]
            report["reference_comparison"][split] = {
                "reference_sha256": reference_hashes[split],
                "local_sha256": local_hash,
                "unchanged": reference_hashes[split] == local_hash,
            }
        report["validation_test_unchanged"] = all(
            report["reference_comparison"][split]["unchanged"] for split in ("validation", "test")
        )
    elif is_local:
        report["reference_comparison"] = "skipped by request"
        report["validation_test_unchanged"] = None
    else:
        report["validation_test_unchanged"] = None

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    failed = (
        not report["family_leakage_free"]
        or not report["exact_command_leakage_free"]
        or report["unknown_label_rows_total"] > 0
        or (is_local and not args.skip_reference_check and not report["validation_test_unchanged"])
    )
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
