"""Independent host-only entrance review; no prepare/run/build/live inventory."""
import copy
import dis
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(ROOT))
import replay as r
import test_host as h
c = r.checker

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def elf_bytes(path):
    data = Path(path).read_bytes()
    assert data[:6] == b'\x7fELF\x02\x01'
    phoff = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    segments = []
    for i in range(count):
        typ, flags, off, va, pa, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, phoff + i * size)
        if typ == 1: segments.append((va, va + filesz, off))
    def read_at(addr, length):
        for lo, hi, off in segments:
            if lo <= addr and addr + length <= hi:
                return data[off + addr - lo:off + addr - lo + length]
        raise AssertionError(('Unmapped ELF bytes', hex(addr)))
    return read_at

def main():
    planpath = ROOT / 'prepared01/plan.json'
    plan = r.read(planpath)
    expected = 'a9a60cc30f3d88d4b15441ec3d2da2bd7367f9334c9cb36731b262bbade50d3e'
    assert sha(planpath) == expected
    before = {p: sha(p) for p in plan['pins']}
    assert before == plan['pins']
    real_temp = tempfile.TemporaryDirectory
    def owned_temp(*args, **kwargs):
        # Supplied tests request producer-root temporaries; relocate fixtures
        # to this reviewer-owned directory without changing checker behavior.
        if kwargs.get('dir') == c.HERE: kwargs['dir'] = OUT
        return real_temp(*args, **kwargs)
    log = io.StringIO()
    with patch.object(tempfile, 'TemporaryDirectory', owned_temp):
        tests = unittest.defaultTestLoader.loadTestsFromTestCase(h.Gates)
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(tests)
    (OUT / 'host_tests.log').write_text(log.getvalue())
    assert result.wasSuccessful() and result.testsRun == 31
    r.validate(plan, r.IMAGE)
    spec = c.specification()
    soc = elf_bytes(c.REF / 'soc/program.elf')
    for key, insn in spec['instructions'].items():
        size = len(insn['insn']) // 2
        assert int.from_bytes(soc(int(key, 16), size), 'little') == int(insn['insn'], 16)
    proof = r.read(c.REF / 'sourceproof.json')
    original = elf_bytes(c.REF / 'prepared/scenario.elf')
    for name, window in proof['helper_windows']['soc'].items():
        assert len(window['original']) == len(window['new']) == 21
        for old, new in zip(window['original'], window['new']):
            assert old[1] == new[1]
            width = len(old[1]) // 2
            assert original(old[0], width) == soc(new[0], width) == int(old[1], 16).to_bytes(width, 'little')

    negative_checks = []
    for fault in ('trap', 'cycle_backwards', 'saved_fflags', 'bad_park_encoding'):
        def rows():
            modified = False
            for row in h.fixture(spec):
                pc = int(row['pc'], 16)
                if row['event'] == 'retire' and not modified:
                    if fault == 'trap': row = dict(row, trap='1'); modified = True
                    elif fault == 'cycle_backwards' and int(row['cycle']) > 10:
                        row = dict(row, cycle='0'); modified = True
                    elif fault == 'saved_fflags' and pc == spec['routine'][8]['pc']:
                        row = dict(row, rd_wdata='1'); modified = True
                    elif fault == 'bad_park_encoding' and pc == spec['park']['pc']:
                        row = dict(row, insn='13'); modified = True
                yield row
        try: c.retirement(rows(), spec)
        except ValueError as error: negative_checks.append(dict(fault=fault, rejected=str(error)))
        else: raise AssertionError(fault)

    # Real signal tests around the *last* current pending-set query in publish.
    function = c.common.publish
    instructions = list(dis.get_instructions(function))
    loads = [i for i, op in enumerate(instructions) if op.argval == 'sigpending']
    last = loads[-1]
    call = next(i for i in range(last + 1, len(instructions)) if instructions[i].opname in ('CALL', 'CALL_FUNCTION', 'CALL_METHOD'))
    signal_tests = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        for before_call in (True, False):
            target = instructions[call if before_call else call + 1].offset
            abort = threading.Event()
            terminal = dict(status=r.PASS)
            fired = []
            with real_temp(dir=OUT) as temp:
                out = Path(temp)
                def trace(frame, event, arg):
                    if frame.f_code is function.__code__:
                        frame.f_trace_opcodes = True
                        if event == 'opcode' and frame.f_lasti == target and not fired:
                            os.kill(os.getpid(), sig)
                            fired.append(sig in signal.sigpending())
                    return trace
                with c.common.abort_signals(abort):
                    sys.settrace(trace)
                    try: function(out, terminal, abort)
                    finally: sys.settrace(None)
                    actual = r.read(out / 'complete.json')
                    assert abort.is_set() and fired == [True]
                assert actual['status'] == ('NOT_PASS' if before_call else r.PASS)
                signal_tests.append(dict(signal=sig.name, before_last_query=before_call, status=actual['status']))

    modules = {}
    worktree = ROOT.parents[4]
    frozen = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources')
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename: continue
        p = Path(filename).resolve()
        if p.suffix == '.py' and p != Path(__file__).resolve() and (p.is_relative_to(worktree) or p.is_relative_to(frozen)):
            modules[str(p)] = sha(p)
    assert all(plan['pins'].get(p) == digest for p, digest in modules.items())
    assert {p: sha(p) for p in plan['pins']} == before
    evidence = dict(status='HOST_REVIEW_PASS_NOT_DUT', plan_sha256=sha(planpath), pins_checked=len(before),
        pins_unchanged=True, supplied_tests=31, supplied_tests_pass=True, negative_checks=negative_checks,
        terminal_real_signals=signal_tests, elf_instruction_count=len(spec['instructions']),
        original_helpers_equal=3, helper_instructions_each=21, loaded_project_modules=modules,
        dut_run=False, live_queries=False, producer_prepare_or_run_called=False)
    (OUT / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k: v for k, v in evidence.items() if k != 'loaded_project_modules'}))

if __name__ == '__main__': main()
