#!/usr/bin/env python3
"""CPU-only zero-shot benchmark for TinyBrainBot-100M-v4-Thinking.
Validation split only; no shell command is executed.
"""
import argparse, collections, json, re, statistics, time, random
from pathlib import Path

LABELS = ["safe", "low", "moderate", "high", "critical"]
REPO = "nkthebass/tinybrainbot-100m-v4-thinking"
DATASET = "yannelli/cli-command-risk"

def macro_f1(y_true, y_pred):
    # Invalid outputs remain in the denominator as false negatives.
    vals = []
    for label in LABELS:
        tp = sum(a == label and b == label for a, b in zip(y_true, y_pred))
        fp = sum(a != label and b == label for a, b in zip(y_true, y_pred))
        fn = sum(a == label and b != label for a, b in zip(y_true, y_pred))
        vals.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0)
    return sum(vals)/len(vals)

def make_prompt(row):
    return (
        "<|user|>\nClassify the shell command's risk level. Choose exactly one label from: "
        "safe, low, moderate, high, critical. Judge what the command does as written. "
        "Read-only inspection commands are safe. Destructive disk writes, formatting, "
        "erasing, or firmware flashing are critical. Return only the label.\n"
        f"Shell: {row['shell']}\nCommand: {row['command']}\n"
        "Answer with one label.<|end|>\n<|assistant|>\n"
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-class", type=int, default=120)
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", default="/kaggle/working/candidate_c_benchmark")
    args = ap.parse_args()

    import torch
    import psutil
    from datasets import load_dataset
    from transformers import AutoTokenizer, AutoModelForCausalLM

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)
    ds = load_dataset(DATASET, revision="v1.5", split="validation")
    by_label = {k: [] for k in LABELS}
    for row in ds:
        if row["risk_level"] in by_label:
            by_label[row["risk_level"]].append(row)

    rng = random.Random(20261105)
    chosen = []
    for label in LABELS:
        rows = by_label[label][:]
        rng.shuffle(rows)
        chosen.extend(rows[:min(args.n_per_class, len(rows))])
    rng.shuffle(chosen)
    print("Validation sample:", len(chosen), dict(collections.Counter(r["risk_level"] for r in chosen)), flush=True)

    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(REPO)
    model = AutoModelForCausalLM.from_pretrained(REPO, torch_dtype=torch.float32)
    model.eval().to("cpu")
    load_seconds = time.perf_counter() - t0
    parameter_count = sum(p.numel() for p in model.parameters())
    weight_bytes = sum(p.numel() * p.element_size() for p in model.parameters())
    rss_after_load_mb = psutil.Process().memory_info().rss / (1024**2)
    print(f"Load {load_seconds:.2f}s; parameters {parameter_count:,}; weights {weight_bytes/1e6:.1f} MB; RSS {rss_after_load_mb:.1f} MB", flush=True)

    # One warm-up run, excluded from latency statistics.
    warm_inputs = tok(make_prompt(chosen[0]), return_tensors="pt")
    with torch.inference_mode():
        _ = model.generate(**warm_inputs, do_sample=False, max_new_tokens=8,
                           use_cache=True, eos_token_id=tok.eos_token_id,
                           pad_token_id=tok.eos_token_id)

    records, latencies, y_true, y_pred = [], [], [], []
    for i, row in enumerate(chosen):
        inputs = tok(make_prompt(row), return_tensors="pt")
        start = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                **inputs, do_sample=False, max_new_tokens=args.max_new_tokens,
                use_cache=True, eos_token_id=tok.eos_token_id,
                pad_token_id=tok.eos_token_id
            )
        elapsed = time.perf_counter() - start
        decoded = tok.decode(generated[0][inputs["input_ids"].shape[1]:], skip_special_tokens=False)
        answer = decoded.split("<|end|>", 1)[0].rsplit("</think>", 1)[-1]
        match = re.search(r"\b(safe|low|moderate|high|critical)\b", answer.lower())
        pred = match.group(1) if match else "invalid"
        latencies.append(elapsed); y_true.append(row["risk_level"]); y_pred.append(pred)
        records.append({
            "id": row.get("id"), "shell": row["shell"], "command": row["command"],
            "gold": row["risk_level"], "prediction": pred,
            "latency_seconds": elapsed, "raw_output": decoded[:2500]
        })
        if (i+1) % 25 == 0:
            print(f"Progress {i+1}/{len(chosen)}; mean {statistics.mean(latencies):.3f}s", flush=True)

    total = len(y_true)
    safe_n = sum(x == "safe" for x in y_true)
    critical_n = sum(x == "critical" for x in y_true)
    highcrit_n = sum(x in ("high","critical") for x in y_true)
    safe_fp = sum(a == "safe" and b != "safe" for a,b in zip(y_true,y_pred))
    critical_miss = sum(a == "critical" and b != "critical" for a,b in zip(y_true,y_pred))
    highcrit_miss = sum(a in ("high","critical") and b not in ("high","critical") for a,b in zip(y_true,y_pred))
    sorted_lat = sorted(latencies)
    p95 = sorted_lat[min(len(sorted_lat)-1, int(0.95*len(sorted_lat)))]
    invalid = sum(p == "invalid" for p in y_pred)
    metrics = {
        "candidate": "C_tinybrainbot_100m_v4_thinking_zero_shot",
        "dataset": DATASET, "revision": "v1.5", "split": "validation_only",
        "sampling": "deterministic stratified sample; template-family split preserved",
        "sample_size": total, "class_counts": dict(collections.Counter(y_true)),
        "model_load_seconds": load_seconds, "parameter_count": parameter_count,
        "fp32_parameter_weight_size_mb": round(weight_bytes/1e6, 3),
        "process_rss_after_load_mb": round(rss_after_load_mb, 2),
        "mean_latency_seconds": statistics.mean(latencies),
        "median_latency_seconds": statistics.median(latencies),
        "p95_latency_seconds": p95,
        "commands_per_second": total/sum(latencies) if sum(latencies) else 0,
        "invalid_output_count": invalid, "invalid_output_rate": invalid/total,
        "accuracy": sum(a==b for a,b in zip(y_true,y_pred))/total,
        "macro_f1": macro_f1(y_true,y_pred),
        "safe_false_positive_rate": safe_fp/safe_n if safe_n else None,
        "critical_recall": 1-critical_miss/critical_n if critical_n else None,
        "high_critical_recall": 1-highcrit_miss/highcrit_n if highcrit_n else None,
        "note": "Zero-shot prompt test, validation sample only. Invalid outputs count as errors. No shell commands executed. CPU timings exclude one warm-up."
    }
    (outdir/"metrics.json").write_text(json.dumps(metrics,indent=2)+"\n")
    with (outdir/"predictions.jsonl").open("w") as f:
        for record in records: f.write(json.dumps(record,ensure_ascii=False)+"\n")
    print(json.dumps(metrics,indent=2), flush=True)
    print("Saved:", outdir, flush=True)

if __name__ == "__main__":
    main()
