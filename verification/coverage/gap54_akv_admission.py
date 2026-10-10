"""Sealed, read-only gap54 admission and independent runtime replay."""
from pathlib import Path
import gap54_akv_oracle as oracle

ROOT, NAME, TEST, FORMAT = oracle.ROOT, oracle.NAME, oracle.TEST, oracle.FORMAT
require = oracle.require


def check_case(item, record, record_path, digest):
    expected = dict(record["case"])
    expected["precheck"] = dict(expected["precheck"],record=str(record_path),record_sha256=digest)
    require(item == expected, "exact sealed case differs; do not append sources/evidence")
    require(item["name"] == TEST and item["timeout_s"] == 600 and type(item["timeout_s"]) is int and
            item["runtime_contract"] == oracle.RUNTIME_FORMAT and item["precheck"]["format"] == FORMAT,
            "case identity/budget/schema differs")


def precheck(item, evidence):
    from coverage_evidence import Evidence
    proof = Evidence()
    schema = item["precheck"]
    path = proof.pin(schema["record"],schema["record_sha256"])
    record = proof.read(path)
    check_case(item,record,path,proof.files[str(path)])
    require(record["status"] == "HOST_PASS_ELF_STATIC_ONLY" and record["vcs_launched"] is False and
            record["returncode"] == 0 and record["format"] == FORMAT, "not host/static-only evidence")
    require(set(record["files"]) | {str(path)} == set(item["evidence"]), "exact artifact set differs")
    proof.hashes(record["files"])
    proof.hashes(item["source_hashes"])
    require(sorted(item["source_hashes"]) == item["sources"], "complete source set differs")
    root = path.parent
    for filename in ("commands.json","source-audit.json","native-targets.json","tool-hashes.json",
                     "negative-tests.json", "cost-analysis.json", "host.log",NAME+".elf",NAME+".elf-fit.json"):
        require(str(root / filename) in record["files"], "required artifact missing: "+filename)
    proof.hashes(proof.read(root / "tool-hashes.json"))
    require(item["binary"] == str(root / (NAME+".elf")) and
            item["binary_sha256"] == proof.files[item["binary"]], "ELF differs")
    host = oracle.validate_log((root / "host.log").read_text(),True)
    elf = oracle.elf_audit(Path(item["binary"]).read_bytes())
    require(host == record["host"] and elf == record["elf"], "saved host/ELF proof differs")
    commands = proof.read(root / "commands.json")
    require(commands and all(c["returncode"] == 0 and c["timeout_s"] <= 120 for c in commands),
            "failed/unbounded software preflight command")
    require(sum(c["command"] == [str(root / "host")] for c in commands) == 1, "missing host execution")
    negative = proof.read(root / "negative-tests.json")
    require(negative["status"] == "PASS" and negative["tests_run"] >= 10 and
            negative["host_mutations_rejected"] == 20 and negative["exhaustive_byte_mutations_rejected"] == 2944 and
            negative["cancelling_xor_rejected"] == 1, "negative oracle tests missing")
    cost = proof.read(root / "cost-analysis.json")
    require(cost["status"] == "STATIC_COST_REDUCED_NOT_RUNTIME_PASS" and cost["new_cost"]["phase_instructions_upper"] < 12000,
            "bounded static scalar cost evidence missing")
    targets = oracle.native_targets(proof)
    require(targets == proof.read(root / "native-targets.json"), "native static evidence changed")
    require(item["source_audit"] == str(root / "source-audit.json"), "audit path differs")
    require(all(k in record["files"] for k in proof.read(root / "source-audit.json")["input_hashes"]),
            "unbound source audit inputs")
    proof.hashes(dict(proof.files))
    evidence.hashes(proof.files)
    return dict(name=TEST,status="PASS",scope="Host ABI/reference and ELF/static only; DUT pending",
        precheck=dict(schema),elf_sha256=item["binary_sha256"],host_checks=oracle.HOST_CHECKS,
        dut_checks=oracle.DUT_CHECKS,operations=12,traps=3,native_candidates=9,timeout_s=600,
        case_sha256=oracle.canonical(item))


def runtime_proof(output, plan, row):
    import run_checked_extension as checked
    full = checked.full
    require(plan.get("checked_extension") == checked.VERSION, "checked plan required")
    cases = [c for c in plan["cases"] if c["name"] == NAME and c["source_name"] == TEST]
    require(len(cases) == 1, "missing/ambiguous runtime case")
    case = cases[0]
    require(row.get("name") == NAME and row.get("kind") == case["kind"] == "directed" and
            row.get("status") == "PASS" and row.get("returncode") == 0 and row.get("passed_only") is True and
            row.get("vdb_valid") is True and row.get("reused") is False, "independent generic PASS required")
    require(row["contract"] == case["contract"] == full.contract(case), "runtime contract differs")
    proof = checked.evidence.Evidence()
    selection = Path(plan["source_selection"]["selection"])
    proof.pin(selection,plan["files"][str(selection)])
    items = [i for i in proof.read(selection)["cases"] if i["name"] == TEST]
    require(len(items) == 1, "selected case differs")
    admitted = precheck(items[0],proof)
    require(all(plan["files"].get(p) == h for p,h in proof.files.items()), "precheck inputs not frozen")
    root = Path(items[0]["precheck"]["record"]).parent
    targets = proof.read(root / "native-targets.json")
    require(plan["design_vdb"] == targets["design_vdb"], "compiled design differs")
    require(row["elf_sha256"] == case["elf_sha256"] == admitted["elf_sha256"], "runtime ELF differs")
    frozen = proof.pin(case["frozen_elf"],admitted["elf_sha256"])
    elf = oracle.elf_audit(frozen.read_bytes())
    target = Path(output).resolve(strict=True) / "results" / NAME
    def bound(path):
        require(str(path) in row["files"], "unbound runtime artifact: "+str(path))
        return proof.pin(path,row["files"][str(path)])
    summaries = proof.read(bound(target / "summary.json"))
    require(len(summaries) == 1 and summaries[0]["name"] == TEST and
            full.batch.classify(summaries[0],row["returncode"]) == "PASS", "runtime summary differs")
    artifact = Path(summaries[0]["artifact_dir"]).resolve(strict=True)
    require(artifact == target / "tests" / ("app_"+NAME), "foreign runtime artifact")
    work = artifact / "work"
    require(Path(row["vdb"]).resolve() == work / "code.vdb", "foreign VDB")
    metadata = proof.read(bound(artifact / "inputs.json"))
    require(metadata["binary"]["sha256"] == admitted["elf_sha256"] and
            metadata["simv"]["image_sha256"] == plan["wrapper_image"], "runtime ELF/image metadata differs")
    proof.pin(bound(artifact / "input.elf"),admitted["elf_sha256"])
    full.batch.audit_ok(proof.read(bound(target / "independent_audit.json")),case,artifact)
    launch = proof.read(bound(work / "gap54-command.json"))
    original = proof.read(bound(artifact / "command.json"))
    actual = proof.read(bound(work / "coverage.command.json"))
    from run_gap54_akv_checked_extension import perf_command
    require(launch == dict(command=perf_command(original["command"]),cwd=str(work),timeout_s=600),
            "local PERF launch record differs")
    expected_actual = [plan["simv"],*launch["command"][1:],"-cm","line+cond+fsm+tgl+branch",
                       "-cm_dir",str(work / "code.vdb"),"-cm_name",NAME]
    require(actual == dict(command=expected_actual,cwd=str(work)) and
            original["command"][0] == plan["wrapper"], "actual simulator command differs")
    trace = bound(artifact / "commit_trace.csv")
    summary = proof.read(bound(artifact / "trace_summary.json"))
    require(summary.get("status") == "VALID" and summary.get("retire_count",0) > 0, "invalid directed trace")
    log = bound(work / "run.vcs.log").read_text(errors="strict")
    uart = oracle.validate_log(log,False,elf)
    cycles = oracle.trace_audit(trace,elf,log)
    require(uart["busy_cycles_sum"] <= cycles["last_cycle"], "command cycles exceed run")
    raw = oracle.native_runtime(row["vdb"],targets,proof)
    require(all(row["vdb_files"].get(p) == h for p,h in proof.files.items()
                if Path(p).is_relative_to(Path(row["vdb"]))), "native data not bound to PASS VDB")
    proof.hashes(dict(proof.files))
    return dict(status="PASS",schema=oracle.RUNTIME_FORMAT,name=NAME,uart=uart,cycles=cycles,
        native=raw,files=proof.files,elf_sha256=admitted["elf_sha256"],
        scope="Independent UART/ELF/retire/CSR/protocol/PERF evidence; raw gains not DVE percentages")
