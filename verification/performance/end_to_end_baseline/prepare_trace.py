#!/usr/bin/env python3
"""Reconstruct the board-tested source delta without editing either worktree."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from audit import digest, read, require, verify_pins

HERE = Path(__file__).resolve().parent
DELIVERY = "da56aa750559c180d631b466de983ff2bb5d54d9"
SOURCE = "ggml/src/ggml-cpu/arch/riscv/qbs.cpp"
BEFORE = "43a86cfd658b3a94817077b8e3cc20eb08f948113bcbc841f449e1279d913f6e"
AFTER = "9aa982ff55414f92d8fc10df8b09cc29eb013dcd2b81deadcbed99216158c8f9"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    p.add_argument("--archive", type=Path,
                   default=Path("/home/wangwy/fpga_runs/qwen3_perf_diagnosis_20261104_01"))
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(state="INCOMPLETE", production_changed=False, new_board_test=False,
                  full_binary_rebuilt=False, delivery_commit=DELIVERY, tests=[])
    pins = {str(HERE / "trace-context.patch"): digest(HERE / "trace-context.patch"),
            str(Path(__file__).resolve()): digest(__file__)}
    try:
        scope = read(a.archive / "trace_candidate_scope_audit_01/result.json")
        verify_pins(scope["source_pins"])
        for suffix in ("qbs.cpp", "qbs.h"):
            name = "ggml/src/ggml-cpu/arch/riscv/" + suffix
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(
                ["git", "-C", str(a.llama), "show", DELIVERY + ":" + name]))
        require(digest(out / SOURCE) == BEFORE, "Wrong delivery preimage")
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "--dry-run", "-i", str(HERE / "trace-context.patch")],
                       cwd=out, check=True)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(HERE / "trace-context.patch")], cwd=out, check=True)
        require(digest(out / SOURCE) == AFTER, "Candidate differs from measured source")
        pins[str(out / SOURCE)] = AFTER
        pins[str(out / SOURCE.replace(".cpp", ".h"))] = digest(out / SOURCE.replace(".cpp", ".h"))
        archived = read(a.archive / "trace_candidate_build_01/build.json")
        for trial in archived["tests"]:
            command = list(trial["command"])
            name = trial["compiler"] + "_" + trial["name"]
            if trial["name"] == "candidate":
                command = ['-DTRACE_TEST_SOURCE="' + str(out / SOURCE) + '"'
                           if arg.startswith("-DTRACE_TEST_SOURCE=") else arg for arg in command]
            command[command.index("-o") + 1] = str(out / name)
            # Record the actual host dependency closure of this test fixture.
            deps_cmd = command[:command.index("-o")] + ["-M", "-MT", "object"]
            deps = subprocess.check_output(deps_cmd, text=True, timeout=120)
            for path in shlex.split(deps.replace("\\\n", " ").split(":", 1)[1]):
                path = str(Path(path).resolve())
                pins[path] = digest(path)
            verify_pins(pins)
            subprocess.run(command, check=True, timeout=180, capture_output=True)
            test = subprocess.run([str(out / name)], check=True, timeout=60, capture_output=True)
            (out / (name + ".stdout")).write_bytes(test.stdout)
            (out / (name + ".stderr")).write_bytes(test.stderr)
            require(test.stdout.decode().strip() == trial["stdout"], "Host marker differs")
            verify_pins(pins)
            report["tests"].append(dict(name=name, command=command, state="PASS",
                stdout=test.stdout.decode().strip(), stderr_sha256=digest(out / (name + ".stderr"))))
        require(len({r["stderr_sha256"] for r in report["tests"]}) == 1,
                "Trace bytes differ across baseline/candidate/compilers")
        report.update(state="MEASURED_SOURCE_RECONSTRUCTED_HOST_TESTS_PASS",
                      before_sha256=BEFORE, after_sha256=AFTER,
                      measured_binary_sha256=scope["production_candidate_sha256"],
                      flag_policy="Snapshot once per blocking context; refresh at next context",
                      artifact_pins=pins)
    except Exception as exc:
        report.update(state="FAIL", error=repr(exc))
        raise
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(report["state"])


if __name__ == "__main__":
    main()
