"""Attention campaign contract. No simulator or SoC build entry points."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
REV = "dbe2b78817ef45b912444afcb85ad6e01a2be135"
CC = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
FORBIDDEN = "software/akv/src/akv_v2_attention_rvv.S"
SDK_OVERLAYS = tuple("software/akv/" + p for p in (
    "src/akv_v2_native_riscv.c", "include/akv/akv.h",
    "experimental/resident_attention/pv_compact.h",
    "experimental/resident_attention/pv_compact.S",
    "experimental/resident_attention/pv.S", "experimental/resident_attention/pv.h",
    "experimental/resident_attention/pv_fast.inc",
    "experimental/resident_attention/qk.S", "experimental/resident_attention/qk.h",
    "experimental/resident_attention/admission.h", "experimental/resident_attention/dispatch.h",
))
GEOMETRY = ROOT / "verification/performance/resident_rvv/qk_shared/full_call/check_work.py"
ORACLE = ROOT / "verification/performance/resident_rvv/qk_shared/full_call_sdk/flags_v2/fixture.py"
LEGACY = ROOT / "verification/performance/akv_pair_eval/check.py"
ELF = ROOT / "verification/performance/resident_rvv/qk_shared/qk_boundary/elf.py"
MODES = ("rvv_tiled", "native_akv", "resident_compact")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def verify(pins):
    require(bool(pins), "Empty source pins")
    for path, digest in pins.items():
        require(Path(path).is_file() and sha(path) == digest, "Input drift: " + str(path))


def cases():
    return json.loads((HERE / "cases.json").read_text())["cases"]


def resident_commands(case, order):
    rows = case["heads"] // case["kv_heads"]
    return [dict(trial=trial, group=group, mode=mode, base=base,
                 tile=start, heads=min(2, rows-base), dimension=case["dimension"],
                 tokens=min(64, case["tokens"]-start))
            for trial, arm in enumerate(order) if arm == 2
            for group in range(case["kv_heads"])
            for start in range(0, case["tokens"], 64)
            for mode in ("QK", "PV") for base in range(0, rows, 2)]
