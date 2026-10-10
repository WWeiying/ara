#!/usr/bin/env python3
"""Prepare review-only FF1 native capture input; deliberately has no launch action."""
import argparse
import json
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True
import inventory_operand_debug as compiled
from test_ff1_parent_width_scope import FF1ParentWidthTests
from test_divsqrt_ff1_width_scope import FF1WidthScopeTests, CORE
from capture_operand_debug import require, sha, write, OUT, ROOT, tool

INVENTORY = OUT / "ff1-width-candidates-701-20261006-01.json"
INVENTORY_SHA = "047af7942df5443f77d774a63887a135d16a8925d594adc93d96ee5a57ed7a92"
MAPPING = OUT / "ff1-case-calibration-20261006-02/mapping.json"
MAPPING_SHA = "fd50e6f852836c3147bc3230f0e75599153e8410f148cbb78fd96f8d3d6a1edd"
CORPUS = OUT / "gap94-offline-admitted-701-20261006-01"
BUILD = OUT / "repaired-aligned-build-20260930-01/build-source-pins.json"


def parameter_block(text, module, instance):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    blocks = []
    for match in re.finditer(r'\b' + re.escape(module) + r'\s*#\s*\(', text):
        start, depth, end = match.end(), 1, match.end()
        while depth and end < len(text):
            depth += (text[end] == '(') - (text[end] == ')')
            end += 1
        require(depth == 0, "Unterminated parameter block")
        suffix = text[end:]
        # ara_soc has a parameterized RTL arm and a bare gatesim arm sharing i_system.
        if module == "ara_system" and instance == "i_system":
            suffix = re.sub(r'^\s*`else\s+ara_system\s+`endif', '', suffix, count=1)
        if re.match(r'\s*' + re.escape(instance) + r'\s*\(', suffix):
            blocks.append(text[start:end - 1])
    require(len(blocks) == 1, "Missing/duplicate exact instance")
    return blocks[0]


def exact_forward(text, module, instance):
    block = parameter_block(text, module, instance)
    values = re.findall(r'\.FPUSupport\s*\(\s*([^()]*)\s*\)', block)
    require(len(values) == 1 and values[0].strip() == "FPUSupport", "FPUSupport forwarding differs")
    require(not re.search(r'\bdefparam\b', re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)),
            "Source defparam requires separate review")
    return dict(module=module, instance=instance, parameter="FPUSupport", value="FPUSupport")


def decision(case, raw, hit, inner, indices):
    require(inner in range(4) and case in indices and indices[case] == raw, "Case/raw calibration differs")
    target = 0 <= case < (0, 29, 42, 42)[inner]
    require(not (target and hit), "Hit contradicts narrow structural bound")
    return target


def prepare(output):
    require(output.parent == OUT and not output.exists() and not output.is_symlink(), "Fresh direct output required")
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c)
                               for c in (FF1ParentWidthTests, FF1WidthScopeTests))
    require(unittest.TextTestRunner().run(suite).wasSuccessful(), "Frozen parent/width proof failed")
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased input")
        value = sha(path)
        require(expected is None or value == expected, "Pin differs: " + str(path))
        require(str(path) not in pins or pins[str(path)] == value, "Conflicting pin")
        pins[str(path)] = value
        return path
    inventory = json.loads(pin(INVENTORY, INVENTORY_SHA).read_bytes())
    mapping = json.loads(pin(MAPPING, MAPPING_SHA).read_bytes())
    require(inventory["status"] == "FF1_NARROW_904_CANDIDATES_NOT_NATIVE_QUALIFIED" and inventory["tests"] == 701 and
            mapping["status"] == "STANDALONE_FF1_CASE_MAPPING_NOT_NATIVE_EXCLUSION" and mapping["cases"] == 54,
            "Wrong static evidence")
    for path, expected in inventory["pins"].items():
        pin(path, expected)
    indices = {r["case"]: r["raw_index"] for r in mapping["observations"]}
    require(len(mapping["observations"]) == 54 and set(indices) == {-2, -1, *range(52)} and
            set(indices.values()) == set(range(54)), "Incomplete calibration")
    bitmap = json.loads(pin(CORPUS / "combined-bits.json").read_bytes())
    status = json.loads(pin(CORPUS / "status.json").read_bytes())
    require(status["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and status["aggregate_passed"] == 701,
            "Not admitted701")
    listing = pin(CORPUS / "combined-inputs.txt").read_text().splitlines()
    require(len(listing) == len(set(listing)) == 702 and listing[1:] == bitmap["tests"] and
            len({str(Path(p).resolve()) for p in listing}) == 702, "Wrong corpus membership")
    for path, expected in bitmap["input_hashes"].items():
        pin(path, expected)
    design = compiled.Design(Path(listing[0]))
    for relative, expected in bitmap["design"].items():
        pin(design.db / relative, expected)
    pin(design.db / "auxiliary/verilog.sourceinfo.xml")
    build = json.loads(pin(BUILD).read_bytes())
    names = ["hardware/deps/fpnew/src/" + n for n in ("fpnew_pkg.sv", "fpnew_top.sv", "fpnew_opgroup_block.sv",
             "fpnew_opgroup_multifmt_slice.sv", "fpnew_divsqrt_th_64_multi.sv")]
    names += [CORE + n for n in ("ct_vfdsu_prepare.v", "ct_vfdsu_scalar_dp.v", "ct_vfdsu_ff1.v", "ct_vfdsu_top.v")]
    names += ["hardware/" + n for n in ("src/lane/vmfpu.sv", "tb/ara_testharness.sv", "src/ara_soc.sv",
              "src/ara_system.sv", "src/ara.sv", "src/lane/lane.sv", "src/lane/vector_fus_stage.sv", "include/ara_pkg.sv")]
    for name in names:
        pin(ROOT / name, build[str(ROOT / name)])
    forwarding = []
    for name, module, instance in (("hardware/src/ara_soc.sv", "ara_system", "i_system"),
            ("hardware/src/ara_system.sv", "ara", "i_ara"), ("hardware/src/ara.sv", "lane", "i_lane"),
            ("hardware/src/lane/lane.sv", "vector_fus_stage", "i_vfus"),
            ("hardware/src/lane/vector_fus_stage.sv", "vmfpu", "i_vmfpu")):
        forwarding.append(dict(source=str(ROOT / name), **exact_forward((ROOT / name).read_text(), module, instance)))
    harness = parameter_block((ROOT / "hardware/tb/ara_testharness.sv").read_text(), "ara_soc", "i_ara_soc")
    require(not re.search(r'\bFPUSupport\b', harness), "Harness FPUSupport override")
    compile_command = json.loads(pin(BUILD.parent / "compile.command.json").read_bytes())["command"]
    scopes, targets, protected, positions = {}, [], [], set()
    inverse = {raw: case for case, raw in indices.items()}
    for scope, record in bitmap["metrics"]["branch"].items():
        if ".i_ara." not in scope or not scope.endswith(("x_frac0_expnt", "x_frac1_expnt")):
            continue
        outer = re.search(r'\.gen_lanes\[([0-3])\]\.i_lane\.', scope)
        inner = re.search(r'\.gen_num_lanes\[([0-3])\]\.', scope)
        require(outer and inner, "Invalid generated parent instance")
        pos = int(outer[1]), int(inner[1]), scope.rsplit(".", 1)[1]
        require(pos not in positions, "Duplicate physical instance")
        positions.add(pos)
        source = design.source(scope)
        require(source["module"] == "ct_vfdsu_ff1" and source["resolved_path"] == str(ROOT / (CORE + "ct_vfdsu_ff1.v")),
                "Compiled source owner differs")
        definition = design.definition(scope, "branch")
        require(record["width"] == 54 and record["checksum"] == mapping["checksum"] == definition.get("chksum"),
                "Compiled shape/calibration differs")
        points = compiled.points("branch", definition, 54)
        require(len(points) == 54 and {p["raw_index"] for p in points} == set(range(54)), "Incomplete compiled shape")
        rows = []
        for point in points:
            raw = point["raw_index"]
            case = inverse[raw]
            hit = bool(int(record["bits"], 16) & (1 << (53 - raw)))
            target = decision(case, raw, hit, pos[1], indices)
            original = dict(scope=scope, input_bit=case, raw_index=raw, hit=hit, checksum=record["checksum"],
                            low_zero_bits=(0, 29, 42, 42)[pos[1]])
            (targets if target else protected).append(original)
            rows.append(dict(calibration=original, target=target, point=point))
        scopes[scope] = dict(source=source, physical_position=list(pos), parent_width=(64, 32, 16, 16)[pos[1]],
                             module_checksum=source["definition_checksum"], metric_checksum=record["checksum"], rows=rows)
    require(positions == {(o, i, p) for o in range(4) for i in range(4) for p in ("x_frac0_expnt", "x_frac1_expnt")},
            "Incomplete parent instance coverage")
    require(len(targets) == 904 and len(protected) == 824 and
            sorted(targets, key=lambda r: (r["scope"], r["raw_index"])) == sorted(inventory["targets"], key=lambda r: (r["scope"], r["raw_index"])) and
            sorted(protected, key=lambda r: (r["scope"], r["raw_index"])) == sorted(inventory["protected"], key=lambda r: (r["scope"], r["raw_index"])),
            "Exact inventory differs")
    sample = Path(listing[-1])
    dirs = list((sample / "snps/coverage/db/testdata").iterdir())
    require(len(dirs) == 1 and dirs[0].is_dir(), "Ambiguous single test")
    for path in sample.rglob("*"):
        if path.is_file():
            pin(path)
    identity = tool.prepare("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve", "/usr/bin/xvfb-run")
    for path in (Path(__file__), Path(__file__).with_name("test_prepare_ff1_native904.py"),
                 Path(__file__).with_name("test_ff1_parent_width_scope.py"), Path(__file__).with_name("test_divsqrt_ff1_width_scope.py"),
                 Path(compiled.__file__), Path(__file__).with_name("closure_point_inventory.py"),
                 Path(__file__).parent / "reviewed_20261004/audit_readonly.py", Path(tool.__file__)):
        pin(path)
    for path, expected in pins.items():
        require(sha(path) == expected, "Input changed during prepare")
    config = dict(status="FF1_NATIVE904_STATIC_CONFIG_REQUIRES_PARENT_REVIEW_NO_DVE", tests=701, targets=904,
                  protected=824, scopes=scopes, pins=pins, design_vdb=listing[0], selected_test_vdb=str(sample),
                  selected_test=str(sample.with_suffix("") / dirs[0].name), tool_identity=identity,
                  native_selectors_qualified=False, default_and_zero_protected=True, RTL_changed=False,
                  application_approval=False, launch_allowed=False,
                  exact_FPUSupport_forwarding=forwarding, harness_FPUSupport_override=False,
                  requested_compile_command=compile_command, effective_compile_flags_defparam_audit_complete=False,
                  required_capture_contract="Observed exact selectors for all1728 positions; exact904 export/reset/import/export; all824 neighbors unchanged; finally globally empty")
    output.mkdir()
    write(output / "config.json", config)
    print(config["status"] + " seal=" + sha(output / "config.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output.absolute())
