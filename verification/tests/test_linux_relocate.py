"""Positive and corruption tests for the independent relocation oracle."""
import copy
import ast
import hashlib
from pathlib import Path
import re
import pytest

from cva6.check_linux_relocate import (PA, DELTA, MODE, check_console, check_trace,
                                     check_csr_and_traps, expected_observations)


@pytest.fixture
def symbols():
    return dict(linux_satp_trampoline=PA + 0x100, linux_virtual_entry=PA + 0x104,
                linux_satp_final=PA + 0x140, reloc_s_resume=PA + 0x180,
                reloc_s_ecall=PA + 0x200, m_handler=PA + 0x240,
                linux_debug_park=PA + 0x280, gp_expected=PA + 0x380,
                final_pg_dir=PA + 0x1000, trampoline_pg_dir=PA + 0x2000,
                pages=PA + 0x4000)


def console(s):
    obs = "".join(f"RELOC_OBS {i} {v:016x}\n" for i, v in enumerate(expected_observations(s)))
    trap = [9, s["reloc_s_ecall"] + DELTA, 0, 0x800]
    return (obs + "".join(f"RELOC_TRAP {i} {v:016x}\n" for i, v in enumerate(trap)) +
            "RELOC_MEMORY 6b6b6b6b6b6b6b6b 13579bdf2468ace0\n" +
            "linux_mmu_relocate: checks=26 failures=0\nPASSED: linux_mmu_relocate\n")


def test_console_positive(symbols):
    check_console(console(symbols), symbols)


@pytest.mark.parametrize("slot", range(13))
def test_wrong_observation_rejected(symbols, slot):
    before = f"RELOC_OBS {slot} {expected_observations(symbols)[slot]:016x}"
    after = f"RELOC_OBS {slot} {expected_observations(symbols)[slot] ^ 1:016x}"
    with pytest.raises(ValueError):
        check_console(console(symbols).replace(before, after), symbols)


def test_pass_marker_alone_and_duplicate_rejected(symbols):
    with pytest.raises(ValueError):
        check_console("PASSED: linux_mmu_relocate\n", symbols)
    with pytest.raises(ValueError):
        check_console(console(symbols) + "RELOC_OBS 0 0000000000000000\n", symbols)


def trace(s):
    code = {p: 0x13 for p in range(PA + 0x104, PA + 0x184, 4)}
    pcs = [s["linux_satp_trampoline"]] + [p + DELTA for p in code] + [s["m_handler"]]
    return [dict(event="retire", pc=f"{p:016x}", insn="00000013") for p in pcs], code


def test_trace_positive(symbols):
    rows, code = trace(symbols)
    assert check_trace(rows, symbols, code)["high_va_retire_count"] == 32


@pytest.mark.parametrize("mutation", ["low_pc", "insn", "duplicate", "swap", "missing"])
def test_bad_trace_rejected(symbols, mutation):
    rows, code = trace(symbols)
    if mutation == "low_pc":
        rows[2]["pc"] = f"{PA + 0x108:016x}"
    elif mutation == "insn":
        rows[2]["insn"] = "ffffffff"
    elif mutation == "duplicate":
        rows.insert(0, copy.deepcopy(rows[0]))
    elif mutation == "swap":
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows.pop(1)
    with pytest.raises(ValueError):
        check_trace(rows, symbols, code)


def probes(s):
    csr = [dict(commit0_pc=f"{pc:x}", ack="01", csr_we="1", priv="01", csr_addr="180",
                csr_wdata=f"{MODE | (root >> 12):016x}") for pc, root in [
                    (s["linux_satp_trampoline"], s["trampoline_pg_dir"]),
                    (s["linux_satp_final"] + DELTA, s["final_pg_dir"])]]
    traps = [dict(ex_valid="1", ex_cause="000000000000000c", priv_q="01", trap_to_priv="01",
                  pc=f"{s['linux_virtual_entry']:x}", ex_tval=f"{s['linux_virtual_entry']:x}",
                  trap_vector=f"{s['linux_virtual_entry'] + DELTA:x}")]
    return csr, traps


def test_probes_positive(symbols):
    check_csr_and_traps(*probes(symbols), symbols)


@pytest.mark.parametrize("mutation", ["priv", "root", "ack", "delegation", "tval", "missing"])
def test_bad_probes_rejected(symbols, mutation):
    csr, traps = probes(symbols)
    if mutation == "priv":
        csr[0]["priv"] = "11"
    elif mutation == "root":
        csr[0]["csr_wdata"] = "0"
    elif mutation == "ack":
        csr[0]["ack"] = "00"
    elif mutation == "delegation":
        traps[0]["trap_to_priv"] = "11"
    elif mutation == "tval":
        traps[0]["ex_tval"] = "0"
    else:
        traps.clear()
    with pytest.raises(ValueError):
        check_csr_and_traps(csr, traps, symbols)


LINUX_HEAD = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6/arch/riscv/kernel/head.S')


@pytest.mark.skipif(not LINUX_HEAD.is_file(), reason="external Linux source not installed")
def test_linux_source_instruction_order():
    source = LINUX_HEAD.read_bytes()
    assert hashlib.sha256(source).hexdigest() == '0dbda1a1b97dc30e1b763268aa495e3e650e50cc022cb1fff50db3b407a1810d'
    body = source.decode().split('relocate_enable_mmu:\n', 1)[1].split('#endif', 1)[0]
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    expected = []
    for line in body.splitlines():
        line = ' '.join(line.split())
        if not line or line.startswith(('XIP_FIXUP_OFFSET', '.align')) or line == '1:':
            continue
        line = line.replace('kernel_map', 'kernel_map_va').replace('KERNEL_MAP_VIRT_ADDR', '0')
        line = line.replace('REG_L', 'ld').replace('1f', 'linux_virtual_entry')
        line = line.replace('CSR_TVEC', 'stvec').replace('CSR_SATP', 'satp')
        line = line.replace('srl ', 'srli ').replace('PAGE_SHIFT', '12')
        line = line.replace('.Lsecondary_park', 'linux_debug_park')
        line = line.replace('load_global_pointer', 'la gp, __global_pointer$')
        expected.append(line)
    root = Path(__file__).resolve().parents[2]
    body = (root / 'apps/riscv-tests/isa/rv64uv/linux_mmu_relocate.c').read_text()
    body = body.split('linux_relocate(', 1)[1].split('\n}', 1)[0]
    asm = ''.join(ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"', body))
    actual = []
    for line in asm.splitlines():
        if line.startswith('.'):
            continue
        line = line.split(':', 1)[-1].strip()
        if line:
            actual.append(line)
    assert actual == expected
