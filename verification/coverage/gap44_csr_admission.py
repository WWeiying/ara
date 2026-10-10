"""Gap44-only evidence adapter; no subprocess, scheduler or hooks on import."""
from pathlib import Path
import re

import gap44_csr_oracle as oracle

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
NAME, TEST, FORMAT = oracle.NAME, oracle.TEST, oracle.FORMAT
BUILD = ROOT / "verification/out/gap44-csr-preflight-20261004-01"
RECORD = BUILD / "evidence.json"
ELF = BUILD / (NAME + ".elf")
SPIKE_ELF = BUILD / (NAME + ".spike")
LOG = BUILD / (NAME + ".spike.log")
AUDIT = BUILD / "source-audit.json"
BUILDER = ROOT / "verification/tests/build_gap44_csr.py"
OWN_SOURCES = (SCRIPT, ROOT / "verification/coverage/run_gap44_csr_checked_extension.py",
               ROOT / "verification/tests/prepare_gap44_csr_admission.py",
               ROOT / "verification/tests/test_gap44_csr_negative.py",
               ROOT / "verification/coverage/gap44_csr_admission.md")
# Original successful first full preflight, never a caller-supplied calibration.
RECORD_SHA256 = "3f2b2044904e160afc414697e18ea4f6b915b7644a5519fa758673e892c1345a"
require = oracle.require


def frozen_inputs(proof):
    require(len(RECORD_SHA256) == 64, "original preflight has not been sealed")
    proof.pin(RECORD, RECORD_SHA256)
    record = proof.read(RECORD)
    require(record.get("status") == "SPIKE_PASS_ONLY" and record.get("format") == FORMAT and
            record.get("name") == TEST and record.get("returncode") == 0 and
            record.get("vcs_launched") is False, "original identity/status")
    files = record["files"]
    required = {str(BUILD / n) for n in ("commands.json", "source-hashes.json", "tool-hashes.json",
                "source-audit.json", "hpm-capability.spike", "hpm-capability.spike.log",
                NAME + ".elf", NAME + ".spike", NAME + ".spike.log")}
    require(required <= set(files), "required compiled evidence omitted")
    require(all(Path(p).parent == BUILD for p in files), "foreign original build artifact")
    proof.hashes(files)
    sources = proof.read(BUILD / "source-hashes.json")
    proof.hashes(sources)
    proof.hashes(proof.read(BUILD / "tool-hashes.json"))
    require(str(BUILDER) in sources and str(Path(oracle.__file__)) in sources and
            str(ROOT / "apps/riscv-tests/isa/rv64uv/csr_gap35_body.h") in sources,
            "required checker/harness source omitted")
    proof.pin(ELF, record["elf_sha256"])
    proof.pin(SPIKE_ELF, record["spike_elf_sha256"])
    require(record["binary"] == str(ELF) and record["spike_elf"] == str(SPIKE_ELF) and
            record["log"] == str(LOG), "original ELF/log path differs")
    stub = oracle.stub_address(SPIKE_ELF.read_bytes())
    require(stub == record["stub"] and oracle.stub_address(ELF.read_bytes()) == record["dut_stub"], "ELF symbol differs")
    command = [str(ROOT / "install/riscv-isa-sim/bin/spike"), "--isa=rv64gcv_zfh",
               "--pmpregions=0", "--varch=vlen:1024,elen:64", str(SPIKE_ELF)]
    commands = proof.read(BUILD / "commands.json")
    rows = [r for r in commands if r["log"] == str(LOG)]
    require(len(rows) == 1 and rows[0]["argv"] == command and rows[0]["cwd"] == str(ROOT) and
            rows[0]["timeout_s"] == 60 and rows[0]["returncode"] == 0 and
            all(r["returncode"] == 0 for r in commands), "compiled/Spike command profile differs")
    capability = oracle.validate_capability((BUILD / "hpm-capability.spike.log").read_text())
    replay = oracle.validate_log(LOG.read_text(), spike=True, stub=stub)
    require(record["validated"] == replay and record["capability"] == capability,
            "saved proof differs from independent replay")
    proof.hashes(dict(proof.files))
    return sources, record, replay


def precheck(item, evidence):
    # Each case owns an exact local evidence set, even in a shared batch proof.
    from coverage_evidence import Evidence
    proof = Evidence()
    require(item.get("name") == TEST, "only the gap44 case is eligible")
    schema = item.get("precheck", {})
    require(schema.get("format") == FORMAT and item.get("runtime_contract") == oracle.RUNTIME_FORMAT,
            "explicit gap44 precheck/runtime format required")
    require(type(item.get("timeout_s")) is int and item["timeout_s"] == 300, "exact 300s case budget required")
    for key in ("record_sha256", "source_hashes_sha256"):
        require(isinstance(schema.get(key), str) and re.fullmatch("[0-9a-f]{64}", schema[key]),
                "explicit SHA256 required: " + key)
    sources, original, replay = frozen_inputs(proof)
    expected_sources = dict(sources)
    for p in OWN_SOURCES:
        proof.pin(p)
        expected_sources[str(p)] = proof.files[str(p)]
    record_path = proof.pin(schema["record"], schema["record_sha256"])
    manifest = proof.pin(schema["source_hashes"], schema["source_hashes_sha256"])
    admission = proof.read(record_path)
    require(admission.get("format") == FORMAT and admission.get("name") == TEST and
            admission.get("status") == "SPIKE_PASS_ONLY" and admission.get("vcs_launched") is False and
            admission.get("returncode") == 0, "admission identity/status")
    require(admission.get("original_record") == str(RECORD) and admission.get("original_record_sha256") == RECORD_SHA256,
            "original evidence anchor differs")
    require(item.get("binary") == admission.get("binary") == str(ELF) and
            item.get("binary_sha256") == admission.get("elf_sha256") == original["elf_sha256"], "DUT ELF differs")
    require(item.get("source_audit") == str(AUDIT) and schema.get("log") == str(LOG), "audit/log path differs")
    require(item.get("source_hashes") == admission.get("source_hashes") == proof.read(manifest) == expected_sources,
            "complete compiled/adapter source set differs")
    require(sorted(item.get("sources", [])) == sorted(expected_sources), "declared source set differs")
    required_files = {p: h for p, h in proof.files.items() if p not in (str(record_path), str(manifest))}
    require(admission.get("files") == required_files, "exact required evidence set differs")
    require(sorted(item.get("evidence", [])) == sorted([*required_files, str(record_path), str(manifest)]),
            "declared evidence set differs")
    require(admission.get("validated") == replay, "admission probe proof differs")
    require(admission.get("hpm_dut_preservation_pending") is True, "Spike cannot prove nonzero DUT HPM preservation")
    proof.hashes(expected_sources)
    proof.hashes(dict(proof.files))
    evidence.hashes(dict(proof.files))
    return dict(name=TEST, status="PASS", precheck=dict(schema), elf_sha256=original["elf_sha256"],
                log_sha256=original["files"][str(LOG)], phases=52, illegal=50, checks=1290,
                hpm_dut_preservation_pending=True, scope="Spike-only; mandatory nonzero DUT HPM guard pending")


def handles(item):
    return item.get("name", "").split(":")[-1] == NAME or item.get("precheck", {}).get("format") == FORMAT


def install_hooks():
    """Compose this case's gates; never assign the parent's checked.SCRIPT."""
    from run_gap44_csr_checked_extension import install_hooks as install
    return install()


def runtime_proof(output, plan, row):
    import run_checked_extension as checked
    full = checked.full
    require(plan.get("checked_extension") == checked.VERSION, "checked plan required")
    cases = [c for c in plan["cases"] if c["name"] == NAME and c["source_name"] == TEST]
    require(len(cases) == 1, "missing/duplicate runtime case")
    case = cases[0]
    require(row.get("name") == NAME and row.get("kind") == case["kind"] == "directed" and
            row.get("status") == "PASS" and row.get("returncode") == 0 and row.get("passed_only") is True and
            row.get("vdb_valid") is True and row.get("reused") is False, "independent generic PASS required")
    require(row.get("contract") == case["contract"] == full.contract(case), "runtime contract differs")
    proof = checked.evidence.Evidence()
    selection = Path(plan["source_selection"]["selection"])
    proof.pin(selection, plan["files"][str(selection)])
    items = [i for i in proof.read(selection)["cases"] if i["name"] == TEST]
    require(len(items) == 1, "missing/duplicate selected case")
    admitted = precheck(items[0], proof)
    require(all(plan["files"].get(p) == h for p, h in proof.files.items()), "precheck inputs not frozen in plan")
    audit = proof.read(AUDIT)
    require(Path(plan["design_vdb"]) == Path(audit["compiled_manifest"]).parent / "simv.vdb", "compiled design differs")
    require(row["elf_sha256"] == case["elf_sha256"] == admitted["elf_sha256"], "runtime ELF differs")
    proof.pin(case["frozen_elf"], admitted["elf_sha256"])
    target = Path(output).resolve(strict=True) / "results" / NAME

    def bound(filename):
        require(str(filename) in row["files"], "unbound runtime artifact: " + str(filename))
        return proof.pin(filename, row["files"][str(filename)])

    summaries = proof.read(bound(target / "summary.json"))
    require(len(summaries) == 1 and summaries[0]["name"] == TEST and
            full.batch.classify(summaries[0], row["returncode"]) == "PASS", "runtime summary differs")
    artifact = Path(summaries[0]["artifact_dir"]).resolve(strict=True)
    require(artifact == target / "tests" / ("rvv_" + NAME), "foreign runtime artifact")
    require(Path(row["vdb"]).resolve() == artifact / "work/code.vdb", "foreign VDB")
    metadata = proof.read(bound(artifact / "inputs.json"))
    require(metadata["binary"]["sha256"] == admitted["elf_sha256"] and
            metadata["simv"]["image_sha256"] == plan["wrapper_image"], "runtime ELF/image metadata differs")
    proof.pin(bound(artifact / "input.elf"), admitted["elf_sha256"])
    checker = Path(full.batch.__file__).resolve()
    proof.pin(checker, plan["files"][str(checker)])
    full.batch.audit_ok(proof.read(bound(target / "independent_audit.json")), case, artifact)
    trace = bound(artifact / "commit_trace.csv")
    trace_summary = proof.read(bound(artifact / "trace_summary.json"))
    require(trace.stat().st_size > 0 and trace_summary.get("status") == "VALID" and
            trace_summary.get("retire_count", 0) > 0, "missing/invalid directed trace")
    log = bound(artifact / "work/run.vcs.log")
    uart = oracle.validate_log(log.read_text(errors="strict"), spike=False)
    proof.hashes(dict(proof.files))
    return dict(status="PASS", schema=oracle.RUNTIME_FORMAT, name=NAME, elf_sha256=admitted["elf_sha256"],
                artifact_dir=str(artifact), uart=uart, files=proof.files,
                scope="1290 immutable C checks + nonzero DUT HPM preservation + strict directed trace audit; not per-phase RVFI")
