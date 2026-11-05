#!/usr/bin/env python3
"""Validate human-reviewed MiMoCode Guard 1.3 supplemental training examples.

This tool never executes shell commands and never assigns risk labels. Every row
must already have a human-reviewed label and provenance. Supplemental rows are
training-only; validation/test remain frozen and must be maintained separately.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, re, sys
from pathlib import Path

LABELS = {"safe", "low", "moderate", "high", "critical"}
REQUIRED = {"command", "shell", "label", "family_id", "source", "reviewed"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|passwd|secret)\\s*[:=]\\s*\\S+"),
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]

def normalize(command: str) -> str:
    return " ".join(command.strip().split())

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Human-reviewed JSONL supplement")
    ap.add_argument("--output", default="v13_supplement_train.jsonl")
    ap.add_argument("--manifest", default="v13_supplement_manifest.json")
    args = ap.parse_args()
    source = Path(args.input)
    if not source.is_file():
        ap.error(f"input file not found: {source}")
    rows, errors, seen = [], [], set()
    family_labels = collections.defaultdict(set)
    raw = source.read_bytes()
    for line_no, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("row must be a JSON object")
            missing = sorted(REQUIRED - item.keys())
            if missing:
                raise ValueError("missing fields: " + ", ".join(missing))
            command = normalize(str(item["command"]))
            label = str(item["label"]).lower().strip()
            family = str(item["family_id"]).strip()
            if not command or len(command) > 12000:
                raise ValueError("command must contain 1..12000 characters")
            if label not in LABELS:
                raise ValueError(f"unknown label: {label}")
            if not str(item["shell"]).strip() or not family:
                raise ValueError("shell and family_id must be non-empty")
            if item["reviewed"] is not True:
                raise ValueError("reviewed must be true; auto-labeled rows are rejected")
            if not str(item["source"]).strip():
                raise ValueError("source provenance is required")
            if any(p.search(command) for p in SECRET_PATTERNS):
                raise ValueError("possible credential/private-key material; remove and review")
            key = (str(item["shell"]).lower().strip(), command)
            if key in seen:
                raise ValueError("duplicate normalized command")
            seen.add(key)
            family_labels[family].add(label)
            rows.append({
                "command": command, "shell": str(item["shell"]).lower().strip(),
                "label": label, "family_id": family,
                "source": str(item["source"]).strip(), "reviewed": True,
            })
        except Exception as exc:
            errors.append({"line": line_no, "error": str(exc)})
    mixed = sorted(k for k, v in family_labels.items() if len(v) > 1)
    if mixed:
        errors.append({"line": None, "error": "family_id has conflicting labels: " + ", ".join(mixed[:20])})
    if errors:
        print(json.dumps({"valid": False, "errors": errors[:100], "error_count": len(errors)}, indent=2))
        return 2
    output = Path(args.output)
    payload = "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in rows)
    output.write_text(payload, encoding="utf-8")
    counts = collections.Counter(x["label"] for x in rows)
    manifest = {
        "schema_version": "1.3",
        "purpose": "supplemental_train_only",
        "source_file": str(source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output_file": str(output),
        "output_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "rows": len(rows), "unique_families": len(family_labels),
        "label_counts": dict(sorted(counts.items())),
        "family_ids_with_multiple_labels": 0,
        "validation_test_modified": False,
        "commands_executed": False,
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
