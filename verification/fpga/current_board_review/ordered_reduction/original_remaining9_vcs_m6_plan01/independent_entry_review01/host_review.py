#!/usr/bin/env python3
"""Independent sealed-input review; no DUT, reference execution or live query."""
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(ROOT))
import test_host02 as delta
from test_host02 import old, replay, c

PLAN_SHA = '10807a26d22d6beb48acdd075e3e1ccea37e5ca69f38c783ce2ed9027375891a'
HOST_SHA = '7d2a76d8ccced172d1de3ceb6aa0606c111db71ec716974b03490eea99d46b68'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def elf_bytes(path, address, size):
    data = Path(path).read_bytes()
    assert data[:6] == b'\x7fELF\x02\x01'
    phoff = struct.unpack_from('<Q', data, 32)[0]
    entsize, count = struct.unpack_from('<HH', data, 54)
    for i in range(count):
        kind, flags, offset, vaddr, paddr, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, phoff+i*entsize)
        if kind == 1 and vaddr <= address and address+size <= vaddr+filesz:
            return data[offset+address-vaddr:offset+address-vaddr+size]
    raise AssertionError((str(path), hex(address), size))

def main():
    assert sha(ROOT/'prepared01/plan.json') == PLAN_SHA
    assert sha(ROOT/'host02.json') == HOST_SHA
    plan = c.read(ROOT/'prepared01/plan.json')
    assert len(plan['pins']) == 1352
    bad = [p for p, digest in plan['pins'].items() if sha(p) != digest]
    assert not bad, bad
    print('All 1352 pins verified', flush=True)
    replay.validate(plan, replay.IMAGE)
    replay.accepted_reference()
    ready = c.read(ROOT/'prepared01/ready.json')
    assert ready['plan_sha256'] == PLAN_SHA and ready['VCS_started'] is False
    assert ready['pins'] == 1352
    assert 'PARENT_REVIEW_JSON' in ready['command'] and 'MF4_DUT_ACCEPTANCE_JSON' in ready['command']
    assert not (ROOT/'prepared01/launch.json').exists()
    assert not (ROOT/'prepared01/replay').exists()
    required = [c.common, c.common.base, c.common.base.shared]
    for module in required:
        assert str(Path(module.__file__).resolve()) in plan['pins'], module.__file__
    prepare = ROOT.parents[1]/'integration/prepare.py'
    assert str(prepare) in plan['pins']
    counts = {}
    for case in plan['cases']:
        spec = plan['specs'][case['shape']]
        for insn in spec['instructions'].values():
            raw = elf_bytes(case['elf'], insn['pc'], len(insn['insn'])//2)
            assert int.from_bytes(raw, 'little') == int(insn['insn'], 16)
        counts[case['shape']] = dict(instructions=len(spec['instructions']), cap=spec['config']['cap'],
            sew=spec['config']['sew'], vl=spec['config']['vl'], elf_sha256=case['sha256'])
    print('Actual ELF bytes checked for all nine instruction maps', flush=True)
    # Run the producer's exact delta selection without its artifact-writing main.
    tree = ast.parse((ROOT/'test_host02.py').read_text())
    main_if = tree.body[-1]
    names = ast.literal_eval(next(n.value for n in main_if.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets)))
    suite = unittest.TestSuite(delta.Delta(n) for n in names)
    suite.addTest(old.Gates('test_all9_full_source_positive_generic_and_strict'))
    suite.addTest(old.Gates('test_unused_all42_PC_immediate_eachshape'))
    original_temp, original_save = tempfile.TemporaryDirectory, c.common.save
    def owned_temp(*args, **kwargs):
        kwargs['dir'] = OUT
        return original_temp(*args, **kwargs)
    def owned_save(path, value):
        path = Path(path)
        if path == ROOT/'host02_timer_before.json':
            path = OUT/'rerun_host02_timer_before.json'
        assert path.is_relative_to(OUT), path
        return original_save(path, value)
    with (OUT/'host_review.log').open('x') as log, patch.object(tempfile, 'TemporaryDirectory', owned_temp), patch.object(c.common, 'save', owned_save):
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    evidence = dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL', plan_sha256=PLAN_SHA,
        pins_verified=1352, actual_elf_instruction_maps=counts, methods=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), delta_checks=delta.Delta.checks,
        extra_checks=old.Gates.checks, DUT_started=False, reference_started=False, live_queries=False)
    (OUT/'host_evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    assert sha(ROOT/'prepared01/plan.json') == PLAN_SHA and sha(ROOT/'host02.json') == HOST_SHA
    assert all(sha(p) == digest for p, digest in plan['pins'].items())
    print(json.dumps({k:v for k,v in evidence.items() if k not in ('delta_checks','extra_checks','actual_elf_instruction_maps')}), flush=True)
    return not result.wasSuccessful()

if __name__ == '__main__':
    raise SystemExit(main())
