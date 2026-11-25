#!/usr/bin/env python3
"""Prepare an isolated successor to the mapped 870cadb9f DC campaign."""

import argparse
import json
from pathlib import Path
import re
import runpy
import shutil
import subprocess

from run_operand_ext import ROOT, save, sha, verify
from run_request_lane_timing_soc import RTL, REQUEST_DEFINE


FLOW = Path("backend/syn/ara_soc/v1-dc")
FLIST = Path("backend/flist/ara_soc_dc.f")
DIRECT_U = {
    "hardware/deps/cva6/core/csr_regfile.sv",
    "hardware/deps/cva6/core/cva6.sv",
    "hardware/deps/cva6/core/decoder.sv",
    "hardware/deps/cva6/core/id_stage.sv",
}
OVERLAYS = DIRECT_U | {
    "hardware/deps/cva6/core/acc_dispatcher.sv",
    "hardware/deps/fpnew/src/fpnew_fma_multi.sv",
}


def prepare(reference, vcs, out):
    verify(reference)
    verify(vcs)
    manifest = json.loads((reference / "manifest.json").read_text())
    if (manifest["main_rtl_commit"][:9], manifest["period_ns"],
        manifest["setup_uncertainty_ns"]) != ("870cadb9f", 1, 0.15):
        raise ValueError("unexpected timing baseline")
    plan = json.loads((vcs / "plan.json").read_text())
    main = plan["baseline"]
    changed = set(subprocess.check_output(
        ["git", "diff", "--name-only", manifest["main_rtl_commit"], main, "--",
         "hardware/src", "hardware/include"], cwd=ROOT, text=True).splitlines())
    replace = changed | set(RTL) | OVERLAYS
    source_audit = json.loads((reference / "source-audit.json").read_text())
    raw_sha = {row["path"]: row["sha256"] for row in source_audit}
    if not replace <= raw_sha.keys():
        raise ValueError(f"source is not in the mapped baseline: {replace - raw_sha.keys()}")

    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(reference / "sources", out / "sources")
    frozen = out / "sources" / manifest["worktree"].lstrip("/")
    sim = vcs / "source"
    differences = sorted(name for name, digest in raw_sha.items() if
                         (sim / name).is_file() and sha(sim / name) != digest and name not in replace)
    if any(not name.startswith("hardware/deps/fpu_div_sqrt_mvp/") for name in differences):
        raise ValueError(f"unreviewed active dependency changes: {differences}")
    # Keep the historical inactive MVP backend bytes. The compared SoCs use
    # THMULTI, not that backend; record the raw-source difference explicitly.
    if "localparam fpnew_pkg::divsqrt_unit_t DivSqrtSel = fpnew_pkg::THMULTI;" not in (
            sim / "hardware/src/lane/vmfpu.sv").read_text():
        raise ValueError("review active divider backend before reusing archived dependencies")

    replaced = {}
    default_removed = []
    for relative in sorted(replace):
        src = sim / relative
        dst = frozen / relative
        replaced[relative] = {"reference": raw_sha[relative], "vcs": sha(src)}
        shutil.copy2(src, dst)
        if relative in {"hardware/deps/cva6/core/decoder.sv",
                        "hardware/deps/cva6/core/id_stage.sv"}:
            # Every actual consumer is checked below before asserting fixed point.
            original = dst.read_bytes()
            token = b"akv_access_allowed_i = 1'b1"
            if original.count(token) != 1:
                raise ValueError(f"unexpected Direct-U input: {relative}")
            dst.write_bytes(original.replace(token, b"akv_access_allowed_i"))
            default_removed.append(relative)
    for relative in ("hardware/deps/cva6/core/cva6.sv", "hardware/deps/cva6/core/id_stage.sv"):
        if len(re.findall(r"\.akv_access_allowed_i\s*\(", (frozen / relative).read_text())) != 1:
            raise ValueError(f"missing explicit Direct-U connection: {relative}")

    # Presto rejects function argument defaults. The only synthesis caller
    # already provides this value; retain the default in the simulation RTL.
    qbs_relative = "hardware/include/qbs_pkg.sv"
    qbs = frozen / qbs_relative
    dispatcher = frozen / "hardware/src/ara_dispatcher.sv"
    argument = b"input bit cooperative_q4_k"
    old = argument + b" = 1'b0"
    source = qbs.read_bytes()
    explicit = b"qbs_capability_word(64'(acc_req_i.rs1), VLEN, QbsCooperativeMul)"
    if source.count(old) != 1 or dispatcher.read_bytes().count(explicit) != 1:
        raise ValueError("review changed QBS capability declaration/call before synthesis")
    qbs.write_bytes(source.replace(old, argument))

    flist = out / FLIST
    flist.parent.mkdir(parents=True)
    original_flist = (reference / FLIST).read_text()
    flags = ["+define+ARA_SHARED_FMA=1"]
    if plan.get("register_request", True):
        flags.append(REQUEST_DEFINE)
    if any(flag in original_flist.splitlines() for flag in flags):
        raise ValueError("unexpected feature define in baseline filelist")
    flist.write_text("\n".join(flags) + "\n" +
                     original_flist.replace(str(reference) + "/", str(out) + "/"))
    for directory in ("global_scripts", "local_scripts", "inputs"):
        shutil.copytree(reference / FLOW / directory, out / FLOW / directory)
    for directory in ("run", "reports", "outputs"):
        (out / FLOW / directory).mkdir()
    for name in (".synopsys_dc.setup", "run.cmd"):
        shutil.copy2(reference / FLOW / "run" / name, out / FLOW / "run" / name)
    tools = out / "tools"
    tools.mkdir()
    for name in ("selection_audit_v2.tcl", "min_timing.tcl", "dc_port_defaults_v2.py"):
        shutil.copy2(reference / "tools" / name, tools / name)
    dc = out / FLOW / "global_scripts/dc.tcl"
    dc.write_bytes(dc.read_bytes().replace(str(reference).encode(), str(out).encode()))
    normalizer = runpy.run_path(str(tools / "dc_port_defaults_v2.py"))
    parser = ROOT / "hardware/scripts/akv/check-synthesis-preflight.py"
    journal = normalizer["apply"](flist, parser, out / "sources")
    if normalizer["plan"](flist, parser):
        raise ValueError("DC syntax adaptation is not at fixed point")
    for relative in replaced:
        replaced[relative]["dc"] = sha(frozen / relative)
    libraries = manifest["library_sha256"]
    for path, digest in libraries.items():
        if sha(Path(path)) != digest:
            raise ValueError(f"DC library changed: {path}")
    save(out / "manifest.json", {
        "baseline": str(reference), "main": main, "paired_vcs": str(vcs),
        "clock_ns": 1, "setup_uncertainty_ns": 0.15, "hold_uncertainty_ns": 0.075,
        "runtime_flags": list(flags), "replaced_sources": replaced,
        "archived_inactive_mvp_sources": differences,
        "direct_u_defaults_removed": default_removed, "syntax_journal": journal,
        "function_default_removed": {"file": qbs_relative, "argument": old.decode()},
        "scope": "Prepared only; review the paired VCS result before starting DC",
    })
    pins = {str(f): sha(f) for f in out.rglob("*") if f.is_file()}
    pins.update(libraries)
    save(out / "source-pins.json", pins)
    save(out / "status.json", {"state": "PREPARED", "paired_vcs": str(vcs)})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--reference", type=Path, required=True)
    cli.add_argument("--vcs", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    prepare(args.reference.resolve(), args.vcs.resolve(), args.output.resolve())
