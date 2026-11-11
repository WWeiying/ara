#!/usr/bin/env python3
"""Exact QEMU10.2 QBS helper/decode trap metadata; no guest or oracle changes."""
from collections import Counter
import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_SHA = '4146b684eaa886d663419f74f186d9ab55c6fd882d3653f77280805a72b95e0c'
if hashlib.sha256((HERE / 'check.py').read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Sealed original checker drift')
spec = importlib.util.spec_from_file_location('scoped_original_check', HERE / 'check.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
SOURCE = c.OUT / 'stage5_qemu_prepare_variant_20261110_03/qemu-10.2.0'
SOURCES = {
    'target/riscv/translate.c': '35dd45b33831f61c5936b59f6c7caef4b1f0a643c660fcc7440fcb21c9e9749a',
    'target/riscv/tcg/tcg-cpu.c': '1c5d71533b69350028dc072e40256e06170f5820ba9e6f1d9d6d3dec40402b45',
    'target/riscv/op_helper.c': '195e6c30c59cead6683ca7d5b19a2621c73761f6b91366085e75959a53fde0b0',
    'target/riscv/qbs_helper.c': '5ed80e3807f078b75be6c89dc2825af8268fbe04d581fe4623d450b2fcc2c2fd',
    'target/riscv/insn_trans/trans_xaraqbs.c.inc': '8f8b6c30ec369e2417c5ce32c8d8afbe59252fb83a5fed28bb470b0029f2ec18'}
# Zero-based ordinals from the sealed C call sequence: bad M8 vd, bad M2 vd,
# and nonzero vstart. Every other illegal case enters the helper.
FRONT = {18: 0x0eb500db, 20: 0x02b500db, 21: 0x00b5005b}


def schedule():
    rows = c.qbs_schedule()
    c.require(len(rows) == 190 and Counter(cause for _, cause, _ in rows) == {0: 121, 2: 49, 5: 20},
              'Frozen QBS case census changed')
    for i, word in FRONT.items():
        c.require(rows[i] == (word, 2, word), 'Front case identity changed')
    return [(word, cause, word if i in FRONT else 0 if cause == 2 else tval)
            for i, (word, cause, tval) in enumerate(rows)]


def architecture(events, bound):
    wanted, index, pending = schedule(), 0, None
    words, traps, layers = Counter(), Counter(), Counter()
    for tag, row in events:
        if tag == 'exec':
            c.require(pending is None and index < len(wanted), 'Unexpected instruction/missing fault')
            word, cause, tval = wanted[index]
            c.require(bound['custom'].get(row['pc']) == word, 'QBS native order/opcode differs')
            words[hex(word)] += 1
            if cause:
                pending = dict(pc=row['pc'], cause=cause, tval=tval)
                layers['decode' if index in FRONT else 'helper' if cause == 2 else 'access'] += 1
            index += 1
        elif tag == 'trap':
            c.require(pending == row, 'Exact layer-specific trap PC/cause/tval differs')
            traps[str(row['cause'])] += 1
            pending = None
        else:
            raise ValueError('Unexpected AKV helper in unchanged QBS smoke')
    c.require(index == 190 and pending is None and layers == {'decode': 3, 'helper': 46, 'access': 20},
              'Incomplete exact QBS trap-layer coverage')
    return dict(native_instructions=index, opcode_counts=dict(words), traps=dict(traps),
                firmware_selfchecks=True, reused_unchanged_elf=True, trap_layers=dict(layers),
                backend_illegal_tval=0, decode_illegal_tval='exact opcode',
                access_tval='exact case address')


def check(log, trace):
    for name, digest in SOURCES.items():
        c.require(c.sha(SOURCE / name) == digest, 'QEMU trap-source drift: ' + name)
    for name, digest in c.QBS_SOURCES.items():
        c.require(c.sha(c.ROOT / 'verification/qbs/qemu' / name) == digest, 'Original QBS source drift')
    c.require(Path(log).read_bytes() == b'', 'Unexpected QBS guest output')
    bound = c.binding('qbs')
    events, cancelled = c.trace_events(Path(trace).read_text(), set(bound['points']))
    return dict(state='NATIVE_ELF_ARCHITECTURE_CHECKED', kind='qbs', elf_sha256=c.QBS_SHA,
                work=architecture(events, bound), log_sha256=c.sha(log), trace_sha256=c.sha(trace),
                cancelled_before_execution=cancelled, correction='qemu10.2-exact-helper-decode-tval',
                original_checker_sha256=BASE_SHA, rtl_timing=False, rtl_protocol_checked=False,
                performance_acceptance=False, service_owner_checked=False, qemu_image_checked=False)
