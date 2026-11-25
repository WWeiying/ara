#!/usr/bin/env python3
"""Prepare, explicitly launch, and check one three-case exact-object VCS run."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

OUT = Path("/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out")
APPROVED = OUT / "resident_deployment_compute_vcs_cost_20261113_01"
APPROVED_PLAN_SHA = "60b59a05e6f6ccdf80c9824032b144071ab4a928390338f6b037ff8cbf1d983c"
OPCODES = {"info": "0005455b", "full": "00b5605b", "qk": "0605705b", "pv": "0485705b", "refill": "02a0605b", "release": "0000505b"}
PER_CASE = [OPCODES["info"]] * 5 + [OPCODES[k] for k in ("full", "qk", "pv", "refill", "qk", "pv", "release")]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, "Input drift: " + str(path))


def unit(out):
    return "resident-views-" + out.name + ".service"


def launch_command(out, review):
    return ["systemd-run", "--user", "--unit=" + unit(out), "--property=Type=exec", "--property=KillMode=control-group",
            "--property=RuntimeMaxSec=2400", "--property=TimeoutStopSec=20",
            "--property=StandardOutput=append:" + str(out / "service.stdout.log"),
            "--property=StandardError=append:" + str(out / "service.stderr.log"), sys.executable, "-B", "-u",
            str(out / "inputs/run.py"), "execute", "--output", str(out), "--review-sha256", review]


def prepare(out, software, approved_module_sha):
    require(out.parent == software.parent == OUT and not out.exists(), "Use fresh direct signoff/out output")
    require(out.name.startswith("resident_view_vcs_"), "Expected resident_view_vcs_ output")
    require(sha(APPROVED / "plan.json") == APPROVED_PLAN_SHA, "Approved plan drift")
    baseline, approved_pins = read(APPROVED / "plan.json"), read(APPROVED / "source-pins.json")
    require(approved_pins[str(APPROVED / "plan.json")] == APPROVED_PLAN_SHA, "Plan not in original pins")
    image = Path(baseline["image"])
    require(image.parent == OUT, "Unexpected approved image")
    require(sha(image / "build.json") == approved_pins[str(image / "build.json")], "Image receipt drift")
    hw, build = read(image / "build.json"), read(software / "build.json")
    require(hw["post_pins_match"] and hw["configuration"]["resident_capability"] == 0x0000040000040301,
            "Approved image capability mismatch")
    require(build["state"] == "REAL_KERNEL_VIEWS_BUILT_NOT_EXECUTED", "Unexpected software receipt")
    require(build["supervisor_sv39_high_va"] and len(build["cases"]) == 3, "Expected three Sv39 cases")
    require(build["module_sha256"] == approved_module_sha, "Explicit final module hash required")
    require(sha(software / "source-pins.json") == build["source_pins_sha256"], "Software inventory drift")
    require(sha(build["elf"]) == build["elf_sha256"], "ELF drift")
    verify(read(software / "source-pins.json"))
    verify(hw["image_pins"])
    expected_image = {p: h for p, h in hw["image_pins"].items() if p == hw["simv"] or p.endswith(".so")}
    require(expected_image == baseline["expected_sim_image"] and baseline["command"][0] == hw["simv"], "Approved binary identity mismatch")
    out.mkdir()
    inputs = out / "inputs"
    inputs.mkdir()
    pins = dict(hw["image_pins"])
    for path in (APPROVED / "plan.json", APPROVED / "source-pins.json", image / "build.json",
                 software / "build.json", software / "source-pins.json", Path(build["elf"]), Path(__file__).resolve()):
        pins[str(path)] = sha(path)
    shutil.copyfile(__file__, inputs / "run.py")
    pins[str(inputs / "run.py")] = sha(inputs / "run.py")
    protocol_root = APPROVED / "inputs/verification/ara_verify"
    for source in sorted(protocol_root.rglob("*.py")):
        require(sha(source) == approved_pins[str(source)], "Approved protocol source drift")
        destination = inputs / "verification/ara_verify" / source.relative_to(protocol_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        pins[str(source)] = sha(source)
        pins[str(destination)] = sha(destination)
    require((inputs / "verification/ara_verify/uvm_dut.py").exists(), "Missing protocol checker")
    environment = dict(baseline["environment"], PYTHONPATH=str(inputs / "verification"))
    work = out / "work"
    command = [hw["simv"], "-no_save", "-l", str(work / "run.vcs.log"), "+PRELOAD=" + build["elf"],
               "+TESTCASE=resident_kernel_compute", "+NO_FSDB", "+NO_INSTR_TRACE",
               "+VECTOR_TRACE=" + str(work / "vector.csv"), "+ARA_CONTRACT_TRACE_LIMIT=2000000", "+ARA_UVM_TRACE_LIMIT=2000000"]
    save(out / "plan.json", dict(command=command, environment=environment, software=str(software), image=str(image),
                                expected_sim_image=expected_image, approved_module_sha256=approved_module_sha,
                                inherited_plan=str(APPROVED / "plan.json"), inherited_plan_sha256=APPROVED_PLAN_SHA,
                                simulator_timeout_seconds=1800, protocol_timeout_seconds=300))
    pins[str(out / "plan.json")] = sha(out / "plan.json")
    verify(pins)
    save(out / "source-pins.json", pins)
    launch = launch_command(out, sha(out / "source-pins.json"))
    save(out / "launch-command.json", launch)
    return dict(state="PREPARED_NOT_LAUNCHED", output=str(out), review_sha256=sha(out / "source-pins.json"), launch_command=launch)


def check_text(text, build):
    require(text.count("Core Test *** SUCCESS ***") == 1, "Core success count")
    require(text.count("RESIDENT_VIEWS_PASS") == 1 and "RESIDENT_VIEWS_FAIL" not in text and "RESIDENT_VIEWS_TRAP" not in text,
            "Harness failed or trapped")
    results = re.findall(r"^RESIDENT_VIEWS_RESULT case=([0-9a-f]{8}) status=([0-9a-f]{8}) flags=([0-9a-f]{8}) "
                         r"fcsr=([0-9a-f]{8}) started=([0-9a-f]{8}) used=([0-9a-f]{8}) changed=([0-9a-f]{8}) errors=([0-9a-f]{8})$", text, re.M)
    expected = [(c["index"], 0, c["expected_flags"], c["expected_flags"], 1, 1, c["changed_halfwords"], 0) for c in build["cases"]]
    require([tuple(int(x, 16) for x in row) for row in results] == expected, "Result/status/fflags/guard/mutation mismatch")
    outputs = re.findall(r"^RESIDENT_VIEWS_OUTPUT case=([0-9a-f]{8}) index=([0-9a-f]{8}) bits=([0-9a-f]{8})$", text, re.M)
    expected_outputs = [(c["index"], i, bits) for c in build["cases"] for i, bits in enumerate(c["expected_outputs"])]
    require(len(expected_outputs) == 768 and [tuple(int(x, 16) for x in row) for row in outputs] == expected_outputs,
            "Output bits/order/count mismatch")
    addresses = re.findall(r"^RESIDENT_VIEWS_ADDRESS case=([0-9a-f]{8}) query=([0-9a-f]{16}) key=([0-9a-f]{16}) "
                           r"value=([0-9a-f]{16}) mask=([0-9a-f]{16}) output=([0-9a-f]{16}) scratch=([0-9a-f]{16}) "
                           r"kstride=([0-9a-f]{8}) vstride=([0-9a-f]{8})$", text, re.M)
    addresses = [tuple(int(x, 16) for x in row) for row in addresses]
    require(len(addresses) == 3 and [row[0] for row in addresses] == [0, 1, 2], "Address record count/order")
    for row, case in zip(addresses, build["cases"]):
        require(all(0xffffffc000000000 <= p < 0xffffffc040000000 for p in row[1:7]), "Not Sv39 high kernel aliases")
        require(row[7:] == (case["key_token_stride"], case["value_token_stride"]), "Stride metadata mismatch")
    require(addresses[1][1:] == addresses[2][1:], "Live update must keep all addresses/strides identical")
    require(addresses[0][2:4] != addresses[1][2:4], "Packed and strided storage must differ")
    lines = text.splitlines()
    active, observed, per_case = None, [], [[] for _ in range(3)]
    for line in lines:
        begin = re.fullmatch(r"RESIDENT_VIEWS_ADDRESS case=([0-9a-f]{8}) .*", line)
        if begin:
            require(active is None, "Overlapping calls")
            active = int(begin[1], 16)
        command = re.match(r"^\[ARA_CONTRACT_TRACE\].* req=1/1 fire=1 .*insn=([0-9a-f]{8}) ", line)
        if command and int(command[1], 16) & 0x7f in (0x0b, 0x2b, 0x5b, 0x7b):
            require(command[1] in OPCODES.values(), "Unexpected custom instruction: " + command[1])
            require(active is not None, "Custom command outside a call")
            observed.append(command[1])
            per_case[active].append(command[1])
        end = re.match(r"^RESIDENT_VIEWS_RESULT case=([0-9a-f]{8}) ", line)
        if end:
            require(active == int(end[1], 16), "Call end/order mismatch")
            active = None
    require(active is None and per_case == [PER_CASE] * 3 and observed == PER_CASE * 3, "Exact per-call command count/order mismatch")
    return dict(outputs_bit_exact=768, fflags=[c["expected_flags"] for c in build["cases"]],
                custom_command_counts={name: Counter(observed)[opcode] for name, opcode in OPCODES.items()},
                same_storage_update_checked=True, nan_padding_checked=True, high_va_addresses=addresses)


def execute(out, review):
    require(Path(__file__).resolve() == out / "inputs/run.py", "Execute only frozen runner")
    require(sha(out / "source-pins.json") == review, "Review hash required")
    owner = subprocess.check_output(["systemctl", "--user", "show", unit(out), "-p", "MainPID", "--value"], text=True).strip()
    require(owner == str(os.getpid()), "Worker must be directly owned by systemd service")
    save(out / "attempt.json", dict(pid=os.getpid(), cgroup=Path("/proc/self/cgroup").read_text()))
    plan, pins = read(out / "plan.json"), read(out / "source-pins.json")
    work = out / "work"
    work.mkdir()
    report = dict(state="FAIL", kernel_booted=False, linux_module_executed=False, board_executed=False,
                  automatic_retry=False, supervisor_sv39_high_va=True)
    commands = []

    def run(name, argv, seconds):
        argv = list(map(str, argv))
        with (work / (name + ".log")).open("x") as log:
            child = subprocess.Popen(argv, cwd=work, env=plan["environment"], stdout=log, stderr=subprocess.STDOUT)
            save(work / (name + ".process.json"), dict(pid=child.pid, command=argv))
            try:
                status = child.wait(timeout=seconds)
            except BaseException:
                child.terminate()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                raise
        commands.append(dict(name=name, returncode=status))
        require(status == 0, "Command failed: " + name + ": " + str(status))

    try:
        verify(pins)
        software = Path(plan["software"])
        build = read(software / "build.json")
        verify(read(software / "source-pins.json"))
        require(build["module_sha256"] == plan["approved_module_sha256"], "Final module approval mismatch")
        run("console", plan["command"], plan["simulator_timeout_seconds"])
        checked = check_text((work / "run.vcs.log").read_text(), build)
        run("protocol", [sys.executable, "-B", "-m", "ara_verify.uvm_dut", "--require-events", "--require-backend",
                         "--require-axi", "--require-axi-write", "--vector-trace", work / "vector.csv",
                         "--log", work / "run.vcs.log", "--simv", plan["command"][0], "--elf", build["elf"],
                         "--output", work / "protocol.json"], plan["protocol_timeout_seconds"])
        protocol = read(work / "protocol.json")
        require(protocol["status"] == "PASS" and not protocol["issues"], "Protocol checker failed")
        require(protocol["elf_sha256"] == build["elf_sha256"] and protocol["log_sha256"] == sha(work / "run.vcs.log"), "Protocol input hash mismatch")
        require(protocol["sim_image_sha256"] == plan["expected_sim_image"], "Protocol image hash mismatch")
        require(all(protocol["contract_counts"][key] == 0 for key in ("exceptions", "outstanding", "protocol_errors")), "Protocol contract violation")
        verify(pins)
        verify(read(software / "source-pins.json"))
        report.update(checked, state="REAL_KERNEL_VIEWS_RTL_CHECKED", core_sha256=build["core_sha256"],
                      module_sha256=build["module_sha256"], elf_sha256=build["elf_sha256"], post_pins_match=True,
                      protocol_sha256=sha(work / "protocol.json"), contract_counts=protocol["contract_counts"])
    except BaseException as error:
        report["error"] = repr(error)
    save(out / "commands.json", commands)
    save(out / "result.json", report)
    print(json.dumps(report), flush=True)
    return int(report["state"] == "FAIL")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "launch", "execute"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--software", type=Path)
    parser.add_argument("--approved-module-sha256")
    parser.add_argument("--review-sha256")
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith("resident_view_vcs_"), "Unexpected run output")
    if args.action == "prepare":
        require(args.software is not None and args.approved_module_sha256 is not None, "Software and confirmed final module hash required")
        print(json.dumps(prepare(out, args.software.resolve(), args.approved_module_sha256)))
    elif args.action == "launch":
        require(sha(out / "source-pins.json") == args.review_sha256, "Review hash required")
        verify(read(out / "source-pins.json"))
        require(not (out / "attempt.json").exists() and not (out / "work").exists(), "No retries in an existing output")
        subprocess.run(launch_command(out, args.review_sha256), check=True)
    else:
        return execute(out, args.review_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
