#!/usr/bin/env python3
"""One O2-only compilation per backend and one bounded Spike cost run."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'prepared02'
NAME = 'alias_v8_e16m8_prefix682'
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, data):
    with p.open('x') as f:
        json.dump(data, f, indent=2)


def command(argv, stem, timeout):
    save(stem.with_suffix('.command.json'), list(map(str, argv)))
    start = time.monotonic()
    with stem.with_suffix('.log').open('xb') as f:
        proc = subprocess.Popen(list(map(str, argv)), stdout=f, stderr=subprocess.STDOUT)
        timed_out = False
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            rc = proc.wait()
    outcome = dict(returncode=rc, pid=proc.pid, elapsed_s=time.monotonic()-start,
                   timed_out=timed_out)
    save(stem.with_suffix('.exit.json'), outcome)
    assert rc == 0 and not timed_out, outcome
    return outcome


def disassemble(elf, gcc, stem):
    objdump = str(Path(gcc).with_name(Path(gcc).name.removesuffix('gcc') + 'objdump'))
    command([objdump, '-d', elf], stem, 30)
    text = stem.with_suffix('.log').read_text()
    symbols = dict((name, int(pc, 16)) for pc, name in
                   re.findall(r'^([0-9a-f]+) <([^>]+)>:', text, re.M))
    blocks = {}
    current = None
    for line in text.splitlines():
        head = re.match(r'^([0-9a-f]+) <([^>]+)>:', line)
        if head:
            current = head[2]
            blocks[current] = []
        insn = re.match(r'^\s*[0-9a-f]+:\s+([0-9a-f]{4,8})\s+', line)
        if insn and current:
            blocks[current].append(insn[1])
    return symbols, blocks


def main():
    run = HERE / 'run01'
    assert run.is_dir()  # Resume tool-path failure; never repeat completed compilation.
    pins = {str(Path(__file__)): sha(__file__), str(SPIKE): sha(SPIKE)}
    commands = {}
    for backend in ('soc', 'spike'):
        source = OLD / backend / (NAME + '.compile.log.command.json')
        argv = json.loads(source.read_text())
        assert argv.count('-Os') == 1
        assert '-fno-tree-vectorize' in argv and '-fno-tree-slp-vectorize' in argv
        pins[str(source)] = sha(source)
        for token in argv:
            p = Path(token[2:] if token.startswith('-I') else token)
            if p.is_file():
                pins[str(p)] = sha(p)
            elif token.startswith('-I'):
                for h in p.glob('*.h'):
                    pins[str(h)] = sha(h)
        argv[argv.index('-Os')] = '-O2'
        argv[argv.index('-o')+1] = str(run / (backend + '.elf'))
        commands[backend] = argv
    save(run / 'input_pins02.json', pins)
    symbols = {}
    for backend, argv in commands.items():
        if (run / (backend + '_compile.exit.json')).exists():
            assert json.loads((run / (backend + '_compile.exit.json')).read_text())['returncode'] == 0
            assert json.loads((run / (backend + '_compile.command.json')).read_text()) == argv
        else:
            command(argv, run / (backend + '_compile'), 120)
        syms, blocks = disassemble(run / (backend + '.elf'), argv[0], run / (backend + '_dis02'))
        _, old_blocks = disassemble(OLD / backend / (NAME + '.elf'), argv[0], run / (backend + '_old_dis'))
        helpers = ['capacity'] + ['op_' + str(i) for i in range(10)]
        assert all(blocks[h] == old_blocks[h] for h in helpers)
        # Raw encodings identify vector arithmetic and vector load/store widths.
        for name, words in blocks.items():
            if name in helpers:
                continue
            for word in words:
                insn = int(word, 16)
                assert not (len(word) == 8 and ((insn & 127) == 87 or
                           ((insn & 127) in (7, 39) and ((insn >> 12) & 7) in (0, 5, 6, 7)))), (name, word)
        symbols[backend] = syms
        nm = str(Path(argv[0]).with_name(Path(argv[0]).name.removesuffix('gcc') + 'nm'))
        command([nm, '-n', run / (backend + '.elf')], run / (backend + '_nm'), 30)
    sym = dict((name, int(pc,16)) for pc, _, name in
               re.findall(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$', (run / 'spike_nm.log').read_text(), re.M))
    assert sym['__bss_end'] < sym['__stack_top'] - 65536
    debug = run / 'spike.cmd'
    with debug.open('x') as f:
        f.write('until pc 0 '+hex(sym['_start'])+'\nreg 0 minstret\nuntil pc 0 '+
                hex(sym['replay_exit'])+'\nreg 0 minstret\nreg 0 a0\nstr '+hex(sym['replay_log'])+'\nrs\n')
    save(run / 'execution_pins.json', {str(p): sha(p) for p in
         [run/'soc.elf', run/'spike.elf', debug, run/'input_pins02.json', Path(__file__)]})
    outcome = command([SPIKE, '-d', '--debug-cmd='+str(debug), '--isa=rv64gcv_zvfh_zvl1024b',
                       '-m2', run/'spike.elf'], run/'spike_cost', 180)
    log = (run/'spike_cost.log').read_text()
    values = [int(v,16) for v in re.findall(r'^0x([0-9a-f]+)$',log,re.M)]
    assert len(values) == 3 and values[2] == 0 and values[1] > values[0]
    assert 'RVV_FP_COMPARE_PASS sew=16 cases=682 errors=0' in log
    assert not re.search(r'RVV_FP_COMPARE_(FAIL|DETAIL|CAPACITY_FAIL)', log)
    assert all(sha(p) == h for p,h in pins.items())
    retired = values[1]-values[0]
    rate = 4529502/7544.534202890936
    save(run/'result.json', dict(status='REFERENCE_COST_ONLY_NOT_DUT_OR_FULL_DYNAMIC_AUDIT',
         calls=682, result_bits=349184, guards=1364, flags_checks=682, returned_vstart_checks=682,
         helper_bytes_unchanged=True, extra_vector_instructions=False,
         source_and_oracle_unchanged=True, retired=retired, original_retired=20260288,
         process=outcome, pins_unchanged=True, bss_end=hex(sym['__bss_end']),
         stack_top=hex(sym['__stack_top']), stack_reserve=65536,
         calibration='M7 full e64 O2; different vector workload, projection only',
         nominal_s=retired/rate, margin20_s=1.2*retired/rate,
         within_budget_projection=1.2*retired/rate<=10800))
    print((run/'result.json').read_text())


if __name__ == '__main__':
    main()
