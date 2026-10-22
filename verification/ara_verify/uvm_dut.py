"""Audit passive CVXIF/AXI UVM and the independent real-DUT contract monitor."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from .artifacts import simulation_image
from .contract import check_contract_log, parse_contract_summary


_UVM_COUNTS = re.compile(
    r"\[CVXIF/COUNT\] observed requests=(?P<requests>\d+) "
    r"responses=(?P<responses>\d+) aborted=(?P<aborted>\d+) "
    r"reused=(?P<reused>\d+) immediate=(?P<immediate>\d+)"
)
_SEVERITY = re.compile(r"^UVM_(ERROR|FATAL)\s*:\s*(\d+)\s*$", re.MULTILINE)
_UVM_EVENT = re.compile(
    r"\[CVXIF/EVENT\] cycle=(?P<cycle>\d+) req_fire=(?P<req_fire>[01]) "
    r"req_id=(?P<req_id>\d+) insn=(?P<insn>[0-9a-fA-FxXzZ]+) "
    r"resp_fire=(?P<resp_fire>[01]) resp_id=(?P<resp_id>\d+) "
    r"exc=(?P<exc>[01xXzZ])"
)
_CONTRACT_EVENT = re.compile(
    r"\[ARA_CONTRACT_TRACE\] sample=pre_edge cycle=(?P<cycle>\d+) "
    r"req=[01xXzZ]/[01xXzZ] fire=(?P<req_fire>[01]) "
    r"id=(?P<req_id>[0-9a-fA-FxXzZ]+) insn=(?P<insn>[0-9a-fA-FxXzZ]+) "
    r"resp=[01xXzZ]/[01xXzZ] fire=(?P<resp_fire>[01]) "
    r"id=(?P<resp_id>[0-9a-fA-FxXzZ]+) exc=(?P<exc>[01xXzZ])"
)
_VID_COUNTS = re.compile(
    r"\[VID/COUNT\] allocations=(?P<allocations>\d+) "
    r"completions=(?P<completions>\d+) aborted=(?P<aborted>\d+) "
    r"max_live=(?P<max_live>\d+)"
)
_AXI_READ_COUNTS = re.compile(
    r"\[AXI/READ_COUNT\] ar=(?P<ar>\d+) r_beats=(?P<r_beats>\d+) "
    r"completed=(?P<completed>\d+) aborted=(?P<aborted>\d+) "
    r"pending=(?P<pending>\d+) max_pending=(?P<max_pending>\d+)"
)
_AXI_WRITE_COUNTS = re.compile(
    r"\[AXI/WRITE_COUNT\] aw=(?P<aw>\d+) w_beats=(?P<w_beats>\d+) "
    r"w_bursts=(?P<w_bursts>\d+) matched=(?P<matched>\d+) "
    r"b=(?P<b>\d+) aborted=(?P<aborted>\d+) "
    r"pending=(?P<pending>\d+) max_pending=(?P<max_pending>\d+)"
)
_AXI_STALL_COUNTS = re.compile(
    r"\[AXI/STALL_COUNT\] ar=(?P<ar>\d+) r=(?P<r>\d+) "
    r"aw=(?P<aw>\d+) w=(?P<w>\d+) b=(?P<b>\d+) "
    r"hold_checks=(?P<hold_checks>\d+)"
)
_VID_EVENT = re.compile(
    r"\[VID/EVENT\] cycle=(?P<cycle>\d+) alloc=(?P<alloc>[01]) "
    r"alloc_id=(?P<alloc_id>\d+) done=(?P<done>[0-9a-fA-F]{2})"
)
_RESET_OBSERVED = re.compile(r"\[CVXIF/RESET\] cycle=(?P<cycle>\d+) epoch=(?P<epoch>\d+)")
_RESET_TRIGGER = re.compile(
    r"\[ARA_UVM_RESET_TEST\] kind=(?P<kind>read|write|state) (?P<event>accepted|observed|released)=1"
)


def _uvm_vid_events(text: str) -> tuple[list[tuple[int, str, int]], list[str]]:
    events = []
    issues = []
    for line in text.splitlines():
        if "[VID/EVENT]" not in line:
            continue
        if not line.startswith("UVM_INFO "):
            continue
        if (match := _VID_EVENT.search(line)) is None:
            issues.append("malformed UVM backend VID event")
            continue
        cycle = int(match["cycle"])
        mask = int(match["done"], 16)
        for vid in range(8):
            if mask & (1 << vid):
                events.append((cycle, "done", vid))
        if match["alloc"] == "1":
            vid = int(match["alloc_id"])
            if vid >= 8:
                issues.append("UVM backend VID allocation is out of range")
            else:
                events.append((cycle, "alloc", vid))
    return events, issues


def _vector_vid_events(path: Path) -> tuple[list[tuple[int, str, int]], list[str]]:
    events = []
    issues = []
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = csv.DictReader(stream)
            if not rows.fieldnames or not {"cycle", "event", "vid"}.issubset(rows.fieldnames):
                return [], ["vector trace lacks cycle/event/vid columns"]
            for row in rows:
                if row["event"] not in ("alloc", "done", "reset"):
                    continue
                try:
                    cycle, vid = int(row["cycle"]), int(row["vid"])
                except (TypeError, ValueError):
                    issues.append("malformed vector trace backend event")
                    continue
                if row["event"] == "reset":
                    events.append((cycle, "reset", -1))
                elif not 0 <= vid < 8:
                    issues.append("vector trace backend VID is out of range")
                else:
                    events.append((cycle, row["event"], vid))
    except (OSError, UnicodeError, csv.Error) as error:
        issues.append(f"cannot read vector trace: {error}")
    return events, issues


def _events(text: str, tag: str, pattern: re.Pattern[str], id_base: int) -> tuple[list[tuple], list[str]]:
    events: list[tuple] = []
    issues: list[str] = []
    idle_records = 0
    for line in text.splitlines():
        if tag not in line or (tag == "[CVXIF/EVENT]" and not line.startswith("UVM_INFO ")):
            continue
        match = pattern.search(line)
        if match is None:
            issues.append(f"malformed {tag} event")
            continue
        fields = match.groupdict()
        req_fire = int(fields["req_fire"])
        resp_fire = int(fields["resp_fire"])
        if not (req_fire or resp_fire):
            if tag == "[ARA_CONTRACT_TRACE]":
                idle_records += 1
            continue
        try:
            events.append((
                int(fields["cycle"]), req_fire,
                int(fields["req_id"], id_base) if req_fire else None,
                int(fields["insn"], 16) if req_fire else None,
                resp_fire,
                int(fields["resp_id"], id_base) if resp_fire else None,
                int(fields["exc"], 2) if resp_fire else None,
            ))
        except ValueError:
            issues.append(f"unknown active field in {tag} event")
    if idle_records:
        issues.append(f"contract trace contains {idle_records} idle records without a handshake")
    return events, issues


def _event_digest(events: list[tuple]) -> str:
    first_cycle = events[0][0]
    normalized = [(event[0] - first_cycle, *event[1:]) for event in events]
    return hashlib.sha256(json.dumps(normalized, separators=(",", ":")).encode()).hexdigest()


def _reset_epoch_vid_digests(
    uvm_events: list[tuple[int, str, int]],
    vector_events: list[tuple[int, str, int]],
    reset_cycle: int,
) -> tuple[str | None, str | None, list[str]]:
    issues = []
    if any(event[0] == reset_cycle for event in uvm_events):
        issues.append("backend VID event occurred in the reset cycle")
    uvm_epochs = [
        [event for event in uvm_events if event[0] < reset_cycle],
        [event for event in uvm_events if event[0] > reset_cycle],
    ]
    markers = [index for index, event in enumerate(vector_events)
               if event[1] == "reset"]
    if len(markers) != 1:
        issues.append(f"expected one independent vector reset marker, found {len(markers)}")
        return None, None, issues
    marker = markers[0]
    vector_epochs = [vector_events[:marker], vector_events[marker + 1:]]
    if any(not events for events in (*uvm_epochs, *vector_epochs)):
        issues.append("backend VID activity is required on both sides of reset")
        return None, None, issues
    for name, epochs in (("UVM", uvm_epochs), ("vector trace", vector_epochs)):
        if any(any(later[0] < earlier[0] for earlier, later in zip(events, events[1:]))
               for events in epochs):
            issues.append(f"{name} backend VID cycle order regressed within reset epoch")
    def epoch_digest(epochs: list[list[tuple[int, str, int]]]) -> str:
        return hashlib.sha256(json.dumps(
            [_event_digest(events) for events in epochs], separators=(",", ":")
        ).encode()).hexdigest()
    return epoch_digest(uvm_epochs), epoch_digest(vector_epochs), issues


def _coverage_observations(
    counts: dict[str, int] | None,
    backend: dict[str, int] | None,
    reads: dict[str, int] | None,
    writes: dict[str, int] | None,
    stalls: dict[str, int] | None,
) -> dict[str, int | None]:
    return {
        "cvxif_requests": counts["requests"] if counts else None,
        "cvxif_same_cycle_reuse": counts["reused"] if counts else None,
        "cvxif_immediate_response": counts["immediate"] if counts else None,
        "backend_vid_max_live": backend["max_live"] if backend else None,
        "axi_read_completed": reads["completed"] if reads else None,
        "axi_read_r_beats": reads["r_beats"] if reads else None,
        "axi_read_max_pending": reads["max_pending"] if reads else None,
        "axi_write_completed": writes["b"] if writes else None,
        "axi_write_w_beats": writes["w_beats"] if writes else None,
        "axi_write_matched_bursts": writes["matched"] if writes else None,
        "axi_write_max_pending": writes["max_pending"] if writes else None,
        **{f"axi_{name}_stall_cycles": stalls[name] if stalls else None
           for name in ("ar", "r", "aw", "w", "b")},
        "axi_hold_checks": stalls["hold_checks"] if stalls else None,
    }


def check_real_uvm_log(path: Path, *, require_events: bool = False,
                       require_backend: bool = False,
                       require_axi: bool = False,
                       require_axi_write: bool = False,
                       vector_trace: Path | None = None,
                       reset_kind: str | None = None) -> dict[str, object]:
    if reset_kind not in (None, "read", "write", "state"):
        raise ValueError("reset_kind must be read, write, state or None")
    issues = check_contract_log(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return {"status": "FAIL", "issues": [*issues, f"cannot read UVM log: {error}"]}

    uvm_matches = list(_UVM_COUNTS.finditer(text))
    contract_matches = [
        record for line in text.splitlines()
        if (record := parse_contract_summary(line)) is not None
    ]
    if len(uvm_matches) != 1:
        issues.append(f"expected one UVM CVXIF summary, found {len(uvm_matches)}")
    if len(contract_matches) != 1:
        issues.append(f"expected one real-DUT contract summary, found {len(contract_matches)}")
    counts = (
        {key: int(value) for key, value in uvm_matches[0].groupdict().items()}
        if len(uvm_matches) == 1 else None
    )
    reset_events = [(int(match["cycle"]), int(match["epoch"]))
                    for match in _RESET_OBSERVED.finditer(text)]
    midrun_resets = reset_events[1:] if reset_events[:1] == [(1, 1)] else reset_events
    reset_triggers = [(match["kind"], match["event"])
                      for match in _RESET_TRIGGER.finditer(text)]
    if reset_kind is None:
        if midrun_resets or reset_triggers:
            issues.append("unexpected mid-run reset in ordinary UVM test")
    elif (len(midrun_resets) != 1 or reset_triggers != [
            (reset_kind, "observed" if reset_kind == "state" else "accepted"),
            (reset_kind, "released")]):
        issues.append("dedicated reset test lacks one matching trigger and observed reset")
    if counts is not None:
        if counts["aborted"] and reset_kind is None:
            issues.append("smoke run reset after accepting a request")
        if counts["requests"] != counts["responses"] + counts["aborted"]:
            issues.append("UVM request/response/reset-abort accounting disagrees")
        if reset_kind is None and contract_matches and any(
            counts[key] != contract_matches[0][key] for key in ("requests", "responses")
        ):
            issues.append("UVM and real-DUT contract traffic counts disagree")
    severity = {name: int(value) for name, value in _SEVERITY.findall(text)}
    if set(severity) != {"ERROR", "FATAL"} or any(severity.values()):
        issues.append("UVM error/fatal report summary is missing or nonzero")
    if "[TEST_DONE]" not in text:
        issues.append("UVM did not complete its check/report phases")
    uvm_events, uvm_event_issues = _events(text, "[CVXIF/EVENT]", _UVM_EVENT, 10)
    contract_events, contract_event_issues = _events(
        text, "[ARA_CONTRACT_TRACE]", _CONTRACT_EVENT, 16
    )
    issues.extend(uvm_event_issues + contract_event_issues)
    if require_events or reset_kind is not None or uvm_events or contract_events:
        if not uvm_events or not contract_events:
            issues.append("UVM and independent contract event traces are both required")
        elif counts is not None:
            for name, events in (("UVM", uvm_events), ("contract", contract_events)):
                if sum(event[1] for event in events) != counts["requests"] or sum(
                    event[4] for event in events
                ) != counts["responses"]:
                    issues.append(f"{name} event trace is incomplete or disagrees with summary")
            if _event_digest(uvm_events) != _event_digest(contract_events):
                issues.append("UVM and independent contract events disagree")
    if reset_kind is not None and len(midrun_resets) == 1 and len(contract_matches) == 1:
        reset_cycle = midrun_resets[0][0]
        if not uvm_events or reset_cycle <= uvm_events[0][0]:
            issues.append("dedicated reset did not follow observed CVXIF activity")
        post_reset = [event for event in uvm_events if event[0] > reset_cycle]
        if any(sum(event[field] for event in post_reset) != contract_matches[0][name]
               for field, name in ((1, "requests"), (4, "responses"))):
            issues.append("post-reset UVM traffic disagrees with contract final epoch")
    backend_matches = list(_VID_COUNTS.finditer(text))
    if len(backend_matches) > 1:
        issues.append(f"multiple backend VID summaries found: {len(backend_matches)}")
    backend_counts = (
        {key: int(value) for key, value in backend_matches[0].groupdict().items()}
        if len(backend_matches) == 1 else None
    )
    if require_backend and backend_counts is None:
        issues.append(f"expected one backend VID summary, found {len(backend_matches)}")
    uvm_vid_events, vid_issues = _uvm_vid_events(text)
    issues.extend(vid_issues)
    if backend_counts is not None and (require_backend or uvm_vid_events):
        if backend_counts["allocations"] == 0:
            issues.append("real DUT UVM observed no backend VID allocations")
        if (backend_counts["allocations"] !=
                backend_counts["completions"] + backend_counts["aborted"]):
            issues.append("backend VID allocation/completion summary differs")
        if (sum(event[1] == "alloc" for event in uvm_vid_events) !=
                backend_counts["allocations"] or
                sum(event[1] == "done" for event in uvm_vid_events) !=
                backend_counts["completions"]):
            issues.append("UVM backend VID event trace is incomplete")
    vector_vid_events = []
    uvm_backend_digest = _event_digest(uvm_vid_events) if uvm_vid_events else None
    vector_backend_digest = None
    if require_backend and vector_trace is None:
        issues.append("independent vector trace is required for backend audit")
    if vector_trace is not None:
        vector_vid_events, vector_issues = _vector_vid_events(vector_trace)
        issues.extend(vector_issues)
        vector_backend_events = [event for event in vector_vid_events if event[1] != "reset"]
        if not uvm_vid_events or not vector_backend_events:
            issues.append("UVM and independent backend VID events are both required")
        elif reset_kind is not None and len(midrun_resets) == 1:
            uvm_backend_digest, vector_backend_digest, epoch_issues = _reset_epoch_vid_digests(
                uvm_vid_events, vector_vid_events, midrun_resets[0][0]
            )
            issues.extend(epoch_issues)
            if (uvm_backend_digest is not None and vector_backend_digest is not None and
                    uvm_backend_digest != vector_backend_digest):
                issues.append("UVM and independent backend VID events disagree across reset epochs")
        else:
            if any(event[1] == "reset" for event in vector_vid_events):
                issues.append("unexpected independent vector reset marker")
            vector_backend_digest = _event_digest(vector_backend_events)
            if uvm_backend_digest != vector_backend_digest:
                issues.append("UVM and independent backend VID events disagree")
    axi_matches = list(_AXI_READ_COUNTS.finditer(text))
    if len(axi_matches) > 1:
        issues.append(f"multiple Ara AXI read summaries found: {len(axi_matches)}")
    axi_counts = (
        {key: int(value) for key, value in axi_matches[0].groupdict().items()}
        if len(axi_matches) == 1 else None
    )
    if require_axi and axi_counts is None:
        issues.append(f"expected one Ara AXI read summary, found {len(axi_matches)}")
    if axi_counts is not None:
        if axi_counts["ar"] != (
            axi_counts["completed"] + axi_counts["aborted"] + axi_counts["pending"]
        ):
            issues.append("Ara AXI read burst accounting disagrees")
        if axi_counts["pending"]:
            issues.append("Ara AXI read bursts remain outstanding")
        if require_axi and (
            axi_counts["ar"] == 0 or axi_counts["completed"] == 0
            or axi_counts["r_beats"] < axi_counts["completed"]
        ):
            issues.append("real DUT UVM observed no complete Ara AXI read traffic")
        if reset_kind == "read" and axi_counts["aborted"] == 0:
            issues.append("read reset did not abort an accepted Ara AXI read")
    write_matches = list(_AXI_WRITE_COUNTS.finditer(text))
    if len(write_matches) > 1:
        issues.append(f"multiple Ara AXI write summaries found: {len(write_matches)}")
    write_counts = (
        {key: int(value) for key, value in write_matches[0].groupdict().items()}
        if len(write_matches) == 1 else None
    )
    if require_axi_write and write_counts is None:
        issues.append(f"expected one Ara AXI write summary, found {len(write_matches)}")
    if write_counts is not None:
        if write_counts["aw"] != (
            write_counts["b"] + write_counts["aborted"] + write_counts["pending"]
        ):
            issues.append("Ara AXI write burst accounting disagrees")
        if write_counts["pending"]:
            issues.append("Ara AXI write bursts remain outstanding")
        if (write_counts["w_bursts"] < write_counts["matched"] or
                write_counts["matched"] < write_counts["b"] or
                write_counts["aw"] < write_counts["matched"] or
                write_counts["w_beats"] < write_counts["w_bursts"]):
            issues.append("Ara AXI AW/W/B traffic counts are inconsistent")
        if require_axi_write and (
            write_counts["aw"] == 0 or write_counts["w_beats"] == 0 or
            write_counts["matched"] == 0 or write_counts["b"] == 0
        ):
            issues.append("real DUT UVM observed no complete Ara AXI write traffic")
        if reset_kind == "write" and write_counts["aborted"] == 0:
            issues.append("write reset did not abort an accepted Ara AXI write")
    if reset_kind == "read" and axi_counts is None:
        issues.append("read reset lacks Ara AXI read accounting")
    if reset_kind == "write" and write_counts is None:
        issues.append("write reset lacks Ara AXI write accounting")
    stall_matches = list(_AXI_STALL_COUNTS.finditer(text))
    stall_counts = (
        {key: int(value) for key, value in stall_matches[0].groupdict().items()}
        if len(stall_matches) == 1 else None
    )
    if len(stall_matches) > 1:
        issues.append("multiple Ara AXI stall summaries found")
    if stall_counts is not None and stall_counts["hold_checks"] > sum(
        stall_counts[name] for name in ("ar", "r", "aw", "w", "b")
    ):
        issues.append("Ara AXI hold checks exceed observed stalled cycles")
    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "reset_kind": reset_kind,
        "uvm_counts": counts,
        "contract_counts": contract_matches[0] if len(contract_matches) == 1 else None,
        "uvm_event_count": len(uvm_events),
        "contract_event_count": len(contract_events),
        "uvm_event_sha256": _event_digest(uvm_events) if uvm_events else None,
        "contract_event_sha256": _event_digest(contract_events) if contract_events else None,
        "backend_counts": backend_counts,
        "axi_read_counts": axi_counts,
        "axi_write_counts": write_counts,
        "axi_stall_counts": stall_counts,
        "coverage_observations": _coverage_observations(
            counts, backend_counts, axi_counts, write_counts, stall_counts
        ),
        "uvm_backend_event_count": len(uvm_vid_events),
        "vector_backend_event_count": sum(event[1] != "reset" for event in vector_vid_events),
        "uvm_backend_event_sha256": uvm_backend_digest,
        "vector_backend_event_sha256": vector_backend_digest,
        "vector_trace_sha256": hashlib.sha256(vector_trace.read_bytes()).hexdigest()
        if vector_trace is not None and vector_trace.is_file() else None,
        "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-events", action="store_true")
    parser.add_argument("--require-backend", action="store_true")
    parser.add_argument("--require-axi", action="store_true")
    parser.add_argument("--require-axi-write", action="store_true")
    parser.add_argument("--vector-trace", type=Path)
    parser.add_argument("--expect-reset-abort", choices=("read", "write", "state"))
    args = parser.parse_args()
    result = check_real_uvm_log(args.log, require_events=args.require_events,
                                require_backend=args.require_backend,
                                require_axi=args.require_axi,
                                require_axi_write=args.require_axi_write,
                                vector_trace=args.vector_trace,
                                reset_kind=args.expect_reset_abort)
    for name, path in (("simv", args.simv), ("elf", args.elf)):
        if not path.is_file():
            result["status"] = "FAIL"
            result["issues"].append(f"{name} is missing: {path}")
        else:
            result[f"{name}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.simv.is_file():
        libraries = Path(str(args.simv) + ".daidir")
        if not libraries.is_dir() or not any(libraries.rglob("*.so")):
            result["status"] = "FAIL"
            result["issues"].append("compiled VCS design libraries are missing")
        else:
            try:
                result["sim_image_sha256"] = simulation_image(args.simv)
            except OSError as error:
                result["status"] = "FAIL"
                result["issues"].append(f"cannot hash compiled VCS design: {error}")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"real DUT CVXIF UVM: {result['status']} ({args.output})")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
