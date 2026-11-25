#!/usr/bin/env python3
"""Build an isolated registered-view module from pinned AKV plus explicit overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
KERNEL = Path("/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6")
GNU = "/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-"
COMMIT = "4a7361f51ba5447a616217dad1c8e72e3ee2b45b"


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, data): p.write_text(json.dumps(data, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    assert out.parent == OUT and out.name.startswith("resident_view_module_") and not out.exists()
    out.mkdir()
    sdk, module = out / "sdk", out / "module"
    sdk.mkdir()
    commands, pins = [], {str(Path(__file__).resolve()): sha(__file__)}
    result = dict(state="FAIL", board_tested=False, rtl_changed=False)

    def run(name, argv):
        argv = list(map(str, argv))
        with (out / (name + ".log")).open("x") as log:
            rc = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=300).returncode
        commands.append(dict(name=name, argv=argv, returncode=rc))
        assert not rc, name
        return (out / (name + ".log")).read_text()

    try:
        run("archive", ["git", "-C", ROOT, "archive", "--format=tar", "--output=" + str(out / "sdk.tar"),
                        COMMIT, "software/akv", "software/llama/platform/linux"])
        run("extract", ["tar", "-xf", out / "sdk.tar", "-C", sdk])
        linux = ROOT / "software/llama/platform/linux"
        module.mkdir()
        sources = [p for p in linux.rglob("*") if p.is_file() and (p.suffix in (".c", ".h", ".S") or p.name.startswith(("Makefile", "Kbuild")))]
        for source in sources:
            dest = module / source.relative_to(linux)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            pins[str(source)] = sha(source)
            pins[str(dest)] = sha(dest)
        for source in (sdk / "software/akv").rglob("*"):
            if source.is_file(): pins[str(source)] = sha(source)
        for name in (".config", "Module.symvers", "include/generated/utsrelease.h"):
            pins[str(KERNEL / name)] = sha(KERNEL / name)
        save(out / "source-pins.json", pins)
        run("kbuild", ["make", "-C", KERNEL, "ARCH=riscv", "CROSS_COMPILE=" + GNU, "M=" + str(module),
                       "ARA_RESIDENT_SDK=" + str(sdk), "-j4", "modules"])
        ko = module / "ara_resident.ko"
        reloc = run("relocations", [GNU + "readelf", "-rW", ko])
        assert "R_RISCV_ALIGN" not in reloc and "R_RISCV_RELAX" not in reloc
        dis = run("broker-disassembly", [GNU + "objdump", "-d", module / "ara_resident_broker.o"])
        ops = re.findall(r"^\s*[0-9a-f]+:\s+[0-9a-f]+\s+([a-z][a-z0-9_.]*)", dis, re.M)
        assert ops and not any(op.startswith(("v", "f")) and op != "fence" for op in ops)
        assert all(sha(path) == value for path, value in pins.items()), "source drift"
        result.update(state="MODULE_BUILT_NOT_EXECUTED", module_sha256=sha(ko),
                      core_sha256=sha(module / "sdk/ara_resident_compute_core.o"),
                      sdk_commit=COMMIT, pins_match=True)
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        save(out / "result.json", result)
        save(out / "commands.json", commands)
    print(json.dumps(result), flush=True)


if __name__ == "__main__": main()
