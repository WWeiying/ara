#!/usr/bin/env python3
"""Existing image only: captured e8/m2 gate, original18, exact controls16."""
import argparse
import csv
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
import capture_failed as c
import analyze_failure as decode
r, p = c.r, c.r.p
LANE_SHA = "dfda48c8f3c9c1a1f0f41499a48b890cfaa112eb822f702ed8738fe3ae3705fa"
CONTROLS = r.HERE.parent / "fp_moves/candidate03_controls16_01"
PROGRAMS = r.HERE / "prepared01/soc"


def cycle_gate(dest):
    baseline = c.OUT / "replay/tests" / c.NAME / "commit_trace.csv"
    current = dest / "replay/tests" / c.NAME / "commit_trace.csv"
    traces = []
    for path in (baseline, current):
        with path.open() as stream:
            rows = list(csv.DictReader(stream))
        target = [x for x in rows if x["event"] == "retire" and x["pc"] == "0000000080000508"]
        p.require(len(target) == 1 and target[0]["insn"] == "60880457", "Target identity differs")
        traces.append([x for x in rows if int(x["cycle"]) <= 19203])
    p.require(traces[0] == traces[1], "Prefix cycles drifted; review capture window before proceeding")
    previous = c.OUT
    try:
        c.OUT = dest
        decode.OUT = dest / "cycle"
        decode.main()
    finally:
        c.OUT = previous
    rows = p.read(dest / "cycle/raw_cycles.json")
    command_checks, address_checks = [], []
    for lane in range(4):
        qpath = r.ARA + f".gen_lanes[{lane}].i_lane.i_operand_requester"
        for q, base in ((0,64), (1,32)):
            commands = [x for x in rows if x[qpath+".operand_request_valid_i"] &
                        x[qpath+".operand_request_ready_o"] & (1 << q)]
            p.require(len(commands) == 1, "Unexpected source command count")
            x = commands[0]
            values = {n:x[qpath+f".operand_request_i[{q}]."+n] for n in ("id","vs","eew","vl","vstart")}
            p.require(values == dict(id=0, vs=base//4, eew=0, vl=32, vstart=0), "Source origin not zero")
            command_checks.append(dict(lane=lane, q=q, cycle=x["cycle"], **values))
            addresses = [x[qpath+f".requester_metadata_q[{q}].addr"] for x in rows
                         if x[qpath+f".operand_requester_gnt[{q}]"]]
            p.require(addresses == list(range(base,base+4)), "VRF source range differs")
            address_checks.append(dict(lane=lane, q=q, addresses=addresses))
    valu = r.ARA + ".gen_lanes[0].i_lane.i_vfus.i_valu"
    accepted = [x for x in rows if x[valu+".valu_valid"] and
                x[valu+".alu_operand_valid_i"] == x[valu+".alu_operand_ready_o"] == 3]
    p.require(len(accepted) == 4, "VALU beat count differs")
    third = accepted[2]
    ab = [(third[valu+"."+n] >> 40) & 255 for n in ("alu_operand_a","alu_operand_b")]
    p.require(ab == [0xac,0xe4] and (third[valu+".valu_result"] >> 40) & 1 == 0, "Source84 comparison not corrected")
    slices = [x for x in rows if x[r.MASK+".in_ready_cnt_en"] and
              x[r.MASK+".masku_operand_alu_valid"] == x[r.MASK+".masku_operand_alu_ready"] == 15]
    p.require([x[r.MASK+".vrf_pnt_q"] for x in slices] == [0,32,64,96], "MASKU slice coordinates differ")
    p.require((slices[2][r.MASK+".alu_result_compressed_seq"] >> 84) & 1 == 0, "MASKU bit84 not zero")
    qpath = r.ARA + ".gen_lanes[2].i_lane.i_operand_requester"
    writes = [x for x in rows if x[qpath+".masku_result_req"] and x[qpath+".masku_result_gnt"]]
    p.require(len(writes) == 1 and writes[0][qpath+".masku_result_addr"] == 32 and
              writes[0][qpath+".masku_result_be"] == 255 and
              (writes[0][qpath+".masku_result_wdata"] >> 20) & 1 == 0, "Final bit84 write not zero")
    p.prepare.save(dest / "cycle/gate.json", dict(status="PASS_ORIGIN0_BIT84_ZERO", prefix_cycles_equal=True,
        commands=command_checks, vrf_addresses=address_checks, valu_cycle=third["cycle"],
        alu_a_byte5=ab[0], alu_b_byte5=ab[1], masku_cycle=slices[2]["cycle"],
        final_write_cycle=writes[0]["cycle"], no_force=True))


def main(args):
    out, image = args.out.resolve(), args.image.resolve()
    p.require(out.is_relative_to(r.HERE) and out != r.HERE and not out.exists(), "Fresh owned output required")
    ledger = p.read(image / "image.json")
    p.require(p.prepare.sha(image / "image.json") == args.image_sha256, "Image ledger pin differs")
    snapshot = Path(ledger["snapshot"])
    p.require(p.read(snapshot / "snapshot.json")["files"]["hardware/src/lane/lane_sequencer.sv"] == LANE_SHA, "Wrong candidate lane")
    out.mkdir()
    pins = p.read(r.HERE / "measurement01/pins.json")
    pins.update(ledger["files"])
    for file in (Path(__file__).resolve(), Path(c.__file__), Path(decode.__file__),
                 r.HERE / "analyze_selected.py", image / "image.json", snapshot / "snapshot.json",
                 c.OUT / "capture.tcl", c.OUT / "plan.json",
                 c.OUT / "replay/tests" / c.NAME / "commit_trace.csv",
                 CONTROLS / "plan.json", CONTROLS / "complete.json"):
        pins[str(file)] = p.prepare.sha(file)
    pins.update({str(snapshot / "sources" / name): digest for name,digest in p.read(snapshot / "snapshot.json")["files"].items()})
    original19 = p.read(PROGRAMS / "programs.json")["programs"]
    p.require(len(original19) == 19 and c.NAME in original19, "Wrong19 membership")
    controls = p.read(CONTROLS / "plan.json")["cases"]
    p.require(len(controls) == 16 and p.read(CONTROLS / "complete.json")["status"] == "PASS_16_M3_TRACE_IDENTICAL_M2", "Controls baseline not PASS")
    stages = [dict(name="first", programs=str(PROGRAMS), cases=[c.NAME], jobs=1),
              dict(name="remaining18", programs=str(PROGRAMS), cases=[n for n in original19 if n != c.NAME], jobs=2)]
    for group, directory in (("smokes", Path("/tmp/current-board-integration-smoke02")),
                             ("singles", Path("/tmp/current-board-integration-fast01/soc"))):
        selected = [x for x in controls if x["group"] == group]
        p.require(len(selected) == (10 if group == "smokes" else 6), "Control membership differs")
        manifest = p.read(directory / "programs.json")
        for entry in selected:
            actual = manifest["programs"][entry["original_name"]]
            p.require(actual["sha256"] == entry["sha256"] and actual["pass_markers"] == entry["pass_markers"], "Control ELF/oracle differs")
        stages.append(dict(name=group, programs=str(directory), cases=[x["original_name"] for x in selected], jobs=2))
    for stage in stages:
        directory = Path(stage["programs"])
        manifest = p.read(directory / "programs.json")
        for file in [directory / "programs.json", *[x for x in Path(manifest["prepared"]).rglob("*") if x.is_file()],
                     *[Path(manifest["programs"][n]["path"]) for n in stage["cases"]]]:
            pins[str(file)] = p.prepare.sha(file)
    r.verify(pins)
    p.prepare.save(out / "plan.json", dict(image=str(image), image_sha256=args.image_sha256, stages=stages,
        timeout_s=180, stop_first_fail=True, pins=pins, no_build=True, no_rtl_edits=True,
        capture_window_ns=[18000,20500], global_cap=24, mem_floor_gib=32, reserved_nf7=2))
    framework = r.shared.framework
    def admitted(repo):
        base, options, test, identity = framework(repo)
        class Runner(base):
            def _run_test(self, case, simv):
                if not self.cancel_event.is_set():
                    p.prepare.save(out / ("admission_"+case.name+".json"), r.resources(out, 2))
                return super()._run_test(case, simv)
        return Runner, options, test, identity
    r.shared.framework = admitted
    r.shared.framework(snapshot / "sources")
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern + "|" + p.FAIL.pattern, engine.FAIL_RE.flags)
    r.shared.oracle_complete = p.oracle
    monitored = engine._run_monitored
    started, observations = time.time(), []
    for stage in stages:
        r.verify(pins)
        dest = out / stage["name"]
        dest.mkdir()
        p.prepare.save(dest / "resources.json", r.resources(out, stage["jobs"]))
        if stage["name"] == "first":
            tcl = dest / "capture.tcl"
            # Identical baseline signal set, commands and time window, no force.
            tcl.write_bytes((c.OUT / "capture.tcl").read_bytes())
            p.prepare.save(dest / "profile.json", p.read(c.OUT / "plan.json"))
            def capture(command, cwd, console, timeout, cancel):
                command = [*command, "-ucli", "-do", str(tcl)]
                p.prepare.save(console.parent / "command.json", dict(command=command, cwd=str(cwd)))
                return monitored(command, cwd, console, timeout, cancel)
            engine._run_monitored = capture
        try:
            rc = r.shared.run_programs(SimpleNamespace(image=image, programs=Path(stage["programs"]),
                out=dest / "replay", case=stage["cases"], jobs=stage["jobs"], timeout=180, execute=True))
        finally:
            engine._run_monitored = monitored
        results = p.read(dest / "replay/summary.json")
        passed = rc == 0 and len(results) == len(stage["cases"]) and all(x["status"] == "PASS" and x["returncode"] == 0 for x in results)
        observations.append(dict(stage=stage["name"], passed=passed, results=results))
        p.prepare.save(dest / "status.json", observations[-1])
        if not passed:
            break
        if stage["name"] == "first":
            cycle_gate(dest)
    r.verify(pins)
    comparisons = []
    for entry in controls:
        new = out / entry["group"] / "replay/tests" / entry["original_name"] / "commit_trace.csv"
        old = CONTROLS / "replay/tests" / entry["id"] / "commit_trace.csv"
        if new.exists():
            comparisons.append(dict(name=entry["id"], candidate03_sha256=p.prepare.sha(old),
                candidate04_sha256=p.prepare.sha(new), cycle_trace_equal=p.prepare.sha(old) == p.prepare.sha(new)))
    passed = len(observations) == 4 and all(x["passed"] for x in observations)
    p.prepare.save(out / "complete.json", dict(status="PASS_19_PLUS_16" if passed else "NOT_PASS", stages=observations,
        elapsed_s=time.time()-started, pins_unchanged=True, comparisons=comparisons,
        scope="19 archived singles and16 controls, not original parent matrices or Linux closure"))
    return int(not passed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output already exists; never modify a previous measurement")
    env = r.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    try:
        sys.exit(main(args))
    except Exception as error:
        if args.out.is_dir():
            p.prepare.save(args.out / "error.json", dict(error=str(error), finished=time.time(), next_stage_not_authorized=True))
        raise
