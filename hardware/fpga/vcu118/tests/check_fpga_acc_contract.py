#!/usr/bin/env python3
"""Run the existing directed contract against frozen FPGA dispatcher sources in XSim."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    ap.add_argument("--vivado-bin", required=True, type=Path)
    ap.add_argument("--sidebands", action="store_true")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[4]
    rtl = repo / "hardware/fpga/ara_dsa_vcu118/rtl"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = out / "inputs"
    frozen.mkdir()
    records = {}

    def copy(source, relative):
        target = frozen / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        target.write_bytes(data)
        records[str(source)] = hashlib.sha256(data).hexdigest()
        return target

    files = ["common_cells/src/cf_math_pkg.sv", "cva6/core/include/config_pkg.sv",
             "cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv",
             "cva6/core/include/riscv_pkg.sv", "cva6/core/include/ariane_pkg.sv",
             "cva6/core/include/build_config_pkg.sv", "fpnew/src/fpnew_pkg.sv",
             "common_cells/src/delta_counter.sv", "common_cells/src/counter.sv",
             "common_cells/src/spill_register_flushable.sv",
             "common_cells/src/spill_register.sv", "cva6/core/cva6_fifo_v3.sv",
             "cva6/core/acc_dispatcher.sv"]
    sources = [copy(rtl / name, name) for name in files]
    for folder in ("common_cells/include", "cva6/core/include", "ara/hardware/include"):
        for path in (rtl / folder).rglob("*.svh"):
            copy(path, path.relative_to(rtl))
    cva6 = copy(rtl / "cva6/core/cva6.sv", "cva6/core/cva6.sv").read_text()
    types = []
    for name in ("branchpredict_sbe_t", "exception_t", "scoreboard_entry_t", "fu_data_t",
                 "dcache_req_i_t", "dcache_req_o_t"):
        matches = re.findall(r"(?:localparam|parameter)\s+type\s+" + name +
                             r"\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*,", cva6)
        if len(matches) != 1:
            raise RuntimeError("Ambiguous type " + name)
        types.append("typedef " + matches[0] + " " + name + ";")
    (frozen / "contract_types.svh").write_text("\n".join(types) + "\n")
    tb = copy(repo / "verification/cva6/acc_dispatcher_contract_tb.sv", "tb.sv")
    if args.sidebands:
        marker = "  function automatic fu_op operation(int k);"
        original_tb = tb.read_text()
        if original_tb.count(marker) != 1:
            raise RuntimeError("Contract fixture changed")
        body = copy(Path(__file__).with_name("acc_dispatcher_sideband_body.svh"), "sideband_body.svh")
        tb.write_text(original_tb.split(marker)[0] + body.read_text())
    sources.append(tb)
    for name in ("checker.py", "stimulus.py"):
        copy(repo / "verification/cva6" / name, "contract/" + name)
    # The historical contract assumed two queue slots. The FPGA dispatcher has
    # four slots and reserves one for the issue register. Adapt only that
    # explicit capacity contract, and exercise the new full-admission boundary.
    dispatcher = (frozen / "cva6/core/acc_dispatcher.sv").read_text()
    for required in ("localparam InstructionQueueDepth = 4;",
                     "acc_insn_queue_usage < (InstructionQueueDepth - 1)"):
        if required not in dispatcher:
            raise RuntimeError("Review required: FPGA queue contract changed")
    checker_path = frozen / "contract/checker.py"
    original = checker_path.read_text()
    old, new = "view == 1 and len(queue) >= 2", "view == 1 and len(queue) >= 3"
    if original.count(old) != 1:
        raise RuntimeError("Historical checker changed; review adapter")
    checker_path.write_text(original.replace(old, new))
    (frozen / "contract/__init__.py").write_text("")
    sys.path.insert(0, str(frozen))
    sys.dont_write_bytecode = True
    stimulus = importlib.import_module("contract.stimulus")
    checker = importlib.import_module("contract.checker")
    planned = stimulus.schedule()
    index = next(i for i, row in enumerate(planned) if row["label"] == "queue_capacity")
    extra = dict(planned[index], label="issue_capacity_extra", seq=12, id=7, kind=0)
    execute = dict(extra, label="execute_capacity_extra", seq=0, id=0, view=0)
    planned[index:index] = [extra, execute]
    (out / "stimulus.txt").write_text(stimulus.render(planned))
    result = {"passed": False, "inputs": records, "cycles_planned": len(planned),
              "sidebands": args.sidebands,
              "testbench_sha256": hashlib.sha256(tb.read_bytes()).hexdigest(),
              "checker_adaptation": {"old": old, "new": new,
                                     "sha256": hashlib.sha256(checker_path.read_bytes()).hexdigest()},
              "scope": "actual FPGA dispatcher, directed contract; not whole CPU/Ara or board signoff"}
    commands = [["xvlog", "-sv", "-d", "ARIANE_ACCELERATOR_PORT=1"]]
    for folder in ("common_cells/include", "cva6/core/include", "ara/hardware/include", "."):
        commands[0] += ["-i", str(frozen / folder)]
    commands[0] += list(map(str, sources))
    commands += [["xelab", "-mt", "2", "-timescale", "1ns/1ps",
                  "acc_dispatcher_contract_tb", "-s", "contract_sim"],
                 ["xsim", "contract_sim", "-runall", "-testplusarg", "STIMULUS=" + str(out / "stimulus.txt")]]
    try:
        for command in commands:
            with (out / (command[0] + ".console.log")).open("w") as log:
                subprocess.run([str(args.vivado_bin.resolve() / command[0]), *command[1:]],
                               cwd=out, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=180)
        console = (out / "xsim.console.log").read_text()
        if args.sidebands:
            if "PASS FPGA_CSR_SIDEBAND checks=24" not in console or "SIDEBAND_FAIL" in console:
                raise RuntimeError("Sideband checks failed; inspect XSim log")
            checked = {"status": "PASS", "sideband_checks": 24}
        else:
            checked = checker.check_evidence(console, (out / "trace.jsonl").read_text(),
                                             json.loads((out / "config.json").read_text()),
                                             returncode=0, expected_stimulus=planned)
            if checked["max_queue"] < 3:
                raise RuntimeError("Current FPGA admission limit was not exercised")
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in records.items()):
            raise RuntimeError("Input drift")
        result.update(passed=True, checked=checked)
        print(json.dumps(checked, indent=2))
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
