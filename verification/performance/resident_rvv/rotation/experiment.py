#!/usr/bin/env python3
"""One frozen-software control: auto versus auto with rotating PV registers."""
import argparse
from collections import Counter
import csv
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parents[1] / "akv_pair_eval"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


accepted = load(PRIMARY / "integration/check.py", "rotation_accepted_checker")
contract = accepted.contract
require, sha = contract.require, contract.sha
BASE = contract.OUT / "akv_pair_integration_build_20261107_01"
SCHEMA = "resident-pv-register-control-v1"
SYMBOL = "akv_experimental_pv_f16_pair"
OWN = ("experiment.py", "main.c", "pv_rotation.S", "test_experiment.py", "README.md")


def baseline():
    meta = accepted.verify_build(BASE)
    pins = json.loads((BASE / "source-pins.json").read_text())
    pins.update(meta["artifacts"])
    pins[str(BASE / "build.json")] = sha(BASE / "build.json")
    pins.update({str(HERE / name): sha(HERE / name) for name in OWN})
    contract.verify(pins)
    return meta, pins


def recipes(output):
    cmds = json.loads((BASE / "commands.json").read_text())
    result = []
    for label, source, obj, template in (
        ("compile-main", HERE / "main.c", "main", "compile-00_main"),
        ("compile-rotation", HERE / "pv_rotation.S", "rotation", "compile-14_akv_v2_attention_rvv")):
        original = next(c for c in cmds if c["label"] == template)
        argv = list(original["argv"])
        for flag, value in (("-c", source), ("-o", output / (obj+".o")),
                            ("-MF", output / (obj+".d"))):
            argv[argv.index(flag)+1] = str(value)
        result.append(dict(label=label, argv=argv))
    link = list(next(c for c in cmds if c["label"] == "link")["argv"])
    link[link.index(str(BASE / "00_main.o"))] = str(output / "main.o")
    link[link.index("-Wl,-Map="+str(BASE / "link.map"))] = "-Wl,-Map="+str(output / "link.map")
    link[link.index("-o")+1] = str(output / "rotation.elf")
    link[link.index("-Wl,--gc-sections"):link.index("-Wl,--gc-sections")] = [
        str(output / "rotation.o"), "-Wl,--wrap="+SYMBOL,
        # Preserve the accepted native ELF identity gate even though both
        # measured arms now call auto. Execution is checked in vector_work.
        "-Wl,--undefined=akv_attention_execute_v2_native"]
    result.append(dict(label="link", argv=link))
    for label in ("disassembly", "segments"):
        argv = [str(output / "rotation.elf") if x == str(BASE / contract.ELF_NAME) else x
                for x in next(c for c in cmds if c["label"] == label)["argv"]]
        result.append(dict(label=label, argv=argv))
    return result


def build(output):
    output = output.resolve()
    require(output.parent == contract.OUT.resolve() and not output.exists(), "Fresh owned output required")
    meta, pins = baseline()
    output.mkdir()
    env = dict(PATH="/usr/bin:/bin", HOME=os.environ.get("HOME", "/home/wangwy"),
               LC_ALL="C", PYTHONDONTWRITEBYTECODE="1")
    commands = []
    for command in recipes(output):
        contract.verify(pins)
        proc = subprocess.run(command["argv"], cwd=output, env=env, text=True,
                              capture_output=True, timeout=180)
        log = output / (command["label"]+".log")
        log.write_text(proc.stdout+proc.stderr)
        commands.append(dict(command, returncode=proc.returncode, cwd=str(output), env=env, log=str(log)))
        (output / "commands.json").write_text(json.dumps(commands, indent=2)+"\n")
        require(proc.returncode == 0, "Compile/link failed: "+str(log))
    old, _ = contract.sealed_modules()
    for dep in output.glob("*.d"):
        for path in old.dependency_inputs(dep):
            value = sha(path)
            require(str(path) not in pins or pins[str(path)] == value, "Compiler input drift")
            pins[str(path)] = value
    contract.verify(pins)
    pinfile = output / "source-pins.json"
    pinfile.write_text(json.dumps(pins, indent=2, sort_keys=True)+"\n")
    result = dict(schema=SCHEMA, state="BUILT_NOT_EXECUTED", hardware_changed=False,
        baseline_build=str(BASE), baseline_build_sha256=sha(BASE / "build.json"),
        sdk_new=meta["sdk_new"], image_contract=meta["image_contract"], shape=meta["shape"],
        golden=meta["golden"], memory_expected=meta["memory_expected"],
        elf=str(output / "rotation.elf"), elf_sha256=sha(output / "rotation.elf"),
        source_pins_sha256=sha(pinfile),
        diagnostic_only=True, baseline_arm="native_auto", candidate_arm="native_auto + PV v8/v10 rotation",
        objects_reused=[x for x in meta["objects"] if Path(x).name != "00_main.o"],
        objects_recompiled=[str(output / "main.o"), str(output / "rotation.o")],
        artifacts={str(p): sha(p) for p in output.rglob("*") if p.is_file()})
    (output / "build.json").write_text(json.dumps(result, indent=2)+"\n")
    verify_build(output)
    return result


def verify_build(output):
    output = Path(output).resolve()
    base, mandatory = baseline()
    m = json.loads((output / "build.json").read_text())
    require(m["schema"] == SCHEMA and m["state"] == "BUILT_NOT_EXECUTED" and
            m["baseline_build"] == str(BASE) and m["baseline_build_sha256"] == sha(BASE / "build.json"),
            "Not the reviewed control build")
    for key in ("sdk_new", "image_contract", "shape", "golden", "memory_expected"):
        require(m[key] == base[key], "Baseline contract drift: "+key)
    require(m["elf"] == str(output / "rotation.elf") and sha(m["elf"]) == m["elf_sha256"], "ELF drift")
    pinfile = output / "source-pins.json"
    require(sha(pinfile) == m["source_pins_sha256"], "Pin inventory drift")
    pins = json.loads(pinfile.read_text())
    require(all(pins.get(k) == v for k, v in mandatory.items()), "Missing mandatory pin")
    contract.verify(pins)
    contract.verify(m["artifacts"])
    actual = {str(p): sha(p) for p in output.rglob("*") if p.is_file() and p.name != "build.json"}
    require(actual == m["artifacts"], "Incomplete/extra build artifact")
    commands = json.loads((output / "commands.json").read_text())
    require([dict(label=c["label"], argv=c["argv"]) for c in commands] == recipes(output) and
            all(c["returncode"] == 0 and c["cwd"] == str(output) for c in commands),
            "Unreviewed build recipe")
    old, _ = contract.sealed_modules()
    for dep in output.glob("*.d"):
        require(all(pins.get(str(p)) == sha(p) for p in old.dependency_inputs(dep)), "Unpinned compiler input")
    accepted.check_elf(m["elf"])
    text = (output / "disassembly.log").read_text()
    require("<__wrap_"+SYMBOL+">:" in text and "<"+SYMBOL+">:" in text and
            "0205355b" in text, "Missing real baseline/rotation implementations")
    return m


def expected_signatures():
    values = []
    for arm in (0, 1, 1, 0):
        for count in (64, 64, 9):
            values += [0x0205745B]*32
            values += [0x0205355B if arm and row % 2 else 0x0205345B for row in range(count)]
    return values


def vector_work(path):
    actual, configs, previous = [], 0, -1
    with Path(path).open() as stream:
        for row in csv.DictReader(stream):
            require(None not in row and all(v is not None for v in row.values()), "Malformed vector row")
            cycle = int(row["cycle"])
            require(previous <= cycle and (row["nr_lanes"], row["vlen_bits"]) == ("4", "1024"),
                    "Vector configuration/time mismatch")
            previous = cycle
            if row["event"] == "config":
                require(configs == 0 and not actual and cycle == 0, "Unexpected vector epoch")
                configs += 1
            require(row["event"] != "reset", "Unexpected reset epoch")
            if row["event"] != "alloc":
                continue
            require(configs == 1, "Allocation before configuration")
            insn = int(row["insn"], 16)
            if insn & 0x707F in (0x305B, 0x705B):
                actual.append(insn)
    require(configs == 1 and actual == expected_signatures(), "Replay identity/order/count mismatch")
    return dict(replay_commands=len(actual), rotated_v10_commands=actual.count(0x0205355B),
                trace_sha256=sha(path), ordered_signatures_checked=True)


def hardware_work(log, original):
    # Same resident work in all four calls; only the row destination alternates.
    one = original.expected_commands()[1046:1283]
    require(len(one) == 237 and one[0]["v2_full"] == one[-1]["release"] == 1,
            "Accepted auto command template changed")
    expected, rows, summaries, totals = one*4, [], [], Counter()
    for line in log.splitlines():
        if line.startswith("[AKV_PERF] "):
            row = original.parse_fields(line[len("[AKV_PERF] "):], original.PERF_FIELDS)
            i = len(rows)
            require(i < len(expected) and row["seq"] == i+1 and
                    all(row[k] == v for k, v in expected[i].items()), "Wrong resident command work")
            require(row["success"] == 1 and row["busy_cycles"] > 0 and
                    all(row[k] == 0 for k in ("fault", "validation_fault", "validation_error",
                                             "read_fault", "v2_rejected")), "Resident command failed")
            require(row["context_ready"] == int(row["command"] != 3), "Wrong context lifecycle")
            require(row["read_payload_bytes"] == row["q_external_bytes"] + row["kv_external_bytes"] +
                    64*row["v2_full"], "Wrong external byte accounting")
            for k in original.SUMMARY_FIELDS - {"records", "success_records", "fault_records", "validation_fault_records"}:
                totals[k] = max(totals[k], row[k]) if k == "read_outstanding_max" else totals[k]+row[k]
            rows.append(row)
        elif line.startswith("[AKV_PERF_SUMMARY] "):
            summaries.append(original.parse_fields(line[len("[AKV_PERF_SUMMARY] "):], original.SUMMARY_FIELDS))
    require(len(rows) == 948, "Incomplete four native auto calls")
    require(summaries == [dict(totals, records=948, success_records=948, fault_records=0,
                              validation_fault_records=0)], "Inconsistent resident summary")
    return dict(commands=948, per_call_commands=[237]*4,
                busy_cycles=[sum(x["busy_cycles"] for x in rows[i:i+237]) for i in range(0, 948, 237)],
                totals=dict(totals))


def check_run(log_path, build_dir):
    m = verify_build(build_dir)
    _, original = contract.sealed_modules()
    text = Path(log_path).read_text()
    measured = original.check_log(text, Path(m["golden"]["captured"]).read_bytes(),
                                  Path(m["golden"]["native_tile64"]).read_bytes(), m["memory_expected"])
    work = hardware_work(text, original)
    require(all(a <= b for a, b in zip(work["busy_cycles"], measured["measured_total_cycles"])),
            "Resident busy time exceeds full call")
    measured.update(state="PASS", baseline_arm=m["baseline_arm"], candidate_arm=m["candidate_arm"],
                    work=work, diagnostic_only=True, sdk_new=m["sdk_new"],
                    elf_sha256=m["elf_sha256"], log_sha256=sha(log_path))
    return measured


def check_vector_workcounts(path, build_dir):
    verify_build(build_dir)
    return vector_work(path)


def run(args):
    owner = contract.load(PRIMARY / "run.py", "rotation_private_owner")
    # Reuse the process/image/protocol owner, not the old experiment's work assumptions.
    owner.load_checker = lambda kind: (HERE / "experiment.py", sys.modules[__name__])
    return owner.run(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("build", "run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--soc-build", type=Path, default=contract.OUT / "chain_soc_admitted_20261107_01")
    parser.add_argument("--timeout", type=int, default=10800)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    args.kind = "qwen3_abba"
    if args.action == "build":
        result = build(args.output)
        print(json.dumps({k: result[k] for k in ("state", "elf", "elf_sha256")}))
    else:
        require(args.build is not None, "--build is required")
        def interrupted(sig, _frame):
            raise InterruptedError("Signal "+str(sig))
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, interrupted)
        run(args)
