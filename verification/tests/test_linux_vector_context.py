"""Static guardrails for the Linux-derived S-mode context test, not RTL proof."""
import ast
import hashlib
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/riscv-tests/isa/rv64uv/linux_vector_context.c"
LINUX = Path("/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6/arch/riscv/include/asm/vector.h")
SOURCE_SHA = "5b732436c12dffc97bb5638111f8c445e2557768cee595c8332dd430a3bd476f"


def asm_in(function):
    text = SOURCE.read_text().split(function + "(", 1)[1].split("\n}", 1)[0]
    return "".join(ast.literal_eval(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"', text))


@pytest.mark.parametrize("name,op", [("linux_save", "vse8.v"), ("linux_restore", "vle8.v")])
def test_standard_rvv_sequence(name, op):
    body = asm_in(name)
    sequence = "vsetvli t0, zero, e8, m8, ta, ma\n" + "add a1, a1, t0\n".join(
        f"{op} v{n}, (a1)\n" for n in (0, 8, 16, 24)
    )
    assert sequence in body
    assert body.startswith("li t1, 0x600\ncsrs sstatus, t1\n")
    assert body.endswith("csrc sstatus, t1\nret\n")
    assert "fence" not in body


def test_csr_order_and_independent_physical_dump():
    save, restore = asm_in("linux_save"), asm_in("linux_restore")
    assert save.index("csrr t0, vstart") < save.index("vsetvli")
    assert restore.index("vle8.v v24") < restore.index("vsetvl zero")
    assert restore.index("vsetvl zero") < restore.index("csrw vstart") < restore.index("csrw vcsr")
    source = SOURCE.read_text()
    dump = source.split("dump_physical(", 1)[1].split("\n}", 1)[0]
    assert [int(x) for x in re.findall(r"DUMP_REG\((\d+)\)", dump)] == list(range(32))
    assert "vs1r.v" in source
    assert "test_case != PLANNED_CHECKS" in source
    assert "vector_context_ecall: ecall" in source


def test_unique_pattern_and_check_count():
    mask = (1 << 64) - 1
    words = [
        (0x132547698BADCFE0 ^ ((c + 1) * 0x1122334455667788) ^
         ((i + 1) * 0x0103070B131D2B3D)) & mask
        for c in range(4) for i in range(512)
    ]
    assert len(set(words)) == len(words)
    assert 7 + 6 * (2 + 5 + 5 + 2 * 512 + 32) == 6415


def test_registered_requirement():
    suites = json.loads((ROOT / "verification/suites.json").read_text())
    assert suites["suites"]["linux-vector-context"]["tests"] == ["rvv:linux_vector_context"]
    plan = json.loads((ROOT / "verification/verification_plan.json").read_text())
    assert any("linux-vector-context" in r.get("suites", []) for r in plan["requirements"])
    assert "linux_vector_context \\" in (SOURCE.parent / "Makefrag").read_text()


@pytest.mark.skipif(not LINUX.is_file(), reason="external Linux source not installed")
def test_local_linux_provenance_and_load_store_sequence():
    data = LINUX.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA
    text = data.decode()
    for function, op in [("__riscv_v_vstate_save", "vse8.v"),
                         ("__riscv_v_vstate_restore", "vle8.v")]:
        body = text.split(function + "(", 1)[1].split("\n}", 1)[0]
        asm = "".join(ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"', body))
        lines = [" ".join(line.split()) for line in asm.splitlines()]
        start = lines.index("vsetvli %0, x0, e8, m8, ta, ma")
        expected = ["vsetvli %0, x0, e8, m8, ta, ma"]
        for n in (0, 8, 16, 24):
            if n:
                expected.append("add %1, %1, %0")
            expected.append(f"{op} v{n}, (%1)")
        assert lines[start:start + 8] == expected
