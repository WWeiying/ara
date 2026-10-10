"""Read-only case-specific NO_TRAFFIC diagnosis, never an admission override."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re

from audit_historical_nonpass_717 import Audit, OUT, ROOT, sha

BASE = OUT / "gap102b-offline-admitted-719-20261006-01"
LOG_NAMES = ("run.vcs.log", "console.log", "rtl_console.log")
ERROR = re.compile(r"^UVM_(ERROR|FATAL)\s+(?!:).*?\[([^\]]+)\]\s+(.*)$")
COUNT = re.compile(r"^UVM_INFO\s+.*?\[(CVXIF/COUNT|VID/COUNT)\]\s+(.*)$")
ALLOWED = {"CVXIF/NO_TRAFFIC", "VID/NO_TRAFFIC"}
FRONT = {
    "villegal_segment_recovery": (3, 1, "Rejected segment request; scalar recovery; no legal backend operation."),
    "villegal_vstart_ops": (27, 8, "Eight vstart!=0 illegal operations; vector CSR/configuration requests only otherwise."),
    "vsetivli": (85, 0, "Configuration and VL/VTYPE readback; no vector data operation."),
    "vsetvli": (85, 0, "Configuration and VL/VTYPE readback; no vector data operation."),
    "vsetvl": (85, 0, "Configuration and VL/VTYPE readback; no vector data operation."),
    "linux_state_prereq": (86, 0, "VS/FS state, vtype/configuration and VS-Off rejection; no vector data operation."),
    "linux_csr_gap33": (1, 0, "CSR privilege/WARL checks; one vset configuration, no backend data operation."),
    "sv39_gap52_superpage_sfence_pmp0": (42, 0, "Scalar S-mode memory/SFENCE/PMP checks; vector CSR save/restore only."),
    "sv39_gap68_warm_permissions_pmp0": (20, 0, "Scalar warm permission loads; vector CSR save/restore only."),
}
SCALAR = {
    "linux_mmu_relocate": "Scalar Linux relocation, page-table and scalar data access checks.",
    "stvec_readback": "STVEC WARL/readback matrix, not vector execution.",
    "coverage_trap_state_quiet": "Scalar trap/delegation payload via trap_state_prereq.c.",
    "trap_state_prereq": "Scalar ECALL/EBREAK/illegal CSR/interrupt trap and privilege checks.",
    "sv39_gap34_load": "G34_KIND=0 scalar ld permission/fault/value matrix.",
    "sv39_gap34_store": "G34_KIND=1 scalar sd permission/fault/memory matrix.",
    "sv39_gap34_fetch": "G34_KIND=2 mret/fetch/ECALL permission/fault matrix.",
    "scalar_gap35_memory": "Scalar memory operations and guards.",
    "scalar_gap35_alu_control": "Scalar ALU/control operations.",
    "scalar_gap35_illegal": "Scalar illegal encodings and trap payload checks.",
    "csr_gap35_counteren": "Counter access privilege checks.",
    "csr_gap35_fp_rw": "Floating-point CSR RMW, not vector execution.",
    "csr_gap35_permissions": "CSR privilege/permission/trap matrix.",
    "fence_t_gap36_smoke": "CVA6 custom0 FENCE.T/controller microreset and scalar state, not Ara backend.",
    "gap37_csr_alias_tvm": "CSR aliases and TVM/SFENCE privilege checks.",
    "csr_gap44_absent": "Absent CSR illegal-access matrix.",
    "scalar_gap63_zcb_reject": "Unsupported scalar compressed Zcb trap matrix.",
}


def parse_log(text):
    errors, counts = [], {}
    summaries = []
    for line_number, line in enumerate(text.splitlines(), 1):
        match = ERROR.match(line)
        if match:
            errors.append(dict(line=line_number, severity=match[1], tag=match[2], message=match[3]))
        match = COUNT.match(line)
        if match:
            if match[1] in counts:
                raise ValueError("Repeated actual UVM counter record")
            counts[match[1]] = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", match[2])}
        if re.match(r"^UVM_(?:ERROR|FATAL)\s*:\s*\d+\s*$", line):
            summaries.append(line)
    return dict(errors=errors, counts=counts, summary_lines=summaries)


def vector_data(word):
    opcode, funct3 = word & 127, (word >> 12) & 7
    return (opcode == 0x57 and funct3 != 7) or (opcode in (7, 0x27) and funct3 in (0, 5, 6, 7))


def trace_evidence(path):
    events, requests, responses = Counter(), [], []
    with path.open() as stream:
        for row in csv.DictReader(stream):
            events[row["event"]] += 1
            if row["event"] == "cvx_req":
                requests.append(dict(id=row["trans_id"], insn=row["insn"], data=vector_data(int(row["insn"], 16))))
            elif row["event"] == "cvx_resp":
                responses.append(dict(id=row["trans_id"], trap=int(row["trap"])))
    complete_pairs = len(requests) == len(responses) and all(q["id"] == r["id"] for q, r in zip(requests, responses))
    return dict(events=dict(events), request_response_pairing=complete_pairs,
                trapped_responses=sum(r["trap"] != 0 for r in responses),
                untrapped_vector_data_requests=sum(q["data"] and not r["trap"] for q, r in zip(requests, responses)),
                request_words=dict(Counter(q["insn"] for q in requests)))


def classify(name, parsed, trace):
    issues = []
    if any(e["tag"] not in ALLOWED or e["severity"] == "FATAL" for e in parsed["errors"]):
        issues.append("Unexpected actual UVM ERROR/FATAL; hold, not silently ignored")
    req = parsed["counts"].get("CVXIF/COUNT", {})
    vid = parsed["counts"].get("VID/COUNT", {})
    expected, traps, reason = (*FRONT[name],) if name in FRONT else (0, 0, SCALAR.get(name, "Unknown expectation"))
    if name not in FRONT and name not in SCALAR:
        issues.append("No case-specific source expectation")
    events = trace["events"]
    if req.get("requests") != expected or req.get("responses") != expected or req.get("aborted") != 0:
        issues.append("Request/response differs from case-specific expectation")
    if any(vid.get(k) != 0 for k in ("allocations", "completions", "aborted", "max_live")):
        issues.append("Backend counter differs from expected zero")
    if events.get("cvx_req", 0) != expected or events.get("cvx_resp", 0) != expected or trace["trapped_responses"] != traps:
        issues.append("Independent trace request/response/trap disagreement")
    if not trace["request_response_pairing"] or trace["untrapped_vector_data_requests"]:
        issues.append("Unexplained legal data request or pairing mismatch")
    if any(n and ("alloc" in k or "uop" in k) for k, n in events.items()):
        issues.append("Unexpected backend trace activity")
    return dict(classification="HOLD_UNEXPECTED_OR_UNPROVEN" if issues else
                "EXPECTED_FRONTEND_ONLY_ZERO_VID" if name in FRONT else "EXPECTED_SCALAR_ZERO_REQ_ZERO_VID",
                expected_requests=expected, expected_rejected_responses=traps, reason=reason, issues=issues)


def source_paths(name):
    if name == "scalar_gap63_zcb_reject":
        return [OUT / "gap63-zcb-preflight-20261004-01/scalar_gap63_zcb_reject.c"]
    if name == "fence_t_gap36_smoke":
        return [ROOT / "apps/fence_t_gap36_smoke" / n for n in ("main.c", "probe.S")]
    folder = ROOT / "apps/riscv-tests/isa/rv64uv"
    paths = [folder / (name + ".c")]
    for path in list(paths):
        for include in re.findall(r'^#include "([^\"]+)"', path.read_text(), re.M):
            if (folder / include).is_file():
                paths.append(folder / include)
    return list(dict.fromkeys(paths))


def run(output):
    if output.exists() or output.parent != OUT:
        raise ValueError("Fresh independent output required")
    a = Audit()
    a.pin(__file__)
    a.pin(Path(__file__).with_name("test_audit_uvm_no_traffic_719.py"))
    manifest = a.load(BASE / "admission-manifest.json")
    for path, digest in manifest["output_pins"].items():
        a.pin(path, digest)
    databases = a.pin(BASE / "combined-inputs.txt").read_text().splitlines()
    assert len(databases) == 720 and len(set(databases)) == 720
    build = a.load(OUT / "repaired-aligned-build-20260930-01/build-source-pins.json")
    compiled, source_identity_gaps = [], []
    for relative in ("verification/uvm/ara_cvxif_uvm_pkg.sv", "hardware/src/ara_dispatcher.sv"):
        path = ROOT / relative
        a.pin(path)
        bound = a.pins[str(path)] == build[str(path)]
        binding = dict(path=str(path), compiled_sha256=build[str(path)], current_sha256=a.pins[str(path)],
                       exact_compiled_source_match=bound)
        compiled.append(binding)
        if not bound:
            source_identity_gaps.append(binding)
    a.pin(ROOT / "verification/ara_verify/contract.py")
    a.pin(ROOT / "verification/ara_verify/plan.py")
    cases, scanned, recovered, missing, other_errors = [], [], [], [], []
    plans = {}
    for value in databases[1:]:
        db = Path(value)
        logs = [db.parent / n for n in LOG_NAMES if (db.parent / n).is_file()]
        adjacent = bool(logs)
        result = next((p for p in db.parents if p.parent.name == "results"), db.parent)
        batch = result.parent.parent
        outcome_path = batch / "outcomes" / (result.name + ".json")
        outcome = a.load(outcome_path) if outcome_path.is_file() else {}
        if not logs:
            logs = [db.parent / "work" / n for n in LOG_NAMES if (db.parent / "work" / n).is_file()]
            if logs:
                for p in logs:
                    a.pin(p, outcome.get("files", {}).get(str(p)))
                recovered.append(dict(vdb=value, logs=[str(p) for p in logs], outcome=str(outcome_path),
                                      path_binding="Same result/work, not historical source log"))
            else:
                missing.append(value)
        parsed_logs = []
        for log in logs:
            parsed = parse_log(a.pin(log).read_text(errors="replace"))
            scanned.append(dict(vdb=value, log=str(log), adjacent=adjacent, **parsed))
            parsed_logs.append((log, parsed))
            other_errors.extend(dict(vdb=value, log=str(log), **e) for e in parsed["errors"] if e["tag"] not in ALLOWED or e["severity"] == "FATAL")
        with_errors = [(p, data) for p, data in parsed_logs if data["errors"]]
        if not with_errors:
            continue
        log, parsed = with_errors[0]
        artifact = log.parent.parent if log.parent.name == "work" else log.parent
        name = artifact.name.removeprefix("rvv_").removeprefix("app_")
        plan_path = batch / "plan.json"
        if str(plan_path) not in plans:
            plans[str(plan_path)] = a.load(plan_path)
        matches = [c for c in plans[str(plan_path)]["cases"] if c["name"] == result.name]
        assert len(matches) == 1
        producer = matches[0]
        elf = a.pin(artifact / "input.elf", producer["elf_sha256"])
        trace = trace_evidence(a.pin(artifact / "commit_trace.csv"))
        ts = a.load(artifact / "trace_summary.json")
        audit = a.load(result / "independent_audit.json")
        summary = a.load(result / "summary.json")
        console = a.pin(artifact / "console.log").read_text(errors="replace")
        source = []
        for path in source_paths(name):
            expected = producer.get("source_files", {}).get(str(path))
            a.pin(path, expected)
            excerpts = [dict(line=i, text=line) for i, line in enumerate(path.read_text().splitlines(), 1)
                        if re.search(r"(?:asm|check|CHECK|vset|vstart|ld |sd |trap|G34_KIND|PASSED|NO_TRAFFIC|FENCE)", line)][:100]
            source.append(dict(path=str(path), sha256=a.pins[str(path)], producer_hash_bound=expected is not None,
                               role="Producer-bound source" if expected else "Current pinned source context, not compile attestation", excerpts=excerpts))
        diagnosis = classify(name, parsed, trace)
        if audit.get("status") != "PASS" or not re.search(r"PASSED", console) or re.search(r"(?:^|\n)FAIL(?:ED)?[: ]", console):
            diagnosis["issues"].append("Functional/oracle evidence incomplete or failing")
            diagnosis["classification"] = "HOLD_UNEXPECTED_OR_UNPROVEN"
        cases.append(dict(name=name, vdb=value, case=result.name, log=str(log), **diagnosis,
                          actual_uvm=parsed, trace=trace, trace_summary=ts, original_oracle=audit,
                          original_summary=summary, oracle=producer["oracle"], software_source=source,
                          exact_elf=str(elf), elf_sha256=a.pins[str(elf)], producer_plan=str(plan_path),
                          original_contract=producer.get("contract"),
                          contract_gap="Original require_contract=false; this diagnosis does not retroactively pass that gate",
                          application_approval=False))
    report = dict(schema="HISTORICAL719_UVM_NO_TRAFFIC_DIAGNOSTIC_V1", status="READONLY_DIAGNOSIS_NOT_ADMISSION",
                  baseline=str(BASE), cases=cases, classifications=dict(Counter(c["classification"] for c in cases)),
                  scanned_logs=scanned, adjacent_log_count=sum(r["adjacent"] for r in scanned),
                  recovered_nonadjacent_vdbs=recovered, missing_case_logs=missing, unexpected_errors=other_errors,
                  design_vdb_not_execution_log=databases[0], compiled_source_bindings=compiled,
                  uvm_source_semantics="scoreboard line504 requires req/resp>0; DUT test line630 requires VID>0 unconditionally. Config/CSR frontend response and illegal rejection do not imply backend allocation.",
                  source_identity_gaps=source_identity_gaps,
                  hold_required=bool(missing or other_errors or source_identity_gaps or any(c["issues"] for c in cases)),
                  official_denominator_verified=False, application_approval=False, simulations_started=False,
                  limitations="Expected NO_TRAFFIC diagnostics remain recorded UVM errors. No generic ignore rule, no change to719; require_contract=false remains an admission policy question. Context-only or mismatching current source is not compiled-image proof; source identity gaps hold source qualification. Exact executed ELF/trace are pinned.",
                  pins=a.pins)
    for path, digest in a.pins.items():
        assert sha(path) == digest, path
    output.mkdir()
    (output / "diagnosis.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")
    lines = ["# 719 NO_TRAFFIC 只读诊断", "", "保留原UVM错误，不修改719、不补做contract准入、不启动仿真。", "",
             "| Case | req/resp | VID | 分类 |", "|---|---:|---:|---|"]
    lines += [f"| {c['name']} | {c['expected_requests']}/{c['expected_requests']} | 0 | {c['classification']} |" for c in cases]
    lines += ["", f"邻近日志 {report['adjacent_log_count']}；追溯非邻近VDB {len(recovered)}；缺失 {len(missing)}；其他实际错误 {len(other_errors)}。",
              f"固定image源码身份未闭环 {len(source_identity_gaps)} 项，保持source资格HOLD；详见JSON期望/实际hash。",
              "26例原audit的require_contract=false未被本诊断改为true；标量/配置/预期非法路径与通用smoke活性门不匹配，不等于已确认RTL故障。", ""]
    (output / "summary.zh.md").write_text("\n".join(lines))
    seal = dict(inputs=a.pins, outputs={str(p): sha(p) for p in (output / "diagnosis.json", output / "summary.zh.md")})
    (output / "seal.json").write_text(json.dumps(seal, indent=2) + "\n")
    print(json.dumps(dict(output=str(output), seal_sha256=sha(output / "seal.json"), cases=len(cases),
                          classifications=report["classifications"], recovered=len(recovered), missing=len(missing),
                          unexpected_errors=len(other_errors), hold_required=report["hold_required"], pins=len(a.pins))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
