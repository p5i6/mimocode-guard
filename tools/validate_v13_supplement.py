#!/usr/bin/env python3
"""Validate human-reviewed, schema-complete MiMoCode Guard 1.3 supplements."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

LABELS = {"safe", "low", "moderate", "high", "critical"}
SOURCES = {"hybrid", "generated", "open_source"}
SHELLS = {"bash", "zsh", "sh", "dash", "fish"}
REQUIRED = {
    "command", "shell", "risk_level", "risk_categories", "reversible",
    "requires_root", "explanation", "safer_alternative", "source",
    "provenance", "derived_from", "family_id", "reviewed",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|passwd|secret)\s*[:=]\s*\S+"),
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def norm(value: str) -> str:
    return " ".join(value.strip().split())


def require_text(row: dict, key: str, *, allow_empty: bool = False) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    value = norm(value)
    if not allow_empty and not value:
        raise ValueError(f"{key} must not be empty")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="v13_supplement_train.jsonl")
    parser.add_argument("--manifest", default="v13_supplement_manifest.json")
    args = parser.parse_args()

    source_path = Path(args.input)
    if not source_path.is_file():
        parser.error(f"input file not found: {source_path}")

    raw = source_path.read_bytes()
    rows = []
    errors = []
    seen_commands = set()
    family_labels = collections.defaultdict(set)

    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("row must be a JSON object")

            missing = sorted(REQUIRED - item.keys())
            if missing:
                raise ValueError("missing fields: " + ", ".join(missing))

            command = require_text(item, "command")
            shell = require_text(item, "shell").lower()
            level = require_text(item, "risk_level").lower()
            source = require_text(item, "source").lower()
            family_id = require_text(item, "family_id")
            explanation = require_text(item, "explanation")
            safer_alternative = require_text(item, "safer_alternative", allow_empty=True)
            provenance = require_text(item, "provenance")
            derived_from = require_text(item, "derived_from", allow_empty=True)

            if len(command) > 12000:
                raise ValueError("command length must be 1..12000 characters")
            if shell not in SHELLS:
                raise ValueError("unsupported shell")
            if level not in LABELS:
                raise ValueError("unknown risk_level")
            if source not in SOURCES:
                raise ValueError("source must be hybrid/generated/open_source")
            if item["reviewed"] is not True:
                raise ValueError("reviewed must be true")
            if not isinstance(item["risk_categories"], list) or not item["risk_categories"]:
                raise ValueError("risk_categories must be a non-empty list of strings")
            if any(not isinstance(v, str) or not norm(v) for v in item["risk_categories"]):
                raise ValueError("risk_categories must contain only non-empty strings")
            if len(set(item["risk_categories"])) != len(item["risk_categories"]):
                raise ValueError("risk_categories must not contain duplicates")
            if level == "safe" and item["risk_categories"] != ["safe_baseline"]:
                raise ValueError("safe rows require risk_categories=['safe_baseline']")
            if level != "safe" and "safe_baseline" in item["risk_categories"]:
                raise ValueError("risky rows cannot use safe_baseline")
            if not isinstance(item["reversible"], bool) or not isinstance(item["requires_root"], bool):
                raise ValueError("reversible/requires_root must be booleans")

            if source == "hybrid":
                if not derived_from or family_id != "hybrid:" + derived_from:
                    raise ValueError("hybrid family_id must equal hybrid:<derived_from>")
            elif source == "generated":
                if not family_id.startswith("generated:") or not family_id.split(":", 1)[1] or derived_from:
                    raise ValueError("generated family_id must be generated:<seed>; derived_from must be empty")
            else:
                expected = "open_source:" + hashlib.sha256(command.encode("utf-8")).hexdigest()
                if family_id != expected or derived_from:
                    raise ValueError("open_source family_id must hash the normalized command; derived_from must be empty")

            searchable = "\n".join((command, explanation, safer_alternative, provenance, derived_from))
            if any(pattern.search(searchable) for pattern in SECRET_PATTERNS):
                raise ValueError("possible credential/private-key material")

            command_key = (shell, command)
            if command_key in seen_commands:
                raise ValueError("duplicate normalized command/shell")
            seen_commands.add(command_key)
            family_labels[family_id].add(level)

            rows.append({
                "command": command,
                "shell": shell,
                "risk_level": level,
                "risk_categories": [norm(v) for v in item["risk_categories"]],
                "reversible": item["reversible"],
                "requires_root": item["requires_root"],
                "explanation": explanation,
                "safer_alternative": safer_alternative,
                "source": source,
                "provenance": provenance,
                "derived_from": derived_from,
                "family_id": family_id,
                "reviewed": True,
            })
        except Exception as exc:
            errors.append({"line": line_number, "error": str(exc)})

    if errors:
        print(json.dumps({
            "valid": False,
            "errors": errors[:100],
            "error_count": len(errors),
            "commands_executed": False,
        }, ensure_ascii=False, indent=2))
        return 2
    if not rows:
        print(json.dumps({"valid": False, "error": "supplement contains no rows"}, indent=2))
        return 2

    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")

    counts = collections.Counter(row["risk_level"] for row in rows)
    manifest = {
        "schema_version": "1.3",
        "purpose": "supplemental_train_only",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "rows": len(rows),
        "unique_families": len(family_labels),
        "risk_level_counts": dict(sorted(counts.items())),
        "families_with_multiple_labels": sum(len(labels) > 1 for labels in family_labels.values()),
        "multiple_labels_per_family_allowed": True,
        "validation_test_modified": False,
        "commands_executed": False,
    }
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
