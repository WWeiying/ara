#!/usr/bin/env python3
"""Stage a pinned, isolated complete FPGA package; never build or program it.

The source snapshot is suitable for integration review, not board signoff.
Original export, dependency checkouts and all prior evidence remain untouched.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification"))
from fpga.check_sources import export_inventory, read_json, relative_name, safe_path
from fpga.prepare_linux_bundle import copy_checked, file_record, plain_path, tree_records, unchanged
from ara_verify.dependency_patches import load_registry, patch_state, validate_submodules

EXPORT = ROOT / "hardware/fpga/ara_dsa_vcu118"
BASE_META = {
    "manifest.json": "0157af3a60db3eb82ea56d234b252715285e27faa2c133b6eccd15d796262eae",
    "SHA256SUMS": "f3423352c61efa2764ebbcdef8ba6beb001d1bed6e3d328b2af091cf616cb4bf",
}
PATCH_HASHES = {
    "cva6": "68074dab617acfecb9bdf9412e459507afa3d5ba8bfa18f903a674bb9bf9823c",
    "fpnew": "40aec9ca3a0ff86ba20af2363b55ec7cbd4e681339a02b73cbc3d9428936a0bc",
}
CORE = (
    "core/acc_dispatcher.sv", "core/issue_read_operands.sv", "core/csr_regfile.sv",
    "core/include/ariane_pkg.sv", "core/include/riscv_pkg.sv", "core/decoder.sv",
)
MVP = {
    "control_mvp.sv": ("9dbaa7e197c2f03dbac4f9936aec88167e183cbbe157eae47177fc6c5042e829",
                       "728111abd5a87e9f11e773dfbbb9ab8c7020b3423c896b569a55b865428fc216"),
    "defs_div_sqrt_mvp.sv": ("61108ca19adc42464d87669f54f9bc08dde7c06db72967bc054f74d0178bb2a2",
                            "14814817e16137d2ac1d4f0960dd47d7ce9b3bc289e02d4e041ac4c1da93c08f"),
    "div_sqrt_top_mvp.sv": ("be362556c28c67c5e6154cb58b61f2340f1bbb5d462396a137c45982783fe744",
                           "2abf0597d491fa7efc108d47dee6ea824017ac52e6361fda1aaeee50a3690367"),
    "norm_div_sqrt_mvp.sv": ("d44cb9b1ce2fc81f332d353ba9c1c76f2e628e90b500a46e55e76edd699a8b10",
                            "b96f2bebe6a2feb2af7e9b937cf980e6681f907c8da9bd7ecf569f15e73cfddf"),
    "nrbd_nrsc_mvp.sv": ("439f7a02775761347887d12b004f752a4850cdbb042b55f64a2d52fb8046d91b",
                         "2e405102c7704302823b9f44a51fecac89662ce0224cc902745f4f047ab08ef2"),
}
PLIC = ("rv_plic.sv", "rv_plic_gateway.sv", "rv_plic_reg_pkg.sv",
        "rv_plic_reg_top.sv", "rv_plic_target.sv")
MMIO = ("axi/src/axi_to_detailed_mem.sv", "register_interface/src/axi_to_reg_v2.sv")
LINUX = ("Image", "ara_vcu118.dtb", "fw_jump.elf", "initramfs.cpio")
# These Linux/loader additions predate this handoff but are outside the old
# export seal. Snapshot them explicitly; do not bring along old run reports or
# arbitrary unsealed application binaries as though validated with this RTL.
UNSEALED_INPUTS = (
    "linux/README.md", "linux/ara_vcu118.dts.in", "linux/build_linux_bringup.sh",
    "linux/rootfs/init", "linux/artifacts/README.md", "linux/artifacts/SHA256SUMS",
    "software/uart_load_raw.py", *("linux/artifacts/" + name for name in LINUX),
)
PRESERVE = {
    "rtl/cva6/core/load_unit.sv": "042db6cbcfdba16f6810a49de010eeb52105829e444a348df5fc7ec89f3ac7dd",
    "rtl/ara/hardware/src/lane/vmfpu.sv": "2f7b2de426a5f7c89710eec96ff3b6af05635641d1b4fb808d1f7290f4958a41",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require_hash(path, expected):
    record = file_record(path)
    require(record["sha256"] == expected, f"unreviewed input: {path}")
    return record


def capture(records, path, expected=None):
    record = file_record(path)
    if expected is not None:
        require(record["sha256"] == expected, f"unreviewed input: {path}")
    key = record["path"]
    require(key not in records or records[key] == record, f"captured input drift: {path}")
    records[key] = record
    return record


def captured_json(records, path):
    record = capture(records, path)
    value = read_json(path)
    unchanged(record)
    return value


def checked_run(directory, kind, inputs=None):
    """Bind a PASS to its raw logs, image, TB and frozen source bytes."""
    inputs = {} if inputs is None else inputs
    report = captured_json(inputs, directory / "summary.json")
    require(report["status"] == "PASS" and not report["errors"], "nonpassing run")
    require(captured_json(inputs, directory / "sources.json") == report["sources"],
            "source table differs from checked summary")
    for name, record in report["sources"].items():
        capture(inputs, Path(record["frozen"]), record["sha256"])
        if name.startswith("host/"):
            capture(inputs, Path(record["path"]), record["sha256"])
    capture(inputs, directory / "build/simv", report["simv_sha256"])
    require(kind in ("plic", "mmio"), "unknown evidence kind")
    probe_name = kind + "_signals.log"
    capture(inputs, directory / "run" / probe_name, report["probe_sha256"])
    for name in ("compile", "simulation"):
        require(report[name]["status"] == "PASS", f"nonpassing {name}")
        capture(inputs, Path(report[name]["log"]), report[name]["log_sha256"])
    # Re-evaluate the captured evidence instead of trusting a summary PASS alone.
    console = (directory / "run/console.log").read_text()
    probe = (directory / "run" / probe_name).read_text()
    if kind == "mmio":
        from run_mmio_read_contract import analyze
        analysis = analyze(console, probe)
        require(not analysis["errors"] and analysis["complete"], "MMIO re-analysis failed")
        require(analysis["counts"] == dict(ar=65, r=74, aw=6, w=6, b=6, regs=91), "MMIO coverage drift")
    else:
        from run_plic_contract import analyze
        shape = dict(block_aw=26, prio_width=3, src=58, targets=2)
        require(report["shape"] == shape, "PLIC evidence configuration drift")
        analysis = analyze(console, probe, shape)
        require(not analysis["errors"] and analysis["probe"]["transactions"] == 370,
                "PLIC re-analysis failed")
    for record in inputs.values():
        unchanged(record)
    return report


def collect(root, export, plic, mmio, linux):
    """Construct the reviewed replacement map without writing any source."""
    inputs = {}
    for name, expected in BASE_META.items():
        capture(inputs, export / name, expected)
    inventory = export_inventory(export)
    require(inventory[0]["status"] == "valid", "baseline export integrity failed")
    capture(inputs, root / "verification/patches/dependencies.json")
    registry = load_registry(root)
    core_inputs = {name: capture(inputs, root / "hardware/deps/cva6" / name) for name in CORE}
    for package, expected in PATCH_HASHES.items():
        capture(inputs, root / f"verification/patches/{package}-local-fixes.patch", expected)
        require(registry[package]["sha256"] == expected, "approved patch changed")
        repo = root / "hardware/deps" / package
        require(patch_state(root, package, repo, registry[package]["revision"]) == "applied",
                f"dependency patch drift: {package}")
        validate_submodules(repo, package)
    for record in core_inputs.values():
        unchanged(record)
    candidates = {}

    def add(target, source, expected=None, reason=""):
        relative_name(target)
        require(target not in candidates, "duplicate replacement")
        record = file_record(source) if expected is None else require_hash(source, expected)
        candidates[target] = {"source": record, "reason": reason}

    add("rtl/ara/hardware/src/ara_dispatcher.sv", root / "hardware/src/ara_dispatcher.sv",
        "59afd489ac2775f5119a70f080c1a53ef6774599f3dd1f8ee0c18577d8080d96", "verified VILL handling")
    for name in CORE:
        add("rtl/cva6/" + name, root / "hardware/deps/cva6" / name,
            core_inputs[name]["sha256"],
            reason="approved fence/stall/VS/tval fixes")
    # These five files restore the clean upstream preimage, not the quarantined
    # sticky-bit patch. The selected scalar/vector divider remains THMULTI.
    for name, (before, after) in MVP.items():
        source = "hardware/deps/fpu_div_sqrt_mvp/hdl/" + name
        target = "rtl/fpu_div_sqrt_mvp/hdl/" + name
        require_hash(export / target, before)
        add(target, root / source, after, "exclude quarantined divider patch")
    for name, expected in PRESERVE.items():
        require_hash(export / name, expected)
    for name in ("rtl/ara/hardware/src/lane/vmfpu.sv", "rtl/cva6/core/fpu_wrap.sv"):
        text = (export / name).read_text()
        require("fpnew_pkg::THMULTI" in text and "fpnew_pkg::PULP" not in text,
                "unreviewed divider configuration")

    plic_run = checked_run(root / "verification/out/plic-contract-fixed-vcs-20260922", "plic", inputs)
    mmio_run = checked_run(root / "verification/out/mmio-contract-fixed-vcs-20260922", "mmio", inputs)
    plic_manifest = captured_json(inputs, plic / "manifest.json")
    require(plic_manifest["contract_fix"]["applied"] is True, "unfixed PLIC")
    capture(inputs, root / "verification/fpga/patches/plic-contract.patch",
            plic_manifest["contract_fix"]["patch"]["sha256"])
    require(plic_manifest["configuration"]["param_values"] ==
            dict(nonstd_regs=0, prio=7, src=58, target=2), "PLIC configuration drift")
    for name in PLIC:
        expected = plic_run["sources"]["plic/rtl/" + name]["sha256"]
        add("rtl/opentitan_peripherals/src/rv_plic/rtl/" + name,
            plic / "rv_plic/rtl" / name, expected, "58 slots/2 contexts and validated PLIC fixes")
    mmio_manifest = captured_json(inputs, mmio / "manifest.json")
    capture(inputs, root / "verification/fpga/patches/mmio-read-range.patch",
            mmio_manifest["patch"]["sha256"])
    for name in MMIO:
        expected = mmio_run["sources"]["rtl/" + name]["sha256"]
        require(plic_run["sources"]["export/" + name]["sha256"] == expected,
                "PLIC and MMIO runs used different bridges")
        add("rtl/" + name, mmio / "rtl" / name, expected, "validated MMIO access/error range")

    lm = captured_json(inputs, linux / "manifest.json")
    require(lm["status"] == "PREPARED_NOT_BOOTED" and lm["inputs_unchanged"], "Linux bundle invalid")
    for name in LINUX:
        add("linux/artifacts/" + name, linux / name, lm["files"][name]["sha256"], "matched Linux bundle")
    template = plic / "ara_vcu118.dts.in"
    add("linux/ara_vcu118.dts.in", template, lm["files"]["inputs/ara_vcu118.dts.in"]["sha256"],
        reason="PLIC ndev57")
    embedded = lm["embedded_dtb"]
    fw, dtb = (linux / "fw_jump.elf").read_bytes(), (linux / "ara_vcu118.dtb").read_bytes()
    require(fw[embedded["file_offset"]:embedded["file_offset"] + len(dtb)] == dtb,
            "OpenSBI embedded DTB mismatch")
    # Current RTL fixes must be the exact inputs of the completed trap regression.
    frozen = root / "verification/out/trap-prereq-fixed-inputs-20260922"
    capture(inputs, frozen / "verification/patches/cva6-local-fixes.patch", PATCH_HASHES["cva6"])
    capture(inputs, frozen / "hardware/deps/cva6/core/decoder.sv",
            candidates["rtl/cva6/core/decoder.sv"]["source"]["sha256"])
    runs = captured_json(inputs, root / "verification/out/trap-prereq-fixed-vcs-20260922/summary.json")
    require(len(runs) == 1 and runs[0]["status"] == "PASS", "trap regression not passing")
    for record in inputs.values():
        unchanged(record)
    return candidates, registry, inputs


def stage_tree(base, destination, replacements, expected_records=None, include_paths=None):
    """Copy first, then change only explicit files. Inputs are never linked."""
    base, destination = plain_path(base), plain_path(destination)
    require(not destination.exists() and not destination.is_relative_to(base), "unsafe destination")
    records = tree_records(base, exclude_build=False)
    require(expected_records is None or records == expected_records, "baseline drift since validation")
    for name in replacements:
        relative_name(name)
        require(name in records, f"replacement target absent: {name}")
    include_paths = set(records) if include_paths is None else set(include_paths)
    require(include_paths <= records.keys(), "missing selected baseline file")
    require(set(replacements) <= include_paths, "replacement excluded from baseline copy")
    for name, record in records.items():
        if name not in include_paths:
            continue
        copy_checked({k: record[k] for k in ("path", "size_bytes", "sha256")}, destination / name)
        (destination / name).chmod(record["mode"])
    changes = []
    for name, item in replacements.items():
        target = safe_path(destination, name)
        require(target.is_file(), f"replacement target absent: {name}")
        before = file_record(target)
        unchanged(item["source"])
        data = Path(item["source"]["path"]).read_bytes()
        require(digest(data) == item["source"]["sha256"], "replacement copy drift")
        old_bytes = target.read_bytes()
        target.write_bytes(data)
        changes.append(dict(file=name, before=before["sha256"], after=digest(data),
                            changed=old_bytes != data, **item))
    require(tree_records(base, exclude_build=False) == records, "baseline changed while staging")
    for item in replacements.values():
        unchanged(item["source"])
    return records, changes


def seal(root):
    records = tree_records(root, exclude_build=False)
    (root / "SHA256SUMS").write_text("".join(
        f"{record['sha256']}  {name}\n" for name, record in sorted(records.items())
        if name != "SHA256SUMS"))


def prepare(output, root=ROOT):
    output = plain_path(output)
    require(output.is_relative_to(root / "verification/out") and
            output != root / "verification/out" and not output.exists(), "use a new verification/out directory")
    export = root / "hardware/fpga/ara_dsa_vcu118"
    plic = root / "verification/out/plic-fixed-candidate-20260922"
    mmio = root / "verification/out/mmio-fixed-candidate-20260922-03"
    linux = root / "verification/out/fpga-linux-plic58-bundle-20260922"
    initial_records = tree_records(export, exclude_build=False)
    tool_inputs = {}
    for name in ("verification/fpga/prepare_soc_candidate.py", "verification/fpga/check_sources.py",
                 "verification/fpga/prepare_linux_bundle.py", "verification/ara_verify/dependency_patches.py",
                 "hardware/fpga/vcu118/export.py", "hardware/fpga/vcu118/prepare.py",
                 "hardware/fpga/vcu118/dispatcher_fpga.py", "hardware/fpga/vcu118/dispatcher_control_fpga.py",
                 "hardware/fpga/vcu118/jtag_fpga.py", "hardware/fpga/vcu118/cdc_fpga.py"):
        capture(tool_inputs, root / name)
    replacements, registry, inputs = collect(root, export, plic, mmio, linux)
    inputs.update(tool_inputs)
    for name in ("plic-contract.patch", "mmio-read-range.patch"):
        capture(inputs, root / "verification/fpga/patches" / name)
    # Copy the sealed source package and explicitly reviewed Linux support,
    # not unrelated unsealed reports or prior application run artifacts.
    covered = {r["path"] for r in export_inventory(export)[0]["files"]} | {"SHA256SUMS"}
    selected = covered | set(UNSEALED_INPUTS)
    require(selected <= initial_records.keys(), "missing required baseline input")
    require(not any(Path(n).suffix in (".bit", ".dcp", ".ltx", ".xpr") for n in selected),
            "build artifact in source selection")
    # Exercise adapters on the current source without writing back to it.
    sys.path.insert(0, str(root / "hardware/fpga/vcu118"))
    import export as adapters
    current = (root / "hardware/src/ara_dispatcher.sv").read_text()
    text = current
    for adapter in (adapters.patch_dispatcher_vlen_casts, adapters.patch_dispatcher_layout,
                    adapters.patch_dispatcher_control):
        text = adapter(text)
    require(text == current, "dispatcher adapter changed current source")
    output.mkdir(parents=True)
    destination = output / "package"
    try:
        records, changes = stage_tree(export, destination, replacements, initial_records, selected)
        provenance = destination / "provenance/verification_handoff"
        provenance.mkdir()
        def archive(source, target):
            key = str(plain_path(source))
            require(key in inputs, f"uncaptured archive input: {source}")
            copy_checked(inputs[key], target)

        for name in BASE_META:
            archive(export / name, provenance / ("base-" + name))
        for name in ("cva6-local-fixes.patch", "fpnew-local-fixes.patch"):
            archive(root / "verification/patches" / name, provenance / name)
        for name in ("plic-contract.patch", "mmio-read-range.patch"):
            archive(root / "verification/fpga/patches" / name, provenance / name)
        for kind in ("plic", "mmio"):
            evidence = root / f"verification/out/{kind}-contract-fixed-vcs-20260922"
            archive(evidence / "summary.json", provenance / f"{kind}-summary.json")
            archive(evidence / "sources.json", provenance / f"{kind}-sources.json")
        archive(linux / "manifest.json", provenance / "linux-bundle.json")
        archive(Path(__file__), provenance / "prepare_soc_candidate.py")
        dump(provenance / "checked-inputs.json", inputs)
        (provenance / "candidate.patch").write_text("".join(
            "".join(difflib.unified_diff((export / item["file"]).read_text().splitlines(True),
                                       (destination / item["file"]).read_text().splitlines(True),
                                       fromfile="a/" + item["file"], tofile="b/" + item["file"]))
            for item in changes if item["changed"] and item["file"].endswith((".sv", ".in"))))
        manifest = read_json(destination / "manifest.json")
        manifest["revision_scope"] = "inherited base commits, not clean source claims; exact replacements in verification_handoff"
        manifest["validation"] = "ISOLATED_INTEGRATION_CANDIDATE_NOT_BUILT_NOT_BOOTED"
        manifest["created_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["verification_handoff"] = {
            "base_manifest_sha256": BASE_META["manifest.json"], "approved_dependency_patches": registry,
            "changes": changes, "preserved_special_files": PRESERVE,
            "soc_simulation": "NOT_RUN", "bitstream": "NOT_BUILT", "board_boot": "NOT_RUN",
            "unresolved": ["FPGA load_unit exception path review/validation", "full-source correspondence",
                           "full SoC IRQ/VM/Linux", "VCU118 build/board access", "custom OS context isolation"],
            "source_hash_scope": "unchanged files retain original source records; replacements use the checked incoming bytes",
            "omitted_base_files": sorted(set(records) - selected),
        }
        manifest["base_source_hashes_before_integration"] = manifest["source_hashes_before_integration"]
        manifest["source_hashes_before_integration"] = [
            {**row, "source_sha256": replacements[row["file"]]["source"]["sha256"]}
            if row["file"] in replacements else row
            for row in manifest["source_hashes_before_integration"]]
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        (destination / "CANDIDATE_STATUS.md").write_text(
            "# Isolated integration candidate\n\n"
            "PREPARED_NOT_BUILT. No bitstream, Linux boot or whole-SoC validation is claimed.\n\n"
            "This package combines approved CVA6/dispatcher fixes, the measured 58-slot/2-context "
            "PLIC and MMIO read-range fixes, and a matching ndev57 Linux payload. "
            "The quarantined PULP divider patch is removed; THMULTI stays selected.\n\n"
            "Existing FPGA adaptations, especially the paired load-unit exception changes, "
            "are retained. Their full-system integration is not yet validated. "
            "Prior validation notes in the copied documentation are historical.\n\n"
            "Exact changes and subsystem evidence are under provenance/verification_handoff/. "
            "Source hashes and successful subsystem tests do not prove whole-SoC equivalence. "
            "Do not reuse a bitstream from the original export as evidence for this candidate.\n")
        (destination / "linux/artifacts/README.md").write_text(
            "# Matched Linux candidate payload\n\n"
            "PREPARED_NOT_BOOTED. The ndev57 DTB matches the one embedded in fw_jump.elf; "
            "SHA256SUMS covers the four load artifacts. "
            "The initramfs includes the checked Linux userspace prerequisites, not a complete "
            "llama.cpp/GGUF deployment. See ../../provenance/verification_handoff/linux-bundle.json.\n")
        # Do not leave the nested checksum list referring to the old DTB/firmware.
        (destination / "linux/artifacts/SHA256SUMS").write_text("".join(
            f"{file_record(destination / 'linux/artifacts' / name)['sha256']}  {name}\n" for name in LINUX))
        dump(provenance / "changes.json", manifest["verification_handoff"])
        seal(destination)
        integrity = export_inventory(destination)[0]
        require(integrity["status"] == "valid", "candidate seal failed")
        require(tree_records(export, exclude_build=False) == records, "baseline input drift")
        for item in replacements.values():
            unchanged(item["source"])
        for record in inputs.values():
            unchanged(record)
        # Unexpected RTL differences are rejected, even when the package is sealed.
        actual = {n for n, r in records.items() if n.startswith("rtl/") and
                  file_record(destination / n)["sha256"] != r["sha256"]}
        expected = {item["file"] for item in changes if item["changed"] and item["file"].startswith("rtl/")}
        require(actual == expected, "unlisted RTL delta")
        report = dict(status="PREPARED_NOT_BUILT", package=str(destination),
                      changed_rtl=sorted(actual), changed_files=changes, input_unchanged=True,
                      omitted_base_files=sorted(set(records) - selected),
                      export_integrity=integrity["status"], soc_simulation="NOT_RUN", board_boot="NOT_RUN")
        dump(output / "manifest.json", report)
        return report
    except BaseException as error:
        dump(output / "failure.json", dict(status="FAIL", error=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = prepare(args.output)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        parser.exit(1, f"SoC candidate preparation failed: {error}\n")
    print(json.dumps({k: report[k] for k in ("status", "package", "changed_rtl", "board_boot")}, indent=2))


if __name__ == "__main__":
    main()
