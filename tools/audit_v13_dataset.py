#!/usr/bin/env python3
"""Audit CLI Command Risk v1.5 splits and report family leakage. No commands run."""
from __future__ import annotations
import argparse, collections, hashlib, json
from datasets import load_dataset

LABELS = ("safe", "low", "moderate", "high", "critical")

def family_of(row):
    # Upstream id embeds the template-family name; derived_from is the
    # authoritative seed template for hybrid rows when populated.
    return str(row.get("derived_from") or row.get("id") or "").strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="yannelli/cli-command-risk")
    ap.add_argument("--revision", default="v1.5")
    ap.add_argument("--output", default="v13_dataset_audit.json")
    args = ap.parse_args()
    ds = load_dataset(args.dataset, revision=args.revision)
    report = {"dataset": args.dataset, "revision": args.revision, "splits": {},
              "cross_split_families": [], "cross_split_commands": [],
              "commands_executed": False}
    family_splits = collections.defaultdict(set)
    command_splits = collections.defaultdict(set)
    for split in ("train", "validation", "test"):
        if split not in ds:
            raise RuntimeError("Missing expected split: " + split)
        counts = collections.Counter()
        source_counts = collections.Counter()
        rows = ds[split]
        for row in rows:
            label = str(row.get("risk_level", "unknown")).lower()
            counts[label] += 1
            source_counts[str(row.get("source", "unknown"))] += 1
            family = family_of(row)
            if family:
                family_splits[family].add(split)
            command = " ".join(str(row.get("command", "")).split())
            shell = str(row.get("shell", "")).lower()
            if command:
                command_splits[(shell, command)].add(split)
        report["splits"][split] = {
            "rows": len(rows), "risk_level_counts": dict(sorted(counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "critical_share": counts["critical"] / max(1, len(rows)),
            "unknown_label_rows": sum(v for k, v in counts.items() if k not in LABELS),
        }
    report["cross_split_families"] = [
        {"family_id": k, "splits": sorted(v)}
        for k, v in family_splits.items() if len(v) > 1
    ][:500]
    report["cross_split_family_count"] = sum(1 for v in family_splits.values() if len(v) > 1)
    report["cross_split_commands"] = [
        {"shell": k[0], "command_sha256": hashlib.sha256(k[1].encode()).hexdigest(),
         "splits": sorted(v)}
        for k, v in command_splits.items() if len(v) > 1
    ][:500]
    report["cross_split_command_count"] = sum(1 for v in command_splits.values() if len(v) > 1)
    report["family_leakage_free"] = report["cross_split_family_count"] == 0
    report["exact_command_leakage_free"] = report["cross_split_command_count"] == 0
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["family_leakage_free"] or not report["exact_command_leakage_free"]:
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
