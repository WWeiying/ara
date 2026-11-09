#!/usr/bin/env python3
"""Recover exact PV operands from accepted RTL, verify each FMA independently."""
import argparse
from collections import defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("resident_pv_reference", HERE.parent / "ordered_reference.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with path.open() as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)),
                "Ambiguous CSV schema")
        for row in reader:
            require(None not in row and None not in row.values(), "Malformed CSV row")
            yield row


def lane_words(rows, lane, vd):
    selected = [r for r in rows if int(r["lane"]) == lane]
    require(len(selected) == 8, "Expected eight accepted VRF writes per lane")
    selected.sort(key=lambda r: int(r["addr"]))
    require([int(r["addr"]) for r in selected] == list(range(vd * 4, vd * 4 + 8)),
            "Wrong VRF address or duplicate write")
    require(all(int(r["be"], 16) == 255 and int(r["vd"]) == vd and
                int(r["eew"]) == 1 and int(r["vl"]) == 128 and int(r["vstart"]) == 0
                for r in selected), "Unexpected VRF geometry")
    return [(int(r["wdata"], 16) >> (16 * part)) & 65535 for r in selected for part in range(4)]


def converted_coefficients(retired, tile):
    converted = [[], []]
    for row in retired:
        if tile["begin"] <= int(row["cycle"]) < tile["end"]:
            insn = int(row["insn"], 16)
            if insn in (0x44007053, 0x4400F0D3):
                head = (insn >> 7) & 31
                require(int(row["rd"]) == head and int(row["trap"]) == 0,
                        "Unexpected conversion retirement")
                bits = int(row["rd_wdata"], 16)
                require(bits >> 16 == (1 << 48) - 1, "Missing FP16 NaN boxing")
                converted[head].append((int(row["cycle"]), bits & 65535))
    require(all(len(row) == tile["rows"] + 1 for row in converted), "Missing scales/coefficients")
    for token, group in enumerate(tile["groups"]):
        require(all(converted[h][token + 1][0] < group[0]["alloc"] for h in range(2)),
                "Coefficient retired after its replay")
        if token + 1 < tile["rows"]:
            require(all(converted[h][token + 2][0] > group[h + 1]["alloc"] for h in range(2)),
                    "Coefficient pairing crossed token")
    return [[bits for _, bits in row[1:]] for row in converted]


def extract(attribution, capture):
    summary = json.loads(attribution.read_text())
    audit = summary["acceptance"]
    require(summary["state"] == "CONTROL_LIFETIMES_ANALYZED" and
            audit["state"] == "CONTROL_INDEPENDENT_AUDIT_PASS", "Unaccepted control")
    raw_path = Path(audit["raw_receipt"])
    require(sha(raw_path) == audit["raw_receipt_sha256"], "Run receipt drift")
    run = json.loads(raw_path.read_text())
    require(run["state"] == "PASS", "Original run did not pass")
    commit = raw_path.parent / "work/commit.csv"
    vector = raw_path.parent / "work/vector_trace.csv"
    checked = {str(attribution): sha(attribution), str(raw_path): sha(raw_path)}
    for path in (commit, vector):
        digest = sha(path)
        require(run["artifacts"][str(path)] == digest, "Trace drift")
        checked[str(path)] = digest
    require(checked[str(vector)] == audit["vector_command_work"]["trace_sha256"],
            "Independent trace identity mismatch")
    require(sha(capture) == "64ae74fda7068fb06023c0c5333ac8227804067797cf6d2b9b0d623b0159b369",
            "Not the accepted Qwen3 captured V tensor")
    captured = struct.unpack("<32768H", capture.read_bytes())
    checked[str(capture)] = sha(capture)
    retired = [r for r in read_csv(commit) if r["event"] == "retire"]
    writes, allocs = defaultdict(list), []
    for row in read_csv(vector):
        if row["event"] == "write":
            writes[int(row["arch_seq"])].append(row)
        elif row["event"] == "alloc":
            allocs.append(row)
    trial = summary["trials"][0]
    require(trial["trial"] == 0 and trial["arm"] == 0 and
            [t["rows"] for t in trial["pv_tiles"]] == [64, 64, 9], "Wrong model tile selection")
    oracle = reference.OrderedReference()
    cases, token_start, checked_fmas = [], 0, 0
    for tile_index, tile in enumerate(trial["pv_tiles"]):
        coefficients = converted_coefficients(retired, tile)
        scale_instructions = [r for r in allocs if tile["begin"] <= int(r["cycle"]) < tile["end"] and
                              int(r["insn"], 16) in (0x92005057, 0x9220D157)]
        require([int(r["insn"], 16) for r in scale_instructions] == [0x92005057, 0x9220D157],
                "Missing rescaled seeds")
        for lane in range(4):
            seeds = [lane_words(writes[int(r["arch_seq"])], lane, 2*h)
                     for h, r in enumerate(scale_instructions)]
            accum = [row[:] for row in seeds]
            values, flags = [], 0
            for token, group in enumerate(tile["groups"]):
                value = lane_words(writes[group[0]["seq"]], lane, 8)
                expected_v = [captured[(token_start+token)*128 + 16*w + lane + part]
                              for w in range(8) for part in (0, 8, 4, 12)]
                require(value == expected_v, "Resident V replay differs from model capture/shuffle")
                values.append(value)
                for h in range(2):
                    recorded = lane_words(writes[group[h+1]["seq"]], lane, 2*h)
                    for elem in range(32):
                        result, ex = oracle.sf.evaluate("fma", 16, 16, 0,
                            coefficients[h][token], value[elem], accum[h][elem])
                        require(result == recorded[elem],
                                f"SoftFloat FMA mismatch tile={tile_index} lane={lane} "
                                f"token={token} head={h} elem={elem}")
                        accum[h][elem] = result
                        flags |= ex
                        checked_fmas += 1
            cases.append(dict(name=f"qwen3_tile{tile_index}_lane{lane}", heads=2,
                              elements=32, tokens=tile["rows"], rm=0, seed=seeds,
                              coefficient=coefficients, values=values, expected=accum, flags=flags))
        token_start += tile["rows"]
    require(checked_fmas == 35072 and len(cases) == 12, "Incomplete real-model PV corpus")
    checked.update(oracle.identity())
    checked[str(Path(__file__).resolve())] = sha(__file__)
    return dict(state="REAL_PV_OPERANDS_INDEPENDENTLY_CHECKED", cases=cases, artifacts=checked,
                checked_scalar_fmas=checked_fmas,
                scope="Three real-model D128/H2 tiles, all four lanes; prepared operands, not SoC acceptance",
                flags_scope="Only ordered FP16 FMAs; excludes already-completed scaling/conversion flags")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--attribution", required=True, type=Path)
    parser.add_argument("--capture-values", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = extract(args.attribution.resolve(), args.capture_values.resolve())
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(state=result["state"], cases=len(result["cases"]),
                          checked_scalar_fmas=result["checked_scalar_fmas"])))
