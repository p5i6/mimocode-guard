#!/usr/bin/env python3
"""Build a local DatasetDict with reviewed additions in train only.

Validation and test rows are copied unchanged from the pinned upstream revision.
The script refuses supplemental families/commands that occur in either frozen
split. It does not train a model or execute any command.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, re
from pathlib import Path
from datasets import Dataset, DatasetDict, concatenate_datasets, load_dataset

def family(row):
    src=str(row.get("source") or "")
    if src=="hybrid": return "hybrid:"+str(row.get("derived_from") or "")
    if src=="generated":
        stub=re.sub(r"-(?:bash|zsh|sh|dash|fish)-[0-9a-f]{12}$","",str(row.get("id") or ""))
        return "generated:"+stub
    if src=="open_source":
        cmd=" ".join(str(row.get("command") or "").split())
        return "open_source:"+hashlib.sha256(cmd.encode()).hexdigest()
    return "unknown:"+str(row.get("id") or "")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--supplement",default="v13_supplement_train.jsonl")
    p.add_argument("--dataset",default="yannelli/cli-command-risk")
    p.add_argument("--revision",default="v1.5")
    p.add_argument("--output",default="mimocode_guard_v13_dataset")
    a=p.parse_args()
    path=Path(a.supplement)
    if not path.is_file(): p.error("validated supplement not found: "+str(path))
    rows=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    ds=load_dataset(a.dataset,revision=a.revision)
    frozen_families=set(); frozen_commands=set(); train_families=set()
    for split in ("validation","test"):
        for row in ds[split]:
            frozen_families.add(family(row))
            frozen_commands.add((" ".join(str(row["command"]).split()),str(row["shell"]).lower()))
    for row in ds["train"]: train_families.add(family(row))
    for i,row in enumerate(rows,1):
        fam=row["family_id"]
        if fam in frozen_families:
            raise RuntimeError(f"supplement row {i} family overlaps frozen validation/test: {fam}")
        cmd=(" ".join(row["command"].split()),row["shell"].lower())
        if cmd in frozen_commands:
            raise RuntimeError(f"supplement row {i} command overlaps frozen validation/test")
        if fam not in train_families and fam.startswith(("hybrid:","generated:")):
            # A genuinely new family is permitted, but it remains train-only.
            pass
    additions=[]
    for row in rows:
        src=row["source"]; shell=row["shell"]; cmd=row["command"]
        if src=="hybrid": stub=row["derived_from"]
        elif src=="generated": stub=row["family_id"].split(":",1)[1]
        else: stub="os-"+row["provenance"]
        digest=hashlib.sha256(cmd.encode()).hexdigest()[:12]
        additions.append({
          "id":f"{stub}-{shell}-{digest}","command":cmd,"shell":shell,
          "risk_level":row["risk_level"],"risk_categories":row["risk_categories"],
          "reversible":row["reversible"],"requires_root":row["requires_root"],
          "explanation":row["explanation"],"safer_alternative":row["safer_alternative"],
          "source":src,"provenance":row["provenance"],"derived_from":row["derived_from"],
          "split":"train"})
    if additions:
        extra=Dataset.from_list(additions)
        merged=concatenate_datasets([ds["train"], extra])
    else: merged=ds["train"]
    out=DatasetDict({"train":merged,"validation":ds["validation"],"test":ds["test"]})
    out.save_to_disk(a.output)
    summary={"dataset":a.dataset,"revision":a.revision,"train_before":len(ds["train"]),
      "supplement_rows_added":len(additions),"train_after":len(merged),
      "validation_rows_unchanged":len(ds["validation"]),"test_rows_unchanged":len(ds["test"]),
      "supplement_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
      "validation_test_modified":False,"commands_executed":False,
      "dataset_saved_to":a.output}
    Path(a.output+"_manifest.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
