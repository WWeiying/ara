"""Read-only, bounded historical execution reconciliation; never admits coverage."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def category(original, passes):
    exact = [p for p in passes if original.get("elf_sha256") is not None
             and p.get("elf_sha256") == original["elf_sha256"]]
    same = [p for p in exact if original.get("image_signature") is not None
            and p.get("image_signature") == original["image_signature"]]
    if any(p["member717"] for p in same):
        return "SAME_IMAGE_SAME_ELF_PASS_ADMITTED"
    if same:
        return "SAME_IMAGE_SAME_ELF_PASS_NOT_ADMITTED"
    if any(p.get("image_signature") and original.get("image_signature")
           and p["image_signature"] != original["image_signature"] for p in exact):
        return "DIFFERENT_IMAGE_SAME_ELF_PASS_ONLY"
    if passes:
        return "OTHER_ELF_OR_UNPROVEN_IDENTITY_PASS_ONLY"
    return "NO_MATCHING_PASS"


class Audit:
    def __init__(self):
        self.pins = {}
        self.images = {}

    def pin(self, path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        # Evidence reads remain inside this task's workspace.
        path.relative_to(ROOT)
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError("Input drift: " + str(path))
        self.pins[str(path)] = actual
        return path

    def load(self, path):
        return json.loads(self.pin(path).read_text())

    def image(self, simv):
        simv = Path(simv)
        if not simv.is_absolute():
            simv = ROOT / simv
        key = str(simv)
        if key not in self.images:
            if not simv.is_file():
                return None
            files = [simv] + sorted(Path(key + ".daidir").glob("*.so"))
            signature = {"simv": sha(self.pin(simv)),
                         "libraries": {p.name: sha(self.pin(p)) for p in files[1:]}}
            digest = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
            self.images[key] = {"signature": digest, "files": len(files), **signature}
        return self.images[key]["signature"]

    def execution(self, record, evidence, members):
        evidence = Path(evidence)
        base = evidence.parent.parent if evidence.parent.name == "outcomes" else evidence.parent
        result = Path(record.get("directory") or base / "results" / record["name"])
        commands = sorted(result.glob("tests/*/work/coverage.command.json"))
        commands += sorted(result.glob("tests/*/work/gap71-command.json"))
        commands += sorted(result.glob("tests/*/command.json"))
        commands += [p for p in (result / "rtl.command.json", result / "command.json") if p.exists()]
        command = None
        command_path = None
        for path in commands:
            data = self.load(path)
            args = data.get("command", [])
            if args and Path(args[0]).name == "simv":
                command, command_path = args, str(path)
                break
        # Frozen coverage wrappers bind their actual image through the producer plan.
        if command is None and commands and (base / "plan.json").exists():
            plan = self.load(base / "plan.json")
            data = self.load(commands[0])
            command = data.get("command", [])
            if command and command[0] == plan.get("wrapper") and plan.get("simv"):
                command = [plan["simv"], *command[1:]]
                command_path = str(commands[0])
                for p, digest in plan.get("image", {}).items():
                    self.pin(p, digest)
            else:
                command = None
        elf = record.get("elf_sha256")
        executed_elf = None
        image = None
        vdb = record.get("vdb")
        if command:
            preload = [s.split("=", 1)[1] for s in command if s.startswith("+PRELOAD=")]
            if len(preload) == 1:
                executed_elf = str(self.pin(preload[0], elf))
                elf = self.pins[executed_elf]
            image = self.image(command[0])
            if "-cm_dir" in command:
                vdb = command[command.index("-cm_dir") + 1]
        return {"name": record["name"], "status": record["status"],
                "elf_sha256": elf, "executed_elf": executed_elf,
                "image_signature": image, "command_evidence": command_path,
                "source": str(evidence), "vdb": vdb,
                "member717": bool(vdb and vdb in members),
                "reason": record.get("reason")}


def run(destination):
    a = Audit()
    a.pin(__file__)
    current = OUT / "cache-port1-offline-admitted-717-20261006-01"
    manifest = a.load(current / "admission-manifest.json")
    for name, digest in manifest["output_pins"].items():
        a.pin(current / name, digest)
    bits = a.load(current / "combined-bits.json")
    members = bits["tests"]
    inputs = a.pin(current / "combined-inputs.txt").read_text().splitlines()
    assert len(members) == len(set(members)) == 717
    design = OUT / "repaired-aligned-build-20260930-01/sim/simv.vdb"
    assert inputs == [str(design), *members]
    for name, digest in bits["design"].items():
        a.pin(design / "snps/coverage/db" / name, digest)
    historical = a.load(OUT / "historical-nonpass-records-20261006-01.json")
    for path, digest in historical["input_sha256"].items():
        a.pin(path, digest)
    prior = a.load(OUT / "historical-nonpass-sixteen-image-membership-reconciliation-706-20261006-01.json")
    for path, digest in prior["input_pins"].items():
        a.pin(path, digest)
    original = []
    passes = []
    target_names = {g["name"] for g in historical["groups"]}
    sources = sorted(OUT.glob("*/all-outcomes.json"))
    sources += sorted((OUT / "closure92-current-20261005-01/outcomes").glob("*.json"))
    for source in sources:
        data = a.load(source)
        records = data if isinstance(data, list) else [data]
        for record in records:
            if record.get("name") not in target_names:
                continue
            if record.get("status") == "PASS":
                for p, digest in record.get("files", {}).items():
                    a.pin(p, digest)
                passes.append(a.execution(record, source, members))
            elif source.parent.name == "outcomes":
                original.append(a.execution(record, source, members))
    repair_source = OUT / "qbs-fault-layout-repair-20261005-01/status.json"
    repair = a.load(repair_source)
    for name, record in repair["cases"].items():
        passes.append(a.execution(dict(record, name=name), repair_source, members))
    prior_by_key = {(g["name"], g["elf_sha256"]): g for g in prior["groups"]}
    groups = []
    for group in historical["groups"]:
        key = group["name"], group["elf_sha256"]
        bound = prior_by_key.get(key)
        records = []
        if bound:
            for r in bound["historical_nonpass"]:
                image = prior["images"][r["image_ref"]]
                assert image["actual_inventory_exact"] and r["preload_equals_expected"]
                records.append({"name": group["name"], "status": r["status"],
                                "elf_sha256": r["executed_elf_sha256"],
                                "image_signature": a.image(r["actual_command"]["command"][0]),
                                "source": r["outcome_record_pointer"], "vdb": r["vdb"],
                                "member717": r["vdb"] in members})
        else:
            records = [a.execution(r, r["evidence"], members) for r in group["records"]]
        groups.append({"name": group["name"], "historical_inventory_elf": group["elf_sha256"],
                       "original": records})
    groups += [{"name": r["name"], "historical_inventory_elf": r["elf_sha256"],
                "original": [r], "extension": "closure92 actual FAIL (not in original 30)"}
               for r in original]
    gap101_path = OUT / "gap101-register-overflow-failure-sealed-20261006-01.json"
    gap101 = a.load(gap101_path)
    # Workspace-only seal verification; external compiler pins are explicitly not read.
    external = []
    for p, digest in gap101["pins"].items():
        if Path(p).is_relative_to(ROOT):
            a.pin(p, digest)
        else:
            external.append(p)
    prep_path = OUT / "gap101-illegal-segment-store-old-image-20261006-01.prepared.json"
    prep = a.load(prep_path)
    command = prep["command"]
    elf_path = a.pin(prep["input_elf"])
    groups.append({"name": prep["case"], "historical_inventory_elf": None,
                   "extension": "GAP101 original architectural FAIL",
                   "original": [{"name": prep["case"], "status": "FAIL",
                                 "elf_sha256": a.pins[str(elf_path)],
                                 "image_signature": a.image(command[0]),
                                 "source": str(gap101_path),
                                 "vdb": command[command.index("-cm_dir") + 1],
                                 "member717": command[command.index("-cm_dir") + 1] in members,
                                 "reason": "7 failed checks; register-overflow architectural failure"}]})
    for group in groups:
        group["passes_same_name"] = [p for p in passes if p["name"] == group["name"]]
        group["category"] = category(group["original"][0], group["passes_same_name"])
        group["run_membership_closed"] = group["category"] == "SAME_IMAGE_SAME_ELF_PASS_ADMITTED"
        group["root_cause_resolved"] = False
        assert not any(r["member717"] for r in group["original"]), "NonPASS VDB admitted"
    gap102_dir = OUT / "gap102-strict-candidate-717-20261006-02"
    gap102 = {p.stem: a.load(p) for p in [gap102_dir / n for n in
              ("failure.json", "observed-data.json", "scalar-comparison.json",
               "vector-comparison.json", "raw-bitmap-delta.json")]}
    assert gap102["observed-data"]["failed_checks"] == 0
    assert gap102["vector-comparison"]["status"] == "PASS"
    assert gap102["scalar-comparison"]["status"] == "TERMINAL_TOHOST_MATCH"
    assert all(v == 0 for v in gap102["raw-bitmap-delta"]["metrics"].values())
    gap101a = a.load(OUT / "gap101a-offline-admitted-716-20261006-01/status.json")
    assert gap101a["original_gap101_fail_excluded"]
    unresolved = [g for g in groups if not g["run_membership_closed"]]
    summary = {"historical_groups": 30, "extended_groups": len(groups),
               "closed_run_and_membership": len(groups) - len(unresolved),
               "not_closed_run_and_membership": len(unresolved),
               "categories": dict(Counter(g["category"] for g in groups))}
    report = {"schema": "historical-nonpass-717-readonly-v1", "status": "READONLY_AUDIT_COMPLETE_NOT_SIGNOFF",
              "baseline_members": 717, "summary": summary, "groups": groups,
              "images": a.images, "gap102": {"classification": "FUNCTIONAL_PASS_ZERO_GAIN_NOT_DUT_FAIL", **gap102},
              "gap101a_not_original_gap101_closure": True,
              "limitations": ["Bounded original 30 + closure92 outcomes + GAP101; not an exhaustive bug census.",
                              "Matching PASS does not establish original timeout root cause resolution.",
                              "Older different-image PASS is comparison evidence, not necessarily a later rerun.",
                              "No fresh oracle replay or inherited 717 re-admission; no simulation or RTL edits.",
                              "Image hashes are rechecked current sealed bytes; execution identity uses saved command/plan records."],
              "external_gap101_compiler_pins_not_read": external,
              "scanned_outcome_sources": [str(p) for p in sources], "input_pins": a.pins}
    # Reject drift again after all reads, before publishing a new evidence directory.
    for p, digest in a.pins.items():
        if sha(p) != digest:
            raise ValueError("Final input drift: " + p)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    labels = {"SAME_IMAGE_SAME_ELF_PASS_NOT_ADMITTED": "同镜像同ELF PASS，未入717",
              "DIFFERENT_IMAGE_SAME_ELF_PASS_ONLY": "仅不同镜像同ELF PASS",
              "OTHER_ELF_OR_UNPROVEN_IDENTITY_PASS_ONLY": "仅其他ELF/身份未证PASS",
              "NO_MATCHING_PASS": "未找到同名PASS"}
    table = ["# 历史nonPASS与717只读核对", "",
             f"原清单30组；扩展后{len(groups)}组；同镜像同ELF PASS且入717共{len(groups)-len(unresolved)}组；仍未完成运行/准入闭环{len(unresolved)}组。",
             "后续PASS不等于原始失败/超时根因已修复。TIMEOUT不直接判RTL bug。", "",
             "| Case | 原始状态 | ELF SHA前12位 | 运行/717状态 |", "|---|---|---|---|"]
    for g in unresolved:
        r = g["original"][0]
        table.append(f"| {g['name']} | {r['status']} | {(r.get('elf_sha256') or '未知')[:12]} | {labels[g['category']]} |")
    table += ["", "GAP101保留原始FAIL（7项失败）；GAP101A是独立案例，不能替代。",
              "GAP102：functional PASS，failed_checks=0，标量/向量比较通过；line/cond/branch/fsm增益均0。collector拒收不是DUT FAIL。",
              "GAP76：标量f14差分MISMATCH、向量PASS，保留未解决差分，不声称已确定RTL根因。",
              "", f"输入封存：audit.json/input_pins，共{len(a.pins)}个workspace文件二次SHA256核验；外部编译器pins未读且不计入已核验数。",
              "不启动仿真、不修改RTL/镜像/既有文档；本报告不执行准入、不提供豁免。"]
    (destination / "summary.zh.md").write_text("\n".join(table) + "\n")
    seal = {"outputs": {p.name: sha(p) for p in sorted(destination.iterdir())},
            "input_pins_count": len(a.pins), "input_pins_sha256": hashlib.sha256(
                json.dumps(a.pins, sort_keys=True).encode()).hexdigest()}
    (destination / "seal.json").write_text(json.dumps(seal, indent=2) + "\n")
    print(json.dumps({"output": str(destination), "summary": summary, "seal": seal}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.resolve().relative_to(OUT)
    run(args.output)
