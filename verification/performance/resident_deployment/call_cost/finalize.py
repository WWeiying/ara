#!/usr/bin/env python3
"""Attach independent RTL evidence to a checked software bundle, without board access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--rtl-result", type=Path, required=True)
    a = p.parse_args()
    out = a.candidate.resolve()
    board = out / "board"
    qualification = json.loads((out / "qualification.json").read_text())
    rtl = json.loads(a.rtl_result.read_text())
    assert qualification["state"] == "HOST_SPIKE_LINUX_CHECKED_BOARD_PENDING"
    assert rtl["state"] == "REAL_KERNEL_COMPUTE_RTL_CHECKED" and rtl["post_pins_match"]
    assert sha(out / "module/sdk/ara_resident_compute_core.o") == rtl["core_sha256"]
    assert sha(board / "ara_resident.ko") == qualification["module_sha256"]
    assert sha(board / "resident-ggml-pair") == qualification["elf_sha256"]
    for path, expected in json.loads((out / "check-source-pins.json").read_text()).items():
        assert sha(path) == expected, path
    receipt = dict(state="HOST_SPIKE_LINUX_AND_RTL_CHECKED_BOARD_PENDING", board_tested=False,
        hardware_changed=False, performance_claim=False, software_qualification=qualification,
        rtl_qualification=rtl, rtl_report=str(a.rtl_result.resolve()),
        rtl_report_sha256=sha(a.rtl_result), source_pins=str(out / "check-source-pins.json"),
        source_pins_sha256=sha(out / "check-source-pins.json"), finalize_sha256=sha(__file__))
    with (board / "acceptance.json").open("x") as f:
        json.dump(receipt, f, indent=2)
        f.write("\n")
    shutil.copyfile(Path(__file__).with_name("HANDOFF_ZH.md"), board / "HANDOFF_ZH.md")
    shutil.copyfile(Path(__file__).with_name("run_cost_pair.sh"), board / "run_cost_pair.sh")
    subprocess.run(["sh", "-n", str(board / "run_cost_pair.sh")], check=True)
    (board / "SHA256SUMS").write_text("".join(f"{sha(f)}  {f.name}\n" for f in sorted(board.iterdir())
                                            if f.is_file() and f.name != "SHA256SUMS"))
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=board, check=True)
    archive = out / "resident-call-cost-checked.tar.gz"
    assert not archive.exists()
    subprocess.run(["tar", "-czf", str(archive), "-C", str(out), "board"], check=True)
    print(json.dumps({"state": receipt["state"], "archive": str(archive), "sha256": sha(archive)}))


if __name__ == "__main__":
    main()
