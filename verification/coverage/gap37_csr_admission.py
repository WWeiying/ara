"""PASS-only gap37 precheck adapter; no build, simulator, or global hook on import."""
import hashlib
from pathlib import Path
import re
import types

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
FORMAT = "gap37-csr-spike-v1"
NAME = "gap37_csr_alias_tvm"
TEST = "rvv:" + NAME
STEM = NAME
OUT = ROOT / "verification/out/gap37-csr-analysis-20261004-01"
BUILD = OUT / "preflight-01"
BUILDER = ROOT / "verification/tests/build_gap37_csr.py"
LOG = BUILD / (STEM + ".spike.log")
ELF = BUILD / (STEM + ".elf")
SPIKE_ELF = BUILD / (STEM + ".spike")
RECORD = BUILD / (STEM + ".evidence.json")
SOURCE_MANIFEST = BUILD / "source-hashes.json"
TOOL_MANIFEST = BUILD / "tool-hashes.json"
COMMANDS = BUILD / "commands.json"
ORIGINAL_SELECTION = OUT / "selection-draft.json"
OWN_SOURCES = (
    SCRIPT,
    ROOT / "verification/tests/prepare_gap37_csr_admission.py",
    ROOT / "verification/tests/test_gap37_csr_admission.py",
    ROOT / "verification/tests/audit_gap37_csr.py",
    ROOT / "verification/tests/finalize_gap37_csr.py",
    ROOT / "verification/tests/test_gap37_csr_preflight.py",
    ROOT / "verification/coverage/gap37_csr_admission.md",
)
# Anchors are the preserved first preflight, not a new producer's claimed PASS.
FROZEN = {
    SOURCE_MANIFEST: "e8bc6c1f256e4293947a6d591a819a016c35a0fa1d90d20335ad275bdc94e2b0",
    TOOL_MANIFEST: "f7ef059b20487f166b252d7dcd390a177d37955a8eedbfd42bd6b3eb05ed5f38",
    COMMANDS: "87cae414fc7b71e14f5554e368a200ad9475ae2123817af74f54c6c8dce29458",
    RECORD: "875e41eab33fee09fc36078e7a717071fc376fa2ed2f3a6a8e5bc6355671a70d",
    LOG: "24d7fa9362da562ba09eb1179a9fb50d7cc59d433becac7822a7b5a186326898",
    ORIGINAL_SELECTION: "863c8a66d0266af6dade93c09a353af8bc278c8ec4a448241eccfd3abca65dca",
}


def require(ok, message):
    if not ok:
        raise ValueError("gap37 admission: " + message)


def path(value):
    p = Path(value)
    return (p if p.is_absolute() else ROOT / p).absolute()


def digest(value):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value), "invalid SHA256")
    return value


def load_validator(proof, hashes):
    filename = proof.pin(BUILDER, hashes[str(BUILDER)])
    data = filename.read_bytes()
    require(hashlib.sha256(data).hexdigest() == hashes[str(BUILDER)], "validator changed while reading")
    # Execute only the hashed source, never cached bytecode, and never its main.
    module = types.ModuleType("gap37_pinned_validator")
    module.__file__ = str(filename)
    exec(compile(data, str(filename), "exec"), module.__dict__)
    proof.pin(filename, hashes[str(BUILDER)])
    return module


def frozen_inputs(proof):
    for filename, sha in FROZEN.items():
        proof.pin(filename, sha)
    sources = proof.read(SOURCE_MANIFEST)
    tools = proof.read(TOOL_MANIFEST)
    proof.hashes(sources)
    proof.hashes(tools)
    native = proof.read(OUT / "native-points.json")
    proof.hashes(native["provenance"])
    proof.hashes({r["path"]: r["sha256"] for r in native["source_pins"]})
    record = proof.read(RECORD)
    require(record["status"] == "SPIKE_PASS_ONLY", "original record is not Spike PASS")
    proof.pin(ELF, record["elf_sha256"])
    proof.pin(SPIKE_ELF, record["spike_elf_sha256"])
    proof.pin(LOG, record["log_sha256"])
    nm_path = proof.pin(BUILD / (STEM + ".nm"))
    symbols = re.findall(r"^([0-9a-f]+) [bB] csr_gap35_stub$", nm_path.read_text(), re.M)
    require(len(symbols) == 1, "missing/ambiguous ELF stub symbol")
    # The original, pinned Spike ELF's symbol. A replaced nm listing cannot
    # recalibrate the EPC oracle even if its new hash is supplied.
    stub = int(symbols[0], 16)
    require(stub == 0x80003a40, "original Spike ELF stub address differs")
    command = [str(ROOT / "install/riscv-isa-sim/bin/spike"), "--isa=rv64gcv_zfh",
               "--pmpregions=0", "--varch=vlen:1024,elen:64", str(SPIKE_ELF)]
    rows = [r for r in proof.read(COMMANDS) if r["log"] == str(LOG)]
    require(len(rows) == 1 and rows[0] == dict(argv=command, cwd=str(ROOT), timeout_s=60, log=str(LOG)),
            "Spike command/profile/budget differs")
    result_rows = proof.read(BUILD / "spike-results.json")
    require(result_rows == [dict(name=STEM, status="SPIKE_PASS_ONLY", phases=52, checks=626,
                                illegal=7, elapsed_build_and_precheck_s=record["elapsed_build_and_precheck_s"])],
            "original results differ")
    return sources, record, stub


def precheck(item, proof):
    """Same (item, Evidence) -> normalized result contract as evidence.precheck."""
    require(item.get("name") == TEST, "only the alias/TVM PASS case is eligible; counters remain rejected")
    schema = item.get("precheck", {})
    require(schema.get("format") == FORMAT, "explicit gap37 format required")
    require(type(item.get("timeout_s")) is int and 0 < item["timeout_s"] <= 600, "invalid case budget")
    record_path = proof.pin(schema["record"], digest(schema["record_sha256"]))
    manifest_path = proof.pin(schema["source_hashes"], digest(schema["source_hashes_sha256"]))
    admission = proof.read(record_path)
    require(admission.get("format") == FORMAT and admission.get("name") == TEST and
            admission.get("status") == "SPIKE_PASS_ONLY", "wrong admission identity/status")
    require(admission.get("vcs_launched") is False and admission.get("returncode") == 0,
            "admission scope/returncode differs")
    require(path(schema["log"]) == LOG, "wrong Spike log")
    require(path(item["binary"]) == ELF and admission.get("binary") == str(ELF), "wrong admitted ELF")
    require(path(item.get("source_audit", "")) == OUT / "source-audit.json", "wrong source audit")
    listed = [path(p) for p in item.get("sources", [])]
    require(listed and len(listed) == len(set(listed)), "empty/duplicate declared sources")
    hashes = proof.read(manifest_path)
    require(item.get("source_hashes") == hashes == admission.get("source_hashes"), "source hash manifests differ")
    require(set(map(str, listed)) == set(hashes), "declared source set differs")
    proof.hashes(hashes)
    original_sources, original_record, stub = frozen_inputs(proof)
    expected_sources = set(original_sources) | set(map(str, OWN_SOURCES))
    require(set(hashes) == expected_sources, "missing/extra builder/helper/admission source")
    require(all(hashes[p] == h for p, h in original_sources.items()), "compiled source hash differs")
    files = admission.get("files")
    require(isinstance(files, dict) and files, "empty admission evidence pins")
    declared = [path(p) for p in item.get("evidence", [])]
    require(len(declared) == len(set(declared)), "duplicate declared evidence")
    require(set(map(str, declared)) == set(files) | {str(record_path), str(manifest_path)},
            "evidence set differs")
    required_files = set(map(str, FROZEN)) | {
        str(BUILD / (STEM + ".nm")), str(BUILD / "spike-results.json"),
        str(OUT / "source-audit.json"), str(OUT / "finalization.json"),
        str(BUILD / "gap37_csr_counters.spike.log"), str(BUILD / "failure.json"),
    }
    require(required_files <= set(files), "missing original evidence pins")
    proof.hashes(files)
    require(admission.get("elf_sha256") == item.get("binary_sha256") == original_record["elf_sha256"],
            "ELF identity differs")
    require(admission.get("log_sha256") == original_record["log_sha256"], "Spike log identity differs")
    require(admission.get("original_record") == str(RECORD), "wrong original record")
    log = LOG.read_text()
    require(not re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b|Fatal:|Error:)", log), "failure marker in Spike log")
    require(sum(line.startswith("PASSED:") for line in log.splitlines()) == 1, "ambiguous PASS marker")
    validator = load_validator(proof, original_sources)
    replay = validator.validate_log(STEM, log, stub)
    require(all(original_record.get(k) == value for k, value in replay.items()), "strict replay differs from original record")
    require(admission.get("validated") == replay, "saved admission differs from strict replay")
    require((replay["phases"], replay["checks"], replay["illegal"], replay["legal"], replay["failures"]) ==
            (52, 626, 7, 45, 0), "selfcheck contract differs")
    # Recheck after imports/replay: all checked pins propagate to the parent's
    # checked plan and its normal launch-boundary frozen-file checks.
    proof.hashes(dict(proof.files))
    return dict(name=TEST, status="PASS", precheck=dict(schema), elf_sha256=original_record["elf_sha256"],
                log_sha256=original_record["log_sha256"], scope="Spike-only",
                phases=52, checks=626, illegal=7, validator=str(BUILDER), adapter=str(SCRIPT))


def handles(item):
    """The parent's dispatcher selects this adapter only for the explicit format."""
    return item.get("precheck", {}).get("format") == FORMAT


def validate_runtime_log(text):
    """DUT UART contract, deliberately distinct from Spike's 52 PROBE records."""
    lines = text.splitlines()
    summary = NAME + " phases=52 checks=626 illegal=7 legal=45 failures=0"
    require(lines.count(summary) == 1, "missing/duplicate or incorrect runtime summary")
    require(sum(line.startswith(NAME + " phases=") for line in lines) == 1, "ambiguous runtime summary")
    require(lines.count("PASSED: " + NAME) == 1 and
            sum(line.startswith("PASSED:") for line in lines) == 1, "missing/ambiguous runtime PASS")
    require(not re.search(r"(?i)\bFAIL(?:ED)?\b|\bFatal:|\bError:", text), "runtime failure marker")
    return dict(phases=52, checks=626, illegal=7, legal=45, failures=0,
                scope="exact UART summary and immutable C selfchecks; no UART per-phase PROBE claim")


def runtime_proof(output, plan, row):
    """Read-only extra worker gate AFTER the normal strict directed audit passes.

    Parent saves this result, merges its files into row.files, and rechecks them
    before summarizing. Any exception must prevent PASS publication/collection.
    """
    import run_checked_extension as checked

    full = checked.full
    require(plan.get("checked_extension") == checked.VERSION, "not a checked plan")
    matches = [c for c in plan["cases"] if c["name"] == NAME and c["source_name"] == TEST]
    require(len(matches) == 1, "missing/duplicate runtime case")
    case = matches[0]
    require(row.get("name") == NAME and row.get("kind") == case["kind"] == "directed" and
            row.get("status") == "PASS" and row.get("returncode") == 0 and
            row.get("passed_only") is True and row.get("vdb_valid") is True and
            row.get("reused") is False, "generic runtime outcome is not independent PASS")
    require(row.get("contract") == case["contract"] == full.contract(case), "runtime contract differs")
    proof = checked.evidence.Evidence()
    selection_path = path(plan["source_selection"]["selection"])
    require(str(selection_path) in plan["files"], "unbound composed selection")
    proof.pin(selection_path, plan["files"][str(selection_path)])
    items = [i for i in proof.read(selection_path)["cases"] if i["name"] == TEST]
    require(len(items) == 1, "missing/duplicate selected runtime case")
    admitted = precheck(items[0], proof)
    require(all(plan["files"].get(p) == h for p, h in proof.files.items()), "runtime precheck inputs not frozen in plan")
    require(row.get("elf_sha256") == case["elf_sha256"] == admitted["elf_sha256"], "runtime ELF differs")
    proof.pin(case["frozen_elf"], admitted["elf_sha256"])
    target = Path(output).resolve(strict=True) / "results" / NAME

    def bound(filename):
        require(str(filename) in row["files"], "unbound runtime artifact: " + str(filename))
        return proof.pin(filename, row["files"][str(filename)])

    summaries = proof.read(bound(target / "summary.json"))
    require(len(summaries) == 1 and summaries[0]["name"] == TEST and
            full.batch.classify(summaries[0], row["returncode"]) == "PASS", "wrong runtime summary artifact")
    artifact = Path(summaries[0]["artifact_dir"]).resolve(strict=True)
    require(artifact.is_relative_to(target), "foreign CSR runtime artifact")
    require(Path(row["vdb"]).resolve() == artifact / "work/code.vdb", "foreign runtime VDB")
    metadata = proof.read(bound(artifact / "inputs.json"))
    require(metadata["binary"]["sha256"] == admitted["elf_sha256"] and
            metadata["simv"]["image_sha256"] == plan["wrapper_image"], "runtime ELF/image metadata differs")
    proof.pin(bound(artifact / "input.elf"), admitted["elf_sha256"])
    audit_path = bound(target / "independent_audit.json")
    checker = Path(full.batch.__file__).resolve()
    require(str(checker) in plan["files"], "unbound generic trace audit checker")
    proof.pin(checker, plan["files"][str(checker)])
    full.batch.audit_ok(proof.read(audit_path), case, artifact)
    trace = bound(artifact / "commit_trace.csv")
    trace_summary = proof.read(bound(artifact / "trace_summary.json"))
    require(trace.stat().st_size > 0 and trace_summary.get("status") == "VALID" and
            trace_summary.get("retire_count", 0) > 0, "missing/invalid directed retirement trace")
    log = bound(artifact / "work/run.vcs.log")
    uart = validate_runtime_log(log.read_text(errors="strict"))
    proof.hashes(dict(proof.files))
    return dict(status="PASS", schema="gap37-csr-uart-generic-trace-v1", name=NAME,
                artifact_dir=str(artifact), elf_sha256=admitted["elf_sha256"], uart=uart,
                generic_audit=str(audit_path), generic_trace=str(trace), files=proof.files,
                scope="exact 626-check UART contract + frozen C/ELF + existing strict directed trace audit; no per-phase RVFI oracle")


def wrap_precheck(delegate):
    """Wrap the parent's complete FENCE/RVFI dispatcher without replacing it."""
    require(callable(delegate), "delegate must be callable")
    if getattr(delegate, "_gap37_csr_admission", False):
        return delegate

    def wrapped(item, proof):
        name = item.get("name", "")
        fmt = item.get("precheck", {}).get("format")
        if name.split(":")[-1].startswith("gap37_csr_") or fmt == FORMAT:
            return precheck(item, proof)
        return delegate(item, proof)

    wrapped._gap37_csr_admission = True
    wrapped.delegate = delegate
    return wrapped


def install(evidence_module, delegate=None):
    """Install last in each parent process; modifies only its in-memory hook."""
    wrapped = wrap_precheck(evidence_module.precheck if delegate is None else delegate)
    evidence_module.precheck = wrapped
    return wrapped
