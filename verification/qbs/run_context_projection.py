#!/usr/bin/env python3
"""Measure full-N real Q8_0 projections on fresh VCS QBS engine RTL.

Pairs each output tile with DIRECT and context execution. Totals include the
first FILL and final RELEASE, but exclude CPU preparation/dispatch; the native
projection apps measure those separately. Response gaps are controlled supply
conditions, not calibrated DDR latency. Run as a foreground service worker.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import signal

from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import PATTERN, check_geometry, run_command

ROOT = Path(__file__).resolve().parents[2]
TILES = 28
M, N, KB = 4, 32, 28
ACT_BYTES = M * KB * 34
WEIGHT_BYTES = N * KB * 34
TILE_RE = (r"^QBS projection tile PASS tile=(\d+) access=(\d+) M=(\d+) "
           r"N=(\d+) Kb=(\d+) cycles=(\d+) payload=(\d+) saved=(\d+)$")
TOTAL_RE = (r"^QBS projection PASS tiles=(\d+) M=(\d+) N=(\d+) Kb=(\d+) "
            r"direct_cycles=(\d+) context_cycles=(\d+) direct_payload=(\d+) "
            r"context_payload=(\d+) saved=(\d+)$")


def vector_identity(text):
    if not text.startswith(f"QBSCMD1 {TILES}\n"):
        raise ValueError("Wrong vector count")
    blocks = re.findall(r"^CMD .*?^END$", text, re.M | re.S)
    if len(blocks) != TILES:
        raise ValueError("Incomplete vector file")
    def fingerprint(block, prefix):
        records = re.findall(r"^" + prefix + r" .*?$", block, re.M)
        if not records:
            raise ValueError("Missing vector records")
        return hashlib.sha256("\n".join(records).encode()).hexdigest()
    weights = [fingerprint(block, "W") for block in blocks]
    activations = [fingerprint(block, "A") for block in blocks]
    if len(set(weights)) != TILES:
        raise ValueError("Output tiles reuse identical weights")
    if len(set(activations)) != 1:
        raise ValueError("Activation changes within resident projection")
    return {"weight_tile_hashes": weights, "activation_hash": activations[0]}


def check_projection(text, vector, gap):
    if re.search(r"Fatal:|Error:|UVM_ERROR|UVM_FATAL", text):
        raise ValueError("Simulator failure")
    if text.count(f"QBS configuration response_gap={gap} context_suite=0\n") != 1:
        raise ValueError("Wrong supply configuration")
    if text.count(f"QBS engine PASS: {TILES} functional cases\n") != 1:
        raise ValueError("Missing unique engine PASS")
    direct = [tuple(map(int, row)) for row in re.findall(PATTERN, text)]
    context = [tuple(map(int, row)) for row in re.findall(TILE_RE, text, re.M)]
    if (len(direct) != TILES or len(context) != TILES or
            [row[0] for row in direct] != list(range(TILES)) or
            [row[0] for row in context] != list(range(TILES))):
        raise ValueError("Incomplete or duplicate command sequence")
    check_geometry(vector, direct)
    for index, (d, c) in enumerate(zip(direct, context)):
        access = 1 if index == 0 else 3 if index == TILES - 1 else 2
        saved = 0 if index == 0 else ACT_BYTES
        if (d[1:7] != (6, M, N, KB, 2, 2) or
                c[1:5] != (access, M, N, KB) or c[5] <= 0 or d[7] <= 0 or
                c[6:] != (16 + WEIGHT_BYTES + ACT_BYTES - saved, saved)):
            raise ValueError("Wrong geometry/lifecycle/traffic")
    totals = [tuple(map(int, row)) for row in re.findall(TOTAL_RE, text, re.M)]
    expected = (TILES, M, N * TILES, KB,
                sum(d[7] for d in direct), sum(c[5] for c in context),
                TILES * (16 + WEIGHT_BYTES + ACT_BYTES),
                sum(c[6] for c in context), (TILES - 1) * ACT_BYTES)
    if totals != [expected] or expected[6] - expected[7] != expected[8]:
        raise ValueError("Projection totals disagree")
    return {"direct": direct, "context": context, "totals": expected,
            "speedup": expected[4] / expected[5],
            "cycle_reduction": 1 - expected[5] / expected[4],
            "performance": "improved" if expected[5] < expected[4] else
                           "neutral" if expected[5] == expected[4] else "regressed",
            "deployment_approved": False,
            "identity": vector_identity(vector)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = args.capture.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    build = out / "engine"
    sources = set()
    for root in ("hardware/src/vlsu/qbs", "hardware/include", "hardware/deps/fpnew",
                 "hardware/deps/common_cells", "hardware/deps/axi", "hardware/deps/tech_cells_generic"):
        sources.update(p for p in (ROOT / root).rglob("*")
                       if p.is_file() and p.suffix in (".sv", ".svh"))
    sources.update(ROOT / "verification/qbs" / name for name in (
        "qbs_engine_tb.sv", "qbs_command_vectors.c", "qbs_ref.c", "qbs_ref.h",
        "Makefile", "run_context_projection.py", "run_tile_context_engine.py",
        "run_half_scale_soc.py"))
    sources.add(ROOT / "apps/common/qbs_abi.h")
    inputs = {capture / name for name in (
        "weight_q8_0.bin", "activation_f32.bin", "output_f32.bin")}
    pinned = hashes(sources | inputs)
    state = {"state": "preparing", "pid": os.getpid(), "cases": {},
             "scope": __doc__, "sources_and_inputs": pinned}
    def save():
        atomic_json(out / "status.json", state)
    def unchanged():
        if any(digest(Path(p)) != sha for p, sha in pinned.items()):
            raise RuntimeError("Source/input/image drift")
    def run(argv, log, timeout=300, expect_fatal=False):
        def started(pid):
            state.update(child_pid=pid, command=list(map(str, argv)), log=str(log))
            save()
        try:
            code = run_command(list(map(str, argv)), log, timeout, os.environ.copy(), started)
            if code not in ((0, 1) if expect_fatal else (0,)):
                raise RuntimeError("Command failed: " + str(log))
        finally:
            state["child_pid"] = None
            save()
    def interrupted(signum, _frame):
        raise InterruptedError(f"worker received signal {signum}")
    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    save()
    try:
        run(["make", "-C", ROOT / "verification/qbs", "rtl-engine-compile",
             "RTL_ENGINE_BUILD=" + str(build)], out / "compile-console.log")
        unchanged()
        image = build / "simv"
        libraries = list(build.glob("simv.daidir/**/*.so"))
        if not image.is_file() or not libraries:
            raise ValueError("Missing fresh VCS image")
        pinned.update(hashes({image, build / "compile.log", *libraries}))
        generator = out / "qbs_command_vectors"
        run(["cc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-ffp-contract=off", "-frounding-math", "-I" + str(ROOT / "apps/common"),
             ROOT / "verification/qbs/qbs_command_vectors.c", ROOT / "verification/qbs/qbs_ref.c",
             "-lm", "-o", generator], out / "generator-compile.log")
        pinned.update(hashes({generator}))
        identities = []
        for start in (0, 4):
            vector = out / f"inputs{start}.vectors"
            run([generator, vector, "--real-projection", "q8_0", capture,
                 896, 896, start, 4, 0, 32], out / f"generator-inputs{start}.log")
            vector_text = vector.read_text()
            identity = vector_identity(vector_text)
            if identities and identity["activation_hash"] == identities[0]["activation_hash"]:
                raise ValueError("Independent input groups are identical")
            identities.append(identity)
            pinned.update(hashes({vector}))
            if start == 0:
                negative = out / "negative_unknown_counter"
                negative.mkdir()
                run([image, "-no_save", "-l", negative / "run.log",
                     "+QBS_FUNCTIONAL_ONLY", "+QBS_PROJECTION_SUITE",
                     "+QBS_PROJECTION_INJECT_COUNTER_X",
                     f"+QBS_COMMAND_VECTOR_FILE={vector}"], negative / "console.log", 300,
                    expect_fatal=True)
                text = (negative / "run.log").read_text()
                if (text.count("case 0 has unknown completion metadata/counters") != 1 or
                        "QBS projection PASS" in text or "QBS engine PASS" in text):
                    raise ValueError("Unknown-counter injection was not rejected")
                state["negative_unknown_counter"] = {
                    "state": "EXPECTED_REJECTION", "log_sha256": digest(negative / "run.log")}
                save()
            for gap in (0, 4):
                unchanged()
                name = f"inputs{start}_gap{gap}"
                directory = out / name
                directory.mkdir()
                state.update(state="running", current=name)
                run([image, "-no_save", "-l", directory / "run.log",
                     "+QBS_FUNCTIONAL_ONLY", "+QBS_PROJECTION_SUITE",
                     f"+QBS_RESPONSE_GAP={gap}", f"+QBS_COMMAND_VECTOR_FILE={vector}"],
                    directory / "console.log", 1800)
                result = check_projection((directory / "run.log").read_text(), vector_text, gap)
                result.update(log_sha256=digest(directory / "run.log"), input_start=start,
                              response_gap=gap)
                state["cases"][name] = result
                save()
        unchanged()
        state["state"] = "PASS"
    except BaseException as error:
        state.update(state="INTERRUPTED" if isinstance(error, (InterruptedError, KeyboardInterrupt))
                     else "FAIL", error=repr(error))
        raise
    finally:
        save()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
