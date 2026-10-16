#!/usr/bin/env python3
"""Reproduce WT read loss and test the actual repaired adapter with host VCS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from ara_verify.dependency_patches import load_registry, patch_state
from cva6.run_contract import execute, validate_output

CORE = "hardware/deps/cva6/core/"
COMMON = "hardware/deps/common_cells/"
AXI = "hardware/deps/axi/"
ADAPTER = CORE + "cache_subsystem/wt_axi_adapter.sv"
ORIGINAL_SHA = "8141dfb8af2f098529b421a1b281bb167a74f4e79bcf7881a795aad3c286d3dd"
SOURCES = [COMMON + "src/cf_math_pkg.sv", AXI + "src/axi_pkg.sv"]
SOURCES += [CORE + "include/" + name for name in (
    "config_pkg.sv", "cv64a6_imafdcv_sv39_config_pkg.sv", "riscv_pkg.sv",
    "ariane_pkg.sv", "build_config_pkg.sv", "wt_cache_pkg.sv")]
SOURCES += [COMMON + "src/lzc.sv", COMMON + "src/rr_arb_tree.sv",
            COMMON + "src/fifo_v3.sv", "hardware/src/axi_inval_filter.sv",
            CORE + "cva6_fifo_v3.sv", CORE + "axi_shim.sv", ADAPTER,
            "verification/cva6/wt_inval_collision_tb.sv"]
EXTRA = [CORE + "cva6.sv", CORE + "cache_subsystem/wt_cache_subsystem.sv",
         COMMON + "include/common_cells/assertions.svh",
         COMMON + "include/common_cells/registers.svh", AXI + "include/axi/typedef.svh",
         AXI + "src/axi_id_remap.sv",
         "verification/patches/cva6-local-fixes.patch", "verification/patches/dependencies.json",
         "verification/cva6/run_wt_inval_collision.py", "verification/cva6/run_contract.py",
         "verification/ara_verify/dependency_patches.py"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def extract(source, name):
    pattern = r"(?:localparam|parameter)\s+type\s+" + re.escape(name) + r"\s*=\s*struct\s+packed\s*\{"
    matches = list(re.finditer(pattern, source))
    if len(matches) != 1:
        raise ValueError("ambiguous actual interface " + name)
    start = source.index("struct", matches[0].start())
    end = matches[0].end() - 1
    depth = 1
    while depth:
        end += 1
        depth += (source[end] == "{") - (source[end] == "}")
    return "typedef " + source[start:end + 1] + " " + name + ";\n"


def original_adapter(repaired):
    changes = [
        ("axi_rd_rdy        = ~invalidate & ~inval_valid_i;", "axi_rd_rdy        = ~invalidate;"),
        ("// Invalidation owns the D-cache return slot. Backpressure AXI as well,\n"
         "    // otherwise a simultaneous read beat is accepted but never captured.",
         "// we are not ready when invalidating"),
        ("// External invalidation can overlap speculative fetches and page walks.\n"
         "    // The shared R channel is held until this return slot is available.",
         "// External invalidation requests (from coprocessor). This is safe as\n"
         "    // there are no other transactions when a coprocessor has pending stores."),
    ]
    for new, old in changes:
        if repaired.count(new) != 1:
            raise ValueError("reviewed adapter change no longer matches")
        repaired = repaired.replace(new, old, 1)
    if sha(repaired.encode()) != ORIGINAL_SHA:
        raise ValueError("baseline is not the exact pre-repair adapter")
    return repaired


def cases(variant):
    if variant == "baseline":
        return [(beat, 0, 1, 0) for beat in (-1, 0, 1, 2, 3)]
    rows = [(beat, 0, hold, b) for beat in (-1, 0, 1, 2, 3)
            for hold in (1, 4) for b in (0, 1)]
    rows += [(beat, 1, hold, 0) for beat in (-1, 0, 1) for hold in (1, 4)]
    rows += [(beat, 2, hold, 0) for beat in (-1, 0) for hold in (1, 4)]
    return rows


def classify(text, receipt, variant, row):
    beat, mode, hold, b = row
    timeout = receipt.get("timeout", False)
    fatal = re.search(r"(?:Fatal:|\$fatal|Error:|UVM_(?:ERROR|FATAL))", text)
    passes = re.findall(r"^INVAL_READ_PASS collide=(-?\d+)\s*$", text, re.M)
    reproduced = variant == "baseline" and beat >= 0
    if reproduced:
        reason = re.search(r"\b(RETURN_DATA_CORRUPT|READ_COMPLETION_LOST|READ_ACCEPTED_DURING_INVALIDATION)\b", text)
        accepted = not timeout and not passes and reason is not None and fatal is not None
        return dict(accepted=accepted,expected_failure=True,
                    observed_failure=reason[1] if reason else None)
    complete = len(re.findall(r"^COLLISION_RESULT\b", text, re.M)) == 1
    accepted = (receipt["returncode"] == 0 and not timeout and not fatal
                and passes == [str(beat)] and complete)
    return dict(accepted=bool(accepted),expected_failure=False)


def run(output):
    output = validate_output(output)
    registry = load_registry(ROOT)
    for package in ("cva6", "axi"):
        if patch_state(ROOT, package, ROOT / "hardware/deps" / package,
                       registry[package]["revision"]) != "applied":
            raise ValueError("requires reviewed " + package + " dependency state")
    vcs = shutil.which("vcs")
    if not vcs:
        raise ValueError("host VCS not found")
    output.mkdir(parents=True)
    frozen = output / "inputs"
    pins = {}
    for relative in dict.fromkeys(SOURCES + EXTRA):
        source = ROOT / relative
        data = source.read_bytes()
        destination = frozen / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        pins[relative] = sha(data)
    generated = frozen / "generated"
    generated.mkdir()
    top = (frozen / CORE / "cva6.sv").read_text()
    cache = (frozen / CORE / "cache_subsystem/wt_cache_subsystem.sv").read_text()
    types = "// Actual CVA6 packed types; Solderpad Hardware License 0.51.\n"
    for name in ("icache_req_t", "icache_rtrn_t"):
        types += extract(top, name)
    for name in ("dcache_inval_t", "dcache_req_t", "dcache_rtrn_t"):
        types += extract(cache, name)
    (generated / "collision_types.svh").write_text(types)
    repaired = (frozen / ADAPTER).read_text()
    (generated / "wt_axi_adapter_original.sv").write_text(original_adapter(repaired))
    save(output / "manifest.json", dict(
        scope="Actual WT adapter/AXI shim/FIFO directed tests, not full SoC or Linux",
        sources=pins, original_adapter_sha256=ORIGINAL_SHA,
        repaired_adapter_sha256=sha(repaired.encode()), axi_id_remap_changed=False,
        generated={p.name: sha(p.read_bytes()) for p in generated.iterdir()}))
    results = []
    control_trace = None
    for variant in ("baseline", "repaired"):
        parent = output / variant
        parent.mkdir()
        command = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                   "-top", "wt_inval_collision_tb"]
        command += ["+incdir+" + str(p) for p in (
            frozen / COMMON / "include", frozen / AXI / "include",
            frozen / CORE / "include", generated)]
        command += [str(generated / "wt_axi_adapter_original.sv") if
                    name == ADAPTER and variant == "baseline" else str(frozen / name)
                    for name in SOURCES]
        command += ["-o", "simv", "-Mdir=csrc"]
        compile_result = execute(command, parent / "compile", 180)
        if compile_result["returncode"] != 0 or compile_result.get("timeout", False):
            raise ValueError("compile failed: " + variant)
        simv = parent / "compile/simv"
        for index, row in enumerate(cases(variant)):
            beat, mode, hold, b = row
            name = f"case{index:02d}_beat{beat}_mode{mode}_hold{hold}_b{b}"
            argv = [str(simv), "-no_save", f"+collide={beat}", f"+mode={mode}",
                    f"+hold={hold}", f"+b_concurrent={b}"]
            receipt = execute(argv, parent / name, 30)
            text = (parent / name / "console.log").read_text(errors="replace")
            trace = [line for line in text.splitlines()
                     if line.startswith(("READ_CYCLE ", "COLLISION_RESULT "))]
            if row == (-1, 0, 1, 0):
                if variant == "baseline":
                    control_trace = trace
                elif not control_trace or trace != control_trace:
                    raise ValueError("normal read cycle evidence changed")
            item = dict(variant=variant,case=name,beat=beat,mode=mode,hold=hold,
                        b_concurrent=b,actual_exit=receipt["returncode"],
                        elapsed_s=receipt["elapsed_s"],cycle_evidence=trace,
                        **classify(text, receipt, variant, row))
            results.append(item)
            save(output / "cases.json", results)
            if not item["accepted"]:
                raise ValueError("unexpected result: " + variant + "/" + name)
    unchanged = all(sha((ROOT / p).read_bytes()) == h for p, h in pins.items())
    summary = dict(status="PASS_BASELINE_REPRODUCED_AND_REPAIRED" if unchanged else "INPUT_DRIFT",
                   original_failures_reproduced=4,baseline_controls_passed=1,
                   repaired_cases_passed=30,case_count=len(results),pins_unchanged=unchanged,
                   normal_read_cycle_evidence_unchanged=True,
                   axi_id_remap_changed=False,full_soc_test=False)
    save(output / "summary.json", summary)
    if not unchanged:
        raise ValueError("source inputs changed during test")
    print(json.dumps(summary, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = validate_output(args.output)
    try:
        run(output)
    except Exception as error:
        if output.is_dir():
            save(output / "failure.json", dict(status="NOT_PASS",error=repr(error)))
        raise


if __name__ == "__main__":
    main()
