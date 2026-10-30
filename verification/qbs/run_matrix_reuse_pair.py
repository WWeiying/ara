#!/usr/bin/env python3
"""Equal-output M4/M8 VCS engine attribution using captured model tensors.

Command-engine cycles only: no CPU quantization, cache/DDR or model latency.
Run this worker directly; all artifacts are kept in a new output directory.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal

from run_half_scale_soc import atomic_json, digest, hashes, run_command

ROOT = Path(__file__).resolve().parents[2]
SLICES = (("m4a", 0, 4, 0, 32), ("m4b", 4, 4, 0, 32),
          ("m8a", 0, 8, 0, 16), ("m8b", 0, 8, 16, 16))


def checked_log(log, m, n, blocks):
    if re.search(r"Fatal:|Error:|UVM_ERROR|UVM_FATAL", log):
        raise ValueError("Simulator error")
    if log.count("QBS engine PASS: 1 functional cases") != 1:
        raise ValueError("Missing unique terminal PASS")
    rows = re.findall(r"QBS end-to-end case 0 PASS profile=\d+ M=(\d+) N=(\d+) Kb=(\d+) layouts=2/([23]) cycles=(\d+)", log)
    if len(rows) != 1 or tuple(map(int, rows[0][:4])) != (m, n, blocks, 3 if m == 8 else 2):
        raise ValueError("Wrong executed geometry")
    result = {"cycles": int(rows[0][4])}
    for label, key in (("phase", "phases"), ("traffic", "traffic"), ("FP probe", "fp")):
        matches = re.findall(r"QBS " + label + r" case=0 ([^\n]+)", log)
        if len(matches) != 1:
            raise ValueError("Missing attribution: " + label)
        result[key] = {name: int(value) for name, value in re.findall(r"(\w+)=(\d+)", matches[0])}
    if sum(result["phases"].values()) != result["cycles"] + 1:
        raise ValueError("Phase accounting differs")
    return result


def outputs(text, input_start, m, output_start, n):
    stride = 16 if m == 8 else 32
    rows = re.findall(r"^O (\d+) ([0-9a-fA-F]{8})$", text, re.M)
    expected = {row * stride + col for row in range(m) for col in range(n)}
    if len(rows) != len(expected) or {int(index) for index, _ in rows} != expected:
        raise ValueError("Wrong vector output coverage")
    return {(input_start + int(index) // stride, output_start + int(index) % stride): int(value, 16)
            for index, value in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = {"state": "preparing", "pid": os.getpid(), "scope": __doc__, "cases": {}}
    def save():
        atomic_json(out / "status.json", state)
    def interrupted(signum, _frame):
        raise InterruptedError(f"signal {signum}")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    def run(argv, log, timeout):
        state.update(command=list(map(str, argv)), log=str(log))
        def started(pid):
            state["child_pid"] = pid
            save()
        try:
            rc = run_command(list(map(str, argv)), log, timeout, os.environ.copy(), started)
            if rc != 0:
                raise RuntimeError(f"Command failed rc={rc}: {log}")
        finally:
            state["child_pid"] = None
            save()
    save()
    try:
        source_roots = [ROOT / p for p in ("hardware/src/vlsu/qbs", "hardware/include",
            "hardware/deps/common_cells", "hardware/deps/axi", "hardware/deps/fpnew",
            "hardware/deps/tech_cells_generic", "software/qbs/include", "apps/common")]
        sources = {path for directory in source_roots for path in directory.rglob("*")
                   if path.is_file() and path.suffix in (".sv", ".svh", ".h")}
        sources.update(ROOT / "verification/qbs" / name for name in
                       ("qbs_engine_tb.sv", "qbs_command_vectors.c", "qbs_ref.c", "qbs_ref.h",
                        "Makefile", "run_matrix_reuse_pair.py", "run_half_scale_soc.py"))
        pinned = hashes(sources)
        captures = {}
        for profile, op in (("q4_K", "attn_q"), ("q6_K", "ffn_down")):
            src = args.capture_root / "prefill/operators" / ("blk_0_" + op + "_weight")
            dst = out / "inputs" / profile
            dst.mkdir(parents=True)
            for name in (f"weight_{profile}.bin", f"weight_{profile}.json", "activation_f32.bin",
                         "activation_f32.json", "output_f32.bin", "output_f32.json", "operator.json"):
                before = digest(src / name)
                shutil.copyfile(src / name, dst / name)
                if digest(dst / name) != before or digest(src / name) != before:
                    raise RuntimeError("Capture drift")
                pinned[str(dst / name)] = before
            shape = json.loads((dst / f"weight_{profile}.json").read_text())["shape"]
            activation_shape = json.loads((dst / "activation_f32.json").read_text())["shape"]
            if activation_shape[0] != shape[0] or activation_shape[1] < 8 or shape[1] < 32:
                raise ValueError("Insufficient real capture")
            captures[profile] = (dst, shape[0], shape[1])
        state["sources_and_inputs"] = pinned
        def unchanged():
            if any(digest(Path(path)) != sha for path, sha in pinned.items()):
                raise RuntimeError("Input/source/image drift")
        state["state"] = "building"
        run(["make", "-C", ROOT / "verification/qbs", "rtl-engine-compile",
             f"RTL_ENGINE_BUILD={out / 'build'}"], out / "build.log", 900)
        generator = out / "qbs_command_vectors"
        run(["cc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-ffp-contract=off", "-frounding-math", "-I" + str(ROOT / "apps/common"),
             ROOT / "verification/qbs/qbs_command_vectors.c", ROOT / "verification/qbs/qbs_ref.c",
             "-lm", "-o", generator], out / "generator-build.log", 120)
        simv = out / "build/simv"
        libraries = list((out / "build/simv.daidir").rglob("*.so"))
        if not libraries:
            raise ValueError("No simulator libraries")
        pinned.update(hashes([simv, generator, *libraries]))
        unchanged()
        state["state"] = "running"
        for profile, (capture, k, full_n) in captures.items():
            golden = {"m4": {}, "m8": {}}
            flags = {"m4": 0, "m8": 0}
            for name, first_m, m, first_n, n in SLICES:
                unchanged()
                case = profile + "_" + name
                directory = out / case
                directory.mkdir()
                vector = directory / "input.vectors"
                run([generator, vector, "--real", profile, capture, full_n, k, first_m, m, first_n, n],
                    directory / "reference.log", 120)
                text = vector.read_text()
                group = name[:2]
                values = outputs(text, first_m, m, first_n, n)
                if golden[group].keys() & values.keys():
                    raise ValueError("Duplicate output slice")
                golden[group].update(values)
                flags[group] |= int(re.findall(r"^CMD .+ ([0-9a-fA-F]+)$", text, re.M)[0], 16)
                pinned[str(vector)] = digest(vector)
                run([simv, "-l", directory / "run.log", "+QBS_FUNCTIONAL_ONLY", "+QBS_FP_PROBE",
                     "+QBS_COMMAND_VECTOR_FILE=" + str(vector),
                     "+QBS_FP_TRACE=" + str(directory / "fp.csv"), "+QBS_FP_TRACE_END=1000"],
                    directory / "console.log", 240)
                checked = checked_log((directory / "run.log").read_text(), m, n, k // 256)
                checked["coordinates"] = [first_m, m, first_n, n, k]
                checked["vector_sha256"] = digest(vector)
                checked["log_sha256"] = digest(directory / "run.log")
                state["cases"][case] = checked
                save()
            if (golden["m4"] != golden["m8"] or len(golden["m4"]) != 256 or flags["m4"] != flags["m8"]):
                raise ValueError("Schedules differ in result bits/flags/work")
            state.setdefault("paired_outputs", {})[profile] = {"outputs": 256, "bit_exact": True, "fflags": flags["m4"]}
        unchanged()
        state["state"] = "PASS"
    except BaseException as error:
        state.update(state="FAIL", error=repr(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
