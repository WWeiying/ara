#!/usr/bin/env python3
"""Prepare or execute an isolated exploration batch; never build or repair RTL.

Plan: {random: [{name, profile, seed}], directed: [{name, test}]}.
An optional replay list accepts {name, summary, case} without replacing random cases.
Optional per-case timeout_s, spike_timeout_s and watchdog_cycles are bounded.
Preparation is the default; execution requires --execute-prepared under systemd.
"""

import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import yaml

from ara_verify.artifacts import sha256, simulation_image
from ara_verify.catalog import load_catalog
from ara_verify.rvv_replay import failed_random_cases
from ara_verify.vcs_source_manifest import collect
from run_coverage_checkpoint import check_service, save

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
PYTHON = sys.executable
OUT = ROOT / "verification/out"
IMAGE = OUT / "seed509-fix-20260926-01/sim/simv"
GENERATOR = OUT / "integrated-random-short-control-preflight-20260925-01/vcs_simv"
SPIKE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike")
NORMAL_FAILURES = {"FAIL", "RTL_FAIL", "RTL_STALL", "RTL_TIMEOUT", "TIMEOUT",
                   "MISMATCH", "VECTOR_MISMATCH", "VECTOR_INCOMPLETE",
                   "INCOMPLETE_PREFIX", "INCOMPLETE_COMPARISON", "CHECKPOINT_FAIL"}
TIMEOUTS = {"RTL_STALL", "RTL_TIMEOUT", "TIMEOUT"}
PRIOR_WRAPPER = "954c17424af6ee24a6f5698786027bb63e17b701c67f436f55d7771e1b91f420"
HISTORICAL_WRAPPERS = {PRIOR_WRAPPER,
    "54f0ba8cf4aab002276a833c8485abb19d05d87b0adb051329b6e383f7f83f01"}


def seed1408_isolation(row, result, outcome, identity):
    """One measured unsupported stimulus, not a general timeout exception."""
    if (row.get("seed") != 1408 or row.get("test") != "ara_dsa_rvv1_load_store_slide_coverage300"
            or outcome.get("status") != "INFRASTRUCTURE_ERROR"
            or not outcome.get("reason", "").startswith("TimeoutExpired: Command ")
            or (result / "summary.json").exists()):
        return None
    artifact = result / "tests/ara_dsa_rvv1_load_store_slide_coverage300_0"
    elf = artifact / "input.elf"
    expected = "5f4b5c985fa9047f2e07ae747763689e45abc8259b77e6bae8402f553376d136"
    inputs = read(artifact / "inputs.json")
    if sha256(elf) != expected or inputs["binary"]["sha256"] != expected:
        raise RuntimeError("seed1408 ELF differs from reviewed evidence")
    if (inputs["simv"]["image_sha256"] != identity["images"][identity["image"]]
            or inputs["spike"]["sha256"] != identity["files"][identity["spike"]]):
        raise RuntimeError("seed1408 execution identity differs")
    spike = artifact / "spike_commit.log"
    if spike.stat().st_size != 2320400384:
        raise RuntimeError("seed1408 reference evidence size differs")
    with spike.open("rb") as stream:
        prefix = stream.read(2097152)
        stream.seek(-65536, 2)
        tail = stream.read(65536)
    if (hashlib.sha256(prefix).hexdigest() != "d39c1c4224e9455fbe845b00420d7e35975f11c7f9627aad3df556cc6f76899a"
            or hashlib.sha256(tail).hexdigest() != "08797d9f6e95777d77c898123688cc04cdf6da3f656b0705a64ec51203089a66"):
        raise RuntimeError("seed1408 bounded reference evidence differs")
    lines = prefix.decode().splitlines()
    fault = next(i for i, line in enumerate(lines) if "0x000000008000129a (0x674be107)" in line)
    vector = [re.search(r" v20\s+0x([0-9a-f]+)", line) for line in lines[:fault]]
    index = (int(next(match.group(1) for match in reversed(vector) if match), 16) >> 96) & 0xffffffff
    bases = [re.search(r" x23\s+0x([0-9a-f]+)", line) for line in lines[:fault]]
    base = int(next(match.group(1) for match in reversed(bases) if match), 16)
    if (base, index, base + index) != (0x80004cda, 0x19f4cfaa, 0x99f51c84):
        raise RuntimeError("seed1408 address derivation differs")
    for filename in ("rtl_console.log", "run.vcs.log"):
        text = (artifact / filename).read_text()
        if ("AXI read address 0x0000000099f51c84 exceeds the 2097152-byte simulation L2" not in text
                or "requests=507 responses=507" not in text or "outstanding=0" not in text
                or "Core Test *** SUCCESS ***" in text):
            raise RuntimeError("seed1408 DUT terminal evidence differs")
    return {"status": "UNSUPPORTED_STIMULUS", "original_status": outcome["status"],
            "reason": "reviewed indexed address outside simulation L2; reference trap retry loop",
            "elf_sha256": expected, "pc": "0x8000129a", "insn": "0x674be107",
            "base": hex(base), "index_element": 3, "index": hex(index), "address": hex(base + index),
            "reference_bytes_inspected": len(prefix) + len(tail),
            "reference_timeout": "inferred, not persisted; no synthetic timeout verdict",
            "artifact_dir": str(artifact)}


def verify_history(old, current, seen=None):
    seen = set() if seen is None else seen
    if old in seen:
        raise RuntimeError("cyclic continuation provenance")
    seen.add(old)
    prior = read(old / "identity.json")
    for key in ("image", "generator", "spike", "source_manifest", "sources", "images"):
        if prior[key] != current[key]:
            raise RuntimeError(f"continuation identity differs: {key}")
    for path, expected in {**prior["files"], **prior.get("reused_evidence", {})}.items():
        if sha256(Path(path)) != expected:
            if Path(path) != SCRIPT or expected not in HISTORICAL_WRAPPERS:
                raise RuntimeError(f"historical input/evidence changed: {path}")
    continuation = old / "continuation.json"
    if continuation.exists():
        if prior["files"].get(str(continuation)) != sha256(continuation):
            raise RuntimeError("historical continuation is not pinned")
        verify_history(output_path(Path(read(continuation)["source"])), current, seen)
    return prior


def rejected_stimulus(row, result, log, rc):
    """Recognize only the measured conservative indexed-store proof rejection."""
    if row["kind"] != "random" or rc != 1 or (result / "summary.json").exists():
        return None
    lines = log.read_text().splitlines()
    source = result / "asm_test" / (row["test"] + "_0.S")
    prefix = f"error: cannot prove vsetvl vtype before indexed store in {source}: "
    if len(lines) != 2 or not lines[0].startswith("python3 ") or not lines[1].startswith(prefix):
        return None
    instruction = lines[1][len(prefix):]
    if not re.fullmatch(r"vsetvl\s+zero,\s*zero,\s*s0", instruction):
        return None
    probe = result / "spike_probe/spike_vstart_probe.elf"
    if any(result.rglob("inputs.json")) or any(path != probe for path in result.rglob("*.elf")):
        return None
    from ara_verify.vector_signature import _find_reaching_immediate, VectorSignatureError
    assembly = source.read_text().splitlines()
    for index, line in enumerate(assembly):
        if line.strip() != instruction:
            continue
        try:
            _find_reaching_immediate(assembly, index, "s0", source)
        except VectorSignatureError as error:
            if not str(error).startswith("cannot prove a straight-line constant definition of s0 "):
                continue
            return {"status": "REJECTED_STIMULUS", "bucket": f"random:{row['test']}:REJECTED_STIMULUS",
                    "reason": lines[1], "returncode": rc, "artifact_dir": str(result),
                    "evidence": {str(path): sha256(path) for path in (source, log)}}
    return None


def continue_batch(old, output):
    """Import evidence, never relabel a historical image as a current build."""
    current = check_identity(output)
    prior = verify_history(old, current)
    for key in ("image", "generator", "spike", "source_manifest", "sources", "images"):
        if prior[key] != current[key]:
            raise RuntimeError(f"continuation identity differs: {key}")
    pins = dict(prior.get("reused_evidence", {}))
    changes = []
    for path, expected in prior["files"].items():
        actual = sha256(Path(path))
        if actual != expected:
            if Path(path) != SCRIPT or expected not in HISTORICAL_WRAPPERS:
                raise RuntimeError(f"historical input changed: {path}")
            changes.append({"path": path, "before": expected, "after": actual})
        if not Path(path).is_relative_to(old):
            if current["files"].get(path) != actual:
                raise RuntimeError(f"continuation external input differs: {path}")
        else:
            pins[path] = actual
    previous = read(old / "plan.json")["cases"]
    rows = read(output / "plan.json")["cases"]
    if (old / "continuation.json").exists():
        for replacement in read(old / "continuation.json")["replacements"]:
            index = next(i for i, row in enumerate(rows) if row["name"] == replacement["replaces"])
            original = rows[index]
            if any(replacement.get(key) != value for key, value in original.items() if key not in {"name", "seed"}):
                raise RuntimeError("inherited replacement changed case parameters")
            rows[index] = replacement
    if previous != rows:
        raise RuntimeError("continuation requires the same full normalized plan")
    state = read(old / "checkpoint.json")
    if state["status"] != "STOPPED":
        raise RuntimeError("continuation source must be stopped")
    by_name = {row["name"]: row for row in rows}
    rejections = {}
    for name, outcome in state["cases"].items():
        row = by_name[name]
        origin = output_path(Path(outcome["source_batch"])) if outcome.get("reused") else old
        result = origin / "cases" / name
        if origin != old and str(result / "batch_result.json") not in prior.get("reused_evidence", {}):
            raise RuntimeError("reused origin lacks historical evidence pin")
        original_outcome = {key: value for key, value in outcome.items()
                            if key not in {"reused", "source_batch", "reuse_chain"}}
        if read(result / "batch_result.json") != original_outcome:
            raise RuntimeError("historical checkpoint/result disagree")
        if outcome["status"] in {"INFRASTRUCTURE_ERROR", "REJECTED_STIMULUS"}:
            rejected = rejected_stimulus(row, result, old / "logs" / f"{name}.log", 1)
            if rejected is None:
                rejected = seed1408_isolation(row, result, outcome, current)
            if rejected is None:
                raise RuntimeError("unrecognized historical infrastructure failure")
            rejections[name] = rejected
            seed = max(r["seed"] for r in rows if r["kind"] == "random" and r["test"] == row["test"]) + 1
            row.update(seed=seed, name=f"{name}-replacement-{seed}", replaces=name)
        else:
            summaries = read(result / "summary.json")
            if len(summaries) != 1 or classify(summaries[0], outcome["returncode"]) != outcome["status"]:
                raise RuntimeError("historical verdict disagrees")
            artifact = Path(summaries[0]["artifact_dir"]).resolve()
            if not artifact.is_relative_to(result.resolve()) or str(artifact) != outcome["artifact_dir"]:
                raise RuntimeError("historical artifact escaped case")
            inputs = read(artifact / "inputs.json")
            if inputs["simv"]["image_sha256"] != current["images"][current["image"]]:
                raise RuntimeError("historical image differs")
            elf = sha256(artifact / "input.elf")
            if elf != inputs["binary"]["sha256"] or elf != row.get("elf_sha256", elf):
                raise RuntimeError("historical ELF differs")
            if row["kind"] != "directed" and inputs["spike"]["sha256"] != current["files"][current["spike"]]:
                raise RuntimeError("historical Spike differs")
            check_environment_logs(result)
            if outcome["status"] == "PASS":
                report = read(result / "independent_audit.json")
                if report.get("status") != "PASS" or report.get("errors"):
                    raise RuntimeError("historical PASS audit invalid")
                _, audit = commands(row, current, result)
                destination = output / "reuse-audits" / f"{name}.json"
                audit[audit.index("--output") + 1] = str(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if invoke(audit, output / "logs" / f"reuse-{name}.log", 300) != 0:
                    raise RuntimeError("reused PASS failed independent audit")
                fresh = read(destination)
                if fresh.get("status") != "PASS" or fresh.get("errors"):
                    raise RuntimeError("reused PASS audit corrupt")
                pins[str(destination)] = sha256(destination)
            publish_case(output, name, {**outcome, "reused": True, "source_batch": str(origin),
                         "reuse_chain": list(dict.fromkeys(outcome.get("reuse_chain", []) + [str(origin), str(old)]))})
        for path in result.rglob("*"):
            if path.is_file():
                pins[str(path)] = sha256(path)
        log = origin / "logs" / f"{name}.log"
        pins[str(log)] = sha256(log)
    for filename in ("identity.json", "checkpoint.json", "plan.json"):
        path = old / filename
        pins[str(path)] = sha256(path)
    save(output / "continuation.json", {"source": str(old), "wrapper_changes": changes,
         "rejected_stimuli": rejections, "replacements": [r for r in rows if "replaces" in r]})
    save(output / "plan.json", {"schema_version": 1, "cases": rows})
    current["reused_evidence"] = pins
    for filename in ("plan.json", "continuation.json"):
        path = output / filename
        current["files"][str(path)] = sha256(path)
    save(output / "identity.json", current)
    check_identity(output)


def read(path):
    return json.loads(path.read_text())


def output_path(path):
    path = path.resolve()
    if path == OUT.resolve() or not path.is_relative_to(OUT.resolve()):
        raise ValueError("output must be beneath verification/out")
    return path


def validate_plan(plan, profiles):
    policy = plan.get("policy", {})
    if "stop_on_any_non_pass" in policy and policy["stop_on_any_non_pass"] is not False:
        raise ValueError("stale fail-fast plan policy conflicts with authorized batch exploration")
    if plan.get("schema_version", 1) != 1 or not all(
            isinstance(plan.get(key), list) for key in ("random", "directed")):
        raise ValueError("expected random and directed lists")
    originals = []
    for kind in ("random", "directed", "replay"):
        for item in plan.get(kind, []):
            row = {**item, "kind": kind}
            if kind == "random":
                row["test"] = row.pop("profile", None)
            originals.append(row)
    names, stimuli, counts = set(), set(), Counter()
    rows = []
    for original in originals:
        row = dict(original)
        name, kind = row.get("name", ""), row.get("kind")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or name in names:
            raise ValueError("case names must be unique and path-safe")
        names.add(name)
        if kind not in ("random", "directed", "replay"):
            raise ValueError(f"unknown case kind: {kind}")
        counts[kind] += 1
        for key, default, maximum in (("timeout_s", 900, 1800), ("spike_timeout_s", 120, 300),
                                       ("watchdog_cycles", 250000, 1000000)):
            value = row.setdefault(key, default)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"invalid {key}: {name}")
        if kind == "random":
            if type(row.get("seed")) is not int or row["seed"] < 0:
                raise ValueError(f"invalid random seed: {name}")
            profile = profiles.get(row.get("test"))
            if profile is None:
                raise ValueError(f"unknown random profile: {row.get('test')}")
            tokens = shlex.split(profile.get("gen_opts", ""))
            sizes = [int(token.split("=", 1)[1]) for token in tokens if token.startswith("+instr_cnt=")]
            if len(sizes) != 1 or not 1 <= sizes[0] <= 300:
                raise ValueError(f"random profile must have one instr_cnt <=300: {row['test']}")
            row["instr_count"] = sizes[0]
            identity = (kind, row["test"], row["seed"])
        elif kind == "directed":
            if not isinstance(row.get("test"), str) or any(x in row["test"] for x in "*?["):
                raise ValueError("directed test must be an exact catalog name")
            identity = (kind, row["test"])
        else:
            if not row.get("summary") or not row.get("case"):
                raise ValueError("replay requires summary and case")
            identity = (kind, str(Path(row["summary"]).resolve()), row["case"])
        if identity in stimuli:
            raise ValueError(f"duplicate stimulus: {name}")
        stimuli.add(identity)
        rows.append(row)
    if counts["random"] < 200 or counts["directed"] < 40:
        raise ValueError("batch requires >=200 generated random and >=40 directed cases")
    return rows


def source_records(manifest):
    saved = read(manifest)
    records = collect(Path(saved["filelist"]), Path(saved["repo_root"]),
                      [Path(path) for path in saved["extra_sources"]])
    if records != saved["files"] or len(records) != 457:
        raise RuntimeError("current image source manifest differs or is not the 457-input checkpoint")
    return records


def prepare(plan_path, output, image, generator, spike):
    profile_path = ROOT / "verification/riscv_dv/testlist.yaml"
    profiles = {row["test"]: row for row in yaml.safe_load(profile_path.read_text())}
    cases = validate_plan(read(plan_path), profiles)
    manifest = image.parent / "vcs_source_manifest.json"
    sources = source_records(manifest)
    for binary in (image, generator, spike):
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise RuntimeError(f"missing executable: {binary}")
    for binary in (image, generator):
        if not Path(str(binary) + ".daidir").is_dir():
            raise RuntimeError(f"missing runtime database: {binary}")
    catalog = load_catalog(ROOT, ROOT / "verification/suites.json")
    files = [plan_path, SCRIPT, profile_path, manifest, image.parent / "simulator.conf", spike,
             ROOT / "verification/verify.py", ROOT / "verification/run_failfast_checkpoint.py"]
    files.extend((ROOT / "verification/ara_verify").glob("*.py"))
    for row in cases:
        if row["kind"] == "random":
            continue
        if row["kind"] == "directed":
            test = catalog.tests.get(row["test"])
            if test is None:
                raise ValueError(f"unknown directed test: {row['test']}")
            elf = test.binary
        else:
            summary = Path(row["summary"]).resolve(strict=True)
            selected = failed_random_cases(summary, [row["case"]], include_passed=True)
            if len(selected) != 1:
                raise ValueError("replay must select exactly one ELF")
            elf = selected[0].elf
            files.append(summary)
        frozen = output / "inputs" / (row["name"] + ".elf")
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(elf, frozen)
        row["elf_sha256"] = sha256(frozen)
        if sha256(elf) != row["elf_sha256"]:
            raise RuntimeError("ELF changed during snapshot")
        files.extend((elf, frozen))
        if row["kind"] == "replay":
            summary = output / "inputs" / (row["name"] + ".json")
            save(summary, [{"name": row["case"], "elf": str(frozen), "status": "FAIL",
                            "seed": selected[0].seed, "profile": selected[0].profile}])
            row["summary"] = str(summary)
            files.append(summary)
    save(output / "plan.json", {"schema_version": 1, "cases": cases})
    files.append(output / "plan.json")
    identity = {"image": str(image), "generator": str(generator), "spike": str(spike),
                "source_manifest": str(manifest), "sources": sources,
                "images": {str(path): simulation_image(path) for path in (image, generator)},
                "files": {str(path): sha256(path) for path in sorted(set(files))}}
    save(output / "identity.json", identity)
    save(output / "checkpoint.json", {"status": "PREPARED", "total": len(cases),
         "completed": 0, "passed": 0, "failed": 0, "infrastructure_errors": 0,
         "cases": {}, "failure_buckets": {}, "workers_max": 5,
         "source_file_count": len(sources), "coverage_builds": 0,
         "scheduler_status_scope": "worker execution only; case verdicts are in this checkpoint",
         "queue_policy": "continue case failures; stop shared queue on infrastructure or integrity failure"})


def check_identity(output, full=True):
    identity = read(output / "identity.json")
    for path, expected in identity["files"].items():
        if sha256(Path(path)) != expected:
            raise RuntimeError(f"batch input changed: {path}")
    if full:
        for path, expected in identity.get("reused_evidence", {}).items():
            if sha256(Path(path)) != expected:
                raise RuntimeError(f"reused evidence changed: {path}")
        if source_records(Path(identity["source_manifest"])) != identity["sources"]:
            raise RuntimeError("batch sources changed")
        for path, expected in identity["images"].items():
            if simulation_image(Path(path)) != expected:
                raise RuntimeError(f"batch image changed: {path}")
    return identity


def commands(row, identity, result):
    verify = [PYTHON, str(ROOT / "verification/verify.py")]
    common = ["--simv", identity["image"], "--timeout", str(row["timeout_s"]),
              "--output", str(result)]
    if row["kind"] == "directed":
        command = verify + ["run", "--test", row["test"], "--skip-build", "--commit-trace",
                            "--jobs", "1"] + common
    else:
        common += ["--spike", identity["spike"], "--spike-isa", "rv64gcv_zvfh_zvl1024b",
                   "--spike-timeout", str(row["spike_timeout_s"]),
                   "--watchdog-cycles", str(row["watchdog_cycles"])]
        if row["kind"] == "random":
            command = verify + ["run-rvv", "--test", row["test"], "--seed", str(row["seed"]),
                "--iterations", "1", "--simulator", "vcs", "--generator-simv", identity["generator"],
                "--vector-signature", "--defined-scalar-sources", "--vector-commit-compare"] + common
        else:
            command = verify + ["replay-failed-rvv", "--summary", row["summary"], "--case", row["case"],
                                "--include-passed", "--jobs", "1"] + common
    audit = verify + ["audit", "--run", str(result), "--require-trace",
                      "--output", str(result / "independent_audit.json")]
    if row["kind"] != "directed":
        audit += ["--require-vector", "--require-full-match"]
    return command, audit


def classify(row, returncode):
    status = row.get("status")
    if row.get("input_errors"):
        raise RuntimeError("case input identity changed")
    reason = row.get("reason", "")
    if re.search(r"changed|identity|private ELF|invalid commit trace|trace.*not produced",
                 reason, re.I):
        raise RuntimeError(f"case integrity/checker failure: {reason}")
    if status not in TIMEOUTS and status not in {"RTL_FAIL", "FAIL"}:
        if any(row.get(key, {}).get("status") == "ERROR" for key in ("comparison", "vector_commit", "trace")):
            raise RuntimeError("checker produced ERROR rather than a test verdict")
    if status == "PASS":
        if returncode != 0:
            raise RuntimeError("PASS summary disagrees with worker exit status")
        return "PASS"
    if status not in NORMAL_FAILURES or returncode not in (0, 1):
        raise RuntimeError(f"infrastructure/unclassified result: {status}, rc={returncode}")
    return status


def publish_case(output, name, result):
    with (output / "checkpoint.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(output / "checkpoint.json")
        state["cases"][name] = result
        counts = Counter(item["status"] for item in state["cases"].values())
        state.update(completed=sum(counts.values()), passed=counts["PASS"],
                     infrastructure_errors=counts["INFRASTRUCTURE_ERROR"],
                     rejected=counts["REJECTED_STIMULUS"],
                     reused=sum(bool(item.get("reused")) for item in state["cases"].values()),
                     failed=sum(counts.values()) - counts["PASS"] - counts["INFRASTRUCTURE_ERROR"] - counts["REJECTED_STIMULUS"])
        state["failure_buckets"] = dict(Counter(item["bucket"] for item in state["cases"].values()
                                                if item["status"] != "PASS"))
        if counts["INFRASTRUCTURE_ERROR"]:
            state["status"] = "STOPPED"
        save(output / "checkpoint.json", state)


def invoke(command, log, timeout):
    log.parent.mkdir(parents=True, exist_ok=True)
    save(log.with_suffix(".command.json"), {"command": command, "timeout_s": timeout})
    with log.open("w") as stream:
        return subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                              timeout=timeout, check=False).returncode


def check_environment_logs(result):
    pattern = re.compile(r"license checkout failed|unable to checkout|\[NOCOMP\]|"
                         r"error while loading shared libraries|No space left on device|"
                         r"Traceback \(most recent call last\)", re.I)
    for name in ("rtl_console.log", "console.log", "run.vcs.log"):
        for path in result.rglob(name):
            with path.open(errors="replace") as stream:
                if any(pattern.search(line) for line in stream):
                    raise RuntimeError(f"systemic environment/checker error in {path}")


def worker(output, name):
    result = output / "cases" / name
    try:
        identity = check_identity(output, full=False)
        row = next(item for item in read(output / "plan.json")["cases"] if item["name"] == name)
        command, audit = commands(row, identity, result)
        # Outer timeout means the runner failed to produce its own bounded verdict.
        rc = invoke(command, output / "logs" / f"{name}.log", row["timeout_s"] + 1500)
        if not (result / "summary.json").exists():
            outcome = rejected_stimulus(row, result, output / "logs" / f"{name}.log", rc)
            if outcome is not None:
                check_environment_logs(result)
                check_identity(output, full=False)
                save(result / "batch_result.json", outcome)
                publish_case(output, name, outcome)
                return 0
        rows = read(result / "summary.json")
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError("runner did not produce exactly one case result")
        check_environment_logs(result)
        verdict = classify(rows[0], rc)
        artifact = Path(rows[0]["artifact_dir"]).resolve()
        if not artifact.is_relative_to(result.resolve()):
            raise RuntimeError("case artifact escaped its isolated directory")
        inputs = read(artifact / "inputs.json")
        if inputs["simv"]["image_sha256"] != identity["images"][identity["image"]]:
            raise RuntimeError("case used a different image from the frozen batch")
        if row["kind"] != "directed" and inputs["spike"]["sha256"] != identity["files"][identity["spike"]]:
            raise RuntimeError("case used a different Spike from the frozen batch")
        elf_hash = sha256(artifact / "input.elf")
        if elf_hash != inputs["binary"]["sha256"] or elf_hash != row.get("elf_sha256", elf_hash):
            raise RuntimeError("case ELF identity differs")
        if verdict == "PASS":
            if invoke(audit, output / "logs" / f"{name}-audit.log", 300) != 0:
                raise RuntimeError("independent PASS audit failed")
            report = read(result / "independent_audit.json")
            if report.get("status") != "PASS" or report.get("errors"):
                raise RuntimeError("independent PASS audit is corrupt/non-PASS")
        check_identity(output, full=False)
        outcome = {"status": verdict,
                   "bucket": f"{row['kind']}:{row.get('test', row.get('case'))}:{verdict}",
                   "returncode": rc, "artifact_dir": str(artifact),
                   "summary": str(result / "summary.json"),
                   "audit": str(result / "independent_audit.json") if verdict == "PASS" else None}
        save(result / "batch_result.json", outcome)
        publish_case(output, name, outcome)
        return 0  # A normal failed test is evidence, not a queue failure.
    except Exception as error:
        outcome = {"status": "INFRASTRUCTURE_ERROR", "bucket": "infrastructure",
                   "reason": f"{type(error).__name__}: {error}", "artifact_dir": str(result)}
        save(result / "batch_result.json", outcome)
        publish_case(output, name, outcome)
        return 1


def execute(output, jobs):
    state = read(output / "checkpoint.json")
    try:
        check_service()
        if state["status"] != "PREPARED" or not 1 <= jobs <= 5:
            raise RuntimeError("requires a fresh PREPARED batch and 1..5 workers")
        # Cooperating batches share one host-wide allocation of at most five slots.
        with (OUT / ".batch-vcs.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            check_identity(output)
            plan = [{"name": row["name"], "cwd": str(ROOT),
                     "command": [PYTHON, str(SCRIPT), "--output", str(output), "--worker", row["name"]]}
                    for row in scheduling_order(read(output / "plan.json")["cases"])
                    if row["name"] not in state["cases"]]
            save(output / "functional-plan.json", plan)
            state.update(status="RUNNING", workers=jobs)
            save(output / "checkpoint.json", state)
            rc = invoke([PYTHON, str(ROOT / "verification/run_failfast_checkpoint.py"),
                         "--plan", str(output / "functional-plan.json"), "--jobs", str(jobs),
                         "--output", str(output / "functional-scheduler")],
                        output / "scheduler.log", 86400)
            check_identity(output)
            state = read(output / "checkpoint.json")
            if rc != 0 or state["infrastructure_errors"] or state["completed"] != state["total"]:
                raise RuntimeError("queue stopped or did not account for every case")
            state["status"] = "COMPLETE_WITH_FAILURES" if state["failed"] else "PASS"
            if state.get("rejected"):
                state["status"] = "INCOMPLETE_STIMULUS"
            save(output / "checkpoint.json", state)
            return 0
    except Exception as error:
        state = read(output / "checkpoint.json")
        state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}")
        save(output / "checkpoint.json", state)
        raise


def scheduling_order(rows):
    priority = {"rvv:vpolicy_type_matrix": 0, "rvv:vpolicy_masked_edges": 1}
    first = sorted((row for row in rows if row.get("test") in priority),
                   key=lambda row: priority[row["test"]])
    directed = [row for row in rows if row["kind"] == "directed" and row not in first]
    random = [row for row in rows if row["kind"] != "directed" and row not in first]
    ordered = list(first)
    for index in range(max(len(directed), len(random))):
        if index < len(directed):
            ordered.append(directed[index])
        if index < len(random):
            ordered.append(random[index])
    return ordered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--continue-from", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", type=Path, default=IMAGE)
    parser.add_argument("--generator", type=Path, default=GENERATOR)
    parser.add_argument("--spike", type=Path, default=SPIKE)
    parser.add_argument("--jobs", type=int, choices=range(1, 6), default=5)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--execute-prepared", action="store_true")
    modes.add_argument("--status", action="store_true")
    modes.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = output_path(args.output)
    if args.status:
        print(json.dumps({"checkpoint": read(output / "checkpoint.json"),
                          "scheduler": read(output / "functional-scheduler/status.json")
                          if (output / "functional-scheduler/status.json").exists() else None}, indent=2))
        return 0
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.worker:
        return worker(output, args.worker)
    if args.execute_prepared:
        return execute(output, args.jobs)
    if not args.plan:
        parser.error("--plan is required for preparation")
    output.mkdir(parents=True, exist_ok=False)
    try:
        prepare(args.plan.resolve(strict=True), output, args.image.resolve(strict=True),
                args.generator.resolve(strict=True), args.spike.resolve(strict=True))
        if args.continue_from:
            state = read(output / "checkpoint.json")
            state["status"] = "PREPARING"
            save(output / "checkpoint.json", state)
            continue_batch(output_path(args.continue_from), output)
            state = read(output / "checkpoint.json")
            state["status"] = "PREPARED"
            save(output / "checkpoint.json", state)
    except Exception as error:
        save(output / "checkpoint.json", {"status": "STOPPED", "phase": "prepare",
             "reason": f"{type(error).__name__}: {error}"})
        raise
    print(f"PREPARED (not launched): {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"BATCH_STOP: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
