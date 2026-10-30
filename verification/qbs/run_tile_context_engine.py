#!/usr/bin/env python3
"""Check capacity-bounded context integration on an explicitly supplied VCS image.

Run after rtl-engine-compile. This worker does not build or silently substitute
an image. Real vectors must come from the captured Q8_0 M4/N32/K896 case.
Cycles exclude activation preparation, CPU dispatch and the full GGML operator.
"""
import argparse
import os
from pathlib import Path
import re
import signal
import subprocess

from run_half_scale_soc import atomic_json, digest, hashes

ROOT = Path(__file__).resolve().parents[2]
PATTERN = (r"QBS end-to-end case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) "
           r"Kb=(\d+) layouts=(\d+)/(\d+) cycles=(\d+)")
CONTEXT = (r"QBS activation context FILL/REUSE/RELEASE PASS case=(\d+) "
           r"M=(\d+) Kb=(\d+) bytes=(\d+) fill_cycles=(\d+) reuse_cycles=(\d+)")


def run_command(argv, log, timeout, env, started):
    with log.open("x") as stream:
        process = subprocess.Popen(argv, cwd=log.parent, stdout=stream,
                                   stderr=subprocess.STDOUT, env=env,
                                   start_new_session=True)
        try:
            started(process.pid)
            return process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise


def check_log(text, count, contexts, gap):
    if re.search(r"Fatal:|Error:|UVM_ERROR|UVM_FATAL", text):
        raise ValueError("Simulator failure")
    if text.count(f"QBS configuration response_gap={gap} context_suite={int(contexts == count)}\n") != 1:
        raise ValueError("Wrong simulator configuration")
    terminal = re.findall(r"^QBS engine PASS: (\d+) functional cases(?: plus four fault classes)?$", text, re.M)
    if terminal != [str(count)]:
        raise ValueError("Missing unique terminal PASS")
    if contexts != count:
        if text.count(f"QBS engine PASS: {count} functional cases plus four fault classes\n") != 1:
            raise ValueError("Missing atomic-fault suite terminal")
        for kind in ("validation", "MMU", "AXI", "PMA"):
            if text.count(f"QBS {kind} atomic-fault PASS\n") != 1:
                raise ValueError("Missing atomic-fault class")
    direct = [tuple(map(int, row)) for row in re.findall(PATTERN, text)]
    reused = [tuple(map(int, row)) for row in re.findall(CONTEXT, text)]
    if len(direct) != count or {row[0] for row in direct} != set(range(count)):
        raise ValueError("Incomplete direct command coverage")
    if len(reused) != contexts or {row[0] for row in reused} != set(range(contexts)):
        raise ValueError("Incomplete context lifecycle coverage")
    for kind in range(3):
        if text.count(f"QBS next-block fault/replay PASS kind={kind}\n") != contexts:
            raise ValueError("Missing fault recovery")
    if text.count("QBS next-block reset/replay PASS\n") != contexts:
        raise ValueError("Missing active reset recovery")
    fault_retries = re.findall(
        r"^QBS context weight fault/retry PASS case=(\d+) release=(\d+) kind=(\d+)$",
        text, re.M)
    expected_retries = {(case, release, kind) for case in range(contexts)
                        for release in range(2) for kind in range(3)}
    if (len(fault_retries) != len(expected_retries) or
            {tuple(map(int, row)) for row in fault_retries} != expected_retries):
        raise ValueError("Missing or duplicate context weight-fault recovery")
    if contexts == 12:
        expected = []
        for compact in (False, True):
            for m in (1, 4, 5, 6, 7, 8):
                rows = 1 if m == 1 else 4 if m == 4 else 8
                block = 34 if compact else 292
                blocks = min(32, 4672 // (rows * block))
                expected.append((6 if compact else 1, m, 5, blocks, 2,
                                 1 if m == 1 else 2 if m == 4 else 3,
                                 rows * block * blocks))
        by_id = {row[0]: row for row in direct}
        context_by_id = {row[0]: row for row in reused}
        for case, shape in enumerate(expected):
            command, context = by_id[case], context_by_id[case]
            if command[1:7] != shape[:6] or context[1:4] != (shape[1], shape[3], shape[6]):
                raise ValueError("Wrong capacity-boundary shape")
    if count == 1 and (direct[0][1:7] != (6, 4, 32, 28, 2, 2) or
                       reused[0][1:4] != (4, 28, 3808)):
        raise ValueError("Wrong real-data geometry")
    return {"direct": direct, "contexts": reused, "response_gap": gap}


def check_geometry(vector_text, direct):
    records = re.findall(r"^CMD (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) [0-9a-fA-F]+$",
                         vector_text, re.M)
    expected = {}
    for row in records:
        case, profile, weight_layout, activation_layout, m, n, kb = map(int, row)
        if case in expected:
            raise ValueError("Duplicate input command")
        expected[case] = (profile, m, n, kb, weight_layout, activation_layout)
    if {row[0]: row[1:7] for row in direct} != expected:
        raise ValueError("Executed command geometry differs from input vectors")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--real-vector", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    image = args.image.resolve(strict=True)
    real = args.real_vector.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    libraries = list(image.with_name(image.name + ".daidir").rglob("*.so"))
    if not libraries:
        raise ValueError("Missing VCS dynamic libraries")
    sources = set()
    for root in ("hardware/src/vlsu/qbs", "hardware/include", "hardware/deps/fpnew",
                 "hardware/deps/common_cells", "hardware/deps/axi", "hardware/deps/tech_cells_generic"):
        sources.update(p for p in (ROOT / root).rglob("*")
                       if p.is_file() and p.suffix in (".sv", ".svh"))
    sources.update(ROOT / p for p in ("verification/qbs/qbs_engine_tb.sv",
        "verification/qbs/qbs_command_vectors.c", "verification/qbs/qbs_ref.c",
        "verification/qbs/qbs_ref.h", "verification/qbs/Makefile",
        "apps/common/qbs_abi.h", "verification/qbs/run_tile_context_engine.py",
        "verification/qbs/run_half_scale_soc.py"))
    pinned = hashes(sources | {image, real, *libraries})
    state = {"state": "preparing", "pid": os.getpid(), "cases": {},
             "scope": __doc__, "sources_and_inputs": pinned}
    def save():
        atomic_json(out / "status.json", state)
    def unchanged():
        if any(digest(Path(p)) != sha for p, sha in pinned.items()):
            raise RuntimeError("Source/input/image drift")
    def run(argv, log):
        def started(pid):
            state.update(child_pid=pid, command=list(map(str, argv)), log=str(log))
            save()
        try:
            if run_command(list(map(str, argv)), log, 240, os.environ.copy(), started) != 0:
                raise RuntimeError("Command failed: " + str(log))
        finally:
            state["child_pid"] = None
            save()
    save()
    try:
        generator = out / "qbs_command_vectors"
        run(["cc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-ffp-contract=off", "-frounding-math", "-I" + str(ROOT / "apps/common"),
             ROOT / "verification/qbs/qbs_command_vectors.c", ROOT / "verification/qbs/qbs_ref.c",
             "-lm", "-o", generator], out / "generator.log")
        direct = out / "direct.vectors"
        context = out / "context.vectors"
        run([generator, direct], out / "direct-generator.log")
        run([generator, context, "--context-suite"], out / "context-generator.log")
        pinned.update(hashes([generator, direct, context]))
        state["state"] = "running"
        for name, vector, count, contexts, gap in (
                ("context", context, 12, 12, 0), ("direct", direct, 36, 1, 0),
                ("real", real, 1, 1, 0), ("real_gap4", real, 1, 1, 4)):
            unchanged()
            directory = out / name
            directory.mkdir()
            argv = [image, "-no_save", "-l", directory / "run.log",
                    "+QBS_RESPONSE_GAP=" + str(gap), "+QBS_COMMAND_VECTOR_FILE=" + str(vector)]
            if contexts == count:
                argv += ["+QBS_FUNCTIONAL_ONLY", "+QBS_CONTEXT_SUITE"]
            run(argv, directory / "console.log")
            result = check_log((directory / "run.log").read_text(), count, contexts, gap)
            check_geometry(vector.read_text(), result["direct"])
            result.update(vector_sha256=digest(vector), log_sha256=digest(directory / "run.log"))
            state["cases"][name] = result
            save()
        unchanged()
        state["state"] = "PASS"
    except BaseException as error:
        state.update(state="FAIL", error=repr(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
