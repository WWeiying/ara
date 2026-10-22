"""Add raw-failure/tool-failure detail without changing the sealed base audit."""
import json

from audit_historical_nonpass_717 import Audit, OUT, sha


def main():
    directory = OUT / "historical-nonpass-membership-reconciliation-717-20261006-01"
    a = Audit()
    a.pin(__file__)
    a.pin(OUT.parent / "coverage/test_audit_historical_nonpass_717.py")
    seal = a.load(directory / "seal.json")
    for name, digest in seal["outputs"].items():
        a.pin(directory / name, digest)
    report = a.load(directory / "audit.json")
    details = []
    for name in ("vgap35_carry_ta", "vgap35_slide_bound"):
        source = OUT / "gap35-vector-checked-preflight-20261004-03"
        rows = a.load(source / "all-outcomes.json")
        row = next(r for r in rows if r["name"] == name)
        for p, digest in row.get("files", {}).items():
            a.pin(p, digest)
        logs = list((source / "results" / name).glob("tests/*/console.log"))
        assert len(logs) == 1
        log = a.pin(logs[0]).read_text()
        assert "Core Test *** FAILED ***" in log and "CVXIF/DUT_FAIL" in log
        details.append({"case": name, "classification": "DUT_SELFCHECK_FAIL_NOT_TOOL_FAILURE",
                        "source": str(logs[0]),
                        "failure_lines": [s for s in log.splitlines() if "FAILED" in s or "DUT_FAIL" in s]})
    fault_source = OUT / "closure92-current-20261005-01/outcomes/gap71_qbs_fault.json"
    fault = a.load(fault_source)
    for p, digest in fault["files"].items():
        a.pin(p, digest)
    fault_logs = [p for p in fault["files"] if p.endswith("/console.log")]
    text = a.pin(fault_logs[0]).read_text()
    assert "GAP71_CHECK_FAILED index=60" in text and "checks=144 errors=1" in text
    details.append({"case": "gap71_qbs_fault", "elf_sha256": fault["elf_sha256"],
                    "classification": "DUT_SELFCHECK_FAIL_NOT_TOOL_FAILURE",
                    "source": fault_logs[0], "failed_check_index": 60,
                    "checks": 144, "errors": 1,
                    "different_image_pass_not_old_image_closure": True})
    red16 = OUT / "gap76-old-image-20261006-01/results/vgap76_red16"
    scalar = a.load(red16 / "scalar-comparison.json")
    vector = a.load(red16 / "vector-comparison.json")
    assert scalar["status"] == "MISMATCH" and vector["status"] == "PASS"
    assert scalar["mismatch"]["reason"] == "fpr_value"
    details.append({"case": "vgap76_red16", "classification": "SCALAR_DIFFERENTIAL_MISMATCH",
                    "not_a_tool_start_failure": True, "rtl_root_cause_proven": False,
                    "scalar": scalar["mismatch"], "vector_status": vector["status"]})
    tool_cases = []
    for name in ("gap101a-admission-precheck-failure-20261006-01.json",
                 "gap102b-preflight-preoutput-failure-20261006-01.json"):
        data = a.load(OUT / name)
        tool_cases.append({"source": str(OUT / name), "status": data["status"],
                           "reason": data["reason"], "classification": "TOOL_PRECHECK_NOT_DUT_FAIL"})
    tool_cases.append({"source": str(OUT / "gap102-strict-candidate-717-20261006-02/failure.json"),
                       "classification": "FUNCTIONAL_PASS_ZERO_GAIN_COLLECTOR_REJECTION_NOT_DUT_FAIL"})
    result = {"schema": "historical-nonpass-717-details-v1", "base_audit_sha256": seal["outputs"]["audit.json"],
              "summary": report["summary"], "raw_failure_details": details,
              "excluded_tool_failures": tool_cases, "additional_input_pins": a.pins,
              "base_input_pins_count": len(report["input_pins"]),
              "simulations_started": False, "rtl_changed": False,
              "official_denominator_verified": False, "application_approval": False,
              "scope": "Historical fixed-image diagnostic membership audit, not new RTL signoff or waiver approval"}
    lines = ["# 历史未闭环案例（717固定旧镜像诊断）", "",
             "原30组：20组同镜像同ELF PASS且其VDB在717中；10组尚未闭环。另补closure92 FAIL与GAP101 FAIL，总计12组（11个case名、12个ELF版本）。",
             "这里的闭环仅指运行PASS+准入成员，不是原始根因修复；所有原nonPASS记录保留。", "",
             "| Case / 原ELF前12位 | 原始结果 | 后续证据与717 |", "|---|---|---|"]
    for group in report["groups"]:
        if group["run_membership_closed"]:
            continue
        r = group["original"][0]
        same_elf = [p for p in group["passes_same_name"] if p["elf_sha256"] == r["elf_sha256"]]
        if same_elf:
            note = "同ELF仅不同镜像PASS；未入717，不关闭旧镜像FAIL"
        elif group["passes_same_name"]:
            old_pass = [p for p in group["passes_same_name"] if p["image_signature"] == r["image_signature"]]
            note = "同镜像PASS但ELF已换且入717；原ELF未闭环" if old_pass else "仅换ELF+换镜像PASS；未入717"
        else:
            note = "未找到同名PASS；原VDB不在717"
        lines.append(f"| {group['name']} / {r['elf_sha256'][:12]} | {r['status']} | {note} |")
    closed = [g for g in report["groups"] if g["run_membership_closed"]]
    lines += ["", "## 已有同镜像同ELF PASS并在717中的20组", "",
              ", ".join(g["name"] for g in closed), "",
              "## 特别区分", "",
              "GAP101原始FAIL：7项检查失败；GAP101A独立NF×EMUL案例PASS不能替代原案例。",
              "GAP102：functional PASS，failed_checks=0，标量TERMINAL_TOHOST_MATCH、向量PASS；line/cond/branch/fsm增益均0。collector拒收不是DUTFAIL。",
              "GAP76 red16：标量f14期望0xffffffffbf800000、实得0xffffffff00000000；向量PASS。保留差分失败，不确定RTL根因。",
              "工具precheck failure单列于details.json，未加入DUT FAIL计数。TIMEOUT不直接计为RTL bug。", "",
              f"封存输入：base audit的{len(report['input_pins'])}个workspace文件已二次核验；本附件另封存失败日志、差分及工具failure证据（见additional_input_pins）。",
              "base seal与附件details-seal独立，未修改原封存输出；外部编译器pins不计作本审计已验证。",
              "official_denominator_verified=False；application_approval=False。不启动仿真，不改RTL/镜像，不宣称新RTL signoff或最终waive批准。"]
    for path, digest in a.pins.items():
        assert sha(path) == digest, "Input drift: " + path
    for name, content in (("details.json", json.dumps(result, indent=2, ensure_ascii=False) + "\n"),
                          ("details.zh.md", "\n".join(lines) + "\n")):
        with (directory / name).open("x") as stream:
            stream.write(content)
    detail_seal = {"base_seal_sha256": sha(directory / "seal.json"),
                   "outputs": {n: sha(directory / n) for n in ("details.json", "details.zh.md")},
                   "additional_input_pins_count": len(a.pins),
                   "total_unique_pins": len(set(report["input_pins"]) | set(a.pins))}
    with (directory / "details-seal.json").open("x") as stream:
        stream.write(json.dumps(detail_seal, indent=2) + "\n")
    print(json.dumps(detail_seal, indent=2))


if __name__ == "__main__":
    main()
