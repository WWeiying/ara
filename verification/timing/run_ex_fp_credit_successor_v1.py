#!/usr/bin/env python3
"""Frozen payload-credit successor: prepare/bind, paired VCS, manually gated global DC.

prepare never reads candidate RTL. bind must follow the default-port cleanup.
Neither command runs EDA. Only explicit systemd launches execute workers.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOC = ROOT / "verification/out/payload-credit-20261122-01/soc"
DC = Path("/home/wangwy/dc_runs/ara_payload_credit_20261122_01")
FLOW = Path("backend/syn/ara_soc/v1-dc")
RTL = (
    "hardware/deps/cva6/core/ex_stage.sv",
    "hardware/src/lane/simd_fpnew.sv",
    "hardware/src/lane/vmfpu.sv",
    "hardware/src/vlsu/qbs/qbs_fp_accumulator.sv",
)
CASES = {
    "vsaxpy_asm": None, "rv64uv-ara-vfmacc": None, "rv64uv-ara-vsetvli": None,
    "qbs_control_smoke": "QBS control smoke (enabled): PASS",
    "akv_context_smoke": "AKV context smoke: PASS",
    "qbs_akv_handoff_smoke": "QBS/AKV handoff smoke: PASS",
    "llama_qwen25_shape_decode_n32_qbs": "QBS_REAL_BENCH case=shape_decode_n32_qbs result=PASS",
}
TIMERS = {
    "task_cycles": r"(?m)^\[PERF\]\s+total_cycles\s*:\s*(\d+)",
    "projection_cycles": r"\btimed_cycles=(\d+)",
    "hw_cycles": r"\[hw-cycles\]:\s*(\d+)",
    "finish_ticks": r"\$finish at simulation time\s+(\d+)",
}
EVIDENCE = Path("/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out")
RESIDENT = {
    "resident_qk": (EVIDENCE / "resident_qk_boundary_build_20261110_01/resident_qk_boundary.elf",
                    r"(?m)^QK_BOUNDARY_DONE cases=23 successes=\d+ rejected=\d+ helper=1 pv=2 compat=1 errors=0$"),
    "resident_pv": (EVIDENCE / "resident_pv_soc_boundary_build_20261109_02/resident_pv_boundary.elf",
                    r"(?m)^PV_BOUNDARY_DONE cases=21 successes=\d+ rejected=\d+ compat=1 errors=0$"),
}
LEGACY_DEFAULTS = (("resident_fp32_i", "1'b0"), ("qbs_mul_lease_i", "1'b0"),
                   ("qbs_mul_valid_i", "1'b0"), ("qbs_mul_weight_i", "'0"),
                   ("qbs_mul_activation_i", "'0"))


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(pins):
    for path, digest in pins.items():
        require(Path(path).is_file() and sha(path) == digest, "Input drift: " + path)


def copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    require(sha(source) == sha(dest), "Copy drift: " + str(source))


def entries(text):
    sources, includes = [], []
    for line in text.splitlines():
        if not line or line.startswith(("//", "+define+")):
            continue
        if line.startswith("+incdir+"):
            includes.extend(Path(p) for p in line.split("+")[2:] if p)
        elif line.startswith("/"):
            sources.append(Path(line))
        else:
            raise ValueError("Unsupported filelist entry: " + line)
    return sources, includes


def metrics(text, marker=None, resident=False):
    require("*** SUCCESS ***" in text, "Missing program success")
    require(not re.search(r"Fatal:|Error(?:-|:)|\*\*\* FAILED \*\*\*|UVM_(?:ERROR|FATAL)\s*:\s*[1-9]", text),
            "Simulation error")
    if marker:
        require(bool(re.search(marker, text)) if resident else marker in text,
                "Missing program-specific passing signature")
    timers = {key: [int(v) for v in re.findall(pattern, text)] for key, pattern in TIMERS.items()}
    require(len(timers["finish_ticks"]) == 1, "Missing/duplicate finish timestamp")
    if resident:
        signatures = [line for line in text.splitlines()
                      if line.startswith(("QK_BOUNDARY_", "PV_BOUNDARY_"))]
        require(len(signatures) > 2, "Missing resident numerical/CSR signatures")
        return {"timers": timers, "signatures": signatures}
    return timers


def default_ports(data):
    # Fail closed before binding; this is a detector, never a source rewrite.
    return re.findall(rb"(?m)^\s*input\b[^\n;]*\b(\w+)\s*=\s*[^,\n]+", data)


def dc_bytes(rel, data):
    # The parent DC already removed exactly these five legacy vmfpu defaults.
    # Keep the identical compatibility transform, in frozen DC inputs only.
    if rel == "hardware/src/lane/vmfpu.sv":
        for port, value in LEGACY_DEFAULTS:
            old = (port + " = " + value + ",").encode()
            require(data.count(old) <= 1, "Ambiguous legacy port default")
            data = data.replace(old, (port + " ,").encode())
    require(not default_ports(data), "Unreviewed input default: " + rel)
    return data


def legacy_lines(data):
    result = []
    for port, value in LEGACY_DEFAULTS:
        lines = [line for line in data.splitlines(keepends=True)
                 if re.search(rb"^\s*input\b.*\b" + port.encode() + rb"\b", line)]
        require(len(lines) == 1 and (port + " = " + value + ",").encode() in lines[0],
                "Legacy default declaration changed: " + port)
        result.extend(lines)
    return result


def prepare(out, dc_out):
    require(not dc_out.exists(), "DC output already exists")
    out.mkdir(parents=True, exist_ok=False)
    (out / "soc").mkdir()
    prior, dc_status = read(SOC / "status.json"), read(DC / "status.json")
    require(prior["state"] == "PASS" and dc_status["state"] == "SYNTHESIS_COMPLETE",
            "Incomplete baseline")
    old_pins = read(DC / "source-pins.json")
    verify(old_pins)
    verify(dc_status["output_sha256"])
    parent = Path(prior["reference"])
    parent_pins = read(parent / "source-pins.json")
    verify(parent_pins)
    dc_parent = Path(read(DC / "manifest.json")["parent"])
    dc_recipe = read(dc_parent / "status.json")["command"]
    require(dc_recipe[dc_recipe.index("-w") + 1] == str(dc_parent / FLOW / "run"),
            "Unexpected ancestral DC command")
    dc_recipe[dc_recipe.index("-w") + 1] = str(dc_out / FLOW / "run")
    image = SOC / "simv"
    require(sha(image) == prior["image_sha256"], "Baseline image changed")
    pins = dict(old_pins)
    pins.update(parent_pins)
    for path in (SOC / "status.json", SOC / "candidate.f", SOC / "command.json",
                 DC / "status.json", DC / "manifest.json", DC / "source-pins.json", image):
        pins[str(path)] = sha(path)
    pins[str(dc_parent / "status.json")] = sha(dc_parent / "status.json")
    pins.update(dc_status["output_sha256"])
    for path in (SOC / "simv.daidir").rglob("*"):
        if path.is_file():
            pins[str(path)] = sha(path)
    text = (SOC / "candidate.f").read_text()
    sources, includes = entries(text)
    build = read(SOC / "command.json")
    dpi = [Path(x) for x in build[1:] if x.startswith("/") and x.endswith(".o")]
    require(len(dpi) == 1, "Unexpected DPI recipe")
    mapping = {}
    closure = set(sources + dpi)
    for directory in set(includes):
        require(directory.is_dir(), "Missing include directory: " + str(directory))
        closure.update(p for p in directory.rglob("*") if p.is_file())
        target = out / "soc/source" / str(directory).lstrip("/")
        target.mkdir(parents=True, exist_ok=True)
        mapping[str(directory)] = str(target)
    for source in sorted(closure):
        dest = out / "soc/source" / str(source).lstrip("/")
        copy(source, dest)
        pins[str(source)] = sha(source)
        pins[str(dest)] = sha(dest)
        mapping[str(source)] = str(dest)
    # Replace tokens in a single pass: nested include/source paths cannot cascade.
    def mapped(line):
        if line.startswith("+incdir+"):
            return "+incdir+" + "+".join(mapping[p] for p in line.split("+")[2:] if p)
        return mapping.get(line, line)
    base_f = "\n".join(mapped(line) for line in text.splitlines()) + "\n"
    (out / "soc/baseline.f").write_text(base_f)
    pins[str(out / "soc/baseline.f")] = sha(out / "soc/baseline.f")
    table = {}
    for rel in RTL:
        old_soc = [p for p in sources if str(p).endswith("/" + rel)]
        old_dc = [Path(p) for p in old_pins if p.endswith("/" + rel)]
        require(len(old_soc) == len(old_dc) == 1, "Ambiguous source: " + rel)
        table[rel] = {"soc": mapping[str(old_soc[0])], "dc": str(old_dc[0]),
                      "soc_sha256": sha(old_soc[0]), "dc_sha256": sha(old_dc[0])}
        require(dc_bytes(rel, old_soc[0].read_bytes()) == old_dc[0].read_bytes(),
                "Unexplained SoC/DC baseline source mismatch: " + rel)
        if rel == "hardware/src/lane/vmfpu.sv":
            legacy_lines(old_soc[0].read_bytes())
            table[rel]["parent_normalizer_byte_identity_proven"] = True
    dc_out.mkdir(parents=True, exist_ok=False)
    for filename in old_pins:
        source = Path(filename)
        if not source.is_relative_to(DC) or source == DC / "manifest.json":
            continue
        relative = source.relative_to(DC)
        dest = dc_out / relative
        copy(source, dest)
        if relative.parts[0] != "sources":
            dest.write_bytes(dest.read_bytes().replace(str(DC).encode(), str(dc_out).encode()))
        if not any(filename.endswith("/" + r) for r in RTL):
            pins[str(dest)] = sha(dest)
    for rel in ("reports", "outputs", "inputs/inc"):
        (dc_out / FLOW / rel).mkdir(parents=True, exist_ok=True)
    (dc_out / FLOW / "run").mkdir(parents=True, exist_ok=True)
    for line in (dc_out / "backend/flist/ara_soc_dc.f").read_text().splitlines():
        if line.startswith("+incdir+"):
            for name in line.split("+")[2:]:
                if name and Path(name).is_relative_to(dc_out / "sources"):
                    Path(name).mkdir(parents=True, exist_ok=True)
    cases = {}
    for name, marker in CASES.items():
        original = read(parent / "candidate" / name / "command.json")
        preload = [x for x in original if x.startswith("+PRELOAD=")]
        require(len(preload) == 1, "ELF recipe mismatch")
        elf = Path(preload[0].split("=", 1)[1])
        dest = out / "elf" / name
        copy(elf, dest)
        log = SOC / name / "run.log"
        expected = metrics(log.read_text(errors="replace"), marker)
        require(expected == prior["equal_cycles"][name], "Cached timing mismatch: " + name)
        pins[str(log)] = sha(log)
        pins[str(dest)] = sha(dest)
        cases[name] = {"elf": str(dest), "marker": marker, "expected": expected,
                       "args": [x for x in original[1:] if not x.startswith("+PRELOAD=")]}
    resident = {}
    for name, (elf, marker) in RESIDENT.items():
        require(elf.is_file() and elf.read_bytes()[:4] == b"\x7fELF", "Missing resident ELF: " + str(elf))
        dest = out / "elf" / name
        copy(elf, dest)
        pins[str(dest)] = sha(dest)
        resident[name] = {"elf": str(dest), "marker": marker, "pair_state": "UNEXECUTED_PAIR_REQUIRED"}
    runner = out / "worker.py"
    copy(Path(__file__), runner)
    pins[str(runner)] = sha(runner)
    build[build.index("-f") + 1] = str(out / "soc/candidate.f")
    build[build.index(str(dpi[0]))] = mapping[str(dpi[0])]
    # Versioned legacy recipes are provenance only; the frozen worker is standalone.
    for name in ("run_payload_credit_soc.py", "run_payload_credit_dc.py"):
        path = ROOT / "verification/timing" / name
        pins[str(path)] = sha(path)
    plan = {"baseline_soc": str(SOC), "baseline_dc": str(DC), "dc_out": str(dc_out),
            "baseline_image": str(image), "rtl": table, "build": build,
            "cases": cases, "resident": resident, "dc_gate": "manual + branch PASS + cast PASS",
            "baseline_dc_command": dc_recipe,
            "invariants": "Only four whitelisted RTL overlays; exact inherited filelists, defines, SDC, libraries and flow"}
    save(out / "baseline-plan.json", plan)
    pins[str(out / "baseline-plan.json")] = sha(out / "baseline-plan.json")
    save(out / "baseline-pins.json", pins)
    save(out / "status.json", {"state": "BASELINE_PREPARED_AWAITING_DEFAULT_CLEANUP_AND_BIND"})


def bind(out):
    require(read(out / "status.json")["state"] == "BASELINE_PREPARED_AWAITING_DEFAULT_CLEANUP_AND_BIND",
            "Bind requires unused baseline preparation")
    pins = read(out / "baseline-pins.json")
    verify(pins)
    plan = read(out / "baseline-plan.json")
    candidate = {rel: (ROOT / rel).read_bytes() for rel in RTL}
    normalized = {rel: dc_bytes(rel, data) for rel, data in candidate.items()}
    vmfpu = "hardware/src/lane/vmfpu.sv"
    require(legacy_lines(candidate[vmfpu]) == legacy_lines(Path(plan["rtl"][vmfpu]["soc"]).read_bytes()),
            "Candidate changed a legacy vmfpu default declaration")
    changes, skipped = {}, []
    filelist = (out / "soc/baseline.f").read_text()
    for rel, data in candidate.items():
        entry = plan["rtl"][rel]
        digest = hashlib.sha256(data).hexdigest()
        if digest == entry["soc_sha256"] == entry["dc_sha256"]:
            skipped.append(rel)
            continue
        # New RTL uses raw cleaned bytes; vmfpu retains the five pinned legacy removals.
        soc_dest = out / "soc/overlay" / rel
        dc_dest = Path(plan["dc_out"]) / Path(entry["dc"]).relative_to(DC)
        require(sha(dc_dest) == entry["dc_sha256"], "Unbound DC overlay drift")
        soc_dest.parent.mkdir(parents=True, exist_ok=True)
        soc_dest.write_bytes(data)
        dc_dest.write_bytes(normalized[rel])
        require(filelist.splitlines().count(entry["soc"]) == 1, "Overlay multiplicity")
        filelist = filelist.replace(entry["soc"], str(soc_dest))
        pins[str(soc_dest)] = digest
        pins[str(dc_dest)] = sha(dc_dest)
        changes[rel] = {"soc_old": entry["soc_sha256"], "dc_old": entry["dc_sha256"], "new": digest,
                        "dc_new": sha(dc_dest), "dc_transform": "five legacy vmfpu defaults only" if data != normalized[rel] else "identity"}
    require(changes, "No new RTL changes")
    for rel, data in candidate.items():
        require((ROOT / rel).read_bytes() == data, "Live RTL changed during bind: " + rel)
    (out / "soc/candidate.f").write_text(filelist)
    pins[str(out / "soc/candidate.f")] = sha(out / "soc/candidate.f")
    plan.update(changes=changes, skipped=skipped)
    save(out / "plan.json", plan)
    pins[str(out / "plan.json")] = sha(out / "plan.json")
    pins[str(out / "baseline-pins.json")] = sha(out / "baseline-pins.json")
    save(out / "source-pins.json", pins)
    save(out / "dc-gate.template.json", {
        "authorization": "PENDING", "candidate_sha256": {r: c["new"] for r, c in changes.items()},
        "branch": {"state": "PENDING", "receipt": "", "sha256": ""},
        "cast": {"state": "PENDING", "receipt": "", "sha256": ""},
        "scope": "User attests both independent test receipts apply to these exact candidate hashes"})
    save(out / "status.json", {"state": "PREPARED_NOT_EXECUTED", "changes": changes, "skipped": skipped})


def execute(argv, cwd, log, timeout):
    save(log.with_suffix(".command.json"), argv)
    with log.open("w") as stream:
        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    require(result.returncode == 0, "Command failed: " + str(log))
    return log.read_text(errors="replace")


def systemd_launch(out, stage, gate=None):
    require(read(out / "status.json")["state"] in
            (("PREPARED_NOT_EXECUTED",) if stage == "soc" else ("WAITING_EXTERNAL_TEST_GATES",)),
            "Wrong launch state")
    verify(read(out / "source-pins.json"))
    if stage == "dc":
        validate_gate(out, gate)
        copy(gate, out / "authorized-dc-gate.json")
    unit = "ex-fp-credit-" + out.name + "-" + stage
    argv = ["systemd-run", "--user", "--unit=" + unit, "--property=Type=exec",
            "--property=KillMode=control-group", "--property=TimeoutStopSec=60",
            "--property=WorkingDirectory=" + str(out),
            "--property=StandardOutput=append:" + str(out / (stage + ".service.log")),
            "--property=StandardError=append:" + str(out / (stage + ".service.log")),
            sys.executable, "-B", str(out / "worker.py"), stage + "-worker", str(out)]
    subprocess.run(argv, check=True)
    print(unit + ".service", flush=True)


def soc_worker(out):
    require(read(out / "status.json")["state"] == "PREPARED_NOT_EXECUTED", "SoC already consumed")
    plan = read(out / "plan.json")
    pins = read(out / "source-pins.json")
    verify(pins)
    save(out / "status.json", {"state": "REFERENCE_RESIDENT_PAIRING", "pid": os.getpid()})
    resident_reference = {}

    def run_case(name, case, image, variant, resident=False):
        directory = out / "soc" / variant / name
        directory.mkdir(parents=True, exist_ok=False)
        args = case.get("args", ["-no_save", "+NO_FSDB", "+NO_INSTR_TRACE", "+ntb_random_seed=1",
                                  "+TESTCASE=" + name])
        argv = [str(image), *args, "+PRELOAD=" + case["elf"]]
        text = execute(argv, directory, directory / "run.log", 1800 if resident else 600)
        return metrics(text, case["marker"], resident)

    # Establish compatibility with the exact old image before accepting a new-image pair.
    for name, case in plan["resident"].items():
        resident_reference[name] = run_case(name, case, plan["baseline_image"], "reference", True)
    save(out / "status.json", {"state": "BUILDING_SOC", "resident_reference": resident_reference})
    execute(plan["build"], out / "soc", out / "soc/build.log", 1800)
    image = out / "soc/simv"
    require(image.is_file(), "No compiled candidate")
    measured = {}
    jobs = [(name, case, False) for name, case in plan["cases"].items()]
    jobs += [(name, case, True) for name, case in plan["resident"].items()]
    save(out / "status.json", {"state": "RUNNING_SOC", "image_sha256": sha(image)})
    # Bounded batches stop further dispatch on a failure; at most three own simulators.
    for start in range(0, len(jobs), 3):
        batch = jobs[start:start + 3]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [(name, case, resident,
                        pool.submit(run_case, name, case, image, "candidate", resident))
                       for name, case, resident in batch]
            for name, case, resident, future in futures:
                actual = future.result()
                expected = resident_reference[name] if resident else case["expected"]
                require(actual == expected, "Signature/cycle mismatch: " + name)
                measured[name] = actual
        verify(pins)
    report = {"state": "PASS", "candidate_sha256": {r: c["new"] for r, c in plan["changes"].items()},
              "image_sha256": sha(image), "equal_cycles_and_signatures": measured,
              "resident_reference": resident_reference, "baseline_image_sha256": sha(plan["baseline_image"])}
    save(out / "soc-pass.json", report)
    save(out / "status.json", {"state": "WAITING_EXTERNAL_TEST_GATES", "soc": "PASS",
                               "dc_launched": False, "soc_pass_sha256": sha(out / "soc-pass.json")})


def validate_gate(out, gate):
    require(gate is not None, "Manual branch/cast gate required")
    g = read(gate)
    report = read(out / "soc-pass.json")
    state = read(out / "status.json")
    require(state["state"] == "WAITING_EXTERNAL_TEST_GATES" and
            state["soc_pass_sha256"] == sha(out / "soc-pass.json") and report["state"] == "PASS",
            "No sealed SoC/Resident PASS")
    require(g["authorization"] == "LAUNCH_GLOBAL_DC" and
            g["candidate_sha256"] == report["candidate_sha256"], "Authorization/candidate mismatch")
    for name in ("branch", "cast"):
        proof = g[name]
        require(proof["state"] == "PASS" and Path(proof["receipt"]).is_file() and
                sha(proof["receipt"]) == proof["sha256"], "External receipt mismatch: " + name)
        receipt = read(proof["receipt"])
        require(receipt.get("state", receipt.get("status")) == "PASS", "External test not PASS: " + name)
    return g


def dc_worker(out):
    gate = out / "authorized-dc-gate.json"
    validated = validate_gate(out, gate)
    pins = read(out / "source-pins.json")
    pins[str(gate)] = sha(gate)
    pins[str(out / "soc-pass.json")] = sha(out / "soc-pass.json")
    pins.update({p["receipt"]: p["sha256"] for p in (validated["branch"], validated["cast"])})
    verify(pins)
    plan = read(out / "plan.json")
    dc_out = Path(plan["dc_out"])
    for rel in plan["changes"]:
        soc_data = (out / "soc/overlay" / rel).read_bytes()
        dc_file = dc_out / Path(plan["rtl"][rel]["dc"]).relative_to(DC)
        require(dc_bytes(rel, soc_data) == dc_file.read_bytes(), "VCS/DC transformation mismatch: " + rel)
    save(dc_out / "source-pins.json", pins)
    save(dc_out / "manifest.json", {"parent": str(DC), "paired_soc": str(out),
                                   "changes": plan["changes"], "invariants": plan["invariants"]})
    save(out / "status.json", {"state": "RUNNING_GLOBAL_DC", "pid": os.getpid()})
    text = execute(plan["baseline_dc_command"], out, dc_out / "console.log", 86400)
    require("DC_FLOW_COMPLETE" in text and not re.search(r"(?m)^(?:Error:|Fatal:)|DC_FLOW_ERROR_COUNT=[1-9]", text),
            "Global DC did not complete cleanly")
    artifacts = [dc_out / FLOW / "outputs" / ("ara_soc_dc." + ext) for ext in ("ddc", "v", "sdc")]
    require(all(p.is_file() and p.stat().st_size for p in artifacts), "Missing mapped output")
    verify(pins)
    result = {"state": "SYNTHESIS_COMPLETE", "output_sha256": {str(p): sha(p) for p in artifacts},
              "timing_signoff": False, "paired_soc": str(out)}
    save(dc_out / "status.json", result)
    save(out / "status.json", result)


def self_test():
    class HostTests(unittest.TestCase):
        def test_metrics(self):
            good = "*** SUCCESS ***\nPV_BOUNDARY_BEGIN x\nPV_BOUNDARY_DATA bits=0000\nPV_BOUNDARY_DONE cases=21 successes=1 rejected=2 compat=1 errors=0\n$finish at simulation time 42\n"
            result = metrics(good, RESIDENT["resident_pv"][1], True)
            self.assertEqual(result["timers"]["finish_ticks"], [42])
            for bad in (good.replace("errors=0", "errors=1"), good + "Fatal: broken\n",
                        good.replace("*** SUCCESS ***", ""), good.replace("$finish", "missing")):
                with self.assertRaises(ValueError):
                    metrics(bad, RESIDENT["resident_pv"][1], True)

        def test_defaults(self):
            self.assertTrue(default_ports(b"input logic mode_i = 1'b0,\n"))
            self.assertFalse(default_ports(b"input logic mode_i,\nassign x = y;"))
            self.assertEqual(dc_bytes("hardware/src/lane/vmfpu.sv",
                                      b"input logic qbs_mul_valid_i = 1'b0,\n"),
                             b"input logic qbs_mul_valid_i ,\n")
            with self.assertRaises(ValueError):
                dc_bytes("hardware/src/lane/simd_fpnew.sv", b"input logic x_i = 1'b0,\n")

        def test_filelist(self):
            self.assertEqual(entries("+define+X=1\n+incdir+/a+/b\n/c.sv\n"),
                             ([Path("/c.sv")], [Path("/a"), Path("/b")]))
            with self.assertRaises(ValueError):
                entries("-f live.f")

        def test_drift(self):
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "pin"
                p.write_text("sealed")
                pins = {str(p): sha(p)}
                verify(pins)
                p.write_text("mutated")
                with self.assertRaises(ValueError):
                    verify(pins)

        def test_manual_gate(self):
            with tempfile.TemporaryDirectory() as d:
                o = Path(d)
                save(o / "soc-pass.json", {"state": "PASS", "candidate_sha256": {"rtl": "sealed"}})
                save(o / "status.json", {"state": "WAITING_EXTERNAL_TEST_GATES",
                                         "soc_pass_sha256": sha(o / "soc-pass.json")})
                save(o / "test.json", {"state": "PASS"})
                proof = {"state": "PASS", "receipt": str(o / "test.json"), "sha256": sha(o / "test.json")}
                gate = {"authorization": "LAUNCH_GLOBAL_DC", "candidate_sha256": {"rtl": "sealed"},
                        "branch": proof, "cast": dict(proof)}
                save(o / "gate.json", gate)
                validate_gate(o, o / "gate.json")
                gate["candidate_sha256"] = {"rtl": "different"}
                save(o / "gate.json", gate)
                with self.assertRaises(ValueError):
                    validate_gate(o, o / "gate.json")
                gate["candidate_sha256"] = {"rtl": "sealed"}
                gate["cast"]["state"] = "PENDING"
                save(o / "gate.json", gate)
                with self.assertRaises(ValueError):
                    validate_gate(o, o / "gate.json")
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(HostTests))
    require(result.wasSuccessful(), "Host tests failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "bind", "launch-soc", "launch-dc",
                                            "soc-worker", "dc-worker", "self-test"))
    parser.add_argument("out", nargs="?", type=Path)
    parser.add_argument("--dc-out", type=Path)
    parser.add_argument("--gate", type=Path)
    args = parser.parse_args()
    if args.action == "self-test":
        self_test()
        return
    require(args.out is not None, "Output path required")
    out = args.out.resolve()
    if args.action == "prepare":
        require(args.dc_out is not None, "Fresh --dc-out required")
        prepare(out, args.dc_out.resolve())
    elif args.action == "bind":
        with (out / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            bind(out)
    elif args.action.startswith("launch-"):
        # Do not hold worker.lock while systemd starts the direct worker.
        # The unique unit name rejects duplicate launches; the worker owns the lock.
        systemd_launch(out, args.action.removeprefix("launch-"), args.gate)
    else:
        require(Path("/proc/self/cgroup").read_text().find(".service") >= 0,
                "Workers require direct systemd service ownership")
        with (out / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                (soc_worker if args.action == "soc-worker" else dc_worker)(out)
            except Exception as error:
                save(out / "status.json", {"state": "FAIL", "stage": args.action, "error": str(error)})
                raise
    print(json.dumps(read(out / "status.json")), flush=True)


if __name__ == "__main__":
    main()
