#!/usr/bin/env python3
"""MiMoCode Guard 1.2: audit uploaded evaluation reports before retraining.

CPU-only, standard-library-only. Run in Kaggle or locally:
    python tools/audit_v12_reports.py

The script downloads the report artifacts from the repository, verifies that
large JSONL files are actually readable, reconciles row counts with the JSON
summaries, and checks shell-variant family overlap across splits.
It does not train a model and never executes command strings.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/p5i6/mimocode-guard/main/artifacts/reports/"
JSON_FILES = (
    "comparison.json",
    "error_analysis.json",
    "calibration_report.json",
    "data_diagnostics.json",
)
JSONL_FILES = (
    "critical_false_safe.jsonl",
    "critical_false_high.jsonl",
    "critical_detector_misses.jsonl",
    "critical_detector_false_positives.jsonl",
    "safe_false_positive.jsonl",
)
OUT = Path("mimocode_guard_v12_audit")
USER_AGENT = "MiMoCode-Guard/1.2-report-audit"


def download(name: str) -> bytes:
    req = urllib.request.Request(BASE + name, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def load_json(data: bytes, name: str):
    try:
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON in {name}: {exc}") from exc


def parse_jsonl(data: bytes, name: str):
    rows = []
    bad = []
    for line_no, raw in enumerate(data.decode("utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except Exception as exc:
            bad.append({"line": line_no, "error": str(exc)})
    return rows, bad


def family_key(row):
    sample_id = str(row.get("id", ""))
    shell = str(row.get("shell", "")).lower()
    if shell:
        sample_id = re.sub(rf"-{re.escape(shell)}-", "-SHELL-", sample_id, flags=re.I)
    return sample_id or None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    docs = {}
    hashes = {}
    for name in JSON_FILES + JSONL_FILES:
        data = download(name)
        (OUT / name).write_bytes(data)
        hashes[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if name.endswith(".json"):
            docs[name] = load_json(data, name)

    summary = docs["error_analysis.json"]
    expected = summary.get("artifact_counts", {})
    mapping = {
        "critical_false_safe.jsonl": "critical_false_safe",
        "critical_false_high.jsonl": "critical_false_high",
        "safe_false_positive.jsonl": "safe_false_positive",
        "critical_detector_misses.jsonl": "critical_detector_misses",
        "critical_detector_false_positives.jsonl": "critical_detector_false_positives",
    }

    report = {
        "audit_version": "1.2",
        "source": BASE,
        "files": hashes,
        "jsonl": {},
        "count_reconciliation": {},
        "cross_split_family_overlap": {},
        "dataset_distribution": docs["data_diagnostics.json"].get("distributions", {}),
        "deployment_ready": False,
        "notes": [
            "This is a report-integrity audit, not a safety certification.",
            "Command strings are treated as data and are never executed.",
            "Test split metrics are report-only and must not be used for model or threshold selection.",
        ],
    }

    for name in JSONL_FILES:
        rows, bad = parse_jsonl((OUT / name).read_bytes(), name)
        by_split = collections.Counter(str(r.get("split", "unknown")) for r in rows)
        by_type = collections.Counter(str(r.get("error_type", "unknown")) for r in rows)
        report["jsonl"][name] = {
            "rows": len(rows),
            "malformed_lines": bad[:20],
            "malformed_line_count": len(bad),
            "by_split": dict(by_split),
            "by_error_type": dict(by_type),
            "sample_commands": [str(r.get("command", ""))[:180] for r in rows[:3]],
        }

        key = mapping[name]
        expected_count = expected.get(key)
        report["count_reconciliation"][name] = {
            "summary_count": expected_count,
            "actual_jsonl_rows": len(rows),
            "matches": expected_count == len(rows) if expected_count is not None else None,
        }

        families = collections.defaultdict(set)
        for row in rows:
            family = family_key(row)
            if family:
                families[family].add(str(row.get("split", "unknown")))
        overlaps = [
            {"family": family, "splits": sorted(splits)}
            for family, splits in families.items()
            if len(splits) > 1
        ]
        report["cross_split_family_overlap"][name] = {
            "unique_families": len(families),
            "overlapping_families": len(overlaps),
            "examples": overlaps[:20],
        }

    report["all_counts_match"] = all(
        item["matches"] is True for item in report["count_reconciliation"].values()
    )
    report["all_jsonl_parse_clean"] = all(
        item["malformed_line_count"] == 0 for item in report["jsonl"].values()
    )
    report["any_cross_split_overlap"] = any(
        item["overlapping_families"] > 0
        for item in report["cross_split_family_overlap"].values()
    )

    out_file = OUT / "audit_summary.json"
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nSaved: {out_file.resolve()}")


if __name__ == "__main__":
    main()
