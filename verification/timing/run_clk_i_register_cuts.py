"""Run isolated request/EW8 register cuts against the completed cast-fused SoC."""

import argparse
from pathlib import Path
import re
import runpy
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "verification/out/cast-fused-soc-dc-20261123-01"
FLOW = Path("backend/syn/ara_soc/v1-dc")
DEFINES = "+define+ARA_REGISTER_ACCELERATOR_REQUEST=1\n+define+ARA_TIMING_SHARED_MUL_REGISTER_EW8=1\n"
LANE_FILES = ("hardware/src/lane/vmfpu.sv", "hardware/src/lane/qbs_lane_mul_borrow.sv")
EXTRA = ("rv64uv-ara-vmul", "rv64uv-ara-vmulh", "rv64uv-ara-vmulhsu",
         "rv64uv-ara-vmulhu", "rv64uv-ara-vsmul")


def main(out, stage, base):
    # The copy executed by systemd is under the output tree, not the repository.
    helpers = runpy.run_path(str(base / "worker.py"))
    require, read, save, sha = (helpers[k] for k in ("require", "read", "save", "sha"))
    previous = read(base / "plan.json")
    ref = Path(previous["parent"])
    base_pins = read(base / "source-pins.json")
    h = runpy.run_path(str(ref / "worker.py"))
    verify, execute = h["verify"], h["_old"]["execute"]
    dc_bytes = h["_old"]["dc_bytes"]
    flow = out / "dc" / FLOW

    if stage == "prepare":
        status = read(base / "status.json")
        baseline = read(base / "soc-pass.json")
        require(status["state"] == "SYNTHESIS_COMPLETE" and status["soc_pass"] == 9,
                "wrong baseline")
        verify(base_pins)
        for name, digest in baseline["logs"].items():
            require(sha(base / "runs" / name / "work/run.log") == digest, name)
        out.mkdir(parents=True)
        (out / "soc").mkdir()
        old_dc, new_dc = base / "dc", out / "dc"
        pins = dict(base_pins)
        seen = set()
        vlist = (base / "soc/sources.f").read_text()
        sources, _ = h["entries"](vlist)
        for path, digest in base_pins.items():
            src = Path(path)
            if not src.is_relative_to(old_dc):
                continue
            rel = src.relative_to(old_dc)
            dst = new_dc / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            lane = next((x for x in LANE_FILES if path.endswith("/" + x)), None)
            if lane:
                baseline_vcs = h["unique"](sources, lane)
                require(sha(baseline_vcs) == base_pins[str(baseline_vcs)] and
                        dc_bytes(lane, baseline_vcs.read_bytes()) == src.read_bytes(),
                        "unexplained VCS/DC RTL mismatch: " + lane)
                candidate = (ROOT / lane).read_bytes()
                require(candidate != baseline_vcs.read_bytes(), "missing lane delta: " + lane)
                dst.write_bytes(dc_bytes(lane, candidate))
                vcs_lane = out / "soc/overlay" / lane
                vcs_lane.parent.mkdir(parents=True, exist_ok=True)
                vcs_lane.write_bytes(candidate)
                vlist = helpers["replace"](vlist, str(baseline_vcs) + "\n", str(vcs_lane) + "\n")
                pins[str(vcs_lane)] = sha(vcs_lane)
                seen.add(lane)
            else:
                shutil.copy2(src, dst)
                if rel.parts[0] != "sources":
                    content = dst.read_text().replace(str(old_dc), str(new_dc))
                    if rel == Path("backend/flist/ara_soc_dc.f"):
                        content = DEFINES + content
                    dst.write_text(content)
            pins[str(dst)] = sha(dst)
        require(seen == set(LANE_FILES), "incomplete lane overlay")
        for path in ("outputs", "reports", "inputs/inc"):
            (flow / path).mkdir(parents=True, exist_ok=True)
        flist = out / "soc/sources.f"
        flist.write_text(DEFINES + vlist)
        build = previous["build"].copy()
        build[build.index("-f") + 1] = str(flist)
        dc = [arg.replace(str(old_dc), str(new_dc)) for arg in previous["dc"]]
        require(dc[dc.index("-w") + 1] == str(flow / "run") and "DC_ELAB_ONLY=0" in dc,
                "invalid DC command")
        subprocess.run(dc[:-3] + ["test", "-x", "./run.cmd"], check=True, timeout=30)
        cases = read(ref / "plan.json")["cases"]
        for name in EXTRA:
            elf = ROOT / "apps/bin" / name
            if not elf.is_file():
                continue
            dest = out / "elf" / name
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(elf, dest)
            pins[str(dest)] = sha(dest)
            cases[name] = dict(elf=str(dest), elf_sha256=sha(dest), marker=None,
                               argv=["-no_save", "+NO_FSDB", "+NO_INSTR_TRACE",
                                     "+ntb_random_seed=1", f"+TESTCASE={name}", f"+PRELOAD={dest}"])
        require(len(cases) >= 13, "missing EW8/native multiplication tests")
        shutil.copy2(__file__, out / "worker.py")
        save(out / "plan.json", dict(base=str(base), build=build, dc=dc, cases=cases))
        for p in (out / "plan.json", out / "worker.py", base / "soc-pass.json", flist):
            pins[str(p)] = sha(p)
        save(out / "source-pins.json", pins)
        save(out / "status.json", dict(state="PREPARED", seal=sha(out / "source-pins.json")))
        return

    plan, state = read(out / "plan.json"), read(out / "status.json")
    seal = sha(out / "source-pins.json")
    require(state["seal"] == seal, "source pins replaced")
    verify(read(out / "source-pins.json"))
    if stage == "soc":
        require(state["state"] == "PREPARED", "must start a fresh candidate")
        save(out / "status.json", dict(state="BUILDING_SOC", seal=seal))
        soc, results = out / "soc", {}
        execute(plan["build"], soc, soc / "build.log", 1200)
        ref_plan = read(ref / "plan.json")
        baseline = read(base / "soc-pass.json")["logs"]

        def run_case(name):
            recipe = plan["cases"][name]
            work = out / "runs" / name / "work"
            work.mkdir(parents=True)
            require(recipe["elf_sha256"] == sha(Path(recipe["elf"])), name)
            log = execute([str(soc / "simv"), *recipe["argv"]], work, work / "run.log", 300)
            require(re.findall(r"(?m)^Loading ELF file (.+)$", log) == [recipe["elf"]], name)
            resident = name.startswith("resident_")
            if resident:
                h["oracle_proof"](ref_plan, name, work, execute=True)
            actual = h["metrics"](log, recipe["marker"], resident)
            expected = None
            if name in baseline:
                old_log = base / "runs" / name / "work/run.log"
                require(sha(old_log) == baseline[name], name + " baseline log drift")
                expected = h["metrics"](old_log.read_text(errors="replace"), recipe["marker"], resident)
            if resident:
                require(actual["signatures"] == expected["signatures"], name + " signature changed")
            return dict(baseline=expected, candidate=actual, log_sha256=sha(work / "run.log"))

        def accept(name, result):
            results[name] = result
            save(out / "status.json", dict(state="SOC_TEST", passed=list(results), seal=seal))

        # Run the riskiest protocol replays first; fail closed on any mismatch.
        h["batch"](list(plan["cases"]), 6, run_case, accept)
        for name, key, percent in (("vsaxpy_asm", "task_cycles", 10),
                                   ("llama_qwen25_shape_decode_n32_qbs", "projection_cycles", 5)):
            result = results[name]
            a, b = result["baseline"][key], result["candidate"][key]
            require(len(a) == len(b) == 1 and a[0] > 0 and b[0] * 100 <= a[0] * (100 + percent),
                    f"{name} exceeds timing-candidate cycle budget: {a} -> {b}")
        verify(read(out / "source-pins.json"))
        save(out / "soc-pass.json", dict(results=results, simv_sha256=sha(soc / "simv"), seal=seal))
        save(out / "status.json", dict(state="SOC_PASS", seal=seal,
                                       proof=sha(out / "soc-pass.json")))
    else:
        require(state["state"] == "SOC_PASS" and state["proof"] == sha(out / "soc-pass.json"),
                "missing candidate validation")
        require(not any((flow / "outputs").iterdir()), "not a fresh DC run")
        save(out / "status.json", dict(state="RUNNING_FULL_DC", seal=seal, proof=state["proof"]))
        log = execute(plan["dc"], out / "dc", out / "dc/console.log", 86400)
        require("DC_FLOW_COMPLETE" in log.splitlines(), "incomplete DC")
        verify(read(out / "source-pins.json"))
        save(out / "status.json", dict(state="SYNTHESIS_COMPLETE", seal=seal, proof=state["proof"],
                                       sha256={ext: sha(flow / "outputs" / ("ara_soc_dc." + ext))
                                               for ext in ("ddc", "v", "sdc")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "soc", "dc"))
    parser.add_argument("out", type=Path)
    parser.add_argument("--base", type=Path, default=BASE)
    args = parser.parse_args()
    out = args.out.resolve()
    try:
        main(out, args.stage, args.base.resolve())
    except Exception as exc:
        if args.stage != "prepare":
            import json
            (out / "failure.json").write_text(json.dumps(dict(stage=args.stage, error=str(exc)), indent=2) + "\n")
        raise
