#!/usr/bin/env python3
"""Validate human-reviewed, schema-complete MiMoCode Guard 1.3 supplements."""
from __future__ import annotations
import argparse, collections, hashlib, json, re
from pathlib import Path

LABELS = {"safe", "low", "moderate", "high", "critical"}
SOURCES = {"hybrid", "generated", "open_source"}
REQUIRED = {"command","shell","risk_level","risk_categories","reversible","requires_root",
            "explanation","safer_alternative","source","provenance","derived_from",
            "family_id","reviewed"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|passwd|secret)\s*[:=]\s*\S+"),
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
def norm(s): return " ".join(str(s).strip().split())
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--output",default="v13_supplement_train.jsonl")
    ap.add_argument("--manifest",default="v13_supplement_manifest.json")
    a=ap.parse_args(); src=Path(a.input)
    if not src.is_file(): ap.error("input file not found: "+str(src))
    raw=src.read_bytes(); rows=[]; errors=[]; seen=set(); fam=collections.defaultdict(set)
    for n,line in enumerate(raw.decode("utf-8-sig").splitlines(),1):
        if not line.strip(): continue
        try:
            x=json.loads(line)
            if not isinstance(x,dict): raise ValueError("row must be an object")
            missing=sorted(REQUIRED-x.keys())
            if missing: raise ValueError("missing fields: "+", ".join(missing))
            cmd=norm(x["command"]); shell=norm(x["shell"]).lower()
            level=norm(x["risk_level"]).lower(); source=norm(x["source"]).lower()
            family=norm(x["family_id"])
            if not cmd or len(cmd)>12000: raise ValueError("command length must be 1..12000")
            if shell not in {"bash","zsh","sh","dash","fish"}: raise ValueError("unsupported shell")
            if level not in LABELS: raise ValueError("unknown risk_level")
            if source not in SOURCES: raise ValueError("source must be hybrid/generated/open_source")
            if x["reviewed"] is not True: raise ValueError("reviewed must be true")
            if not isinstance(x["risk_categories"],list) or not x["risk_categories"]: raise ValueError("risk_categories must be a non-empty list")
            if level=="safe" and x["risk_categories"] != ["safe_baseline"]: raise ValueError("safe rows require risk_categories=['safe_baseline']")
            if level!="safe" and "safe_baseline" in x["risk_categories"]: raise ValueError("risky rows cannot use safe_baseline")
            if not isinstance(x["reversible"],bool) or not isinstance(x["requires_root"],bool): raise ValueError("reversible/requires_root must be booleans")
            provenance=norm(x["provenance"]); derived=norm(x["derived_from"])
            if source=="hybrid" and (not derived or family!="hybrid:"+derived): raise ValueError("hybrid family_id must equal hybrid:<derived_from>")
            if source=="generated" and (not family.startswith("generated:") or derived): raise ValueError("generated family_id must be generated:<seed>; derived_from must be empty")
            if source=="open_source":
                expected="open_source:"+hashlib.sha256(cmd.encode()).hexdigest()
                if family!=expected or not provenance or derived: raise ValueError("open_source family_id must hash the normalized command; provenance required; derived_from empty")
            if any(p.search(cmd) for p in SECRET_PATTERNS): raise ValueError("possible credential/private-key material")
            key=(shell,cmd)
            if key in seen: raise ValueError("duplicate normalized command/shell")
            seen.add(key); fam[family].add(level)
            rows.append({"command":cmd,"shell":shell,"risk_level":level,
              "risk_categories":x["risk_categories"],"reversible":x["reversible"],
              "requires_root":x["requires_root"],"explanation":norm(x["explanation"]),
              "safer_alternative":norm(x["safer_alternative"]),"source":source,
              "provenance":provenance,"derived_from":derived,"family_id":family,"reviewed":True})
        except Exception as e: errors.append({"line":n,"error":str(e)})
    if errors:
        print(json.dumps({"valid":False,"errors":errors[:100],"error_count":len(errors)},ensure_ascii=False,indent=2)); return 2
    payload="".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in rows)
    Path(a.output).write_text(payload,encoding="utf-8")
    counts=collections.Counter(x["risk_level"] for x in rows)
    manifest={"schema_version":"1.3","purpose":"supplemental_train_only",
      "source_sha256":hashlib.sha256(raw).hexdigest(),"output_sha256":hashlib.sha256(payload.encode()).hexdigest(),
      "rows":len(rows),"unique_families":len(fam),"risk_level_counts":dict(sorted(counts.items())),
      "families_with_multiple_labels":sum(len(v)>1 for v in fam.values()),
      "validation_test_modified":False,"commands_executed":False}
    Path(a.manifest).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
