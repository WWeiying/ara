#!/usr/bin/env python3
"""Freeze and check the Direct-U helper with mocked OS responses."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
LLAMA = Path("/home/wangwy/llama/llama.cpp")
SDK = OUT / "resident_direct_build_compact_20261113_01/inputs/sdk/software/akv"
ARCH = "ggml/src/ggml-cpu/arch/riscv"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != OUT or not out.name.startswith("resident_direct_model_helper_"):
        parser.error("use a fresh resident_direct_model_helper_* output")
    out.mkdir()
    inputs = out / "inputs"
    pins = {}
    for relative in ("tests/test-ara-linux-direct.cpp", *(ARCH + "/" + name for name in
                     ("linux-direct.cpp", "linux-direct.h", "entry.h", "platform.h"))):
        source, dest = LLAMA / relative, inputs / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        pins[str(source)] = sha(source)
        pins[str(dest)] = sha(dest)
    shutil.copytree(SDK, inputs / "sdk")
    direct = ROOT / "software/llama/platform/linux/direct"
    for name in ("direct_client.h", "direct_uapi.h"):
        source, dest = direct / name, inputs / name
        shutil.copyfile(source, dest)
        pins[str(source)] = sha(source)
    for path in inputs.rglob("*"):
        if path.is_file():
            pins[str(path)] = sha(path)
    (out / "source-pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    flags = ["-std=c++17", "-O2", "-UNDEBUG", "-Wall", "-Wextra", "-Werror",
             "-I" + str(inputs), "-I" + str(inputs / ARCH),
             "-I" + str(inputs / "sdk/include"), "-I" + str(inputs / "sdk/experimental")]
    source = inputs / "tests/test-ara-linux-direct.cpp"
    result = dict(state="FAIL", scope="mocked OS lifecycle only", board_executed=False,
                  rtl_executed=False, native_math_executed=False, commands=[])

    def run(name, command):
        command = list(map(str, command))
        with (out / (name + ".log")).open("w") as log:
            proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        result["commands"].append(dict(argv=command, returncode=proc.returncode))
        if proc.returncode:
            raise RuntimeError(name + " failed")

    try:
        for variant, compiler, extra in (
                ("host", "g++", []),
                ("asan", "clang++", ["-O1", "-g", "-fsanitize=address,undefined"]),
                ("unpinned", "g++", ['-DGGML_AKV_DIRECT_CONTRACT_SHA256=""'])):
            exe = out / ("test-" + variant)
            run("build-" + variant, [compiler, *flags, *extra, source, "-o", exe])
            run("run-" + variant, [exe])
            if "PASS:" not in (out / ("run-" + variant + ".log")).read_text():
                raise RuntimeError("missing pass marker: " + variant)
        if any(sha(Path(p)) != expected for p, expected in pins.items()):
            raise RuntimeError("input drift")
        result["state"] = "HELPER_HOST_SANITIZER_PIN_GUARD_PASS"
    except Exception as error:
        result["error"] = str(error)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["state"] + ": " + str(out))
    return result["state"] != "HELPER_HOST_SANITIZER_PIN_GUARD_PASS"


if __name__ == "__main__":
    raise SystemExit(main())
