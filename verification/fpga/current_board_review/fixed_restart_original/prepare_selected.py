#!/usr/bin/env python3
"""Original source-selected single/pair discriminators, explicitly not prefix acceptance."""
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('fixed_original_preparation', Path(__file__).with_name('prepare.py'))
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)

HERE, sha, save, run, require = original.HERE, original.sha, original.save, original.run, original.require
PARENT = HERE / 'prepared01'
OUT = HERE / 'selected01'
CASES = [('fixed_e8_m4_single776', 776), ('fixed_e8_m4_pair775_776', 775)]


def source_select(text, first):
    text = original.replace(text, '    unsigned cap=capacity();',
                            '    unsigned source_trial=0;\n    unsigned cap=capacity();')
    # RNG, original loop enumeration and mask construction are unchanged.
    # Only selected tuples enter their original destination initialization,
    # assembly and complete oracle. Skipped vector calls are not warmup.
    text = original.replace(text, '                    accumulator_trial=accumulator;', f'''                    unsigned original_trial=source_trial++;
                    if(original_trial<{first} || original_trial>776) continue;
                    text("FIXED_ORIGINAL_TRIAL index=");number(original_trial);text("\\n");
                    accumulator_trial=accumulator;''')
    text = original.replace(text, '                    ++checks;',
                            '                    ++checks;\n                    if(source_trial==777) goto selection_complete;')
    return original.replace(text, '    text(errors ? "RVV_MATRIX_FAILED',
                             'selection_complete:\n    text(errors ? "RVV_MATRIX_FAILED')


def markers(name, first):
    count = 777 - first
    return [f'RVV_MATRIX_PASS sew=8 vlmax=512 cases={count} elements={count*512} errors=0 seeds=3 guard_tail_mask_vstart=checked',
            f'FIXED_SELECTION_PASS {name} first={first} last=776 calls={count}',
            'BOARD_CASE_PASS ' + name, 'BOARD_REPLAY_PASS']


def host(case, name, first):
    out = case / 'host'
    out.mkdir()
    count = 777 - first
    model = (HERE / 'host_model.c').read_text()
    model = model.replace('calls>=777', 'calls>=COUNT').replace('calls!=777', 'calls!=COUNT')
    model = original.replace(model, 'calls,op,vl,start,control,(unsigned long long)h',
                              'calls+FIRST,op,vl,start,control,(unsigned long long)h')
    (out / 'selected_model.c').write_text(model)
    exe = out / 'model'
    run(['/usr/bin/cc', '-O2', '-Wall', '-Wextra', '-Werror', '-DSEW=8', '-DFRACTIONAL_SUITE=1',
         '-DHOST_REFERENCE=1', f'-DFIRST={first}', f'-DCOUNT={count}', '-I' + str(case / 'prepared/original'),
         case / 'prepared/case.c', out / 'selected_model.c', '-o', exe], out / 'compile.log')
    run([exe], out / 'positive.log')
    text = (out / 'positive.log').read_text()
    actual = [s for s in text.splitlines() if s.startswith('CALL ')]
    full = [s for s in (PARENT / 'host/prefix.log').read_text().splitlines() if s.startswith('CALL ')]
    require(actual == full[first:777] and len(actual) == count, 'Selected inputs/controls differ from actual777 host trace')
    require(markers(name, first)[0] in text and 'FAIL' not in text and
            f'HOST_END calls={count} injected=0 result=0' in text, 'Selected host oracle failed')
    mutations = [(1, 'active'), (2, 'prestart'), (5, 'left_guard'), (6, 'right_guard'),
                 (7, 'vstart'), (9, 'spurious_vxsat')]
    if first == 775: mutations.append((8, 'lost_sticky_vxsat'))
    for mutation, label in mutations:
        log = out / (label + '.negative.log')
        run([exe, str(mutation)], log, expected=1)
        require('RVV_MATRIX_FAIL' in log.read_text() and
                f'HOST_END calls={count} injected=1 result=1' in log.read_text(), 'Oracle missed ' + label)
    save(out / 'status.json', dict(status='HOST_PASS_SOURCE_SELECTION_NOT_PREFIX',
        matched_parent_log=str(PARENT / 'host/prefix.log'), exact_call_rows=actual,
        selected_original_trials=list(range(first, 777)), negative_rejected=[label for _, label in mutations],
        inapplicable_mutations=['maskedoff', 'tail'] + (['lost_sticky_vxsat'] if first == 776 else [])))


def build(case, name, first):
    prepared = case / 'prepared'
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror', '-nostdlib', '-static',
             '-Wl,--build-id=none', '-Wl,--gc-sections', '-T', prepared / 'replay.ld']
    entries = {}
    for backend in ('soc', 'spike'):
        out = case / backend
        out.mkdir()
        elf = out / (name + '.elf')
        command = [original.CC, *flags, '-DSEW=8', '-DFRACTIONAL_SUITE=1', '-I' + str(prepared / 'original')]
        if backend == 'spike': command.append('-DSPIKE_REFERENCE=1')
        command += [prepared / 'case.c', prepared / 'original/scenario.S', prepared / 'main.c',
                    prepared / 'startup.S', prepared / 'runtime.c', '-lgcc', '-o', elf]
        run(command, out / 'compile.log')
        run([original.CC.with_name('riscv64-unknown-elf-objdump'), '-d', elf], out / 'program.dis')
        nm = subprocess.check_output([original.CC.with_name('riscv64-unknown-elf-nm'), '-n', elf], text=True, timeout=15)
        symbols = {m[3]: int(m[1], 16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$', nm, re.M)}
        require(symbols['__bss_end'] < 0x800f0000, 'Memory bound')
        save(out / 'symbols.json', symbols)
        body = (out / 'program.dis').read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        parent_body = (PARENT / backend / (original.ID + '.dis')).read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        bits = lambda s: re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{4,8})\s', s, re.M)
        require(bits(body) == bits(parent_body) and len(bits(body)) == 24, 'Original helper instruction bytes changed')
        target = re.search(r'^\s*([0-9a-f]+):\s+9c880c57\s+vsmul.vv\s+v24,v8,v16,v0.t', body, re.M)
        require(target is not None, 'Original target missing')
        entries[backend] = dict(path=str(elf), sha256=sha(elf), cases=[name], configurations=777-first,
            selected_original_trials=list(range(first,777)), original_prefix_acceptance=False,
            target_pc=int(target[1],16), target_opcode='9c880c57', target_count=777-first,
            pass_markers=markers(name,first), helper_24_instruction_bytes_identical=True)
    return entries


def reference(case, name, first):
    out = case / 'reference'
    out.mkdir()
    symbols = json.loads((case / 'spike/symbols.json').read_text())
    commands = out / 'debug.cmd'
    commands.write_text(f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]:x}\nrs\n')
    elf = case / 'spike' / (name + '.elf')
    log = out / 'spike.log'
    seconds = run([original.SPIKE, '-d', '--debug-cmd=' + str(commands), '--isa=' + original.ISA, '-m2', elf], log, timeout=60)
    text = log.read_text()
    values = re.findall(r'^0x([0-9a-f]{16})$', text, re.M)
    require(len(values) == 3 and int(values[0],16) == 0, 'Spike exit/counters')
    require(not re.search(r'FAIL|TRAP|Error|FATAL', text), 'Spike raw failure')
    for marker in markers(name,first): require(text.count(marker) == 1, 'Missing/duplicate oracle marker')
    require(re.findall(r'FIXED_ORIGINAL_TRIAL index=(\d+)',text) == [str(n) for n in range(first,777)], 'Original call selection differs')
    result = dict(name=name, status='SPIKE_PASS_SOURCE_SELECTION_NOT_PREFIX', calls=777-first,
        original_trials=list(range(first,777)), instructions_to_replay_exit=int(values[1],16),
        cycles_to_replay_exit=int(values[2],16), elapsed_s=seconds,
        elf_sha256=sha(elf), log_sha256=sha(log), original_prefix_acceptance=False, DUT_started=False)
    save(out / 'status.json', result)
    return result


def main():
    parent_pins = json.loads((PARENT / 'pins.json').read_text())
    require(all(sha(path) == digest for path,digest in parent_pins.items()), 'Immutable777 input drift')
    parent_digest = sha(PARENT / 'pins.json')
    OUT.mkdir(exist_ok=False)
    sys.path.insert(0,str(original.helper.ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart,probe_paths
    cc,probe = probe_paths(original.helper.ROOT)
    require(check_spike_vstart(original.SPIKE,cc,OUT / 'vstart_probe',probe)['status'] == 'PASS', 'Spike vstart unsupported')
    all_entries = {b:{} for b in ('soc','spike')}
    costs = []
    tuples = json.loads((PARENT / 'host/expected_calls.json').read_text())
    for name,first in CASES:
        case = OUT / name
        prepared = case / 'prepared'
        shutil.copytree(PARENT / 'prepared/original',prepared / 'original')
        for file in ('startup.S','runtime.c','replay.ld'):
            shutil.copyfile(PARENT / 'prepared' / file,prepared / file)
        runtime = (PARENT / 'prepared/runtime_only.c').read_text()
        source = source_select(runtime,first)
        (prepared / 'case.c').write_text(source)
        (prepared / 'selection.diff').write_text(''.join(difflib.unified_diff(runtime.splitlines(True),source.splitlines(True))))
        main = (PARENT / 'prepared/main.c').read_text().replace(original.ID,name)
        main = original.replace(main,'FIXED_PREFIX_PASS ' + name + ' trials=777',markers(name,first)[1])
        (prepared / 'main.c').write_text(main)
        save(case / 'scope.json',dict(name=name,selected_original_calls=tuples[first:777], original_calls_skipped=first,
            skipped_vector_calls_executed=False, fabricated_warmup=False, full_original_oracle_per_selected_call=True,
            original_source_initialization_and_rng=True, prefix777_acceptance=False, original_linux_replayed=False))
        host(case,name,first)
        for backend,entry in build(case,name,first).items(): all_entries[backend][name] = entry
        costs.append(reference(case,name,first))
    for backend,entries in all_entries.items():
        directory = OUT / backend
        directory.mkdir()
        save(directory / 'programs.json',dict(schema_version=1,backend=backend,programs=entries,
            compiler=dict(path=str(original.CC),sha256=sha(original.CC)),vcs_started=False))
    full = json.loads((PARENT / 'reference/status.json').read_text())
    costs.append(dict(full,name=original.ID,calls=777,original_trials='0..776 contiguous',original_prefix_acceptance='REFERENCE_ONLY'))
    require(sha(PARENT / 'pins.json') == parent_digest and
            all(sha(path) == digest for path,digest in parent_pins.items()), '777 changed during preparation')
    save(OUT / 'costs.json',dict(status='REFERENCE_COSTS_ONLY_NO_DUT',rows=costs))
    pins = dict(parent_pins)
    pins.update({str(p):sha(p) for p in OUT.rglob('*') if p.is_file()})
    for p in (Path(__file__),PARENT / 'pins.json',PARENT / 'complete.json'): pins[str(p)] = sha(p)
    save(OUT / 'pins.json',pins)
    save(OUT / 'complete.json',dict(status='READY_SINGLE776_PAIR775_776_SPIKE_PASS_NOT_DUT',
        parent777_pins_unchanged=True,pin_count=len(pins),pins_sha256=sha(OUT / 'pins.json'),
        original_prefix777_acceptance=False,DUT_started=False,reference_costs=costs))
    print((OUT / 'complete.json').read_text())


if __name__ == '__main__':
    main()
