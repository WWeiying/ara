#!/usr/bin/env python3
"""Interpret passive probes only after unchanged-cycle/numerical acceptance."""
import argparse
from collections import Counter, defaultdict
import csv
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("resident_retirement_analysis", HERE.parent / "analyze.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
require, sha = reference.require, reference.sha


def popcount(value):
    require(value >= 0, "Negative bit vector")
    return bin(value).count("1")


def is_fma(insn):
    # OPFVF vfmacc.vf / vfwmacc.vf, including any legal register selections.
    return insn & 0x707F == 0x5057 and insn >> 26 in (0x2C, 0x3C)


def phase_at(cycle, spans, begin, end):
    if not begin <= cycle < end:
        return "outside_call"
    for span in spans:
        if span["begin"] <= cycle < span["end"]:
            return "qk" if span["helper"] == reference.HELPERS[0] else "pv"
    return "other_call_work"


def lifecycle(path):
    events = []
    with path.open() as stream:
        for row in csv.DictReader(stream):
            require(row["event"] != "reset", "Unexpected reset epoch")
            if row["event"] in ("alloc", "done"):
                events.append((int(row["cycle"]), row["event"], int(row["vid"]),
                               int(row["arch_seq"]), int(row["insn"], 16), int(row["vstart"])))
    require(events and all(a[0] <= b[0] for a, b in zip(events, events[1:])),
            "Nonmonotonic/empty instruction lifetime trace")
    return events


def advance(active, events, index, cycle):
    while index < len(events) and events[index][0] <= cycle:
        _, event, vid, seq, insn, vstart = events[index]
        if event == "alloc":
            require(vid not in active, "VID allocated before completion")
            active[vid] = dict(seq=seq, insn=insn, vstart=vstart)
        else:
            require(vid in active and active[vid]["seq"] == seq, "VID completion mismatch")
            del active[vid]
        index += 1
    return index


def fma_contracts(path, begin, end):
    contracts = {}
    with path.open() as stream:
        for row in csv.DictReader(stream):
            if row["event"] != "alloc" or not begin <= int(row["cycle"]) < end:
                continue
            insn = int(row["insn"], 16)
            if is_fma(insn):
                seq = int(row["arch_seq"])
                require(seq not in contracts and int(row["vstart"]) == 0,
                        "Duplicate or restarted FMA allocation")
                contracts[seq] = dict(vl=int(row["vl"]),
                                      kind="qk" if insn >> 26 == 0x3C else "pv")
    require(contracts, "No FMA allocations in the complete call")
    return contracts


def validate_fma_work(contracts, observed):
    require(set(contracts) == set(observed), "Missing or extra FMA acceptance sequence")
    totals = defaultdict(Counter)
    for seq, contract in contracts.items():
        require(observed[seq] == contract["vl"],
                f"FMA {seq}: accepted elements {observed[seq]} != VL {contract['vl']}")
        totals[contract["kind"]].update(instructions=1, useful_fmas=observed[seq])
    return dict(totals)


def lane_observations(row, active):
    c = Counter(cycles=1)
    issue = bool(row["issue_valid"] and row["issue_remaining"])
    fire = bool(row["fp_valid"] and row["fp_ready"])
    c["fp_input_handshakes"] = int(fire)
    c["fp_output_handshakes"] = int(row["fp_out_valid"] and row["fp_out_ready"])
    c["no_instruction_to_issue_cycles"] = int(not issue)
    c["instruction_waiting_operands_cycles"] = int(issue and not row["operands_valid"])
    c["latency_gated_cycles"] = int(issue and row["latency_stall"])
    c["fp_input_backpressure_cycles"] = int(row["fp_valid"] and not row["fp_ready"])
    c["fp_output_backpressure_cycles"] = int(row["fp_out_valid"] and not row["fp_out_ready"])
    c["result_queue_full_cycles"] = row["result_full"]
    c["vrf_result_denied_cycles"] = int(row["result_req"] and not row["result_gnt"])
    c["vrf_result_handshakes"] = int(row["result_req"] and row["result_gnt"])
    missing = row["operand_required"] & ~row["operand_valid"]
    for channel in range(3):
        c[f"instruction_missing_operand_{channel}_cycles"] = int(issue and bool(missing & (1 << channel)))
    if fire:
        require(issue and row["issue_id"] in active, "FPU acceptance lacks live instruction")
        instruction = active[row["issue_id"]]
        if is_fma(instruction["insn"]):
            require(instruction["vstart"] == 0 and row["vm"] == 1 and row["state"] == 0,
                    "Unreviewed masked/restarted/reduction FMA in profiling window")
            require(row["sew"] in (1, 2) and row["issue_be"] < 256,
                    "Unreviewed FMA destination width")
            c["fma_input_handshakes"] = 1
            c["fma_destination_byte_enable_elements"] = popcount(row["issue_be"]) >> row["sew"]
    return c


def akv_observations(row, lanes=4):
    mask = (1 << lanes) - 1
    fire = row["replay_req"] & row["replay_gnt"]
    accepted = row["accepted"] | fire
    final = row["final_seen"] | (row["replay_final"] & accepted)
    write = row["state"] == 7  # Frozen akv_engine.sv: AKV_ENGINE_REPLAY_WRITE.
    c = Counter(cycles=1)
    c["busy_cycles"] = row["busy"]
    c["command_fires"] = row["command_fire"]
    c["terminals"] = row["terminal"]
    c["frontend_valid_not_ready_cycles"] = int(row["front_valid"] and not row["front_ready"])
    c["replay_write_state_cycles"] = int(write)
    c["replay_lane_accepts"] = popcount(fire)
    c["replay_request_denied_cycles"] = int(bool(row["replay_req"] & ~row["replay_gnt"]))
    c["replay_final_confirmation_wait_cycles"] = int(write and accepted == mask and final != mask)
    c["replay_word_completions"] = int(write and accepted == mask and final == mask)
    c["replay_backpressure_counter_condition_cycles"] = int(write and bool(row["replay_req"]) and
                                                            (accepted != mask or final != mask))
    c["column_bank_read_cycles"] = row["column_bank"]
    c["context_conflict_cycles"] = row["bank_conflict"]
    c["axi_ar_handshakes"] = int(row["ar_valid"] and row["ar_ready"])
    c["axi_r_handshakes"] = int(row["r_valid"] and row["r_ready"])
    c["axi_ar_backpressure_cycles"] = int(row["ar_valid"] and not row["ar_ready"])
    c["axi_r_backpressure_cycles"] = int(row["r_valid"] and not row["r_ready"])
    return c


def numeric_rows(path, first, end):
    count = 0
    with path.open() as stream:
        for raw in csv.DictReader(stream):
            require(None not in raw and all(v is not None for v in raw.values()), "Malformed CSV")
            row = {k: int(v, 16 if k == "insn" else 10) for k, v in raw.items()}
            require(row["cycle"] == first + count, "Incomplete/noncontiguous cycle sample")
            count += 1
            yield row
    require(count == end-first, "Incomplete sample window")


def analyze(profile, accepted, build):
    result_path = profile / "result.json"
    result = json.loads(result_path.read_text())
    require(result["state"] == "PASSIVE_REPLAY_PASS" and
            result["exact_reference_timing_and_outputs"] and result["independent_protocol_checked"] and
            result["post_pins_match"], "Passive replay not fully accepted")
    plan_path = profile / "plan.json"
    plan = json.loads(plan_path.read_text())
    pins = json.loads((profile / "source-pins.json").read_text())
    require(pins[str(plan_path)] == sha(plan_path) and plan["datapath_changes"] == [],
            "Probe plan drift/datapath changed")
    first, end = plan["first_cycle"], plan["end_cycle"]
    require(plan["configuration"]["nr_lanes"] == 4, "Unreviewed lane configuration")
    reference_data = reference.analyze(accepted, build)
    trial = reference_data["trials"][1]
    require(first <= trial["trace_begin"] < trial["trace_end"] <= end and trial["arm"] == 1,
            "Profile does not cover complete first auto call")
    paths = [profile / "work/vector_trace.csv"] + [
        profile / ("work/resident." + name + ".csv") for name in ("akv", "lane0", "lane1", "lane2", "lane3")]
    artifacts = {str(p): sha(p) for p in paths}
    require(all(result["artifacts"].get(p) == value for p, value in artifacts.items()),
            "Accepted probe artifact drift")
    events = lifecycle(paths[0])
    lane_results, accepted_cycles, observed_fmas = {}, defaultdict(set), Counter()
    for lane in range(4):
        phases, active, index = defaultdict(Counter), {}, 0
        for row in numeric_rows(paths[lane+2], first, end):
            cycle = row["cycle"]
            index = advance(active, events, index, cycle)
            phase = phase_at(cycle, trial["helpers"], trial["trace_begin"], trial["trace_end"])
            counts = lane_observations(row, active)
            phases[phase].update(counts)
            if counts["fma_input_handshakes"]:
                accepted_cycles[phase].add(cycle)
                if trial["trace_begin"] <= cycle < trial["trace_end"]:
                    observed_fmas[active[row["issue_id"]]["seq"]] += counts[
                        "fma_destination_byte_enable_elements"]
        lane_results[str(lane)] = dict(phases)
    contracts = fma_contracts(paths[0], trial["trace_begin"], trial["trace_end"])
    work = validate_fma_work(contracts, observed_fmas)
    require(work == {"qk": dict(instructions=768, useful_fmas=35072),
                     "pv": dict(instructions=274, useful_fmas=35072)},
            "FMA work differs from the frozen D128/H2/T137 mathematical contract")
    engine = defaultdict(Counter)
    for row in numeric_rows(paths[1], first, end):
        phase = phase_at(row["cycle"], trial["helpers"], trial["trace_begin"], trial["trace_end"])
        engine[phase].update(akv_observations(row))
    phases = {}
    for phase in engine:
        ncycles = engine[phase]["cycles"]
        totals = Counter()
        for lane in lane_results.values():
            require(lane[phase]["cycles"] == ncycles, "Engine/lane sample mismatch")
            totals.update(lane[phase])
        phases[phase] = dict(cycles=ncycles, akv=engine[phase], lane_totals=totals,
            fma_any_lane_input_cycles=len(accepted_cycles[phase]),
            fma_lane_input_acceptance_ratio=totals["fma_input_handshakes"]/(4*ncycles),
            fp_lane_input_acceptance_ratio=totals["fp_input_handshakes"]/(4*ncycles))
    return dict(schema="resident-cycle-attribution-v1", state="ACCEPTED_PROBES_ANALYZED",
        scope="First auto complete call, real Qwen3 D128/H2/T137, plus window margins",
        arithmetic_utilization_definition="Input acceptance per lane-cycle; not occupied pipeline stages",
        nonadditive_diagnostics=True, hardware_optimization_measured=False,
        phases=phases, lanes=lane_results, checked_arithmetic_work=work, reference_trial=trial,
        source_artifacts={**artifacts, str(result_path): sha(result_path), str(plan_path): sha(plan_path)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--accepted", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.profile.resolve(), args.accepted.resolve(), args.build.resolve())
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(state=result["state"], output=str(args.output))))
