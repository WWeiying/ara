"""Gate one isolated full-SoC DC run on the accepted programs and cycle counts."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    temp.replace(path)


def require(ok, message):
    if not ok:
        raise ValueError(str(message))


def replace(text, old, new):
    require(text.count(old) == 1, old)
    return text.replace(old, new)


def prepare(out, prev, equiv, soft):
    root = Path(__file__).resolve().parents[2]
    flow = Path("backend/syn/ara_soc/v1-dc")
    old = prev / "dc"
    parent = read(prev / "plan.json")
    passed = read(prev / "soc-pass.json")
    require(read(prev / "status.json")["soc_pass_sha256"] == sha(prev / "soc-pass.json")
            and passed["source_seal"] == sha(prev / "source-pins.json"), "unsealed reference")
    pins = read(prev / "source-pins.json")
    require(pins[str(prev / "worker.py")] == sha(prev / "worker.py"), "reference worker drift")
    helpers = runpy.run_path(str(prev / "worker.py"))
    helpers["verify"](pins)
    eq = read(equiv / "pass.json")
    require(eq["state"] == "PASS" and eq["log_sha256"] == sha(equiv / "run.log")
            and read(soft / "audit.json")["status"] == "PASS", "missing component evidence")
    changes = eq["changes"]
    require(set(changes) == {"hardware/deps/fpnew/src/" + name + ".sv"
                             for name in ("fpnew_cast_multi", "fpnew_rounding")}, "wrong delta")
    out.mkdir(parents=True, exist_ok=False)
    dc, soc = out / "dc", out / "soc"
    soc.mkdir()
    sdc = flow / "local_scripts/ara_soc.sdc"
    changes_seen = set()
    srcs = helpers["entries"]((prev / "soc/candidate/sources.f").read_text())[0]
    flist = (prev / "soc/candidate/sources.f").read_text()
    for srcname, digest in list(pins.items()):
        src = Path(srcname)
        if not src.is_relative_to(old):
            continue
        rel = src.relative_to(old)
        dest = dc / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        rtl = next((r for r in changes if srcname.endswith("/" + r)), None)
        if rtl:
            soc_ref = helpers["unique"](srcs, rtl)
            require(digest == sha(soc_ref) == changes[rtl]["old"], "VCS/DC reference differs")
            current = root / rtl
            require(sha(current) == changes[rtl]["new"] == sha(soft / "inputs" /
                    Path(rtl).relative_to("hardware/deps")), "untested RTL: " + rtl)
            shutil.copy2(current, dest)
            flist = replace(flist, str(soc_ref) + "\n", str(dest) + "\n")
            changes_seen.add(rtl)
        elif rel == sdc:
            shutil.copy2(root / rel, dest)
            require("set clock_setup_uncertainty_ns 0.20\n" in dest.read_text()
                    and "set_clock_uncertainty -hold  0.075 " in dest.read_text(), "constraint drift")
        else:
            shutil.copy2(src, dest)
            if rel.parts[0] != "sources":
                text = dest.read_text().replace(str(old), str(dc))
                if rel == flow / "global_scripts/dc.tcl":
                    text = replace(text, '"clock_uncertainty_ns=0.15"',
                                   '"clock_uncertainty_ns=$clock_setup_uncertainty_ns"')
                    # Same map, legacy budget for a fair comparison; restore before exporting SDC.
                    text = replace(text, "### dataout", """set cast_port [get_pins -quiet {i_system/i_ariane/ex_stage_i/fpu_gen_fpu_i/fpu_gen_i_fpnew_bulk/gen_operation_groups_3__i_opgroup_block/result_o*}]
if {[sizeof_collection $cast_port] > 0} {
    report_timing -delay_type max -group clk_i -through $cast_port -max_paths 20 -nets -input_pins > ../reports/clk_i_scalar_conv_max.tim
} else {
    puts "Scalar CONV port not found; no filtered timing report."
}
set_clock_uncertainty -setup 0.15 [get_clocks clk_i]
report_qor -significant_digits 3 > ../reports/qor_compare_setup015.rpt
set_clock_uncertainty -setup $clock_setup_uncertainty_ns [get_clocks clk_i]
### dataout""")
                dest.write_text(text)
        pins[str(dest)] = sha(dest)
    require(changes_seen == set(changes), "incomplete DC overlay")
    (soc / "sources.f").write_text(flist)
    dc_sources, inc = helpers["entries"]((dc / "backend/flist/ara_soc_dc.f").read_text())
    require(all(str(p) in pins and p.is_relative_to(dc) for p in dc_sources), "unfrozen sources")
    for incdir in inc:
        require(incdir.is_relative_to(dc / "sources"), incdir)
        incdir.mkdir(parents=True, exist_ok=True)
    for sub in ("reports", "outputs", "inputs/inc"):
        (dc / flow / sub).mkdir(parents=True, exist_ok=True)
    build = parent["builds"]["candidate"].copy()
    build[build.index("-f")+1] = str(soc / "sources.f")
    cmd = parent["dc_command"].copy()
    require(cmd[cmd.index("-w")+1] == str(old / flow / "run") and "DC_ELAB_ONLY=0" in cmd,
            "not parent full DC")
    cmd[cmd.index("-w")+1] = str(dc / flow / "run")
    subprocess.run(cmd[:-3] + ["test", "-x", "./run.cmd"], check=True, timeout=30)
    shutil.copy2(__file__, out / "worker.py")
    save(out / "plan.json", dict(parent=str(prev), dc=cmd, build=build, flow=str(flow),
                                component=str(equiv), softfloat=str(soft), changes=changes))
    pins.update({str(p): sha(p) for p in (out / "plan.json", out / "worker.py", soc / "sources.f",
                 prev / "soc-pass.json", equiv / "pass.json", soft / "audit.json")})
    save(out / "source-pins.json", pins)
    save(out / "status.json", {"state": "PREPARED", "seal": sha(out / "source-pins.json")})


def run(out, seal):
    require(sha(out / "source-pins.json") == seal and read(out / "status.json")["state"] == "PREPARED",
            "not a fresh sealed run")
    plan = read(out / "plan.json")
    prev = Path(plan["parent"])
    parent = read(prev / "plan.json")
    expected = read(prev / "soc-pass.json")["equal"]
    require(set(expected) == set(parent["cases"]), "incomplete SoC reference")
    h = runpy.run_path(str(prev / "worker.py"))
    execute = h["_old"]["execute"]
    pins = read(out / "source-pins.json")
    h["verify"](pins)
    soc = out / "soc"
    save(out / "status.json", {"state": "BUILDING_SOC"})
    execute(plan["build"], soc, soc / "build.log", 3600)
    image = sha(soc / "simv")
    completed = {}

    def case(name):
        recipe = parent["cases"][name]
        work = out / "runs" / name / "work"
        work.mkdir(parents=True)
        require(sha(recipe["elf"]) == recipe["elf_sha256"], name)
        log = execute([str(soc / "simv"), *recipe["argv"]], work, work / "run.log", 3600)
        if name.startswith("resident_"):
            h["oracle_proof"](parent, name, work, execute=True)
        require(h["checked_result"](recipe, name, log) == expected[name], name + " cycles/signature")
        return sha(work / "run.log")

    def accept(name, digest):
        completed[name] = digest
        save(out / "status.json", {"state": "SOC_TEST", "passed": list(completed),
                                    "total": len(expected)})

    h["batch"](list(expected), 6, case, accept)
    h["verify"](pins)
    save(out / "soc-pass.json", {"simv_sha256": image, "logs": completed, "reference": str(prev)})
    dc = out / "dc"
    outputs = dc / plan["flow"] / "outputs"
    require(not any(outputs.iterdir()), "stale DC outputs")
    save(out / "status.json", {"state": "RUNNING_FULL_DC", "soc_pass": len(completed)})
    log = execute(plan["dc"], dc, dc / "console.log", 86400)
    require("DC_FLOW_COMPLETE" in log.splitlines(), "incomplete DC")
    h["verify"](pins)
    save(out / "status.json", {"state": "SYNTHESIS_COMPLETE", "soc_pass": len(completed),
                                "sha256": {ext: sha(outputs / ("ara_soc_dc." + ext))
                                           for ext in ("ddc","v","sdc")}})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    ap.add_argument("--prepare", nargs=3, type=Path, metavar=("PARENT", "EQUIV", "SOFTFLOAT"))
    ap.add_argument("--seal")
    a = ap.parse_args()
    out = a.out.resolve()
    if a.prepare:
        prepare(out, *(p.resolve() for p in a.prepare))
    else:
        with (out / "worker.lock").open("x"):
            try:
                run(out, a.seal)
            except Exception as exc:
                save(out / "status.json", {"state": "FAIL", "error": str(exc),
                                            "previous": read(out / "status.json")})
                raise
