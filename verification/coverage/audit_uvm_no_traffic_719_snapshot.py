"""Add frozen dispatcher proof without reinterpreting original719 admission."""
import argparse
import json
from pathlib import Path

from audit_historical_nonpass_717 import Audit, OUT, ROOT, sha

ORIGINAL = OUT / "uvm-no-traffic-diagnostic-719-20261006-01"
ORIGINAL_SEAL = "3f284421baa0db043c52a5f53ed918525de192b0732b55c72a65f27abc36e3a3"
HARDWARE_PATH = ROOT / "hardware/src/ara_dispatcher.sv"
SNAPSHOT = OUT / "old-image-source-evidence-20261006-01/ara_dispatcher.sv"
SNAPSHOT_SHA = "9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43"
BUILD = OUT / "repaired-aligned-build-20260930-01/build-source-pins.json"
BUILD_SHA = "6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b"


def require(value, message):
    if not value:
        raise ValueError(message)


def blocks(text):
    specs = {
        "backend_default_disabled": ("    ara_req_valid = 1'b0;", "    ara_req_valid = 1'b0;"),
        "configuration_frontend": ("              OPCFG: begin: opcfg", "              OPIVV: begin: opivv"),
        "vector_csr_frontend": ("          riscv::OpcodeSystem: begin", "          QbsOpcodeCustom2: begin : custom2"),
        "vstart_rejection": ("      // RVV requires these non-restartable operations", "      // Mask compares produce one destination register."),
        "illegal_rejection": ("      // Raise an illegal instruction exception", "      // Check if we need to reshuffle"),
    }
    result = {}
    for name, (start, end) in specs.items():
        begin = text.index(start)
        finish = text.index(end, begin) if start != end else begin + len(start)
        section = text[begin:finish]
        result[name] = dict(line=text.count("\n", 0, begin) + 1, text=section)
    for name in ("configuration_frontend", "vector_csr_frontend"):
        section = result[name]["text"]
        require("ara_req_valid" not in section, "Unexpected backend validity write in " + name)
        require("acc_resp_o.resp_valid" in section or name == "configuration_frontend", "Missing response")
    require("acc_resp_o.result = csr_vl_d;" in result["configuration_frontend"]["text"], "Missing configuration result")
    require("requires_zero_vstart(ara_req.op)" in result["vstart_rejection"]["text"], "Missing vstart legality gate")
    rejected = " ".join(result["illegal_rejection"]["text"].split())
    for token in ("ara_req_valid = 1'b0;", "acc_resp_o.resp_valid = 1'b1;",
                  "acc_resp_o.exception.valid = 1'b1;", "acc_resp_o.exception.cause = riscv::ILLEGAL_INSTR;"):
        require(token in rejected, "Missing rejection guarantee " + token)
    return result


def bind_snapshot(a):
    a.pin(BUILD, BUILD_SHA)
    build = json.loads(BUILD.read_text())
    require(build[str(HARDWARE_PATH)] == SNAPSHOT_SHA, "Hardware build mapping differs")
    a.pin(SNAPSHOT, SNAPSHOT_SHA)
    return dict(snapshot=str(SNAPSHOT), snapshot_sha256=SNAPSHOT_SHA,
                compiled_hardware_source_path=str(HARDWARE_PATH), build_manifest=str(BUILD),
                build_manifest_sha256=BUILD_SHA, exact_compiled_source_match=True,
                current_hardware_source_read=False, evidence=blocks(SNAPSHOT.read_text()))


def original_inputs(a, seal):
    for path, digest in seal["inputs"].items():
        # Preserve the original current-RTL pin as historical context only.
        if path != str(HARDWARE_PATH):
            a.pin(path, digest)
    for path, digest in seal["outputs"].items():
        a.pin(path, digest)


def policy_summary(cases):
    for case in cases:
        policy = case["original_oracle"]["policy"]
        require(all(policy[key] is False for key in ("require_contract", "require_full_match", "require_vector")),
                "Original oracle policy changed")
        require(not case["application_approval"], "Unexpected application approval")
    return dict(cases=len(cases), require_contract_false=len(cases), require_full_match_false=len(cases),
                require_vector_false=len(cases), full_isa_differential_pass_claimed=False,
                original_policy_promoted=False, formal_membership_modified=False)


def run(output):
    require(output.parent == OUT and not output.exists(), "Fresh independent successor required")
    a = Audit()
    a.pin(__file__)
    a.pin(Path(__file__).with_name("test_audit_uvm_no_traffic_719_snapshot.py"))
    a.pin(ORIGINAL / "seal.json", ORIGINAL_SEAL)
    seal = json.loads((ORIGINAL / "seal.json").read_text())
    original_inputs(a, seal)
    old = json.loads((ORIGINAL / "diagnosis.json").read_text())
    require(old["hold_required"] and len(old["source_identity_gaps"]) == 1 and
            old["source_identity_gaps"][0]["path"] == str(HARDWARE_PATH), "Exact prior HOLD required")
    binding = bind_snapshot(a)
    scope = policy_summary(old["cases"])
    record = dict(status="FROZEN_DISPATCHER_SOURCE_BOUND_DIAGNOSTIC_NOT_ADMISSION", original=str(ORIGINAL),
                  original_seal_sha256=ORIGINAL_SEAL, original_hold_preserved=True,
                  snapshot_binding=binding, successor_dispatcher_identity_gap_resolved=True,
                  original_classifications=old["classifications"], cases=old["cases"], oracle_scope=scope,
                  remaining_holds=["Original require_contract=false is not converted to contract PASS.",
                                   "Software selfcheck and trace/protocol evidence are not full ISA differential verification.",
                                   "Context-only software sources remain labeled; this successor resolves dispatcher snapshot identity only."],
                  unexpected_errors=old["unexpected_errors"], missing_case_logs=old["missing_case_logs"],
                  formal_membership_modified=False, application_approval=False, simulations_started=False, pins=a.pins)
    for path, digest in a.pins.items():
        require(sha(path) == digest, "Input drift " + path)
    output.mkdir()
    report = output / "snapshot-diagnosis.json"
    report.write_text(json.dumps(record, indent=2) + "\n")
    summary = output / "summary.zh.md"
    summary.write_text("# 719 冻结源码只读补证\n\n"
                       "冻结dispatcher snapshot与旧build-source-pins硬件源路径的SHA精确一致；未读取当前RTL。\n\n"
                       "配置/向量CSR在前端响应；非法指令先撤销后端请求再返回异常。原17 scalar、9 frontend-only分类保留。\n\n"
                       "原报告HOLD和seal不变。仅successor闭环dispatcher源码身份；26例require_contract/full_match/vector=false不提升，软件自检PASS不是全ISA differential PASS。正式集合与准入批准不变。\n")
    evidence = dict(inputs=a.pins, outputs={str(p): sha(p) for p in (report, summary)})
    (output / "seal.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(dict(output=str(output), seal_sha256=sha(output / "seal.json"),
                          report_sha256=sha(report), pins=len(a.pins), dispatcher_identity_bound=True,
                          original_hold_preserved=True, application_approval=False)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
