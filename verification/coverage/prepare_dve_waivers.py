#!/usr/bin/env python3
"""Prepare reviewed, design-bound DVE exclusions; never edits input VDBs."""
import argparse
import csv
import gzip
import hashlib
import json
import re
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
APPROVED = {
    "91339887780e3c2cda547e2ec3b19bd2c6617a131dff5911fb61606c9241d321": "repair-closure-20260927",
    "bf767acd21b7998baf850702403144b36c1eae56fcec1d5aba0c554ecfb454c2": "coverage-20260927",
}
SHAPES = {
    "repair-closure-20260927": "f54120bdce5c7b51f387f40afc07ef70db2cdae01e8a1852beba0c8e32b96833",
    "coverage-20260927": "d1e3e5fa5a0f5fd134797e7aa7f69a9219d77a60513eee6214caf9975bf4ca27",
}
# Only observational verification modules, not memory models or AXI drivers.
MONITORS = {
    "llm_perf_monitor", "vrf_perf_monitor", "ara_commit_monitor",
    "ara_acc_contract_monitor", "ara_fault_vstart_probe",
    "uvm_custom_install_verdi_recording",
}


def approved_points():
    points = set()
    for lane in range(4):
        for queue in ("alu_a", "alu_b", "mfpu_a", "mfpu_b", "mfpu_c", "mask_b"):
            path = (f"ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{lane}].i_lane."
                    f"i_operand_queues.i_operand_queue_{queue}")
            points.update((path, kind) for kind in ("Block 7", "Block 172", "Toggle flush_i"))
            if queue in ("alu_a", "alu_b"):
                points.update((path, f"Branch {n} (0)") for n in (2, 7))
    return points


def exclusion_items(text):
    """Read only the reviewed native syntax, rejecting wider/unknown directives."""
    result, path, has_point = set(), None, False
    def finish():
        if path is not None and not has_point:
            result.add((path, "INSTANCE"))
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("//", "CHECKSUM:", "ANNOTATION:")):
            continue
        if line.startswith("INSTANCE:"):
            finish()
            path, has_point = line.split(":", 1)[1].strip(), False
            continue
        if path is None:
            raise ValueError("Exclusion outside an instance")
        if m := re.fullmatch(r'Block (\d+)(?:\s+"[^"]*"\s+"[^"]*")?', line):
            key = "Block " + m[1]
        elif m := re.fullmatch(r'Branch (\d+)(?:\s+"[^"]*"\s+"[^"]*")?\s+\((\d+)\)(?:\s+"[^"]*")?', line):
            key = f"Branch {m[1]} ({m[2]})"
        elif re.fullmatch(r'Toggle flush_i(?:\s+"[^"]*")?', line):
            key = "Toggle flush_i"
        else:
            raise ValueError(f"Unreviewed exclusion directive: {line}")
        result.add((path, key))
        has_point = True
    finish()
    return result


def scopes(data):
    root = ET.fromstring(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
    nodes = {i.get("id"): (i, d.get("name"))
             for d in root.findall("srcdef") for i in d.findall("srcinst")}
    def path(key):
        node, _ = nodes[key]
        return ((path(node.get("pid")) + ".") if node.get("pid") in nodes else "") + node.get("name")
    result = []
    for key, (node, module) in nodes.items():
        if module in MONITORS:
            result.append((path(key), 1, "Verification-only observer; excluded from product RTL code coverage"))
    if not result:
        raise ValueError("Approved design has no expected verification observers")
    return sorted(result)


def prepare(design, output, mode):
    source = design / "snps/coverage/db/design/verilog.design.xml"
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    record = {"design_sha256": digest, "policy": "reviewed-v1", "mode": mode,
              "raw_report": "summary.csv", "waived_report": None}
    if mode == "off":
        record["status"] = "DISABLED"
    elif digest not in APPROVED:
        record["status"] = "NOT_APPLICABLE_UNREVIEWED_DESIGN"
    else:
        shape_dir = design / "snps/coverage/db/shape"
        shape_files = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                       for f in sorted(shape_dir.iterdir()) if f.is_file()}
        shape_hash = hashlib.sha256(json.dumps(shape_files, sort_keys=True).encode()).hexdigest()
        if shape_hash != SHAPES[APPROVED[digest]]:
            raise ValueError("Coverage point shapes differ from reviewed design")
        record["shape_files"] = shape_files
        entries = scopes(data)
        lines = ["set waiver_scopes {"]
        for path, recursive, reason in entries:
            if any(c in path for c in "{}\\\n\r"):
                raise ValueError("Unsafe instance path")
            lines.append(f"  {{{path}}} {recursive} {{{reason}}}")
        lines.append("}")
        (output / "waiver_plan.tcl").write_text("\n".join(lines) + "\n")
        points = HERE / "waivers/operand_flush.el"
        if exclusion_items(points.read_text()) != approved_points():
            raise ValueError("Native point exclusions differ from approved exact set")
        shutil.copyfile(points, output / "points.el")
        record["points_sha256"] = hashlib.sha256(points.read_bytes()).hexdigest()
        record.update(status="PREPARED", configuration=APPROVED[digest], scopes=entries,
                      waived_report="summary_waived.csv")
    (output / "waiver_status.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def finalize(design, output):
    record = json.loads((output / "waiver_status.json").read_text())
    digest = hashlib.sha256((design / "snps/coverage/db/design/verilog.design.xml").read_bytes()).hexdigest()
    if digest != record["design_sha256"]:
        raise ValueError("Compiled design changed during DVE export")
    if record["status"] != "PREPARED":
        return
    for name, expected in record["shape_files"].items():
        if hashlib.sha256((design / "snps/coverage/db/shape" / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Input coverage shape changed during DVE export")
    for name in ("summary.csv", "summary_waived.csv"):
        with (output / name).open() as stream:
            rows = list(csv.DictReader(stream))
        if not rows or not {"Line", "Condition", "Branch", "FSM", "Toggle"} <= rows[0].keys():
            raise ValueError("Incomplete DVE coverage report")
    exclusion = (output / "exclusions.el").read_text()
    expected = approved_points() | {(p, "INSTANCE") for p, _, _ in record["scopes"]}
    if exclusion_items(exclusion) != expected:
        raise ValueError("DVE saved missing or additional unapproved exclusions")
    record.update(status="APPLIED", files={name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                  for name in ("summary.csv", "summary_waived.csv", "exclusions.el")})
    (output / "waiver_status.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--design", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--mode", choices=("auto", "off"), default="auto")
    p.add_argument("--finalize", action="store_true")
    a = p.parse_args()
    if a.finalize:
        finalize(a.design, a.output)
    else:
        print(prepare(a.design, a.output, a.mode)["status"])
