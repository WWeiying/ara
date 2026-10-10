"""Integrity gate for pre-edge cva6_state_prereq_sink captures, not an ISA oracle."""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path
from typing import Iterable


class ProbeError(ValueError):
    pass


REQUIRED_PAYLOAD = {
    "csr": {"mstatus_q", "mstatus_d", "csr_addr", "csr_we", "pc", "ack", "ex_valid", "ex_cause", "ex_tval", "priv"},
    "fpu": {"up_valid", "up_ready", "in_valid", "in_ready", "out_valid", "out_ready", "result", "out_status", "out_tag"},
    "mmu": {"en_i", "en_d", "root", "req", "va", "req_q", "va_q", "pte_q", "valid", "pa", "ex_valid", "cause", "tval", "ptw_req", "ptw_rsp"},
    "mmu_route": {"enabled", "scalar_valid", "scalar_ready", "acc_req", "acc_va", "acc_valid", "acc_pa", "selected_req", "selected_va", "selected_valid"},
    "addrgen": {"enabled", "state", "axi_state", "pe_valid", "pe_id", "held_id", "bytes", "mmu_req", "ack", "ex_valid", "vstart", "qpush", "qpop", "ar_v", "aw_v"},
    "vlsu": {"ar_v", "ar_r", "ar", "aw_v", "aw_r", "aw", "w_v", "w_r", "w", "r_v", "r_r", "r", "b_v", "b_r", "b", "vrf_req", "vrf_gnt", "vrf_final", "vrf_data", "vrf_be"},
    "ptw": {"state", "next", "level_q", "level_d", "ptr_q", "ptr_d", "va_q", "va_d", "root", "cache_req", "cache_gnt", "cache_rvalid", "cache_rdata", "rvalid_q", "rdata_q", "pte", "update", "error", "access_error"},
    "seq": {"state", "next", "req_valid", "req_ready", "req", "token_event", "pe_valid", "pe_ready", "pe_rsp", "lane_q", "mask_q", "running_q", "running_d", "ack", "ex", "vstart", "burst_ex", "resp_ex", "resp_vstart"},
    "dispatcher": {"state", "next", "flush_state", "flush_next", "insn", "acc_valid", "acc_ready", "resp_valid", "resp_ready", "acc_ex", "arch_ex", "arch_vstart", "vstart_q", "vstart_d", "flush_out", "flush_done", "ara_idle"},
    "trap_decode": {"schema", "issue_ports", "flush", "priv", "irq_mie", "irq_mip", "irq_mideleg", "irq_sie", "irq_global",
                    "p0_fetch_valid", "p0_fetch_ready", "p0_fetch_fire", "p0_fetch_pc", "p0_fetch_instr", "p0_fetch_ex_valid", "p0_fetch_ex_cause", "p0_fetch_ex_tval",
                    "p0_decode_instr", "p0_compressed", "p0_illegal", "p0_decoded_valid", "p0_fetch_stall",
                    "p0_dec_pc", "p0_dec_ex_valid", "p0_dec_ex_cause", "p0_dec_ex_tval",
                    "p0_q_valid", "p0_q_pc", "p0_q_orig", "p0_q_ex_valid", "p0_q_ex_cause", "p0_q_ex_tval",
                    "p0_n_valid", "p0_n_pc", "p0_n_orig", "p0_n_ex_valid", "p0_n_ex_cause", "p0_n_ex_tval",
                    "p0_out_valid", "p0_out_ack", "p0_out_fire", "p0_out_pc", "p0_out_orig", "p0_out_ex_valid", "p0_out_ex_cause", "p0_out_ex_tval"},
    "trap_ctrl": {"schema", "xlen", "gplen", "tval_en", "zero_tval", "pc", "ex_valid", "ex_cause", "ex_tval",
                  "priv_q", "priv_d", "trap_to_priv", "epc", "trap_vector", "eret", "flush", "mret", "sret",
                  "mstatus_q", "mstatus_d", "mie_q", "mie_d", "mip_q", "mip_d", "medeleg_q", "medeleg_d", "mideleg_q", "mideleg_d",
                  "mepc_q", "mepc_d", "sepc_q", "sepc_d", "mcause_q", "mcause_d", "scause_q", "scause_d", "mtval_q", "mtval_d", "stval_q", "stval_d",
                  "csr_addr", "conv_addr", "csr_op", "csr_we", "csr_read", "csr_wdata_in", "csr_wdata", "csr_rdata_out", "read_fault", "write_fault", "priv_fault",
                  "csr_ex_valid", "csr_ex_cause", "csr_ex_tval", "commit0_pc", "commit0_id", "commit0_ex_valid", "commit0_ex_cause", "commit0_ex_tval", "ack"},
}


def _fields(text: str) -> dict[str, str]:
    result = {}
    for token in text.split():
        if token.count("=") != 1:
            raise ProbeError(f"malformed field: {token}")
        key, value = token.split("=")
        if not key or not value or key in result:
            raise ProbeError(f"empty or duplicate field: {key}")
        result[key] = value
    return result


def _uint(data: dict[str, str], key: str) -> int:
    value = data.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise ProbeError(f"missing/invalid unsigned {key}: {value!r}")
    return int(value)


def parse_probe(text: str, kind: str, *, clock_observations: dict | None = None) -> dict:
    if kind not in REQUIRED_PAYLOAD:
        raise ProbeError(f"unsupported probe schema: {kind}")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    headers = [line for line in lines if line.startswith("# CVA6_STATE_PREREQ ")]
    ends = [line for line in lines if line.startswith("# END ")]
    if len(headers) != 1 or len(ends) != 1:
        raise ProbeError("capture needs exactly one header and one END")
    if lines[0] != headers[0] or lines[-1] != ends[0]:
        raise ProbeError("header/END must bound the entire capture")
    header = _fields(headers[0][len("# CVA6_STATE_PREREQ "):])
    if header.get("version") != "1" or header.get("kind") != kind or not header.get("instance"):
        raise ProbeError("wrong capture version, kind or instance")
    limit = _uint(header, "max_rows")
    if not 1 <= limit <= 8192:
        raise ProbeError("invalid capture row bound")
    if "# sample=pre_edge input_skew=1step edge_time_unit=ns cycle_origin=first_posedge" not in lines:
        raise ProbeError("missing exact pre-edge sampling contract")
    if any(line.startswith("# TRUNCATED") for line in lines):
        raise ProbeError("capture contains TRUNCATED")
    previous_cycle, previous_epoch, previous_time = -1, 0, -1.0
    count, active_count = 0, 0
    first_time = None
    for line in lines:
        if line.startswith("#"):
            continue
        if not line.startswith("cycle="):
            raise ProbeError("unexpected non-row content")
        fields = _fields(line)
        missing = REQUIRED_PAYLOAD[kind] - fields.keys()
        if missing:
            raise ProbeError(f"missing {kind} signals: {','.join(sorted(missing))}")
        if kind in ("trap_decode", "trap_ctrl") and _uint(fields, "schema") != 1:
            raise ProbeError("unsupported trap payload schema")
        if kind == "trap_decode":
            ports = _uint(fields, "issue_ports")
            if ports not in (1, 2):
                raise ProbeError("unsupported CVA6 issue port count")
            for port in range(1, ports):
                required = {f"p{port}_{key[3:]}" for key in REQUIRED_PAYLOAD[kind] if key.startswith("p0_")}
                if required - fields.keys():
                    raise ProbeError(f"missing trap_decode port {port} signals")
        cycle, epoch = _uint(fields, "cycle"), _uint(fields, "epoch")
        if _uint(fields, "row") != count or cycle <= previous_cycle or epoch < previous_epoch:
            raise ProbeError("nonmonotonic row, cycle or reset epoch")
        if _uint(fields, "gap") != cycle - previous_cycle - 1:
            raise ProbeError("gap does not match omitted cycles")
        if fields.get("activity") not in ("0", "1") or fields.get("rst_n") not in ("0", "1", "x", "z"):
            raise ProbeError("invalid activity/reset encoding")
        stamp = fields.get("edge_time_ns", "")
        if not re.fullmatch(r"[0-9]+\.[0-9]+", stamp):
            raise ProbeError("invalid edge time")
        edge_time = Decimal(stamp)
        if edge_time <= previous_time:
            raise ProbeError("nonmonotonic edge time")
        if count == 0:
            if cycle != 0:
                raise ProbeError("missing initial reset snapshot at cycle zero")
            first_time = edge_time
        if clock_observations is not None:
            sample = (str(edge_time.normalize()), epoch, fields["rst_n"])
            if cycle in clock_observations and clock_observations[cycle] != sample:
                raise ProbeError(f"conflicting time/reset/epoch at shared cycle {cycle}")
            clock_observations[cycle] = sample
        count += 1
        active_count += int(fields["activity"])
        previous_cycle, previous_epoch, previous_time = cycle, epoch, edge_time
    end = _fields(ends[0][len("# END "):])
    if _uint(end, "sim_final") != 1 or _uint(end, "truncated") != 0 or _uint(end, "dropped") != 0:
        raise ProbeError("capture not finalized completely")
    if not count or count > limit or _uint(end, "rows") != count or _uint(end, "limit") != limit:
        raise ProbeError("END row/limit count mismatch")
    if _uint(end, "sampled_edges") <= previous_cycle:
        raise ProbeError("END sampled edge count precedes last row")
    if _uint(end, "activity_edges") != active_count or _uint(end, "epoch") != previous_epoch:
        raise ProbeError("END activity/epoch mismatch")
    return {"kind": kind, "instance": header["instance"], "rows": count,
            "sampled_edges": int(end["sampled_edges"]), "epoch": previous_epoch,
            "activity_edges": active_count, "first_edge_ns": str(first_time)}


def check_probe_capture(workdir: Path, kinds: Iterable[str]) -> dict:
    kinds = list(kinds)
    issues, captures = [], []
    clock_observations = {}
    if not kinds or len(kinds) != len(set(kinds)):
        issues.append("probe kind list must be nonempty and unique")
    for kind in kinds:
        if re.fullmatch(r"[a-z][a-z0-9_]*", kind) is None:
            issues.append(f"invalid probe kind: {kind!r}")
            continue
        paths = sorted(workdir.glob(f"state_prereq.{kind}.log*"))
        if len(paths) != 1 or paths[0].is_symlink() or not paths[0].is_file():
            issues.append(f"{kind}: expected one regular capture, found {len(paths)}")
            continue
        path = paths[0]
        try:
            data = path.read_bytes()
            capture = parse_probe(data.decode("utf-8"), kind, clock_observations=clock_observations)
            capture.update(path=str(path), sha256=hashlib.sha256(data).hexdigest())
            captures.append(capture)
        except (OSError, UnicodeError, ProbeError) as error:
            issues.append(f"{kind}: {error}")
    clocks = {(item["sampled_edges"], item["epoch"], item["first_edge_ns"]) for item in captures}
    if len(clocks) > 1:
        issues.append("capture clock/reset boundaries differ")
    return {"status": "PASS" if not issues else "FAIL", "scope": "capture_integrity_only",
            "required_kinds": kinds, "captures": captures, "issues": issues}
