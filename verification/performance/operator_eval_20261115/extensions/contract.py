"""Bounded group-5/6 inputs and identity utilities; no execution engine."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
REV = "dbe2b78817ef45b912444afcb85ad6e01a2be135"
CC = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
LLAMA = Path("/home/wangwy/llama/llama.cpp")
F16_CAPTURE = OUT / "e2e_qwen3_f16_attention_capture_20261106_01"
QUANT_CAPTURE = OUT / "quant-prefill-capture-20261028-01"
QUANT_AUDIT = OUT / "quant-prefill-capture-audit-20261028-01"
ORDER = (0, 1, 1, 0)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, "Input changed: " + path)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
