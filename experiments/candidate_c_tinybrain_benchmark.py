#!/usr/bin/env python3
"""CPU-only zero-shot benchmark for TinyBrainBot-100M-v4-Thinking.
Uses ONLY the v1.5 validation split. Never executes shell commands.
"""
import argparse, collections, json, os, re, statistics, time, tracemalloc
from pathlib import Path

LABELS = ["safe", "low", "moderate", "high", "critical"]
REPO = "nkthebass/tinybrainbot-100m-v4-thinking"
DATASET = "yannelli/cli-command-risk"

def macro_f1(y_true, y_pred):
    vals = []
    for label in LABELS:
        tp = sum(a == label and b == label for a, b in zip(y_true, y_pred))
        fp = sum(a != label and b == label for a, b in zip(y_true, y_pred))
        fn = sum(a == label and b != label for a, b in zip(y_true, y_pred))
        vals.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0)
    return sum(vals)/len(vals)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-class", type=int, default=120, help="validation rows per label; default 120 (600 total)")
    ap.add_argument("--max-new-tokens", type=int, default=48)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", default="/kaggle/working/candidate_c_benchmark")
    args = ap.parse_args()

    import torch
    from datasets import load_dataset
    from transformers import AutoTokenizer, AutoModelForCausalLM

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)

    print("Loading validation split only...", flush=True)
    ds = load_dataset(DATASET, revision="v1.5", split="validation")
    by_label = {k: [] for k in LABELS}
    for row in ds:
        lab = row["risk_level"]
        if lab in by_label: by_label[lab].append(row)
    chosen = []
    # Deterministic, evenly stratified sample; preserve official template-family split.
    import random
    rng = random.Random(20261105)
    for lab in LABELS:
        rows = by_label[lab][:]
        rng.shuffle(rows)
        chosen.extend(rows[:min(args.n_per_class, len(rows))])
    rng.shuffle(chosen)
    print("Rows:", len(chosen), "class_counts:", dict(collections.Counter(r["risk_level"] for r in chosen)), flush=True)

    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(REPO)
    model = AutoModelForCausalLM.from_pretrained(REPO, torch_dtype=torch.float32)
    model.eval()
    model.to("cpu")
    load_seconds = time.perf_counter() - t0
    print(f"Model load: {load_seconds:.2f}s", flush=True)

    records, latencies, y_true, y_pred = [], [], [], []
    bad = 0
    for i, row in enumerate(chosen):
        prompt = (
            "<|user|>Classify the shell command's risk level. "
            "Choose exactly one label from: safe, low, moderate, high, critical. "
            "Judge what the command does as written, not what it might do in another context. "
            "Read-only inspection commands are safe. Destructive disk writes, formatting, "
            "erasing, or firmware flashing are critical. Return only the label.\n"
            f"Shell: {row['shell']}\nCommand: {row['command']}\n"
            "Answer with one label.<|end|>\n<|assistant|>"
        )
        inputs = tok(prompt, return_tensors="pt")
        start = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                **inputs, do_sample=False, max_new_tokens=args.max_new_tokens,
                use_cache=True, pad_token_id=tok.eos_token_id
            )
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)
        decoded = tok.decode(generated[0][inputs["input_ids"].shape[1]:], skip_special_tokens=False)
        # Thinking may precede the final answer; inspect only text after its closing tag.
        final_text = decoded.rsplit("</think>", 1)[-1]
        match = re.search(r"\b(safe|low|moderate|high|critical)\b", final_text.lower())
        pred = match.group(1) if match else "invalid"
        if pred == "invalid": bad += 1
        y_true.append(row["risk_level"])
        y_pred.append(pred)
        records.append({
            "id": row.get("id"), "shell": row["shell"], "command": row["command"],
            "gold": row["risk_level"], "prediction": pred, "latency_seconds": elapsed,
            "raw_output": decoded[:2000]
        })
        if (i+1) % 25 == 0:
            print(f"Progress {i+1}/{len(chosen)} | mean latency {statistics.mean(latencies):.3f}s", flush=True)

    valid_pairs = [(a,b) for a,b in zip(y_true,y_pred) if b in LABELS]
    yt = [x[0] for x in valid_pairs]; yp = [x[1] for x in valid_pairs]
    total = len(y_true)
    safe_n = sum(x == "safe" for x in y_true)
    critical_n = sum(x == "critical" for x in y_true)
    highcrit_n = sum(x in ("high","critical") for x in y_true)
    safe_fp = sum(a == "safe" and b != "safe" for a,b in zip(y_true,y_pred))
    critical_miss = sum(a == "critical" and b in ("safe","low","moderate","high","invalid") for a,b in zip(y_true,y_pred))
    highcrit_miss = sum(a in ("high","critical") and b not in ("high","critical") for a,b in zip(y_true,y_pred))
    sorted_lat = sorted(latencies)
    p95 = sorted_lat[min(len(sorted_lat)-1, int(0.95*len(sorted_lat)))] if sorted_lat else None
    metrics = {
        "candidate":"C_tinybrainbot_100m_v4_thinking_zero_shot",
        "dataset":"yannelli/cli-command-risk", "revision":"v1.5", "split":"validation_only",
        "sample_size":total, "class_counts":dict(collections.Counter(y_true)),
        "load_seconds":load_seconds, "mean_latency_seconds":statistics.mean(latencies),
        "median_latency_seconds":statistics.median(latencies), "p95_latency_seconds":p95,
        "commands_per_second":total/sum(latencies) if sum(latencies) else 0,
        "invalid_output_count":bad, "invalid_output_rate":bad/total if total else 0,
        "accuracy":sum(a==b for a,b in zip(y_true,y_pred))/total if total else 0,
        "macro_f1_valid_outputs_only":macro_f1(yt,yp) if yt else 0,
        "safe_false_positive_rate":safe_fp/safe_n if safe_n else None,
        "critical_recall":1-critical_miss/critical_n if critical_n else None,
        "high_critical_recall":1-highcrit_miss/highcrit_n if highcrit_n else None,
        "note":"Zero-shot prompt benchmark; validation sample only. Invalid outputs count as errors in accuracy/recall. No command was executed."
    }
    (outdir/"metrics.json").write_text(json.dumps(metrics,indent=2)+"\n")
    with (outdir/"predictions.jsonl").open("w") as f:
        for r in records: f.write(json.dumps(r,ensure_ascii=False)+"\n")
    print(json.dumps(metrics,indent=2), flush=True)
    print("Saved:", outdir, flush=True)

if __name__ == "__main__":
    main()
