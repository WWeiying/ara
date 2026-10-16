#!/usr/bin/env python3
"""Run a bounded real-store-buffer probe-semantics test from sealed RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "verification/cva6"))
import run_load_contract as contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = contract.validate_output(args.output, args.package)
    output.mkdir(parents=True)
    (output / "build").mkdir()
    report = {"status": "FAIL", "scope": "real_store_buffer_probe_semantics",
              "board_modified": False, "functional_rtl_modified": False,
              "real_cpu": False, "real_mmu": False, "error": None}
    records = {}
    try:
        manifest = contract.freeze_inputs(args.package, output)
        records.update(manifest["sources"])
        relative = "rtl/cva6/core/store_buffer.sv"
        data = contract.read_file(args.package / relative)
        sealed = dict((line.split(maxsplit=1)[1].lstrip("*"), line.split()[0])
                      for line in (args.package / "SHA256SUMS").read_text().splitlines())
        if sealed.get(relative) != contract.digest(data):
            raise ValueError("store buffer differs from package seal")
        dest = output / "inputs/package" / relative
        records[relative] = contract.freeze_bytes(dest, data)
        tb = Path(__file__).with_name("scalar_store_probe_tb.sv")
        target = output / "inputs/store_probe_tb.sv"
        records["store_probe_tb.sv"] = contract.freeze_bytes(target, tb.read_bytes())
        records["store_probe_runner.py"] = contract.freeze_bytes(
            output / "inputs/store_probe_runner.py", Path(__file__).read_bytes())
        manifest["compile_sources"] = [p for p in manifest["compile_sources"]
                                       if not p.endswith("load_unit_contract_tb.sv")]
        manifest["compile_sources"] += ["package/" + relative, "store_probe_tb.sv"]
        manifest["top"] = "scalar_store_probe_tb"
        contract.save(output / "store_probe_manifest.json", manifest)
        vcs = shutil.which("vcs")
        if not vcs:
            raise ValueError("VCS not found")
        commands = [("compile", contract.compile_command(output, vcs, manifest), 180),
                    ("run", [str(output / "build/simv")], 30)]
        for stage, command, timeout in commands:
            report[stage + "_argv"] = command
            with (output / (stage + ".log")).open("w") as log:
                result = subprocess.run(command, cwd=output / "build", stdout=log,
                                        stderr=subprocess.STDOUT, timeout=timeout)
            text = (output / (stage + ".log")).read_text()
            if result.returncode or contract.BUILD_ERROR.search(text):
                raise ValueError(stage + " failed; inspect log")
        if "STORE_PROBE_PASS checks=" not in text or "STORE_PROBE_FAIL" in text:
            raise ValueError("missing pass marker")
        if contract.changed_inputs(records):
            raise ValueError("frozen inputs changed during test")
        report["status"] = "PASS"
    except Exception as exc:
        report["error"] = str(exc)
    report["sources"] = records
    report["logs"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in output.glob("*.log")}
    contract.save(output / "store_probe_summary.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("sources", "logs")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
