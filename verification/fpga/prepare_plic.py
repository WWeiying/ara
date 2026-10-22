#!/usr/bin/env python3
"""Generate the pinned Cheshire PLIC in a fresh, isolated candidate directory.

This prepares hardware/software inputs; it does not modify the FPGA export,
build a bitstream, or establish Linux/board correctness.
--fix-contract applies the pinned core-template patch only in a separate working
copy. The input snapshots remain pristine; generation is not functional proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

if __package__:
    from .prepare_linux_bundle import (NativeRunner, copy_checked, file_record,
                                       native_tool, plain_path, save_json,
                                       tree_digest, tree_records, unchanged)
else:
    from prepare_linux_bundle import (NativeRunner, copy_checked, file_record,
                                      native_tool, plain_path, save_json,
                                      tree_digest, tree_records, unchanged)


ROOT = Path(__file__).resolve().parents[2]
REVISIONS = {
    "cheshire": "cd73fd892a09da8aa9ae03171c0338bd3873007c",
    "opentitan_peripherals": "cd3153de2783abd3d03d0595e6c4b32413c62f14",
    "register_interface": "ae616e5a1ec2b41e72d200e5ab09c65e94aebd3d",
}
SUBSETS = {
    "cheshire": ["hw/rv_plic.cfg.hjson"],
    "opentitan_peripherals": ["util", "src/rv_plic/tpl/rv_plic", "requirements.txt"],
    "register_interface": ["vendor/lowrisc_opentitan/util"],
}
CONFIG = {"src": 58, "target": 2, "prio": 7, "nonstd_regs": 0}
RTL = ("rv_plic.sv", "rv_plic_gateway.sv", "rv_plic_target.sv",
       "rv_plic_reg_pkg.sv", "rv_plic_reg_top.sv")
CONTRACT_TEMPLATE = "src/rv_plic/tpl/rv_plic/rtl/rv_plic.sv.tpl"
CONTRACT_TEMPLATE_SHA256 = "fb759a7b69af346104bb64e0e6e338526c9ea64023701afdf52027d8fe329631"
CONTRACT_PATCH = Path(__file__).with_name("patches") / "plic-contract.patch"
CONTRACT_PATCH_SHA256 = "c67ae55aa10cd1901142b1ecf028901ee36c80fbf48db7278e4e575907dd3f13"


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout


def snapshot(repo: Path, name: str, destination: Path) -> dict:
    repo = plain_path(repo)
    revision, subsets = REVISIONS[name], SUBSETS[name]
    if git(repo, "rev-parse", "HEAD").decode().strip() != revision:
        raise ValueError(f"unexpected {name} revision; no reset/download is performed")
    if git(repo, "status", "--porcelain", "--untracked-files=no", "--", *subsets):
        raise ValueError(f"modified {name} generator inputs; review before generating")
    rows = git(repo, "ls-tree", "-rz", revision, "--", *subsets).split(b"\0")
    records = {}
    for row in rows:
        if not row:
            continue
        metadata, relative = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        relative = relative.decode()
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError(f"unsupported generator input: {name}/{relative}")
        source = plain_path(repo / relative)
        content = source.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if blob != oid:
            raise ValueError(f"input does not match pinned blob: {source}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)
        target.chmod(int(mode, 8) & 0o777)
        records[relative] = {"source": str(source), "git_blob": oid,
                             "sha256": hashlib.sha256(content).hexdigest()}
    if not records:
        raise ValueError(f"no generator inputs for {name}")
    return {"root": str(repo), "revision": revision, "files": records}


def assert_unchanged(inputs: dict, frozen: Path) -> None:
    for name, record in inputs.items():
        for relative, row in record["files"].items():
            for path in (Path(row["source"]), frozen / name / relative):
                if file_record(path)["sha256"] != row["sha256"]:
                    raise ValueError(f"generator input changed: {path}")


def candidate_dts(template: str) -> str:
    # This explicit, single-property migration is checked against the actual
    # generated PLIC by check_plic; it is not a general DTS parser.
    old = "riscv,ndev = <51>;"
    if template.count(old) != 1 or template.count("riscv,ndev") != 1:
        raise ValueError("unexpected DTS ndev input; review the migration")
    return template.replace(old, "riscv,ndev = <57>;")


def contract_working_copy(output: Path, runner: NativeRunner, record: dict) -> Path:
    """Apply only the audited patch, never to frozen or external inputs."""
    frozen = output / "inputs/opentitan_peripherals"
    before = tree_records(frozen, exclude_build=False)
    if before[CONTRACT_TEMPLATE]["sha256"] != CONTRACT_TEMPLATE_SHA256:
        raise ValueError("contract template preimage does not match audited input")
    patch_source = file_record(CONTRACT_PATCH)
    if patch_source["sha256"] != CONTRACT_PATCH_SHA256:
        raise ValueError("contract patch hash does not match audited patch")
    patch = output / "inputs/patches/plic-contract.patch"
    copy_checked(patch_source, patch)
    record.update(patch_source=patch_source, patch=file_record(patch),
                  template_before=before[CONTRACT_TEMPLATE])
    working = output / "work/opentitan_peripherals"
    shutil.copytree(frozen, working)
    if tree_digest(tree_records(working, exclude_build=False)) != tree_digest(before):
        raise ValueError("contract working copy does not match frozen inputs")
    tool = native_tool("patch")
    record["patch_tool"] = tool
    record["patch_version"] = runner.run([tool["argv0"], "--version"], working,
                                          "patch-version", timeout=30)
    argv = [tool["argv0"], "--batch", "--forward", "--fuzz=0",
            "--no-backup-if-mismatch", "-p1", "--input", str(patch)]
    runner.run([*argv, "--dry-run"], working, "contract-patch-check", timeout=30)
    runner.run(argv, working, "contract-patch-apply", timeout=30)
    after = tree_records(working, exclude_build=False)
    changed = sorted(name for name in before.keys() | after.keys()
                     if name not in before or name not in after or
                     any(before[name][key] != after[name][key]
                         for key in ("sha256", "size_bytes", "mode")))
    if changed != [CONTRACT_TEMPLATE]:
        raise ValueError(f"contract patch changed unexpected files: {changed}")
    if tree_records(frozen, exclude_build=False) != before:
        raise ValueError("contract patch changed frozen inputs")
    unchanged(patch_source)
    unchanged(record["patch"])
    unchanged(tool["resolved"])
    record.update(applied=True, working_directory=str(working), changed_files=changed,
                  template_after=after[CONTRACT_TEMPLATE], working_inputs=after)
    return working


def assert_contract_unchanged(record: dict) -> None:
    if not record["applied"]:
        return
    unchanged(record["patch_source"])
    unchanged(record["patch"])
    working = Path(record["working_directory"])
    if tree_records(working, exclude_build=False) != record["working_inputs"]:
        raise ValueError("contract working inputs changed during generation")


def prepare(output: Path, roots_path: Path, template: Path, *, fix_contract: bool = False) -> dict:
    import hjson

    output = plain_path(output)
    output.relative_to(ROOT / "verification/out")
    if output == ROOT / "verification/out" or output.exists():
        raise ValueError("select a new directory below verification/out")
    roots_path, template = plain_path(roots_path), plain_path(template)
    roots = json.loads(roots_path.read_text())
    for name in REVISIONS:
        source = plain_path(Path(roots[name]))
        if source == output or source in output.parents or output in source.parents:
            raise ValueError(f"input/output overlap: {source}")
    source_inputs = {"roots": file_record(roots_path), "template": file_record(template)}
    output.mkdir(parents=True)
    frozen = output / "inputs"
    report = {"schema_version": 1, "status": "PREPARING", "applied_to_export": False,
              "rtl_simulation": "NOT_RUN", "board_boot": "NOT_RUN", "commands": [],
              "input_files": source_inputs, "generator_inputs": {},
              "contract_fix": {"requested": fix_contract, "applied": False,
                               "functional_validation": "NOT_RUN", "bridge_fix": False}}
    try:
        for name in REVISIONS:
            report["generator_inputs"][name] = snapshot(Path(roots[name]), name, frozen / name)
        (frozen / "prepare_plic.py").write_bytes(Path(__file__).read_bytes())
        report["preparer"] = file_record(frozen / "prepare_plic.py")
        helper = Path(__file__).with_name("prepare_linux_bundle.py")
        (frozen / helper.name).write_bytes(helper.read_bytes())
        report["runner_helper"] = file_record(frozen / helper.name)
        (frozen / "ara_vcu118.dts.in").write_bytes(template.read_bytes())
        cfg = frozen / "cheshire/hw/rv_plic.cfg.hjson"
        parsed = hjson.loads(cfg.read_text())
        if parsed != {"instance_name": "rv_plic", "param_values": CONFIG}:
            raise ValueError(f"unexpected Cheshire PLIC config: {parsed}")
        report["configuration"] = parsed
        report["python"] = {"executable": sys.executable, "version": sys.version}
        register_util = frozen / "register_interface/vendor/lowrisc_opentitan/util"
        otp = frozen / "opentitan_peripherals"
        environment = {**os.environ, "PYTHONPATH": str(register_util),
                       "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                       "LC_ALL": "C", "TZ": "UTC"}
        runner = NativeRunner(output, environment, report["commands"])
        if fix_contract:
            otp = contract_working_copy(output, runner, report["contract_fix"])
        packages = runner.run([sys.executable, "-m", "pip", "freeze", "--all"], output, "packages")
        (output / "python-requirements.lock").write_text(packages)
        imported = runner.run([sys.executable, "-B", "-c",
                               "import reggen; print(reggen.__file__)"], output, "reggen-origin").strip()
        if Path(imported).parent != register_util / "reggen":
            raise ValueError(f"wrong reggen imported: {imported}")
        runner.run([sys.executable, "-B", str(otp / "util/ipgen.py"), "generate",
                    "-C", str(otp / "src/rv_plic/tpl/rv_plic"),
                    "-c", str(cfg), "-o", str(output / "rv_plic")], output, "ipgen")
        header = runner.run([sys.executable, "-B", str(register_util / "regtool.py"),
                             "--cdefines", str(output / "rv_plic/data/rv_plic.hjson")], output, "c-header")
        (output / "sw").mkdir()
        (output / "sw/rv_plic_regs.h").write_text(header)
        (output / "ara_vcu118.dts.in").write_text(candidate_dts(
            (frozen / "ara_vcu118.dts.in").read_text()))
        for name in RTL:
            if not (output / "rv_plic/rtl" / name).is_file():
                raise ValueError(f"missing generated RTL: {name}")
        if hjson.loads((output / "rv_plic/data/rv_plic.ipconfig.hjson").read_text()) != parsed:
            raise ValueError("generated ipconfig does not match input")
        assert_unchanged(report["generator_inputs"], frozen)
        assert_contract_unchanged(report["contract_fix"])
        for row in source_inputs.values():
            if file_record(Path(row["path"])) != row:
                raise ValueError(f"integration input changed: {row['path']}")
        outputs = list((output / "rv_plic").rglob("*")) + [output / "sw/rv_plic_regs.h",
                                                            output / "ara_vcu118.dts.in"]
        report["files"] = {str(p.relative_to(output)): file_record(p)
                           for p in sorted(outputs) if p.is_file()}
        if fix_contract:
            report["contract_fix"]["generated_core"] = report["files"]["rv_plic/rtl/rv_plic.sv"]
        report.update(status="GENERATED_NOT_VALIDATED", inputs_unchanged=True)
        save_json(output / "manifest.json", report)
    except BaseException as error:
        report.update(status="FAILED", error=str(error))
        save_json(output / "failure.json", report)
        raise
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--template", type=Path,
                        default=ROOT / "hardware/fpga/ara_dsa_vcu118/linux/ara_vcu118.dts.in")
    parser.add_argument("--fix-contract", action="store_true",
                        help="patch a separate working copy for IE[0]/completion; not functional proof")
    args = parser.parse_args(argv)
    try:
        report = prepare(args.output, args.roots, args.template, fix_contract=args.fix_contract)
    except (OSError, ValueError, subprocess.SubprocessError, ImportError) as error:
        parser.exit(1, f"PLIC preparation failed: {error}\n")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
