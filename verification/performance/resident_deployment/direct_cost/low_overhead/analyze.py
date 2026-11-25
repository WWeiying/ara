#!/usr/bin/env python3
"""Validate a frozen direct-U SDK pair receipt. No GGML/model inference claim."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

SDK_COMMIT = "4a7361f51ba5447a616217dad1c8e72e3ee2b45b"
SCOPE = "complete-sdk-attention"
TOKENS = (65, 128, 137)
ORDER = (0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0)
MODES = ("native-akv", "resident")
# Independent, already-qualified Qwen3 oracle: little-endian F32 output bits.
GOLDENS = {65: (3, "cbf34e663f3add32"), 128: (3, "07758780b7043d8a"),
           137: (3, "3a3569a8f1462877")}
SHA = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def parse_json(text):
    def invalid(value):
        raise ValueError("nonfinite JSON constant: " + value)
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integer(value, low=0):
    return type(value) is int and value >= low


def equals(record, expected, label):
    for key, value in expected.items():
        actual = record.get(key)
        require(type(actual) is type(value) and actual == value, label + ": " + key)


def package(root):
    inventory = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        require(match is not None, "malformed package checksum")
        digest, name = match.groups()
        require(name not in inventory and name != "SHA256SUMS", "duplicate/self package checksum")
        require(sha(root / name) == digest, "package hash mismatch: " + name)
        inventory[name] = digest
    require({"resident-direct-pair", "run_board.sh", "analyze.py", "README.md", "source-pins.json", "goldens.json"}
            <= inventory.keys(), "incomplete frozen package")
    pins = parse_json((root / "source-pins.json").read_text())
    require(type(pins) is dict and pins, "missing source pins")
    require(all(type(k) is str and type(v) is str and SHA.fullmatch(v) for k, v in pins.items()),
            "invalid source pin digest")
    for name in ("run_board.sh", "analyze.py", "README.md", "goldens.json"):
        require(any(Path(path).name == name and digest == inventory[name] for path, digest in pins.items()),
                "package/source pin disagreement: " + name)
    for suffix in ("/direct_cost/low_overhead/bench.cpp", "/direct_cost/build_low_overhead.py", "/direct/direct_client.c",
                   "/direct/direct_client.h", "/direct/direct_uapi.h", "/software/akv/src/akv_v2_native_riscv.c",
                   "/software/akv/src/akv_v2_attention_rvv.S", "/resident_attention/qk.S", "/resident_attention/pv.S"):
        require(any(path.endswith(suffix) for path in pins), "missing source pin: " + suffix)
    return inventory


def records(root, label, tokens, probe):
    require((root / (label + ".rc")).read_text().strip() == "0", label + ": process failed")
    lines = (root / (label + ".log")).read_text().splitlines()
    expected_tags = ["DIRECT_SETUP"] + ([] if probe else ["DIRECT_SAMPLE"] * 14) + ["DIRECT_DONE"]
    marker = "AKV_DIRECT_PROBE_PASS" if probe else "AKV_DIRECT_PAIR_PASS"
    require(len(lines) == len(expected_tags) + 1 and lines[-1] == marker, label + ": incomplete/extra log")
    values = []
    for line, tag in zip(lines, expected_tags):
        require(line.startswith(tag + " "), label + ": record order/tag")
        value = parse_json(line[len(tag) + 1:])
        require(type(value) is dict, label + ": non-object record")
        values.append(value)
    setup, done = values[0], values[-1]
    equals(setup, dict(scope=SCOPE, sdk_commit=SDK_COMMIT, tokens=tokens, probe=probe,
                       abi=1, features=7, online_cpus=1, gate_signature="0x414b5601", hart=0,
                       acquires=1, vlenb=128, finite_prechecks=1, mlockall=True, stack_prefault_bytes=262144,
                       vector_first_use=True, fp_initialized=True, fixture_preflights=2, errors=0), label + " setup")
    require(integer(setup.get("lease_generation"), 1) and integer(setup.get("owner_tid"), 1),
            label + ": missing lease identity")
    equals(done, dict(tokens=tokens, acquires=1, releases=1, hot_client_calls=0, errors=0), label + " done")
    if probe:
        return []
    samples = values[1:-1]
    trials = [0, 0]
    tiles = (tokens + 63) // 64
    for sequence, (arm, sample) in enumerate(zip(ORDER, samples)):
        trial = trials[arm]
        trials[arm] += 1
        equals(sample, dict(sequence=sequence, mode=MODES[arm], tokens=tokens, trial=trial, cold=trial == 0,
                            status=0, completed_groups=1, sdk_calls=1, info_calls=0,
                            native_qk=0 if arm else tiles, native_pv=0 if arm else tiles,
                            resident_qk=tiles if arm else 0, resident_pv=tiles if arm else 0,
                            incoming_fflags=8, fflags=GOLDENS[tokens][0] | 8, vcsr=0, vstart=0,
                            hot_client_calls=0, output_fnv64=GOLDENS[tokens][1], errors=0),
               label + " sample " + str(sequence))
        require(integer(sample.get("ns"), 1) and sample["ns"] < 2**63, label + ": invalid duration")
    return samples


def analyze(root):
    root = Path(root)
    require((root / "status").read_text().strip() == "COMPLETE", "board collection not COMPLETE")
    inventory = package(root)
    platform = parse_json((root / "platform.json").read_text())
    require(type(platform) is dict, "non-object platform receipt")
    equals(platform, dict(schema=1, operator_accepted=True, machine="riscv64", online_cpus="0"), "platform")
    require(type(platform.get("board_id")) is str and re.fullmatch(r"[A-Za-z0-9._-]+", platform["board_id"]),
            "missing board identity")
    for key in ("bitstream_sha256", "kernel_sha256"):
        require(type(platform.get(key)) is str and SHA.fullmatch(platform[key]), "missing image attestation: " + key)
    records(root, "probe", 0, True)
    rows = []
    for tokens in TOKENS:
        samples = records(root, "t" + str(tokens), tokens, False)
        row = {"tokens": tokens, "heads": 2, "dimension": 128}
        medians = []
        for mode in MODES:
            selected = [s for s in samples if s["mode"] == mode]
            warm = [s["ns"] for s in selected if not s["cold"]]
            median = statistics.median(warm)
            medians.append(median)
            row[mode] = dict(cold_ns=selected[0]["ns"], warm_samples=len(warm), warm_median_ns=median,
                             warm_mean_ns=statistics.mean(warm), warm_min_ns=min(warm), warm_max_ns=max(warm),
                             last_over_first_warm=warm[-1] / warm[0])
        ratios = []
        for start in (2, 6, 10):
            a, b, c, d = samples[start:start + 4]
            ratios.append((a["ns"] + d["ns"]) / (b["ns"] + c["ns"]))
        row.update(native_akv_over_resident=medians[0] / medians[1],
                   resident_latency_reduction=1 - medians[1] / medians[0], abba_ratios=ratios)
        rows.append(row)
    return dict(state="VALIDATED_DIRECT_SDK_SAMPLES", scope=SCOPE, sdk_commit=SDK_COMMIT,
                sample_count=42, warm_sample_count=36, rows=rows, platform=platform,
                elf_sha256=inventory["resident-direct-pair"], source_pins_sha256=inventory["source-pins.json"],
                complete_ggml_graph=False, model_performance_claim=False, performance_acceptance=False,
                image_identity="operator attestation plus runtime gate/SDK capability checks, not bitstream readback",
                timing="CLOCK_MONOTONIC_RAW; symmetric leaf/INFO/entry witness overhead included; first-arm cold, not cache-cold")


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps(dict(state="FAIL", error=str(exc))))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

