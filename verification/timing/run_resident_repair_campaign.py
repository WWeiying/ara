#!/usr/bin/env python3
"""One-shot ex-fp-credit-02 successor, registered retirement fix, original ELFs only."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys


ROOT = Path("/home/wangwy/openproject/ara_dsa")
OUT = ROOT / "verification/out"
PARENT = OUT / "ex-fp-credit-20261122-02"
SOURCE = ROOT / "verification/timing/run_resident_repair_campaign.py"
FLOW = Path("backend/syn/ara_soc/v1-dc")
SDC = FLOW / "local_scripts/ara_soc.sdc"
FLIST = Path("backend/flist/ara_soc_dc.f")
FIX = "hardware/deps/cva6/core/commit_stage.sv"
PRE = "bf59bfa36960ec6227cb49d86e60f8b8f9507590f64ecfafffa9d8d8f94abb60"
POST = "ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249"
PATCH = ROOT / "verification/patches/cva6-local-fixes.patch"
REGISTRY = PATCH.with_name("dependencies.json")
FAILED = PARENT / "soc/reference/resident_qk"
BRANCH = OUT / "cva6_single_branch_independent_20261122_03/report.json"
CAST = ROOT / "verification/timing/out_qbs_cast_equiv_20261122_03/report.json"
ORACLE = ROOT / "verification/timing/resident_firmware_oracle_v1.py"
ANCHORS = {
    ORACLE: "bcaae7346b52b9e17f6cd294cb8d113f46cca112e65dd37a219316799973ee93",
    PARENT / "worker.py": "3951cb23a1681a8f1b3b5223397d7bd792b1b526a50758ae639f719b78905a08",
    PARENT / "source-pins.json": "f6dbd73d43dfa80c2ca107f61d735f0d98e4886b40d04d286615332a69d69491",
    PARENT / "status.json": "220958b885bc1a0283342aaf6b490022fe0260dcd45c7c6b657596c856d2ce77",
    FAILED / "run.command.json": "806e4dcf0cd3775d78bf28b14804ddffa2f81f91094ae16ea83fb2143c809775",
    FAILED / "run.log": "e9d51f537065f8db834cc8e6991330ecb7d1d371f0a4e94e1b17e3ccfa53c5c8",
    BRANCH: "3684ae8eb2ffca48001ce0bc4965b7089afcb02c64d0b985e706cd859d7b2d38",
    CAST: "1b9ab7563a6cab9eb39232717bfb58e7b36334e4845ee20139906215dca733df",
    PATCH: "4afb780061813ca90b19e94aa6b552ac0c11df7ac57a33bf594a9392468dd3b8",
}
SDC_SHA = "972295afde05c3e26017425426b3f31b66f73ec14b667fda49f46d0822131dfa"
SIDES = ("baseline", "candidate")


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


# Use the actual sealed checker/recipe helpers, not the version in the working tree.
_worker = PARENT / "worker.py"
check(hashlib.sha256(_worker.read_bytes()).hexdigest() == ANCHORS[_worker], "parent worker drift")
_old = runpy.run_path(str(_worker))
read, save, sha, verify, metrics, entries, dc_bytes = (
    _old[key] for key in ("read", "save", "sha", "verify", "metrics", "entries", "dc_bytes"))


def digests(paths):
    return {str(p): sha(p) for p in paths}


def state(out, name, **fields):
    save(out / "status.json", dict(state=name, pid=os.getpid(), **fields))


def unique(sources, rel):
    matches = [p for p in sources if str(p).endswith("/" + rel)]
    check(len(matches) == 1, f"{rel}: expected one source, found {matches}")
    return matches[0]


def single_fix(old, new):
    entry = read(REGISTRY)["patches"]["cva6"]
    check(entry["patch"] == PATCH.name and entry["sha256"] == sha(PATCH) == ANCHORS[PATCH],
          "unregistered CVA6 patch")
    check(sha(old) == PRE, "wrong commit_stage preimage")
    hunks = [s for s in re.split(rb"(?m)(?=^diff --git )", PATCH.read_bytes())
             if s.startswith(b"diff --git a/core/commit_stage.sv b/core/commit_stage.sv\n")]
    check(len(hunks) == 1, "ambiguous commit_stage patch")
    subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "--output", str(new), str(old)],
                   cwd=new.parent, input=hunks[0], check=True)
    check(sha(new) == POST, "wrong registered postimage")


def live_check(plan):
    actual = digests(ROOT / rel for rel in plan["ledger"])
    for rel, row in plan["ledger"].items():
        digest = actual[str(ROOT / rel)]
        check(digest == row["candidate_sha256"],
              "working tree differs from reviewed candidate: " + rel)
        check(sha(row["candidate"]) == row["candidate_sha256"], "effective candidate drift: " + rel)
    return actual


def receipts(ledger):
    for path, rel, keys in (
        (BRANCH, _old["RTL"][0], ("baseline_ex_stage_sha256", "candidate_ex_stage_sha256")),
        (CAST, _old["RTL"][-1], ("reference_accumulator_sha256", "candidate_accumulator_sha256")),
    ):
        data = read(path)
        check(sha(path) == ANCHORS[path] and data["state"] == "PASS" and
              [data[k] for k in keys] == [ledger[rel][s + "_sha256"] for s in SIDES],
              "independent proof does not cover both images: " + str(path))
    return digests((BRANCH, CAST))


def bind_oracle(inputs, cases):
    frozen = inputs / ORACLE.name
    _old["copy"](ORACLE, frozen)
    check(sha(frozen) == ANCHORS[ORACLE], "unreviewed oracle")
    spec = runpy.run_path(str(frozen))
    pins = digests((frozen,))
    for kind, (bdir, _, bpin, gdir, rdir, rpin) in spec["CONFIG"].items():
        root = spec["OUT"]
        build, audit = root / bdir / "build.json", root / rdir / "report.json"
        verify({str(build): bpin, str(audit): rpin})
        info, golden = read(build), root / gdir / "work/run.vcs.log"
        pins[str(build)], pins[str(audit)] = bpin, rpin
        pins[str(golden)] = read(audit)["artifacts" if kind == "qk" else "evidence_sha256"][str(golden)]
        pins.update({p: h for p, h in info["artifacts"].items()
                     if p.endswith((".py", "/vectors.json", ".elf"))})
        check(cases["resident_" + kind]["elf_sha256"] == info["elf_sha256"], "wrong oracle ELF")
    verify(pins)
    return dict(file=str(frozen), pins=pins)


def prepare(out, jobs):
    check(1 <= jobs <= 8, "use 1..8 simulators")
    out.mkdir(exist_ok=False)
    pins = {str(p): h for p, h in ANCHORS.items()}
    verify(pins)
    pins.update(read(PARENT / "source-pins.json"))
    verify(pins)
    parent = read(PARENT / "plan.json")
    check(set(parent["changes"]) == set(_old["RTL"]), "parent timing delta changed")
    for src in (PARENT / "status.json", FAILED / "run.log", FAILED / "run.command.json"):
        dest = out / "original-qk-failure" / src.name
        _old["copy"](src, dest)
        pins[str(dest)] = ANCHORS[src]
    inputs = out / "inputs"
    inputs.mkdir()
    old_dc, dc = Path(parent["dc_out"]), out / "dc"
    old_lists = {s: (PARENT / "soc" / (s + ".f")).read_text() for s in SIDES}
    old_files = {s: entries(lines)[0] for s, lines in old_lists.items()}
    pre = unique(old_files["baseline"], FIX)
    repaired = inputs / FIX
    repaired.parent.mkdir(parents=True)
    single_fix(pre, repaired)
    check(unique(old_files["candidate"], FIX) == pre, "different pre-repair input")
    pins.update(digests((repaired,)))
    registry_copy = inputs / REGISTRY.name
    _old["copy"](REGISTRY, registry_copy)
    pins.update(digests((registry_copy,)))
    old_dc_files = entries((old_dc / FLIST).read_text())[0]
    dc_pre = unique(old_dc_files, FIX)
    check(sha(dc_pre) == PRE, "DC preimage drift")

    # Copy only pinned DC inputs; relocate run-root references, never normalize RTL anew.
    for name in list(pins):
        src = Path(name)
        if not src.is_relative_to(old_dc):
            continue
        rel = src.relative_to(old_dc)
        dest = dc / rel
        _old["copy"](src, dest)
        if src == dc_pre:
            shutil.copyfile(repaired, dest)
        elif rel.parts[0] != "sources":
            data = dest.read_bytes()
            dest.write_bytes(data.replace(os.fsencode(old_dc), os.fsencode(dc)))
        pins[str(dest)] = sha(dest)
    for directory in ("run", "reports", "outputs", "inputs/inc"):
        (dc / FLOW / directory).mkdir(parents=True, exist_ok=True)
    dc_files, inc = entries((dc / FLIST).read_text())
    for p in inc:
        check(p.is_relative_to(dc / "sources"), "external DC include")
        p.mkdir(parents=True, exist_ok=True)
    check(all(str(p) in pins and p.is_relative_to(dc) for p in dc_files), "unpinned DC filelist")
    check(sha(dc / SDC) == sha(Path(parent["baseline_dc"]) / SDC) == SDC_SHA, "SDC drift")
    ledger, builds, lists = {}, {}, {}
    for side in SIDES:
        work = out / "soc" / side
        work.mkdir(parents=True)
        flist = work / "sources.f"
        lines = old_lists[side].splitlines()
        lines[lines.index(str(pre))] = str(repaired)
        flist.write_text("\n".join(lines) + "\n")
        pins[str(flist)] = sha(flist)
        lists[side] = entries(flist.read_text())[0]
        argv = parent["build"].copy()
        argv[argv.index("-f") + 1] = str(flist)
        builds[side] = argv
    for rel in (FIX, *_old["RTL"]):
        files = {s: unique(lists[s], rel) for s in SIDES}
        files["dc"] = unique(dc_files, rel)
        row = {**{k: str(p) for k, p in files.items()},
               **{k + "_sha256": sha(p) for k, p in files.items()}}
        expected = (POST, POST, POST) if rel == FIX else tuple(
            parent["changes"][rel][k] for k in ("soc_old", "new", "dc_new"))
        check(tuple(row[k + "_sha256"] for k in (*SIDES, "dc")) == expected and
              dc_bytes(rel, files["candidate"].read_bytes()) == files["dc"].read_bytes(),
              "five-file SoC/DC identity failed: " + rel)
        ledger[rel] = row
    recipes = {}
    for name, case in {**parent["cases"], **parent["resident"]}.items():
        elf = Path(case["elf"])
        check(elf == PARENT / "elf" / name and pins[str(elf)] == sha(elf) and
              elf.read_bytes()[:4] == b"\x7fELF", "not the pinned original ELF: " + name)
        args = case.get("args", ["-no_save", "+NO_FSDB", "+NO_INSTR_TRACE", "+ntb_random_seed=1",
                                 "+TESTCASE=" + name])
        recipes[name] = dict(**case, argv=[*args, "+PRELOAD=" + str(elf)], elf_sha256=pins[str(elf)])
    check(set(recipes) == set(_old["CASES"]) | set(_old["RESIDENT"]), "incomplete cases")
    check(read(FAILED / "run.command.json") == [parent["baseline_image"], *recipes["resident_qk"]["argv"]],
          "original failed QK recipe mismatch")
    dc_cmd = parent["baseline_dc_command"].copy()
    idx = dc_cmd.index("-w") + 1
    check("DC_ELAB_ONLY=0" in dc_cmd and dc_cmd[idx] == str(old_dc / FLOW / "run"), "not full DC")
    dc_cmd[idx] = str(dc / FLOW / "run")
    check(dc_cmd[-3:] == ["bash", "-lc", "exec ./run.cmd"], "unexpected DC wrapper")
    preflight = dc_cmd[:-3] + ["test", "-r", "./run.cmd"]
    subprocess.run(preflight, check=True, timeout=30)
    save(out / "dc-preflight.json", dict(argv=preflight, returncode=0, cwd=dc_cmd[idx]))
    pins.update(digests((out / "dc-preflight.json",)))
    plan = dict(parent=str(PARENT), ledger=ledger, branch_cast=receipts(ledger), builds=builds,
                cases=recipes, dc_command=dc_cmd, jobs=jobs, sdc_sha256=SDC_SHA,
                commit_stage_pre=PRE, commit_stage_post=POST, patch_sha256=sha(PATCH))
    plan["oracle"] = bind_oracle(inputs, recipes)
    pins.update(plan["oracle"]["pins"])
    plan["live_at_prepare"] = live_check(plan)
    save(out / "plan.json", plan)
    _old["copy"](SOURCE, out / "worker.py")
    pins.update(digests((out / "worker.py", out / "plan.json")))
    save(out / "source-pins.json", pins)
    verify(pins)
    state(out, "PREPARED", seal=sha(out / "source-pins.json"))


def checked_result(case, name, log):
    check(re.findall(r"(?m)^Loading ELF file (.+)$", log) == [case["elf"]], "wrong ELF load: " + name)
    resident = name in _old["RESIDENT"]
    data = metrics(log, case["marker"], resident)
    if resident:
        prefix, count = ("QK", 23) if name == "resident_qk" else ("PV", 21)
        for kind in ("CASE", "DATA"):
            ids = re.findall(rf"(?m)^{prefix}_BOUNDARY_{kind} id=(\d+) phase=1\b", log)
            check(set(map(int, ids)) == set(range(count)), "incomplete resident records: " + name)
        check(len(re.findall(rf"(?m)^{prefix}_BOUNDARY_DONE ", log)) == 1, "duplicate DONE")
    else:
        check(data == case["expected"], "historical cycle mismatch: " + name)
    return data


def unit(out, stage):
    return f"{out.name}-{stage}.service"


def submit(out, stage, seal, proof=None):
    u = unit(out, stage)
    log = f"append:{out}/{stage}.service.log"
    argv = ["systemd-run", "--user", "--unit=" + u, "-p", "Type=exec", "-p", "KillMode=control-group",
            "-p", "WorkingDirectory=" + str(out), "-p", "StandardOutput=" + log,
            "-p", "StandardError=" + log, sys.executable, "-B", str(out / "worker.py"),
            stage, str(out), "--seal", seal]
    if proof:
        argv.extend(["--proof", proof])
    subprocess.run(argv, check=True)
    print(u, flush=True)


def batch(items, jobs, task, accept, on_error=None):
    # Do not enqueue the whole suite: check every completed job before replenishing.
    pending, todo = {}, iter(items)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        while True:
            while len(pending) < jobs:
                item = next(todo, None)
                if item is None:
                    break
                pending[pool.submit(task, item)] = item
            if not pending:
                return
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                item = pending.pop(future)
                try:
                    accept(item, future.result())
                except Exception as exc:
                    if on_error:
                        on_error(item, exc)
                    raise


def image_pins(out):
    paths = []
    for side in SIDES:
        work = out / "soc" / side
        paths.append(work / "simv")
        libs = [p for p in (work / "simv.daidir").rglob("*") if p.is_file()]
        check(libs, "missing simulator support files: " + side)
        paths.extend(libs)
    return digests(paths)


def case_dir(out, side, name):
    # ara_tb writes ../gold_results.txt; give every case its own parent too.
    return out / "runs" / side / name / "work"


def case_argv(out, plan, side, name):
    return [str(out / "soc" / side / "simv"), *plan["cases"][name]["argv"]]


def oracle_proof(plan, name, work, execute=False):
    spec, case = plan["oracle"], plan["cases"][name]
    kind = name.removeprefix("resident_")
    log, receipt = work / "run.log", work / "resident-oracle.json"
    argv = [sys.executable, "-IB", spec["file"], kind, "--elf", case["elf"], "--log", str(log)]
    if execute:
        verify(spec["pins"])
        _old["execute"](argv, work, receipt, 60)
    result = read(receipt)
    expected = dict(state="PASS", scope="resident_uart_oracle_only", kernel=kind,
                    numerical_checked=True, golden_uart_equal=True, trace_checked=False,
                    protocol_checked=False, elf=case["elf"], elf_sha256=case["elf_sha256"],
                    log=str(log), log_sha256=sha(log))
    cmd = receipt.with_suffix(".command.json")
    check(read(cmd) == argv and all(result.get(k) == v for k, v in expected.items()),
          "invalid or stale resident oracle receipt: " + str(receipt))
    return digests((receipt, cmd))


def compare_all(out, plan):
    evidence, measured = {}, {}
    for name, case in plan["cases"].items():
        pair = []
        for side in SIDES:
            work = case_dir(out, side, name)
            log, cmd = work / "run.log", work / "run.command.json"
            check(read(cmd) == case_argv(out, plan, side, name), f"command drift: {side}/{name}")
            evidence.update(digests((log, cmd)))
            if name in _old["RESIDENT"]:
                evidence.update(oracle_proof(plan, name, work))
            pair.append(checked_result(case, name, log.read_text(errors="replace")))
        check(pair[0] == pair[1], "paired signatures/cycles differ: " + name)
        measured[name] = pair[0]
    return dict(state="PASS", equal=measured, evidence=evidence, receipts=receipts(plan["ledger"]),
                resident_scope="UART numerical/golden only; no trace or protocol coverage",
                ledger=plan["ledger"], elf_sha256={n: c["elf_sha256"] for n, c in plan["cases"].items()})


def soc(out, plan, pins, seal):
    state(out, "BUILDING_BOTH")

    def failed(item, exc):
        state(out, "FAIL_DRAINING_IN_FLIGHT", item=item, error=str(exc),
              dc_launched=False, previous=read(out / "status.json"))

    def build(side):
        work = out / "soc" / side
        _old["execute"](plan["builds"][side], work, work / "build.log", 3600)

    batch(SIDES, 2, build, lambda side, _: print("Built", side, flush=True), failed)
    images = image_pins(out)
    verify(pins)
    state(out, "RUNNING_PAIRED_SOC", completed=0, total=18)
    results = {}

    def run(item):
        side, name = item
        cwd = case_dir(out, side, name)
        cwd.mkdir(parents=True, exist_ok=False)
        case = plan["cases"][name]
        argv = case_argv(out, plan, side, name)
        verify({argv[0]: images[argv[0]], case["elf"]: case["elf_sha256"]})
        print("Running", side, name, flush=True)
        text = _old["execute"](argv, cwd, cwd / "run.log", 3600 if name in _old["RESIDENT"] else 600)
        if name in _old["RESIDENT"]:
            oracle_proof(plan, name, cwd, execute=True)
        return checked_result(case, name, text)

    def accept(item, value):
        side, name = item
        results[item] = value
        other = ("baseline" if side == "candidate" else "candidate", name)
        if other in results:
            check(value == results[other], "paired signatures/cycles differ: " + name)
        state(out, "RUNNING_PAIRED_SOC", completed=len(results), total=18, last=list(item))

    names = [*_old["RESIDENT"], *_old["CASES"]]
    batch([(s, n) for n in names for s in SIDES], plan["jobs"], run, accept, failed)
    verify(pins)
    check(image_pins(out) == images, "built image drift")
    report = dict(**compare_all(out, plan), images=images, source_seal=seal)
    save(out / "soc-pass.json", report)
    digest = sha(out / "soc-pass.json")
    state(out, "SOC_PASS_DC_GATED", soc_pass_sha256=digest)
    submit(out, "dc", seal, digest)


def full_dc(out, plan, pins, seal, proof):
    check(proof and sha(out / "soc-pass.json") == proof == read(out / "status.json")["soc_pass_sha256"],
          "missing or changed SoC gate")
    check(read(out / "soc-pass.json") == dict(**compare_all(out, plan), images=image_pins(out),
                                               source_seal=seal), "SoC evidence drift")
    verify(pins)
    work = out / "dc"
    check(not any((work / FLOW / "outputs").iterdir()), "stale DC outputs")
    state(out, "RUNNING_FULL_DC", soc_pass_sha256=proof)
    log = _old["execute"](plan["dc_command"], out, work / "console.log", 86400)
    check(re.search(r"(?m)^DC_FLOW_COMPLETE$", log) and
          not re.search(r"(?m)^(?:Error:|Fatal:|DC_FLOW_ERROR_COUNT=[1-9])", log), "unclean DC")
    outputs = [work / FLOW / "outputs" / ("ara_soc_dc." + ext) for ext in ("ddc", "sdc", "v")]
    check(all(p.is_file() and p.stat().st_size for p in outputs), "missing mapped DC output")
    verify(pins)
    state(out, "SYNTHESIS_COMPLETE", output_sha256=digests(outputs), soc_pass_sha256=proof,
          timing_signoff=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "launch", "status", "soc", "dc"))
    p.add_argument("out", type=Path)
    p.add_argument("--jobs", type=int, default=6, help="parallel case processes (prepare only)")
    p.add_argument("--seal", help=argparse.SUPPRESS)
    p.add_argument("--proof", help=argparse.SUPPRESS)
    args = p.parse_args()
    out = args.out.resolve()
    check(out.parent == OUT and re.fullmatch(r"resident-repair-[a-zA-Z0-9-]+", out.name),
          "expected a fresh verification/out/resident-repair-* directory")
    if args.action == "prepare":
        prepare(out, args.jobs)
        return
    status = read(out / "status.json")
    if args.action == "status":
        print(json.dumps(status, indent=2))
        return
    seal = sha(out / "source-pins.json")
    pins = read(out / "source-pins.json")
    if args.action == "launch":
        check(status == dict(state="PREPARED", pid=status["pid"], seal=seal), "not unused/sealed")
        verify(pins)
        plan = read(out / "plan.json")
        actual = live_check(plan)
        print(json.dumps(dict(live=actual, effective={r: v["candidate_sha256"]
                         for r, v in plan["ledger"].items()}), indent=2), flush=True)
        submit(out, "soc", seal)
        return
    stage = args.action
    check(any(line.endswith("/" + unit(out, stage)) for line in Path("/proc/self/cgroup").read_text().splitlines())
          and Path(__file__).resolve() == out / "worker.py", "require directly owned frozen service")
    with (out / (stage + ".lock")).open("x") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            check(args.seal == seal and status["state"] ==
                  ("PREPARED" if stage == "soc" else "SOC_PASS_DC_GATED"), "invalid launch state/seal")
            verify(pins)
            plan = read(out / "plan.json")
            if stage == "soc":
                live_check(plan)
                soc(out, plan, pins, seal)
            else:
                full_dc(out, plan, pins, seal, args.proof)
        except Exception as exc:
            state(out, "FAIL", stage=stage, error=str(exc), last_status=read(out / "status.json"))
            raise


if __name__ == "__main__":
    main()
