#!/usr/bin/env python3
"""Check complete native/Resident ABBA logs before reporting measured latency."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def records(text, mode, tokens, rc):
    require(rc == 0, "process failed")
    require(text.count("RESIDENT_GGML_PAIR_PASS") == 1, "missing/duplicate PASS")
    rows = [json.loads(line[5:]) for line in text.splitlines() if line.startswith("PAIR ")]
    require(len(rows) == 4, "need one warmup and three measured calls")
    for trial, row in enumerate(rows):
        require(row["mode"] == mode and row["tokens"] == tokens and row["trial"] == trial,
                "wrong identity/order")
        require(row["warmup"] is (trial == 0), "wrong warmup flag")
        require(row["accepted"] is True and row["errors"] == 0, "incorrect computation")
        require(type(row["ns"]) is int and row["ns"] > 0, "invalid latency")
        require(row["portal_calls"] == row["portal_completed"] == int(mode == "resident"),
                "Resident not actually completed or wrong path")
    return rows


def analyze(directory, bundle):
    manifest_raw = (directory / "manifest.json").read_bytes()
    require(manifest_raw == (bundle / "manifest.json").read_bytes(), "manifest changed")
    require((directory / "SHA256SUMS").read_bytes() == (bundle / "SHA256SUMS").read_bytes(),
            "bundle checksum list changed")
    manifest = json.loads(manifest_raw)
    require(hashlib.sha256((bundle / "resident-ggml-pair").read_bytes()).hexdigest() ==
            manifest["elf_sha256"], "ELF hash mismatch")
    require((directory / "status").read_text().strip() == "COMPLETE", "run incomplete")
    require("RESIDENT_INFO abi=1 lanes=4 vlen=1024 max_tokens=256" in
            (directory / "probe.log").read_text(), "device not admitted")
    for name in ("board_id.txt", "module_sha256.txt", "uname.txt"):
        require(bool((directory / name).read_text().strip()), "missing board identity")
    results = []
    for tokens in (65, 128, 137):
        groups = {"native": [], "resident": []}
        cold = {"native": [], "resident": []}
        process_means = {"native": [], "resident": []}
        for index, mode in enumerate(("native", "resident", "resident", "native")):
            stem = directory / f"t{tokens}_{index}_{mode}"
            rows = records(stem.with_suffix(".log").read_text(), mode, tokens,
                           int(stem.with_suffix(".rc").read_text()))
            require(all(r["fflags"] == manifest["expected_flags"][str(tokens)] for r in rows),
                    "wrong exception flags")
            cold[mode].append(rows[0]["ns"])
            values = [r["ns"] for r in rows[1:]]
            groups[mode].extend(values)
            process_means[mode].append(statistics.mean(values))
        native = statistics.mean(groups["native"])
        resident = statistics.mean(groups["resident"])
        results.append(dict(tokens=tokens, native_mean_ns=native, resident_mean_ns=resident,
            speedup=native / resident, latency_reduction_percent=100 * (1 - resident / native),
            samples_ns=groups, first_call_ns=cold, process_means_ns=process_means,
            native_drift_percent=100 * (max(process_means['native']) / min(process_means['native']) - 1),
            resident_drift_percent=100 * (max(process_means['resident']) / min(process_means['resident']) - 1)))
    return dict(state="FUNCTION_AND_PATH_PASS", scope=manifest["scope"],
                board_id=(directory / "board_id.txt").read_text().strip(),
                elf_sha256=manifest["elf_sha256"], results=results)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results", type=Path)
    p.add_argument("--bundle", type=Path, required=True)
    args = p.parse_args()
    try:
        print(json.dumps(analyze(args.results, args.bundle), indent=2))
    except (ValueError, KeyError, OSError) as error:
        p.exit(1, f"REJECTED: {error}\n")
