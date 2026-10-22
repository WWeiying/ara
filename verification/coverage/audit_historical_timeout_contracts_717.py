"""Offline tail/ELF/software-contract analysis of three historical TIMEOUTs."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import struct

from audit_historical_nonpass_717 import Audit, OUT, ROOT, sha


def code_at(blob, pc, size):
    if len(blob) < 64 or blob[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected ELF64 LE")
    h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    if h[1] != 243 or h[10] != 64 or h[5] + h[11] * 64 > len(blob):
        raise ValueError("Unsupported/truncated RISC-V ELF sections")
    matches = []
    for i in range(h[11]):
        s = struct.unpack_from("<IIQQQQIIQQ", blob, h[5] + i * 64)
        if s[1] != 8 and s[2] & 4 and s[3] <= pc and pc + size <= s[3] + s[5]:
            offset = s[4] + pc - s[3]
            if offset + size > len(blob):
                raise ValueError("Truncated ELF text")
            matches.append(blob[offset:offset + size])
    if len(matches) != 1:
        raise ValueError("PC not uniquely bound to ELF executable section")
    return matches[0]


def summarize(rows):
    retired = [r for r in rows if r["event"] == "retire"]
    assert [int(r["order"]) for r in retired] == list(range(len(retired)))
    assert all(int(x["cycle"]) <= int(y["cycle"]) for x, y in zip(rows, rows[1:]))
    regs = {}
    for r in retired:
        if int(r["rd"]):
            regs[r["rd"]] = r["rd_wdata"]
    custom = [{k: r[k] for k in ("cycle", "order", "pc", "insn", "trap")}
              for r in retired if int(r["insn"], 16) & 127 == 91]
    return {"rows": len(rows), "retired": len(retired), "last_retire": retired[-1],
            "last_12_retire": retired[-12:], "last_register_writes": regs,
            "retired_custom": custom, "events": dict(Counter(r["event"] for r in rows)),
            "source_loop_retired": sum(0x8000097e <= int(r["pc"], 16) <= 0x80000a04 for r in retired)}


def main(destination):
    destination.resolve().relative_to(OUT)
    assert not destination.exists(), "Fresh output required"
    a = Audit()
    a.pin(__file__)
    a.pin(ROOT / "verification/coverage/audit_historical_nonpass_717.py")
    a.pin(ROOT / "verification/coverage/test_audit_historical_timeout_contracts_717.py")
    configs = [
        ("vgap35_carry_illegal", "gap35-vector-checked-preflight-20261004-03", "rvv", 600,
         "gap35-rvv-ready-20261004-02/vgap35_carry_illegal.dis", "rv64uv-ara-vgap35_carry_illegal"),
        ("akv_gap35_descriptor", "gap35-vector-checked-preflight-20261004-03", "app", 300,
         "gap35-accel-build-20261004-02/akv_gap35_descriptor.disassembly.log", "akv_gap35_descriptor.elf"),
        ("akv_gap46_skew_context", "gap48-current-20261004-01", "app", 600,
         "gap46-akv-preflight-20261004-03/akv_gap46_skew_context.disassembly.log", "akv_gap46_skew_context.elf")]
    cases = []
    for name, producer, kind, budget, dis_path, built_name in configs:
        base = OUT / producer
        plan = a.load(base / "plan.json")
        case = next(c for c in plan["cases"] if c["name"] == name)
        assert case["timeout_s"] == budget
        skipped = []
        for path, digest in case["source_files"].items():
            if Path(path).is_relative_to(ROOT):
                a.pin(path, digest)
            else:
                skipped.append(path)
        test = base / "results" / name / "tests" / (kind + "_" + name)
        elf = a.pin(test / "input.elf", case["elf_sha256"])
        dis = a.pin(OUT / dis_path)
        built = a.pin(dis.parent / built_name, case["elf_sha256"])
        assert sha(elf) == sha(built)
        trace = a.pin(test / "commit_trace.csv")
        with trace.open() as stream:
            rows = list(csv.DictReader(stream))
        stats = summarize(rows)
        blob = elf.read_bytes()
        for row in stats["last_12_retire"]:
            word = int(row["insn"], 16)
            size = 4 if word & 3 == 3 else 2
            assert int.from_bytes(code_at(blob, int(row["pc"], 16), size), "little") == word
        a.load(test / "inputs.json")
        a.load(test / "command.json")
        actual = a.load(test / "work/coverage.command.json")
        log = a.pin(test / "work/run.vcs.log").read_text()
        core = a.pin(test / "work/trace_hart_0.log").read_text()
        summary = a.load(base / "results" / name / "summary.json")
        assert summary[0]["status"] == "TIMEOUT"
        result = {"name": name, "original_status": "TIMEOUT", "timeout_s": budget,
                  "elf_sha256": case["elf_sha256"], "trace": str(trace), "disassembly": str(dis),
                  "tail_instructions_exact_elf_match": True, "actual_command": actual,
                  "stats": stats, "external_source_pins_not_read": skipped,
                  "remaining_functional_pass_proven": False, "root_cause_fixed": False}
        if name == "vgap35_carry_illegal":
            assert stats["retired"] == 863 and int(stats["last_retire"]["pc"], 16) == 0x800001ee
            assert int.from_bytes(code_at(blob, 0x800001f2, 4), "little") == 0x305599f3
            assert "Cause: Illegal Instruction" in core and "001fffffffffff00" in core
            assert "1446 U 00000000800001ee" in core and "tval: 00000000305599f3" in core
            result.update(classification="SOFTWARE_PRIVILEGE_CONTRACT_MISMATCH_NOT_SLOW_EXECUTION",
                observed="U-mode main reaches privileged csrrw mtvec at 0x800001f2; cause2/tval305599f3 then repeated instruction access faults at 0x001fffffffffff00.",
                software_contract="4 reserved carry opcodes, 40 trap/CSR checks +512 unchanged vector bytes +3 common checks =555. None of the four target opcodes was reached.",
                budget_only_reliable_solution=False,
                environment_only_same_elf_solution_proven=False,
                falsifier="A saved trace showing main in M mode, a different actual ELF, or the four target opcodes reached would refute this binding; current exact ELF/U trace does not.",
                next_action="Do not extend timeout. Existing gap36 M-mode init-hook successor is different ELF; keep original timeout unresolved. No software/RTL edit or rerun here.")
        elif name == "akv_gap35_descriptor":
            assert stats["retired"] == 72802 and int(stats["last_retire"]["pc"], 16) == 0x8000026a
            assert int(stats["last_register_writes"]["19"], 16) == 5
            exceptions = [line for line in core.splitlines() if line.startswith("Exception")]
            assert len(exceptions) == 5 and all("Illegal Instruction" in s for s in exceptions)
            assert "FAILED" not in log and "FAIL " not in log
            result.update(classification="BUDGET_INSUFFICIENT_STRONG_PROGRESS_EVIDENCE_NOT_FULL_PASS",
                observed="5 expected illegal-instruction traps; s3(test)=5; sixth setup iteration in pattern stream1,row1, dim119->120, limit128. No custom command outstanding inferred from software location, not from absent retire-custom alone.",
                software_contract="23 invalid descriptor/tile mutations, 1 valid V2 fill, row2 load and release; 6751 DUT checks (23*260+3*257). Full256-halfword comparisons and exact trap PC/cause/tval remain required.",
                budget_only_reliable_solution=False,
                budget_hypothesis_supported=True,
                planning_estimate_only_seconds=1440,
                estimate_basis="300s observed for >=5 completed iterations; naive24/5 scaling, not bound or execution guarantee; final valid commands unmeasured.",
                falsifier="Further static trace shows fixed-PC polling, missing expected trap or pending command rather than monotonically increasing setup/test index; later valid fill/load/release can independently fail.",
                next_action="Environment/concurrency and a bounded same-ELF budget review are plausible; do not claim reliable completion. Existing six gap36 shards change ELF and do not close this original.")
        else:
            contract = a.load(OUT / "gap46-akv-preflight-20261004-03/source-audit.json")
            assert contract["dut_checks"] == 3237 and contract["host_checks"] == 3216
            assert stats["retired"] == 223178 and int(stats["last_retire"]["pc"], 16) == 0x80000994
            assert len(stats["retired_custom"]) == 4
            perf = [{k: int(v) for k, v in (s.split("=") for s in line.split()[1:])}
                    for line in log.splitlines() if line.startswith("[AKV_PERF] ")]
            assert len(perf) == 4 and [r["busy_cycles"] for r in perf] == [81, 13, 13, 13]
            assert all(r["success"] == 1 and r["fault"] == 0 for r in perf)
            assert "AKV46_PHASE phase=3" in log and "checks=807 errors=0" in log
            result.update(classification="SCALAR_ORACLE_COST_DOMINATES_NOT_OBSERVED_AKV_STALL",
                observed="4 custom instructions completed; FULL81 busy cycles, 3 ROWs13 each. Phases1..3 complete807 checks/errors0; phase4 CSR snapshot present, comparison still running at source_byte loop.",
                software_contract="12 phases: FULL V1,3 ROWs,3 illegal lifecycle/row cases,FULL V2,3 ROWs,RELEASE. Legal phases269 checks, illegal272; total3237 DUT checks,3 traps,fflags21/vstart0, full VRF/source/descriptor/guard comparisons.",
                actual_perf=perf,
                source_loop_fraction=stats["source_loop_retired"] / stats["retired"],
                budget_only_reliable_solution=False,
                budget_hypothesis_supported=True,
                planning_estimate_only_seconds=2400,
                estimate_basis="600s observed while phase4 comparison unfinished; conservative12/3 scaling of completed phases, not an upper bound. Recovery/V2/RELEASE stages unmeasured.",
                falsifier="A custom request without terminal response, growing busy_cycles, missing retire progress or bad later trap/data checks would refute budget-only/full-pass inference.",
                next_action="Review host contention/trace I/O and same-ELF budget only under later approval; gap54 scalar-oracle optimization changes ELF, preserves intended checks but is not original-case closure.")
        cases.append(result)
    report = {"schema": "historical-timeout-contracts-717-v1", "cases": cases, "input_pins": a.pins,
              "status": "STATIC_OFFLINE_ANALYSIS_NOT_FIXED_NOT_ADMITTED", "simulations_started": False,
              "rtl_changed": False, "compiler_or_image_changes": False, "application_approval": False,
              "replay_cli": "python3 verification/coverage/audit_historical_timeout_contracts_717.py --output verification/out/historical-timeout-contracts-717-parent-replay-20261006-01"}
    for path, digest in a.pins.items():
        assert sha(path) == digest, "Final input drift: " + path
    destination.mkdir(parents=True)
    (destination / "analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    lines = ["# 三例历史TIMEOUT静态诊断", "",
             "| Case | 末trace/软件位置 | 判断 |", "|---|---|---|",
             "| vgap35_carry_illegal | 863退休；U态0x800001f2写mtvec非法；随后无效trap地址反复取指fault | 软件特权契约不匹配；加预算无效，同ELF环境修复未证明 |",
             "| akv_gap35_descriptor | 72802退休/cycle87923；前5次预期illegal trap；test=5，第6轮setup数据生成 | 强支持预算不足；24轮粗估1440s，仅规划估算，后续合法命令未验证 |",
             "| akv_gap46_skew_context | 223178退休/cycle251123；4命令完成；busy81/13/13/13；phase4源字节比较 | 标量校验成本主导；12阶段粗估2400s，非上界/非PASS保证 |", "",
             "三例均不能据静态分析认定已修复/准入。carry没有达到目标非法carry指令。两AKV末trace持续前进，但未完成部分仍可能暴露功能问题。",
             "6751项descriptor DUT检查、3237项skew DUT检查及所有trap/guard约束不可弱化。",
             "已有gap36/gap54软件successor是不同ELF，不关闭原case。未改RTL/软件/镜像，不启动仿真。",
             f"输入封存：analysis.json/input_pins，{len(a.pins)}个workspace文件二次核验；外部header/compiler pins未读另列。"]
    (destination / "summary.zh.md").write_text("\n".join(lines) + "\n")
    seal = {"outputs": {p.name: sha(p) for p in sorted(destination.iterdir())},
            "input_pins_count": len(a.pins)}
    (destination / "seal.json").write_text(json.dumps(seal, indent=2) + "\n")
    print(json.dumps({"output": str(destination), "seal": seal}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    main(parser.parse_args().output)
