#!/usr/bin/env python3
"""Narrow only six empty enumeration loops; retain archived stimulus and oracle."""
import difflib
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import prepare_batch as base
from replay_candidate03 import FAIL, oracle, pins_check, read, require

HERE = base.HERE
OUT = HERE / 'successor01'
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')


def replacements(op):
    return [
        ('for(unsigned seed=0;seed<3;++seed)', 'for(unsigned seed=0;seed<1;++seed)'),
        ('for(unsigned op=0;op<OP_COUNT;++op)', f'for(unsigned op={op};op<{op+1};++op)'),
        ('for(unsigned s=0;s<8;++s)', 'for(unsigned s=0;s<1;++s)'),
        ('for(unsigned l=0;l<7;++l)', 'for(unsigned l=2;l<3;++l)'),
        ('for(unsigned mode=0;mode<4;++mode)', 'for(unsigned mode=0;mode<1;++mode)'),
        ('for(unsigned trial=0;trial<(RESTART_PERMUTATIONS ? 4U:1U);++trial)',
         'for(unsigned trial=0;trial<1;++trial)'),
    ]


def narrow(source, op):
    for old, new in replacements(op):
        require(source.count(old) == 1, 'Loop boundary differs: ' + old)
        source = source.replace(old, new)
    return source


def symbol(elf, name, objdump):
    for line in subprocess.check_output([str(objdump), '-t', str(elf)], text=True).splitlines():
        fields = line.split()
        if fields and fields[-1] == name:
            return int(fields[0], 16), int(fields[-2], 16)
    raise ValueError('Missing symbol: ' + name)


def main():
    require(not OUT.exists(), 'Fresh successor required; no overwrite')
    old = read(HERE / 'prepared01/provenance.json')
    inventory = read(HERE / 'inventory83.json')
    old_plan = read(HERE / 'vcs_candidate03_01/plan.json')
    pins = dict(old_plan['pins'])
    for directory in ('prepared01', 'soc01', 'spike01', 'reference01'):
        for path in (HERE / directory).rglob('*'):
            if path.is_file():
                pins.setdefault(str(path), base.sha(path))
    for name in ('plan.json', 'complete.json', 'worker_exit.json', 'replay/summary.json'):
        path = HERE / 'vcs_candidate03_01' / name
        pins[str(path)] = base.sha(path)
    for name in ('gather_e16_m1_ops0', 'gather_e8_mf8'):
        folder = HERE / 'vcs_candidate03_01/replay/tests' / name
        for file in ('console.log', 'commit_trace.csv', 'input.elf', 'inputs.json'):
            pins[str(folder / file)] = base.sha(folder / file)
    pins_check(pins)
    OUT.mkdir()
    base.save(OUT / 'baseline_pins.json', pins)
    prepared = OUT / 'prepared01'
    shutil.copytree(HERE / 'prepared01', prepared)
    (prepared / 'provenance.json').unlink()
    diffs = OUT / 'source_diffs'
    diffs.mkdir()
    checks = []
    tuples = read(HERE / 'host_tuple_checks.json')['selected']
    for case in old['cases']:
        name = case['id']
        original = case['original_case']
        op = original['selected_trial']['op']
        record, = [r for r in inventory['records'] if r['case']['name'] == original['name']]
        require(record['case'] == original, name + ': inventory drift')
        for file, digest in original['scenario_sources'].items():
            require(base.sha(prepared / name / 'original' / file) == digest,
                    name + ': archived source drift')
        for file, digest in (('scenario.elf', original['sha256']),
                             ('original.elf', original['original_elf_sha256'])):
            path = Path(case['source_directory']) / file
            require(base.sha(path) == digest, name + ': archived ELF drift')
            pins[str(path)] = digest
        source = (HERE / 'prepared01' / name / 'case.c').read_text()
        port = narrow(source, op)
        restored = port
        for before, after in replacements(op):
            require(restored.count(after) == 1, 'Ambiguous successor boundary')
            restored = restored.replace(after, before)
        require(restored == source, name + ': non-loop change')
        (prepared / name / 'case.c').write_text(port)
        diff = ''.join(difflib.unified_diff(source.splitlines(True), port.splitlines(True),
            fromfile='prepared01/' + name + '/case.c',
            tofile='successor01/prepared01/' + name + '/case.c'))
        (diffs / (name + '.diff')).write_text(diff)
        require(source[source.index('            for(unsigned i=0;i<128;'): ] ==
                port[port.index('            for(unsigned i=0;i<128;'): ],
                name + ': setup/oracle/statistics changed')
        pattern = r'if\(!\(seed==(\d+) && op==(\d+) && s==(\d+) && l==(\d+) && mode==(\d+) && trial==(\d+)\)\)continue;'
        match, = re.findall(pattern, source)
        selected = tuple(map(int, match))
        require(selected == (0, op, 0, 2, 0, 0), name + ': unexpected tuple')
        old_executed = [t for t in itertools.product(range(3), range(21), range(8),
                        range(7), range(4), range(4)) if t[1] == op and t == selected]
        new_executed = list(itertools.product(range(1), range(op, op+1), range(1),
                            range(2, 3), range(1), range(1)))
        require(old_executed == new_executed == [selected], name + ': semantic domain changed')
        shape, = [t for t in tuples if t['name'] == original['name']]
        cap = shape['capacity']
        rng = 0xe736815b449aec21
        data = []
        mask = (1 << original['sew']) - 1
        for index in range(cap):
            rng ^= (rng << 13) & ((1 << 64) - 1)
            rng ^= rng >> 7
            rng ^= (rng << 17) & ((1 << 64) - 1)
            data.append(rng & mask)
        index = 1 if op in (0, 20) else 31 if op == 3 else 0
        expected = [91, data[index] if index < cap else 0]
        require(expected == shape['expected_first_two'], name + ': old tuple values differ')
        checks.append(dict(name=name, status='PASS', tuple=selected, old_enumerations=56448,
            new_enumerations=1, original_trial=original['selected_trial'], capacity=cap,
            expected_first_two=expected, full_cap_expected=expected+[91]*(cap-2),
            guards=[91,91], expected_returned_vstart=0, expected_cases=1, expected_errors=0,
            unchanged_setup_oracle_statistics=True, reversible_six_loop_diff=True,
            old_source_sha256=base.sha(HERE / 'prepared01' / name / 'case.c'),
            new_source_sha256=base.sha(prepared / name / 'case.c'),
            diff_sha256=base.sha(diffs / (name + '.diff'))))
    provenance = dict(old, scope='Eight exact tuple source successors, loop-bound changes only; '
                      'not original Linux ELF/parent matrix/83-case acceptance',
                      generator_sha256=base.sha(Path(__file__)),
                      predecessor_provenance_sha256=base.sha(HERE / 'prepared01/provenance.json'),
                      baseline_pins_sha256=base.sha(OUT / 'baseline_pins.json'))
    provenance['files'] = {str(p.relative_to(prepared)): base.sha(p)
                           for p in sorted(prepared.rglob('*')) if p.is_file()}
    base.save(prepared / 'provenance.json', provenance)
    pins_check(pins)
    base.save(OUT / 'baseline_pins.json', pins)
    provenance['baseline_pins_sha256'] = base.sha(OUT / 'baseline_pins.json')
    base.save(prepared / 'provenance.json', provenance)
    base.save(OUT / 'host_semantics.json', dict(status='PASS_8_EXACT_TUPLES', results=checks,
        old_pins_unchanged=True, generator_sha256=base.sha(Path(__file__))))
    base.HERE = OUT
    soc = base.build(prepared, provenance, 'soc')
    programs = base.build(prepared, provenance, 'spike')
    cc = base.ROOT / 'install/riscv-gcc/bin/riscv64-unknown-elf-gcc'
    objdump = cc.with_name('riscv64-unknown-elf-objdump')
    reference = OUT / 'reference01'
    reference.mkdir()
    sys.path.insert(0, str(base.ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    probe_cc, probe_source = probe_paths(base.ROOT)
    probe = check_spike_vstart(SPIKE, probe_cc, reference / 'vstart_probe', probe_source)
    require(probe['status'] == 'PASS', 'Spike vstart capability not PASS')
    results = []
    for name, entry in programs.items():
        elf = Path(entry['path'])
        exit_pc, _ = symbol(elf, 'replay_exit', objdump)
        log_pc, _ = symbol(elf, 'replay_log', objdump)
        debug = reference / (name + '.cmd')
        debug.write_text(f'until pc 0 {exit_pc:x}\nreg 0 a0\nstr {log_pc:x}\nrs\n')
        command = [str(SPIKE), '-d', '--debug-cmd=' + str(debug),
                   '--isa=rv64gcv_zvl1024b', '-m2', str(elf)]
        log = reference / (name + '.log')
        with log.open('x') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=30)
        text = log.read_text()
        require(result.returncode == 0 and oracle(entry, text) and
                re.search(r'^0x0{16}$', text, re.M), name + ': Spike full oracle/exit not PASS')
        results.append(dict(name=name, status='PASS', returncode=0, command=command,
            full_oracle_markers=True, log_sha256=base.sha(log), elf_sha256=entry['sha256'],
            soc_elf_sha256=soc[name]['sha256']))
    pins_check(pins)
    base.save(reference / 'reference.json', dict(status='SPIKE_8_PASS_NOT_DUT', results=results,
        spike_sha256=base.sha(SPIKE), old_pins_unchanged=True,
        scope='Source ports with HTIF exit and full scalar oracle; not SoC timing/board acceptance'))
    print('SUCCESSOR_8_HOST_AND_SPIKE_PASS', OUT, flush=True)


if __name__ == '__main__':
    main()
