"""Private, bounded host-VCS lane/MASKU test. No shared build files are modified."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--baseline", action="store_true")
    p.add_argument("--frozen", type=Path, help="Previous snapshot; replace only lane_sequencer")
    p.add_argument("--lane", type=Path, help="Explicit previously captured lane RTL")
    p.add_argument("--jobs", type=int, default=4)
    a = p.parse_args()
    assert 1 <= a.jobs <= 4
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    snap = out / "snapshot"
    common = "hardware/deps/common_cells"
    cva6 = "hardware/deps/cva6/core/include"
    sources = [f"{common}/src/cf_math_pkg.sv", "hardware/deps/axi/src/axi_pkg.sv",
               f"{cva6}/config_pkg.sv", f"{cva6}/cv64a6_imafdcv_sv39_config_pkg.sv",
               f"{cva6}/riscv_pkg.sv", "hardware/include/rvv_pkg.sv",
               "hardware/deps/fpnew/src/fpnew_pkg.sv", "hardware/include/ara_pkg.sv"]
    sources += [f"{common}/src/{s}.sv" for s in
                ("spill_register_flushable", "spill_register", "lzc", "popcount",
                 "delta_counter", "fifo_v3")]
    sources += ["hardware/src/common_cells_compat/fall_through_register_v1.sv",
                "hardware/src/lane/simd_alu.sv", "hardware/src/lane/fixed_p_rounding.sv",
                "hardware/src/lane/valu.sv",
                "hardware/src/lane/lane_sequencer.sv", "hardware/src/masku/masku_operands.sv",
                "hardware/src/masku/masku.sv"]
    extras = ["hardware/src/lane/lane.sv"]
    extras += [str(f.relative_to(ROOT)) for d in
               (ROOT / common / "include", ROOT / "hardware/include")
               for f in d.rglob("*.svh")]
    pins = {}
    for rel in sources + extras:
        source = (a.frozen / rel) if a.frozen else ROOT / rel
        if rel.endswith("/lane_sequencer.sv"):
            source = a.lane or ROOT / rel
        dest = snap / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        pins[rel] = digest(dest)
    # Derive interface typedefs verbatim from the snapshotted current lane.
    lane = (snap / "hardware/src/lane/lane.sv").read_text()
    structs = re.findall(r"typedef struct packed \{[^}]*\} (\w+);", lane)
    assert "operand_request_cmd_t" in structs and "vfu_operation_t" in structs
    types = []
    for name in ("operand_request_cmd_t", "vfu_operation_t"):
        types.append(re.search(r"typedef struct packed \{[^}]*\} " + name + ";", lane)[0])
    (snap / "lane_types.svh").write_text("\n".join(types) + "\n")
    shutil.copyfile(HERE / "lane_mask_tb.sv", snap / "lane_mask_tb.sv")
    shutil.copyfile(Path(__file__), out / "runner_snapshot.py")
    (out / "sources.json").write_text(json.dumps(pins, indent=2) + "\n")
    command = ["vcs", "-full64", "-sverilog", "-timescale=1ns/1ps", "-debug_access+all",
               "+incdir+" + str(snap / common / "include"),
               "+incdir+" + str(snap / "hardware/include"), "+incdir+" + str(snap),
               "-top", "lane_mask_tb", *[str(snap / s) for s in sources],
               str(snap / "lane_mask_tb.sv"), "-o", str(out / "simv"), "-l", "compile.log"]
    (out / "compile-command.json").write_text(json.dumps(command, indent=2))
    with (out / "compile.console.log").open("w") as log:
        subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                       timeout=180, check=True)
    cases = [("compare_small", 0, 8, 4, 3, 0),
             ("compare_control", 0, 512, 0, 0, 0),
             ("compare_boundary", 0, 512, 256, 0, 0),
             ("mfpu_boundary", 1, 512, 256, 1, 0),
             ("alu_boundary", 2, 512, 256, 0, 0),
             ("load_boundary", 3, 512, 256, 0, 0),
             ("store_boundary", 4, 512, 256, 0, 0),
             ("logic_request", 5, 512, 256, 0, 0),
             ("slideup_request", 7, 512, 256, 0, 0),
             ("slidedown_request", 8, 512, 256, 0, 0)]
    if not a.baseline:
        cases += [(f"compare_s{sew}_m{mode}_v{vl}_r{start}", 0, vl, start, sew, mode)
                  for sew in range(4) for mode in range(3)
                  for vl, start in ((8, 1), (min(257, 1024 >> sew), min(255, (1024 >> sew)-1)),
                                    (min(512, 1024 >> sew), min(257, (1024 >> sew)-1)))]
        cases += [("fpcompare_request", 6, 512, 256, 1, 0)]
    cases = list(dict.fromkeys(cases))
    assert len({case[0] for case in cases}) == len(cases)
    (out / "test-pins.json").write_text(json.dumps({
        str(p.relative_to(out)): digest(p) for p in
        (snap / "lane_types.svh", snap / "lane_mask_tb.sv", out / "runner_snapshot.py")
    }, indent=2) + "\n")
    def execute(case):
        name, kind, vl, start, sew, mode = case
        run = out / name
        run.mkdir()
        expect = int(a.baseline and name in ("compare_boundary", "mfpu_boundary", "alu_boundary"))
        if a.baseline and name == "slidedown_request":
            expect = 2
        command = [str(out / "simv"), "-l", "run.log", f"+KIND={kind}", f"+VL={vl}",
                   f"+START={start}", f"+SEW={sew}", f"+MODE={mode}", f"+EXPECT_FAIL={int(expect)}"]
        if name in ("compare_small", "compare_boundary", "mfpu_boundary"):
            command.append("+WAVE")
        (run / "command.json").write_text(json.dumps(command, indent=2))
        with (run / "console.log").open("w") as log:
            proc = subprocess.run(command, cwd=run, stdout=log, stderr=subprocess.STDOUT, timeout=30)
        text = (run / "run.log").read_text()
        marker = "EXPECTED_CURRENT_FAILURE" if expect else "PASS lane_mask"
        result = dict(name=name, returncode=proc.returncode, expected_failure=expect,
                      passed=proc.returncode == 0 and marker in text,
                      result=[s for s in text.splitlines() if s.startswith("RESULT ")])
        print(json.dumps(result), flush=True)
        return result
    results = []
    # Bound startup concurrency; each process owns its run directory and FSDB.
    # Dispatch in small batches and stop on a new failure before the next batch.
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        for first in range(0, len(cases), a.jobs):
            batch = list(pool.map(execute, cases[first:first+a.jobs]))
            results.extend(batch)
            (out / "status.json").write_text(json.dumps(results, indent=2) + "\n")
            if not all(r["passed"] for r in batch):
                raise SystemExit(1)
    assert all(digest(snap / rel) == sha for rel, sha in pins.items())


if __name__ == "__main__":
    main()
