#!/usr/bin/env python3
"""Rerun a frozen real-model RVV/QBS/AKV pair matrix on one VCS image."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "verification/uvm/run_real_dut_case.sh"
QBS_CHECK = ROOT / "verification/qbs/check_real_dut_evidence.py"
PAIR_CHECK = ROOT / "verification/qbs/audit_paired_campaign.py"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def source_path(value, source_root):
    path = Path(value)
    return (path if path.is_absolute() else source_root / path).resolve(strict=True)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def make_plan(source, simv, output, source_root=ROOT):
    spec = json.loads(source.read_text())
    if spec.get("schema_version") != 1 or len(spec.get("qbs_pairs", [])) != 10:
        raise ValueError("expected the frozen ten-pair QBS manifest")
    if not (simv.is_file() and (simv.parent / "simv.daidir").is_dir() and
            (simv.parent / "simulator.conf").is_file()):
        raise ValueError("VCS image is incomplete")
    simulator_conf = simv.parent / "simulator.conf"
    settings = dict(line.split("=", 1) for line in simulator_conf.read_text().splitlines()
                    if "=" in line)
    if settings.get("qbs") != "1" or settings.get("akv_v2") != "1":
        raise ValueError("VCS image must enable both QBS and AKV-v2")
    cases = []
    new_manifest = {"schema_version": 1, "qbs_pairs": [], "akv_pair": {}}
    seen = set()
    for pair in spec["qbs_pairs"]:
        name = pair["format"] + ("_" + pair["variant"] if pair.get("variant") else "")
        if name in seen or "/" in name or ".." in name:
            raise ValueError(f"duplicate or unsafe pair name: {name}")
        seen.add(name)
        record = dict(pair)
        for mode in ("rvv", "qbs"):
            old_run = source_path(pair[f"{mode}_run"], source_root)
            app = source_path(pair[f"{mode}_app"], source_root)
            elf = (old_run / "work/input.elf").resolve(strict=True)
            (app / "case.json").resolve(strict=True)
            destination = output / name / mode
            inputs = [app / "case.json", *(app / "generated" / item for item in
                       ("source_weight.bin", "activation_f32.bin", "golden_f32.bin"))]
            cases.append({"name": name, "mode": mode, "elf": str(elf),
                          "elf_sha256": digest(elf), "app": str(app),
                          "app_inputs_sha256": {str(path): digest(path) for path in inputs},
                          "output": str(destination), "testcase": app.name})
            record[f"{mode}_run"] = str(destination)
        new_manifest["qbs_pairs"].append(record)
    akv = dict(spec["akv_pair"])
    for mode in ("rvv", "akv"):
        elf = source_path(akv[f"{mode}_elf"], source_root)
        assembly = source_path(akv[f"{mode}_asm"], source_root)
        destination = output / "akv_v2" / mode
        cases.append({"name": "akv_v2", "mode": mode, "elf": str(elf),
                      "elf_sha256": digest(elf), "assembly": str(assembly),
                      "assembly_sha256": digest(assembly),
                      "output": str(destination),
                      "testcase": f"attention_{mode}"})
        akv[f"{mode}_run"] = str(destination)
    new_manifest["akv_pair"] = akv
    return {"status": "PLANNED", "source_manifest": str(source),
            "source_root": str(source_root.resolve()),
            "source_manifest_sha256": digest(source), "simv": str(simv),
            "simv_sha256": digest(simv), "runner_sha256": digest(RUNNER),
            "simulator_conf_sha256": digest(simulator_conf),
            "cases": cases, "output_manifest": new_manifest}


def resume_plan(source, simv, output, source_root=ROOT):
    saved = json.loads((output / "plan.json").read_text())
    fresh = make_plan(source, simv, output, source_root)
    for key in ("source_root", "source_manifest_sha256", "simv", "simv_sha256", "runner_sha256",
                "simulator_conf_sha256"):
        if saved.get(key) != fresh[key]:
            raise ValueError(f"resume input differs: {key}")
    stable = ("name", "mode", "elf", "elf_sha256", "app", "app_inputs_sha256",
              "assembly", "assembly_sha256", "testcase")
    if len(saved.get("cases", [])) != len(fresh["cases"]):
        raise ValueError("resume case count differs")
    for old, new in zip(saved["cases"], fresh["cases"]):
        if any(old.get(key) != new.get(key) for key in stable):
            raise ValueError(f"resume case input differs: {new['name']}/{new['mode']}")
    return saved


def _retry_destination(case, output, plan, index):
    destination = Path(case["output"])
    if not destination.exists():
        return destination
    case.setdefault("attempts", []).append({
        "output": str(destination), "status": case.get("status"),
        "returncode": case.get("returncode"),
    })
    attempt = 1
    while True:
        retry = destination.with_name(f"{destination.name}.retry-{attempt}")
        if not retry.exists():
            break
        attempt += 1
    case["output"] = str(retry)
    record = (plan["output_manifest"]["qbs_pairs"][index // 2]
              if index < 20 else plan["output_manifest"]["akv_pair"])
    record[f"{case['mode']}_run"] = str(retry)
    return retry


def inputs_match(plan, case, simv):
    return not (digest(simv) != plan["simv_sha256"] or
                digest(simv.parent / "simulator.conf") != plan["simulator_conf_sha256"] or
                digest(RUNNER) != plan["runner_sha256"] or
                digest(Path(case["elf"])) != case["elf_sha256"] or
                ("assembly" in case and digest(Path(case["assembly"])) !=
                 case["assembly_sha256"]) or
                any(digest(Path(path)) != expected for path, expected in
                    case.get("app_inputs_sha256", {}).items()))


def run_case(case, command, destination, log_path, timeout_seconds):
    with log_path.open("a") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log,
                                stderr=subprocess.STDOUT, check=False,
                                env={**os.environ,
                                     "ARA_VCS_TIMEOUT_SECONDS": str(timeout_seconds)})
        outcome = {"returncode": result.returncode}
        if result.returncode == 0 and case["mode"] == "qbs":
            evidence = [sys.executable, str(QBS_CHECK), "--run", str(destination),
                        "--case-json", str(Path(case["app"]) / "case.json"),
                        "--output", str(destination / "qbs_evidence.json")]
            result = subprocess.run(evidence, cwd=ROOT, stdout=log,
                                    stderr=subprocess.STDOUT, check=False)
            outcome["evidence_returncode"] = result.returncode
        outcome["status"] = "PASS" if result.returncode == 0 else "FAIL"
        if result.returncode:
            stage = "QBS evidence" if "evidence_returncode" in outcome else "runner"
            outcome["reason"] = f"{stage} exited with status {result.returncode}"
        return outcome


def run(plan, output, simv, timeout_seconds, jobs=1):
    if jobs <= 0:
        raise ValueError("jobs must be positive")
    plan["status"] = "RUNNING"
    write_json(output / "plan.json", plan)
    pending = ((index, case) for index, case in enumerate(plan["cases"])
               if case.get("status") != "PASS")
    failed = False
    active = {}
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        while True:
            while not failed and len(active) < jobs:
                try:
                    index, case = next(pending)
                except StopIteration:
                    break
                try:
                    valid = inputs_match(plan, case, simv)
                except OSError as error:
                    valid = False
                    case["reason"] = f"frozen input unavailable: {error}"
                if not valid:
                    case["status"] = "FAIL"
                    case.setdefault("reason", "frozen input or runner hash changed")
                    failed = True
                    write_json(output / "plan.json", plan)
                    break
                destination = _retry_destination(case, output, plan, index)
                command = [str(RUNNER), str(simv), case["elf"], case["testcase"],
                           str(destination)]
                log_path = (output / "runner.log" if jobs == 1 else
                            output / "logs" / f"{index:02d}-{destination.name}.log")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                case.pop("reason", None)
                case.pop("returncode", None)
                case.pop("evidence_returncode", None)
                case["command"] = command
                case["timeout_seconds"] = timeout_seconds
                case["log"] = str(log_path)
                case["status"] = "RUNNING"
                write_json(output / "plan.json", plan)
                future = executor.submit(run_case, case, command, destination,
                                         log_path, timeout_seconds)
                active[future] = case
            if not active:
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                case = active.pop(future)
                try:
                    case.update(future.result())
                except Exception as error:
                    case["status"] = "FAIL"
                    case["reason"] = f"runner invocation failed: {error}"
                failed |= case["status"] != "PASS"
                write_json(output / "plan.json", plan)
    if failed:
        plan["status"] = "FAIL"
        write_json(output / "plan.json", plan)
        return 1
    manifest = output / "paired_manifest.json"
    write_json(manifest, plan["output_manifest"])
    with (output / "runner.log").open("a") as log:
        result = subprocess.run([sys.executable, str(PAIR_CHECK), "--manifest",
                                 str(manifest), "--output", str(output / "audit.json")],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                check=False)
    plan["status"] = "PASS" if result.returncode == 0 else "FAIL"
    plan["audit_returncode"] = result.returncode
    write_json(output / "plan.json", plan)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT,
                        help="root for relative frozen inputs in the source manifest")
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--jobs", type=int, default=1,
                        help="maximum concurrent case runs (default: 1)")
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or args.jobs <= 0 or (args.resume and args.plan_only):
        parser.error("timeout and jobs must be positive; --resume and --plan-only are exclusive")
    source = args.source_manifest.resolve(strict=True)
    source_root = args.source_root.resolve(strict=True)
    simv = args.simv.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() and not args.resume:
        parser.error(f"output already exists: {output}")
    if args.resume:
        if not (output / "plan.json").is_file():
            parser.error(f"no resumable plan: {output}")
        plan = resume_plan(source, simv, output, source_root)
    else:
        plan = make_plan(source, simv, output, source_root)
        output.mkdir(parents=True)
        write_json(output / "plan.json", plan)
    if args.plan_only:
        print(f"planned {len(plan['cases'])} frozen real-model runs in {output}")
        return 0
    return run(plan, output, simv, args.timeout_seconds, args.jobs)


if __name__ == "__main__":
    raise SystemExit(main())
