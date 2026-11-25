#!/usr/bin/env python3
"""Strict three-arm board comparison; never treats missing runs as passing."""
import argparse
import json
from pathlib import Path
import statistics


def analyze(root):
    assert (root / "status").read_text().strip() == "COMPLETE"
    rows, checks = [], 0
    for kv in (1, 4):
        for token in ("65", "128", "137", "stream"):
            samples = {mode: [] for mode in ("native", "session", "views")}
            for index, mode in enumerate(("native", "session", "views", "views", "session", "native")):
                stem = root / f"k{kv}_t{token}_{index}_{mode}"
                assert stem.with_suffix(".rc").read_text().strip() == "0"
                text = stem.with_suffix(".log").read_text()
                assert text.count("RESIDENT_VIEW_PAIR_PASS") == 1
                records = [json.loads(line.removeprefix("VIEW_PAIR ")) for line in text.splitlines() if line.startswith("VIEW_PAIR ")]
                assert len(records) == 7
                for trial, r in enumerate(records):
                    expected = (65, 128, 137)[trial % 3] if token == "stream" else int(token)
                    calls = 0 if mode == "native" else 1 if mode == "views" else kv
                    assert r["trial"] == trial and r["tokens"] == expected and r["kv_heads"] == kv
                    assert r["mode"] == mode and r["stream"] == (token == "stream")
                    assert r["warmup"] == (trial == 0) and not r["diagnostic"] and not r["errors"]
                    assert r["ns"] > 0 and r["calls"] == r["completed"] == calls
                    assert r["groups"] == (0 if mode == "native" else kv)
                    assert r["registrations"] == (1 if mode == "views" and not trial else 0)
                    checks += 1
                    if trial: samples[mode].append(r["ns"])
            row = dict(kv_heads=kv, tokens=token, samples_per_mode=12)
            for mode, values in samples.items():
                row[mode + "_mean_ms"] = statistics.mean(values) / 1e6
                row[mode + "_min_ms"] = min(values) / 1e6
                row[mode + "_max_ms"] = max(values) / 1e6
            row["native_over_views"] = row["native_mean_ms"] / row["views_mean_ms"]
            row["session_over_views"] = row["session_mean_ms"] / row["views_mean_ms"]
            rows.append(row)
    return dict(state="CHECKED", checked_calls=checks, board_measured=True, rows=rows,
                scope="GGML decode attention, captured real head data replicated for layout/batch testing; not whole-model speedup")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results", type=Path)
    a = p.parse_args()
    print(json.dumps(analyze(a.results), indent=2))
