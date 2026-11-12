#!/usr/bin/env python3
"""Check source identity and effective optimization hierarchy without Vivado."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from export import optimization_defines, patch_akv_byte_counts, patch_qbs_fault_decode
from sync import digest, read_hashes


def check_sources(package):
    manifest = json.loads((package / "manifest.json").read_text())
    expected = {"ARA_QBS_ENABLE": 1, "ARA_AKV_ENABLE": 1, "ARA_AKV_V2_ENABLE": 1,
                **optimization_defines("candidate_all")}
    for name, value in expected.items():
        if manifest["defines"].get(name) != value:
            raise RuntimeError(f"Missing enabled selector: {name}")
    if {"TARGET_SRAM_MC", "FOR_VERIFY", "IDEAL_DISPATCHER"} & manifest["defines"].keys():
        raise RuntimeError("Verification or ASIC memory selector in FPGA package")
    if manifest["defines"].get("VLEN") != 1024 or manifest["defines"].get("NR_LANES") != 4:
        raise RuntimeError("Candidate geometry changed")
    sums = read_hashes(package)
    for name, value in sums.items():
        if digest(package / name) != value:
            raise RuntimeError(f"Package identity mismatch: {name}")
    transforms = {
        "hardware/src/vlsu/qbs/qbs_engine.sv": patch_qbs_fault_decode,
        "hardware/src/vlsu/akv/akv_engine.sv": patch_akv_byte_counts,
    }
    checked = []
    for row in manifest["source_hashes_before_integration"]:
        name = row["file"]
        if not name.startswith("rtl/ara/hardware/"):
            continue
        source = name[len("rtl/ara/"):]
        raw = (ROOT / source).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["source_sha256"]:
            raise RuntimeError(f"Main source identity mismatch: {source}")
        transformed = transforms.get(source, lambda text: text)(raw.decode()).encode()
        if (package / name).read_bytes() != transformed:
            raise RuntimeError(f"Unexpected FPGA source delta: {source}")
        checked.append(source)
    for directory in (ROOT / "hardware/src", ROOT / "hardware/include"):
        for source in directory.rglob("*"):
            if source.is_file() and source.suffix in (".sv", ".svh"):
                relative = source.relative_to(ROOT).as_posix()
                if relative in {"hardware/src/accel_dispatcher_ideal.sv",
                                "hardware/src/ara_soc.sv", "hardware/src/ara_system.sv"}:
                    continue  # Verification-only dispatcher / replaced Cheshire SoC wrappers.
                if relative not in checked:
                    raise RuntimeError(f"Main RTL omitted from export: {relative}")
    files = manifest["files"]
    if len(files) != len(set(files)):
        raise RuntimeError("Duplicate compilation file")
    source_tcl = (package / "scripts/sources.tcl").read_text()
    for name in files + manifest["include_dirs"]:
        if not (package / name).exists() or "{" + name + "}" not in source_tcl:
            raise RuntimeError(f"Missing source or Tcl list entry: {name}")
    for name, value in expected.items():
        if "{" + name + "=" + str(value) + "}" not in source_tcl:
            raise RuntimeError(f"Selector missing from actual Tcl list: {name}")
    return {"ara_source_records": len(checked), "compilation_files": len(files),
            "package_hash_records": len(sums), "enabled_selectors": expected}


def check_hierarchy(package):
    checker = HERE / "check_rtl.py"
    namespace = {"__name__": "__main__", "__file__": str(checker)}
    old_argv = sys.argv
    sys.argv = [str(checker), str(package), "--profile", "dual_ddr_ethernet", "--allow-vendor-ip"]
    try:
        try:
            exec(compile(checker.read_text(), str(checker), "exec"), namespace)
        except SystemExit as result:
            if result.code:
                raise RuntimeError(f"Existing full FPGA checker failed: {result.code}") from result
    finally:
        sys.argv = old_argv
    root = namespace["compilation"].getRoot()
    base = "ara_dsa_vcu118.i_cheshire_soc.gen_cva6_cores[0].gen_ara.i_ara"
    found = []

    def require(suffix, definition=None, value=None):
        path = base + suffix
        symbol = root.lookupName(path)
        if symbol is None or getattr(symbol, "isUninstantiated", False):
            raise RuntimeError(f"Optimization not elaborated: {path}")
        if definition is not None and symbol.definition.name != definition:
            raise RuntimeError(f"Unexpected implementation at {path}")
        if value is not None and int(symbol.value.value) != value:
            raise RuntimeError(f"Disabled/mismatched parameter at {path}")
        found.append(path)

    require(".QbsLaneMulSupported", value=1)
    require(".i_dispatcher.QbsCooperativeMul", value=1)
    for lane in range(4):
        prefix = f".gen_lanes[{lane}].i_lane"
        require(prefix + ".EnableResidentPv", value=1)
        require(prefix + ".EnableResidentQk", value=1)
        require(prefix + ".gen_resident_pv.i_resident_pv", "akv_resident_pv_lane")
        vmfpu = prefix + ".i_vfus.i_vmfpu"
        require(vmfpu + ".SharedFma", value=1)
        require(vmfpu + ".QbsLaneMulEnabled", value=1)
        require(vmfpu + ".i_shared_mul", "simd_mul_shared")
        for width in (8, 16, 32, 64):
            legacy = root.lookupName(base + vmfpu + f".i_simd_mul_ew{width}")
            if legacy is not None and not getattr(legacy, "isUninstantiated", False):
                raise RuntimeError("Legacy multiplier bank survived shared-multiplier selection")
        require(vmfpu + ".gen_qbs_mul_borrow.i_borrow", "qbs_lane_mul_borrow")
        require(vmfpu + ".fpu_gen.i_fpnew_bulk.gen_shared.gen_group[0].gen_fma.i_fma",
                "simd_fma_shared")
        require(vmfpu + ".fpu_gen.i_fpnew_bulk.gen_shared.gen_group[0].gen_fma.i_fma.CompactPipeline",
                value=1)
    require(".i_vlsu.ResidentPvSupported", value=1)
    require(".i_vlsu.ResidentQkSupported", value=1)
    require(".i_vlsu.gen_resident_pv.i_control", "akv_resident_pv_control")
    require(".i_vlsu.i_shared_reader", "qbs_akv_shared_reader")
    return {"checks": len(found), "checked_paths": found,
            "vendor_ip_not_elaborated": True, "board_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("Refusing existing evidence file")
    result = {"sources": check_sources(args.package.resolve())}
    result["hierarchy"] = check_hierarchy(args.package.resolve())
    result["state"] = "SOURCE_AND_EFFECTIVE_HIERARCHY_PASS_NOT_BITSTREAM_ACCEPTANCE"
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
