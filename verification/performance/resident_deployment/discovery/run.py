#!/usr/bin/env python3
"""Bounded host/VCS discovery checks, using frozen inputs in signoff OUT only."""

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SIGNOFF = ROOT.parent / "ara_dsa_signoff_integration"
OUT = SIGNOFF / "verification/out"
SCOPED = (
    "config/akv_abi.json", "scripts/gen_akv_abi.py", "hardware/include/akv_pkg.sv",
    "apps/common/akv_abi.h", "software/akv/include/akv/akv_abi.h",
    "software/akv/include/akv/akv.h", "software/akv/src/akv_runtime.c",
    "software/akv/tests/akv_resident_capability_test.c", "software/akv/Makefile",
)
AUDIT = (
    "AGENTS.md", "hardware/include/ara_pkg.sv", "hardware/include/vlsu_shared_reader.svh",
    "hardware/src/ara.sv", "hardware/src/ara_dispatcher.sv",
    "hardware/src/cva6_accel_first_pass_decoder.sv", "hardware/src/vlsu/vlsu.sv",
    "hardware/src/lane/lane.sv", "hardware/src/lane/vector_fus_stage.sv",
    "hardware/src/lane/vmfpu.sv",
)
DEFINES = ("ARA_AKV_ENABLE", "ARA_AKV_V2_ENABLE",
           "ARA_AKV_RESIDENT_PV_ENABLE", "ARA_AKV_RESIDENT_QK_ENABLE")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def extract(text, pattern):
    matches = re.findall(pattern, text, re.S)
    require(len(matches) == 1, "Ambiguous/missing source gate: " + pattern)
    return matches[0]


def extract_gates(inputs, work):
    dispatcher = (inputs / "hardware/src/ara_dispatcher.sv").read_text()
    names = ("akv_implementation_supported", "akv_v2_implementation_supported",
             "akv_resident_pv_implementation_supported", "akv_resident_qk_implementation_supported")
    gates = [extract(dispatcher, rf"\b({name}\s*=\s*[^;]+;)") for name in names]
    for stem, path, prefix in (
        ("EnableResident", "hardware/src/lane/lane.sv", "localparam bit"),
        ("Resident", "hardware/src/vlsu/vlsu.sv", "localparam bit"),
    ):
        text = (inputs / path).read_text()
        for kind in ("Pv", "Qk"):
            name = stem + kind + ("Supported" if stem == "Resident" else "")
            gates.append(extract(text, rf"{prefix}\s+({name}\s*=\s*[^;]+;)"))
    (work / "discovery_dispatcher_gates.svh").write_text("\n".join(gates) + "\n")
    ara = (inputs / "hardware/include/ara_pkg.sv").read_text()
    enum = extract(ara, r"(typedef enum logic \[5:0\] \{[^}]+\} fpu_support_e;)")
    functions = [extract(ara, rf"(function automatic logic {name}\(.*?endfunction : {name})")
                 for name in ("RVVH", "RVVF")]
    (work / "discovery_fpu.svh").write_text(enum + "\n" + "\n".join(functions) + "\n")
    top = (inputs / "hardware/src/ara.sv").read_text()
    require(len(re.findall(r"\.FPUSupport\s*\(FPUSupport\s*\)", top)) == 2,
            "Reaudit top FPUSupport forwarding")
    fus = (inputs / "hardware/src/lane/vector_fus_stage.sv").read_text()
    require(".EnableResidentPv(EnableResidentPv && NrLanes == 4 && VLEN == 1024 && RVVH(FPUSupport))" in fus,
            "Reaudit FUS Resident gate")
    vmfpu = (inputs / "hardware/src/lane/vmfpu.sv").read_text()
    require("if (EnableResidentPv && RVVH(FPUSupport)) begin : gen_resident_pv" in vmfpu,
            "Reaudit VMFPU Resident gate")
    require("qbs_akv_shared_reader #(" in
            (inputs / "hardware/include/vlsu_shared_reader.svh").read_text(),
            "Reaudit shared reader instantiation")
    require(re.search(r"akv_resident_pv_capability_word\(\s*64'\(acc_req_i.rs1\),\s*"
                      r"akv_resident_pv_implementation_supported\)", dispatcher),
            "Dispatcher is not passing actual PV support")
    require(re.search(r"akv_resident_qk_capability_word\(\s*64'\(acc_req_i.rs1\),\s*"
                      r"akv_resident_qk_implementation_supported\)", dispatcher),
            "Dispatcher is not passing actual QK support")
    return {"extracted_gates": gates, "top_fpu_forwarding": True,
            "scope": "static gate audit and isolated expressions, not full-SoC execution"}


def check_generator(inputs):
    spec = importlib.util.spec_from_file_location("frozen_generator", inputs / "scripts/gen_akv_abi.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    original = generator.load_spec()
    generator.validate_spec(original)
    for key in original["resident_capability"]:
        for value in (original["resident_capability"][key] + 1, True):
            changed = json.loads(json.dumps(original))
            changed["resident_capability"][key] = value
            try:
                generator.validate_spec(changed)
            except ValueError:
                continue
            raise RuntimeError("Generator accepted encoding drift: " + key)
    require(original["resident_pv_profile"]["supported"] is False and
            original["resident_qk_profile"]["supported"] is False,
            "Reference compile-time defaults must remain off")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.parent == OUT.resolve() and
            re.fullmatch(r"resident_deployment_discovery_[A-Za-z0-9_-]+", out.name),
            "Use a fresh direct signoff verification/out/resident_deployment_discovery_* directory")
    require(subprocess.check_output(["git", "-C", str(SIGNOFF), "branch", "--show-current"],
                                    text=True).strip() == "ara_dsa_signoff_integration",
            "Wrong signoff branch")
    vcs = shutil.which("vcs")
    require(vcs, "Host VCS is required")
    out.mkdir(exist_ok=False)
    inputs, work = out / "inputs", out / "work"
    inputs.mkdir()
    work.mkdir()
    commands, pins = [], {}
    result = {"state": "FAIL", "board_tested": False, "synthesis": False,
              "full_soc_built": False, "platform_authority_granted": False,
              "compute_or_datapath_changed": False}

    def verify():
        for name, digest in pins.items():
            require(sha(name) == digest, "Input identity drift: " + name)

    def execute(argv, name, cwd=work, timeout=120):
        verify()
        commands.append({"argv": list(map(str, argv)), "cwd": str(cwd), "timeout": timeout})
        save(out / "commands.json", commands)
        print("RUN " + name, flush=True)
        with (out / (name + ".log")).open("w") as log:
            proc = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=timeout)
        require(proc.returncode == 0, name + " failed; see its log")
        verify()
        return (out / (name + ".log")).read_text()

    try:
        revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                           text=True).strip()
        # Pinned SDK support sources exclude unrelated dirty native C/assembly.
        archive = subprocess.check_output(["git", "-C", str(ROOT), "archive", revision, "software/akv"])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                require(not member.issym() and not member.islnk() and
                        not Path(member.name).is_absolute() and ".." not in Path(member.name).parts,
                        "Unexpected SDK archive member")
            tar.extractall(inputs)
        sources = [ROOT / name for name in (*SCOPED, *AUDIT)]
        sources += sorted(path for path in HERE.iterdir() if path.is_file())
        for source in sources:
            destination = inputs / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            pins[str(source)] = sha(source)
            shutil.copyfile(source, destination)
            require(sha(destination) == pins[str(source)], "Snapshot race: " + str(source))
        gate_audit = extract_gates(inputs, work)
        for path in [*inputs.rglob("*"), *work.glob("*.svh")]:
            if path.is_file():
                pins[str(path)] = sha(path)
                path.chmod(0o444)
        for tool in (vcs, sys.executable, shutil.which("make"), shutil.which("cc"), shutil.which("c++")):
            require(tool, "Missing host tool")
            pins[str(Path(tool).resolve())] = sha(Path(tool).resolve())
        pins[str(SIGNOFF / "AGENTS.md")] = sha(SIGNOFF / "AGENTS.md")
        save(out / "source-pins.json", pins)
        save(out / "provenance.json", {"source_root": str(ROOT), "sdk_archive_revision": revision,
             "sdk_overlay": SCOPED, "signoff_branch": "ara_dsa_signoff_integration",
             "gate_audit": gate_audit, "all_consumers_require_rebuild": True})
        print("FROZEN " + str(out), flush=True)
        check_generator(inputs)
        execute([sys.executable, "-B", inputs / "scripts/gen_akv_abi.py", "--check"], "generator")
        execute(["make", "-C", inputs / "software/akv", "BUILD=" + str(work / "sdk"), "check"],
                "host-sdk")
        cpp = work / "header.cpp"
        cpp.write_text('#include "akv/akv.h"\n'
                       'akv_status_t (*decode)(uint64_t, akv_capabilities_t *) = '
                       'akv_capabilities_decode_resident;\n')
        execute(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I",
                 inputs / "software/akv/include", "-c", cpp, "-o", work / "header.o"], "cpp-header")
        frozen_here = inputs / HERE.relative_to(ROOT)
        vectors = []
        for flags in range(16):
            build = work / f"sv_{flags:02d}"
            build.mkdir()
            compile_log = execute([vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                "-top", "resident_discovery_tb", "+incdir+" + str(work),
                *["+define+" + name for bit, name in enumerate(DEFINES) if flags & (1 << bit)],
                inputs / "hardware/include/akv_pkg.sv", frozen_here / "resident_discovery_tb.sv",
                "-o", build / "simv"], f"sv-{flags:02d}-compile", cwd=build)
            require(not re.search(r"(?m)^(Error-|Error:|Fatal:)", compile_log), "SV compile error")
            log = execute([build / "simv", "-no_save"], f"sv-{flags:02d}-run", cwd=build, timeout=20)
            require("resident_discovery_tb: PASS" in log, "Missing SV PASS")
            case = [line.removeprefix("VECTOR ") for line in log.splitlines() if line.startswith("VECTOR ")]
            require(len(case) == 120, "Incomplete SV matrix")
            vectors.extend(case)
        require(len(vectors) == 1920, "Incomplete configuration matrix")
        vector_path = out / "sv-vectors.txt"
        vector_path.write_text("\n".join(vectors) + "\n")
        execute([work / "sdk/akv_resident_capability_test", vector_path], "sv-to-sdk", timeout=20)
        verify()
        result.update(state="PASS", sv_configurations=16, sv_to_sdk_vectors=len(vectors),
                      host_sdk_tests=5, legacy_words_unchanged=True, reference_resident_off=True,
                      malformed_fails_closed_without_native_loss=True, input_identity_match=True)
    except Exception as error:
        result["error"] = str(error)
    save(out / "result.json", result)
    artifacts = {str(path.relative_to(out)): sha(path) for path in out.rglob("*")
                 if path.is_file() and "inputs" not in path.relative_to(out).parts}
    save(out / "artifact-pins.json", artifacts)
    with (out / "SHA256SUMS").open("w") as checksums:
        for path in sorted(out.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                checksums.write(sha(path) + "  " + str(path.relative_to(out)) + "\n")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["state"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
