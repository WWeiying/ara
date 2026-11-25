#!/usr/bin/env python3
"""Compare real preflight helpers with the frozen prepared-board predecessor."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SDK = ROOT / "software/akv"
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
PREVIOUS = OUT / "resident_direct_build_prepared_20261113_02"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, type=Path)
    out = ap.parse_args().output.resolve()
    out.mkdir(exist_ok=False)
    report = dict(state="FAIL", numerical_execution=False, rtl_execution=False)
    pins, commands = {}, []
    try:
        old = PREVIOUS / "inputs/sdk/software/akv"
        previous_pins = json.loads((PREVIOUS / "source-pins.json").read_text())
        # Check frozen inputs only, not the now intentionally changed worktree.
        for p in old.rglob("*"):
            if p.is_file() and sha(p) != previous_pins[str(p)]:
                raise ValueError("frozen predecessor drift: " + str(p))
        for root in (SDK, old):
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in (".c", ".h", ".S", ".inc", ".py"):
                    pins[str(p)] = sha(p)
        for tool in ("/usr/bin/cc", "/usr/bin/clang"):
            pins[tool] = sha(tool)
        (out / "source-pins.json").write_text(json.dumps(pins, indent=2) + "\n")
        for p in (HERE / "test_preflight_once.c", Path(__file__)):
            shutil.copyfile(p, out / p.name)
        other = [SDK / "src" / n for n in ("akv_runtime.c", "akv_native_riscv.c",
                 "akv_v2_reference.c", "akv_prefill_reference.c", "akv_features.c", "akv_decode.c")]
        results = {}
        for label, root, sanitizer in (("previous", old, False), ("current", SDK, False),
                                        ("previous_ubsan", old, True),
                                        ("current_ubsan", SDK, True)):
            core = root / "src/akv_v2_native_riscv.c"
            binary = out / label
            argv = ["/usr/bin/clang" if sanitizer else "/usr/bin/cc", "-std=c11", "-O2",
                    "-Wall", "-Wextra", "-Werror", "-Wno-unknown-pragmas",
                    "-fno-fast-math", "-ffp-contract=off", "-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1",
                    "-DAKV_EXPERIMENTAL_RESIDENT_FEATURES_V2=1",
                    '-DRESIDENT_CORE="' + str(core) + '"', "-I" + str(SDK / "include")]
            if sanitizer:
                argv += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            argv += [str(HERE / "test_preflight_once.c"), *map(str, other), "-lm", "-o", str(binary)]
            for name, command in ((label + "_compile", argv), (label + "_run", [str(binary)])):
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        timeout=90, text=True)
                (out / (name + ".log")).write_text(result.stdout)
                commands.append(dict(name=name, argv=command, returncode=result.returncode))
                if result.returncode:
                    raise ValueError("failed: " + name)
            results[label] = json.loads(result.stdout)
        for field in ("cases", "accepted", "feature_cases", "feature_accepted"):
            if len({r[field] for r in results.values()}) != 1:
                raise ValueError("differential mismatch: " + field)
        # Floating exception code generation may differ across compilers. Keep
        # it in the oracle and compare predecessor/candidate with each compiler.
        for suffix in ("", "_ubsan"):
            if results["previous" + suffix]["digest"] != results["current" + suffix]["digest"]:
                raise ValueError("differential mismatch: digest" + suffix)
        if results["previous"]["sample_direct_descriptor_checks"] != 2 or \
           results["previous"]["sample_full_plan_checks"] != 1:
            raise ValueError("unexpected predecessor work")
        for label in ("current", "current_ubsan"):
            r = results[label]
            if r["direct_descriptor_checks"] != r["accepted"] or r["full_plan_checks"] != 0:
                raise ValueError("duplicate validation remains: " + label)
        if any(sha(p) != value for p, value in pins.items()):
            raise ValueError("inputs changed while testing")
        report.update(state="PREFLIGHT_EQUIVALENCE_PASS", results=results, post_pins_match=True,
                      previous=str(PREVIOUS), descriptor_passes_per_accepted_call_before=3,
                      descriptor_passes_per_accepted_call_after=1,
                      note="Full plan validation contains another descriptor validation; no timing claim.")
    except Exception as exc:
        report["error"] = str(exc)
    (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return report["state"] != "PREFLIGHT_EQUIVALENCE_PASS"


if __name__ == "__main__":
    raise SystemExit(main())
