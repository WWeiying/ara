#!/usr/bin/env python3
"""Run bounded checks on uploaded, unmodified Vivado functional netlists."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="Directory with manifest.json and evidence.zip")
    parser.add_argument("output", type=Path, help="New local result directory")
    args = parser.parse_args()
    iverilog, vvp = shutil.which("iverilog"), shutil.which("vvp")
    if not iverilog or not vvp:
        parser.error("Icarus Verilog and vvp are required")
    tests = Path(__file__).resolve().parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"scope": "Archived LLC cutter, splitter, read-address and write-unit logic only",
              "not_tested": ["inter-module wiring", "JTAG IP and live AXI commands",
                             "memory storage/read data path", "timing"],
              "stages": [], "passed": False}
    try:
        manifest = json.loads((args.evidence / "manifest.json").read_text(encoding="utf-8-sig"))
        archive = args.evidence / "evidence.zip"
        if sha(archive.read_bytes()) != manifest["archive_sha256"]:
            raise ValueError("Archive hash mismatch")
        with zipfile.ZipFile(archive) as bundle:
            for item in manifest["files"]:
                data = bundle.read(item["path"])
                if len(data) != item["bytes"] or sha(data) != item["sha256"]:
                    raise ValueError(f"File hash mismatch: {item['path']}")
            for name in ("i_read_unit.v", "i_write_unit.v", "i_ar_splitter.v", "i_aw_splitter.v"):
                (output / name).write_bytes(bundle.read("netlist/" + name))
        record["archive_sha256"] = manifest["archive_sha256"]
        record["inputs"] = manifest["files"]
        stages = (
            ("ar_cutter", "host_llc_cutter_netlist_tb.sv", "i_ar_splitter.v", []),
            ("ar_splitter", "host_llc_splitter_netlist_tb.sv", "i_ar_splitter.v", []),
            ("aw_splitter", "host_llc_splitter_netlist_tb.sv", "i_aw_splitter.v", ["-DWRITE_CUTTER"]),
            ("read_unit", "host_llc_read_netlist_tb.sv", "i_read_unit.v", []),
            ("write_unit", "host_llc_write_netlist_tb.sv", "i_write_unit.v", []),
        )
        for name, bench, netlist, defines in stages:
            stage = {"name": name, "bench_sha256": sha((tests / bench).read_bytes()), "passed": False}
            record["stages"].append(stage)
            command = [iverilog, "-g2012", *defines, "-s", "tb", "-s", "glbl", "-o",
                       str(output / (name + ".vvp")), str(tests / bench), str(output / netlist)]
            stage["compile"] = command
            with (output / (name + ".compile.log")).open("w") as stream:
                subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=30)
            with (output / (name + ".log")).open("w") as stream:
                subprocess.run([vvp, str(output / (name + ".vvp"))], stdout=stream,
                               stderr=subprocess.STDOUT, check=True, timeout=120)
            log = (output / (name + ".log")).read_text()
            marker = next((line for line in log.splitlines() if line.startswith("PASS ")), None)
            if marker is None:
                raise ValueError(f"Missing PASS marker: {name}")
            stage.update(passed=True, result=marker)
            print(f"{name}: {marker}", flush=True)
        record["passed"] = True
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        record["error"] = str(exc)
        raise SystemExit(f"FAILED: {exc}; inspect {output}") from None
    finally:
        (output / "result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"EVIDENCE {output}")


if __name__ == "__main__":
    main()
