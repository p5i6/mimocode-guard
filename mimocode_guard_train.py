#!/usr/bin/env python3
"""MiMoCode Guard 1.2 launcher with an integrated pre-training report audit."""
from __future__ import annotations
import base64, collections, gzip, hashlib, json, os, runpy, urllib.request
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/p5i6/mimocode-guard/main/payload/"
REPORT_URL = "https://raw.githubusercontent.com/p5i6/mimocode-guard/main/artifacts/reports/"
PARTS = ("part-01.txt", "part-02.txt", "part-03.txt", "part-04.txt", "part-05.txt")
EXPECTED_SHA256 = "b4c48906ecff6d00f91fc4b8f344c2ac508b589989568b976b0ebc69f3b2af9d"
JSON_FILES = ("comparison.json", "error_analysis.json", "calibration_report.json", "data_diagnostics.json")
JSONL_MAP = {"critical_false_safe.jsonl":"critical_false_safe", "critical_false_high.jsonl":"critical_false_high", "safe_false_positive.jsonl":"safe_false_positive", "critical_detector_misses.jsonl":"critical_detector_misses", "critical_detector_false_positives.jsonl":"critical_detector_false_positives"}

def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent":"MiMoCode-Guard/1.2"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()

def audit_reports():
    if os.environ.get("MIMOCODE_SKIP_REPORT_AUDIT") == "1":
        print("[MiMoCode Guard] Report audit explicitly skipped.", flush=True)
        return
    print("[MiMoCode Guard] Running integrated report audit...", flush=True)
    out_dir = Path("mimocode_guard_v12_audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    docs, file_meta = {}, {}
    for name in JSON_FILES:
        raw = fetch(REPORT_URL + name)
        (out_dir / name).write_bytes(raw)
        file_meta[name] = {"bytes":len(raw), "sha256":hashlib.sha256(raw).hexdigest()}
        try:
            docs[name] = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Report audit failed: invalid {name}: {exc}") from exc
    expected = docs["error_analysis.json"].get("artifact_counts", {})
    summary = {"audit_version":"1.2", "source":REPORT_URL, "files":file_meta, "jsonl":{}, "count_reconciliation":{}, "deployment_ready":False}
    fatal = []
    for filename, count_key in JSONL_MAP.items():
        raw = fetch(REPORT_URL + filename)
        (out_dir / filename).write_bytes(raw)
        file_meta[filename] = {"bytes":len(raw), "sha256":hashlib.sha256(raw).hexdigest()}
        rows, malformed = 0, []
        split_counts, type_counts = collections.Counter(), collections.Counter()
        for line_no, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception as exc:
                malformed.append({"line":line_no, "error":str(exc)})
                continue
            rows += 1
            split_counts[str(item.get("split","unknown"))] += 1
            type_counts[str(item.get("error_type","unknown"))] += 1
        expected_count = expected.get(count_key)
        matches = expected_count == rows if expected_count is not None else None
        summary["jsonl"][filename] = {"rows":rows, "malformed_line_count":len(malformed), "malformed_examples":malformed[:10], "by_split":dict(split_counts), "by_error_type":dict(type_counts)}
        summary["count_reconciliation"][filename] = {"summary_count":expected_count, "actual_jsonl_rows":rows, "matches":matches}
        if malformed:
            fatal.append(f"{filename}: {len(malformed)} malformed JSONL lines")
        if matches is False:
            fatal.append(f"{filename}: summary says {expected_count}, actual rows {rows}")
    summary["all_counts_match"] = all(x["matches"] is True for x in summary["count_reconciliation"].values())
    summary["all_jsonl_parse_clean"] = all(x["malformed_line_count"] == 0 for x in summary["jsonl"].values())
    summary["selected_candidate"] = docs["comparison.json"].get("selected_candidate")
    summary["deployment_status"] = docs["comparison.json"].get("deployment_status")
    summary["warnings"] = ["Report integrity is not a safety certification.", "Test split metrics are report-only and must not guide model or threshold selection.", "Review split distribution shift before retraining."]
    summary_path = out_dir / "audit_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary["count_reconciliation"], indent=2), flush=True)
    print("[MiMoCode Guard] Audit summary: " + str(summary_path.resolve()), flush=True)
    if fatal:
        raise RuntimeError("Report audit failed; training stopped. " + " | ".join(fatal))
    print("[MiMoCode Guard] Report integrity passed. Continuing to training.", flush=True)

def main():
    audit_reports()
    encoded_parts = []
    for name in PARTS:
        request = urllib.request.Request(BASE_URL + name, headers={"User-Agent":"MiMoCode-Guard/1.2"})
        with urllib.request.urlopen(request, timeout=60) as response:
            encoded_parts.append(response.read().decode("ascii").strip())
    source = gzip.decompress(base64.b64decode("".join(encoded_parts), validate=True))
    actual_sha256 = hashlib.sha256(source).hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        raise RuntimeError(f"Trainer integrity check failed: expected {EXPECTED_SHA256}, got {actual_sha256}")
    implementation = Path(__file__).resolve().with_name("_mimocode_guard_train_impl.py")
    implementation.write_bytes(source)
    print("[MiMoCode Guard] Verified trainer SHA-256: " + actual_sha256, flush=True)
    runpy.run_path(str(implementation), run_name="__main__")

if __name__ == "__main__":
    main()