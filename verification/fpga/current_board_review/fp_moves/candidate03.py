#!/usr/bin/env python3
"""Pinned scalar-move A/B; one separate image, serial programs, no RTL edits."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
import focused as f

HERE, checked, prepare = f.HERE, f.checked, f.prepare
CANDIDATE = Path("/home/wangwy/fpga_runs/current_board_memory_candidate03")
DISPATCHER = "05e9a4633d3d3a989fc5433fbf647c26c9d21ec1837b210ee84b6c712f6815fd"
ROOT = HERE.parents[3]
CAPTURE = {"fp_move_original", "int_plain_restart", "fp_old64_restart", "int_old8_restart"}


def read(p):
    return json.loads(p.read_text())


def profile():
    names = f.profile()
    names += [f.ARA + ".i_dispatcher." + n for n in (
        "state_q", "state_d", "decode_blocked", "ara_req", "layout_req",
        "reshuffle_req_q", "reshuffle_req_d", "eew_q[24]", "eew_d[24]",
        "eew_valid_q", "vs_buffer_q", "eew_old_buffer_q", "eew_new_buffer_q",
        "rs_lmul_cnt_q", "rs_lmul_cnt_limit_q")]
    return names


def replay(image_dir, build_dirs, out):
    out.mkdir(parents=True, exist_ok=False)
    ledger = read(image_dir / "image.json")
    if image_dir == f.IMAGE:
        assert prepare.sha(image_dir / "image.json") == f.IMAGE_SHA
    else:
        assert image_dir == CANDIDATE / "campaign/image"
        assert prepare.sha(Path(ledger["snapshot"]) / "sources/hardware/src/ara_dispatcher.sv") == DISPATCHER
    programs, pins = {}, dict(ledger["files"])
    pins[str(image_dir / "image.json")] = prepare.sha(image_dir / "image.json")
    for build_dir in build_dirs:
        assert read(build_dir / "reference.json")["status"] == "PASS"
        assert read(build_dir / "host.json")["status"] == "PASS"
        items = read(build_dir / "soc/programs.json")["programs"]
        assert not set(programs) & set(items)
        programs.update(items)
        checked.run_programs(SimpleNamespace(image=image_dir, programs=build_dir / "soc",
            case=list(items), jobs=1, timeout=180, execute=False,
            out=out / ("preflight_" + build_dir.name)))
        for p in build_dir.rglob("*"):
            if p.is_file() and (p.suffix in (".elf", ".json") or "prepared" in p.parts):
                pins[str(p)] = prepare.sha(p)
    for p in (Path(__file__), HERE / "focused.py", HERE / "supplement.py"):
        pins[str(p)] = prepare.sha(p)
    prepare.save(out / "pins.json", pins)
    prepare.save(out / "profile.json", dict(signals=profile(), window_ns=[0, 50000]))
    results = []
    for name, entry in programs.items():
        dest = out / name
        dest.mkdir()
        prepare.save(dest / "resources.json", f.resource_check())
        assert prepare.sha(Path(entry["path"])) == entry["sha256"]
        shutil.copyfile(entry["path"], dest / "input.elf")
        command = ["/usr/bin/nice", "-n", "10", ledger["simv"], "-no_save", "-l", "run.vcs.log",
                   "+ntb_random_seed=1", "+PRELOAD=" + str(dest / "input.elf"), "+TESTCASE=" + name,
                   "+NO_FSDB", "+COMMIT_TRACE=" + str(dest / "commit_trace.csv")]
        if name in CAPTURE:
            tcl = ["onerror {quit}", "set fid [dump -file selected.fsdb -type FSDB]"]
            tcl += ["dump -add {" + n + "} -aggregates -fid $fid" for n in profile()]
            tcl += ["run -absolute 50000ns", "dump -disable -fid $fid", "dump -flush $fid", "run", "quit"]
            (dest / "capture.tcl").write_text("\n".join(tcl) + "\n")
            command += ["-ucli", "-do", str(dest / "capture.tcl")]
        prepare.save(dest / "command.json", dict(command=command, timeout_s=180,
            elf_sha256=entry["sha256"], image_sha256=prepare.sha(image_dir / "image.json")))
        began, timeout = time.monotonic(), False
        with (dest / "console.log").open("w") as log:
            process = subprocess.Popen(command, cwd=dest, env=checked.environment(),
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            prepare.save(dest / "launch.json", dict(pid=process.pid, started=time.time()))
            try:
                rc = process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                timeout = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    rc = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    rc = process.wait()
        log = (dest / "console.log").read_text()
        passed = rc == 0 and all(m in log for m in entry["pass_markers"]) and "Core Test *** SUCCESS *** (tohost = 0)" in log
        numerical = "RVV_FP_MOVE_FAIL sew=16 cases=1 errors=" in log
        result = dict(name=name, status="TIMEOUT" if timeout else "PASS" if passed else "FAIL",
            returncode=rc, elapsed_s=time.monotonic()-began,
            oracle_lines=[s for s in log.splitlines() if "RVV_FP_MOVE_" in s or "BOARD_CASE_" in s],
            input_sha256=prepare.sha(dest / "input.elf"), console_sha256=prepare.sha(dest / "console.log"))
        prepare.save(dest / "status.json", result)
        results.append(result)
        print(json.dumps(result), flush=True)
        # Baseline numerical failures are the hypothesis under test, not grounds
        # for omitting the already-authorized controls. All other failures stop.
        if timeout or (not passed and not numerical):
            break
    for path, digest in pins.items():
        assert prepare.sha(Path(path)) == digest, path
    status = "PASS" if len(results) == len(programs) and all(x["status"] == "PASS" for x in results) else "MEASURED_NONPASS"
    prepare.save(out / "complete.json", dict(status=status, results=results,
        all_planned_completed=len(results) == len(programs), pins_unchanged=True, jobs=1,
        image_sha256=prepare.sha(image_dir / "image.json"), no_rtl_edits=True))


def freeze():
    assert not CANDIDATE.exists(), "candidate destination already exists"
    old = read(Path(read(f.IMAGE / "image.json")["snapshot"]) / "snapshot.json")
    changes = []
    for n, digest in old["files"].items():
        if n.startswith("hardware/src/") and prepare.sha(ROOT / n) != digest:
            changes.append(n)
    assert changes == ["hardware/src/ara_dispatcher.sv"], changes
    assert prepare.sha(ROOT / changes[0]) == DISPATCHER
    CANDIDATE.mkdir()
    prepare.save(CANDIDATE / "resources_before_freeze.json", f.resource_check())
    checked.snapshot(CANDIDATE / "frozen")
    snap = read(CANDIDATE / "frozen/snapshot.json")
    changes = [n for n, digest in snap["files"].items()
               if n.startswith("hardware/src/") and old["files"].get(n) != digest]
    assert changes == ["hardware/src/ara_dispatcher.sv"], changes
    assert snap["files"][changes[0]] == DISPATCHER
    prepare.save(CANDIDATE / "delta.json", dict(changed_production_files=changes,
        dispatcher_sha256=DISPATCHER, base_image_sha256=f.IMAGE_SHA,
        frozen_sha256=prepare.sha(CANDIDATE / "frozen/snapshot.json"),
        scope="Only two scalar-insert internal-vstart assignments and comments"))
    print("FROZEN", CANDIDATE, DISPATCHER, flush=True)


def build_and_after():
    baseline = HERE / "candidate02_supplement01/complete.json"
    integer = HERE / "integer_before_cycle01/finding.json"
    assert read(baseline)["all_planned_completed"]
    assert next(r for r in read(baseline)["results"] if r["name"] == "int_plain_restart")["status"] == "FAIL"
    assert read(integer)["be_suppression_proved"]
    snap = CANDIDATE / "frozen"
    assert read(snap / "snapshot.json")["files"]["hardware/src/ara_dispatcher.sv"] == DISPATCHER
    prepare.save(CANDIDATE / "resources_before_build.json", f.resource_check())
    checked.build_image(SimpleNamespace(snapshot=snap, out=CANDIDATE / "campaign/image", authorize_build=True))
    replay(CANDIDATE / "campaign/image", [HERE / "port02", HERE / "supplement01"], HERE / "candidate03_after01")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("baseline", "freeze", "build-after"))
    args = parser.parse_args()
    if args.mode == "baseline":
        replay(f.IMAGE, [HERE / "supplement01"], HERE / "candidate02_supplement01")
    elif args.mode == "freeze":
        freeze()
    else:
        build_and_after()
