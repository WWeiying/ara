#!/usr/bin/env python3
"""Source-selected original vmacc boundary calls; host/Spike only, not prefix closure."""
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('immutable_macc_prefix', HERE / 'prepare_prefix.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
sha, save, run, require = original.sha, original.save, original.run, original.require
PARENT = HERE / 'prepared02'
OUT = HERE / 'selected01'
CASES = [('macc_e8_m4_single481', 481), ('macc_e8_m4_pair480_481', 480)]


def source_select(text, first):
    text = original.replace(text, '    unsigned cap=capacity();',
                            '    unsigned source_trial=0;\n    unsigned cap=capacity();')
    # Preserve RNG and loop enumeration; skip before destination setup and oracle.
    text = original.replace(text, '                    accumulator_trial=accumulator;', f'''                    unsigned original_trial=source_trial++;
                    if(original_trial<{first} || original_trial>481) continue;
                    text("MACC_ORIGINAL_TRIAL index=");number(original_trial);text("\\n");
                    accumulator_trial=accumulator;''')
    text = original.replace(text, '                    ++checks;',
                            '                    ++checks;\n                    if(source_trial==482) goto selection_complete;')
    return original.replace(text, '    text(errors ? "RVV_MATRIX_FAILED',
                            'selection_complete:\n    text(errors ? "RVV_MATRIX_FAILED')


def markers(name, first):
    count = 482 - first
    return [f'RVV_MATRIX_PASS sew=8 vlmax=512 cases={count} elements={count*512} errors=0 seeds=5 guard_tail_mask_vstart=checked',
            f'MACC_SELECTION_PASS {name} first={first} last=481 calls={count}',
            'BOARD_CASE_PASS ' + name, 'BOARD_REPLAY_PASS']


def accepted(text, code, name, first):
    return code == 0 and not original.FAIL.search(text) and all(
        text.splitlines().count(m) == 1 for m in markers(name, first)) and re.findall(
            r'MACC_ORIGINAL_TRIAL index=(\d+)', text) == [str(n) for n in range(first, 482)]


def host(case, name, first):
    out = case / 'host'; out.mkdir()
    count = 482 - first
    model = (HERE / 'host_model.c').read_text()
    model = model.replace('calls==482', 'calls==COUNT').replace('calls>=482', 'calls>=COUNT').replace('calls!=482', 'calls!=COUNT')
    model = original.replace(model, 'calls,op,vl,start,rm,', 'calls+FIRST,op,vl,start,rm,')
    (out / 'model.c').write_text(model)
    text = original.replace((case / 'prepared/case.c').read_text(),
                            '__asm__ volatile("csrr %0,vlenb":"=r"(max_start));',
                            'max_start=128; /* Host-only VLENB substitution. */')
    (out / 'case.c').write_text(text)
    exe = out / 'model'
    run(['/usr/bin/cc', '-O2', '-Wall', '-Wextra', '-Werror', '-DSEW=8', f'-DFIRST={first}', f'-DCOUNT={count}',
         '-I' + str(case / 'prepared/original'), out / 'case.c', out / 'model.c', '-o', exe], out / 'compile.log')
    run([exe], out / 'positive.log')
    text = (out / 'positive.log').read_text()
    actual = [s for s in text.splitlines() if s.startswith('CALL ')]
    for label in ('prefix', 'full_capture'):
        rows = [s for s in (PARENT / 'host' / (label + '.log')).read_text().splitlines() if s.startswith('CALL ')]
        require(actual == rows[first:482] and len(actual) == count, 'Parent snapshot mismatch: ' + label)
    require(actual == original.expected()[0][first:482], 'Independent Python snapshot mismatch')
    require(markers(name, first)[0] in text and not original.FAIL.search(text) and
            f'HOST_END calls={count} injected=0 result=0' in text, 'Host original oracle failed')
    mutations = [(1, 'active'), (2, 'prestart'), (5, 'left_guard'), (6, 'right_guard'),
                 (7, 'vstart_low'), (8, 'return_high')]
    for mutation, label in mutations:
        log = out / (label + '.negative.log')
        run([exe, str(mutation)], log, expected=1)
        require('RVV_MATRIX_FAIL' in log.read_text() and
                f'HOST_END calls={count} injected=1 result=1' in log.read_text(), 'Oracle missed ' + label)
    valid = '\n'.join([*(f'MACC_ORIGINAL_TRIAL index={n}' for n in range(first, 482)), *markers(name, first)]) + '\n'
    tests = [accepted(valid, 0, name, first), not accepted(valid + 'RVV_MATRIX_FAIL op=vmacc.vv\n', 0, name, first),
             not accepted(valid, 1, name, first), not accepted(valid.replace('BOARD_REPLAY_PASS', ''), 0, name, first),
             not accepted(valid.replace(f'cases={count}', 'cases=482'), 0, name, first),
             not accepted(valid + 'BOARD_REPLAY_TRAP\n', 0, name, first),
             not accepted(valid.replace('index=481', 'index=482'), 0, name, first)]
    require(all(tests), 'Terminal checker negative failure')
    save(out / 'status.json', dict(status='HOST_PASS_SOURCE_SELECTION_NOT_PREFIX', exact_call_rows=actual,
         parent_prefix_and_full_capture_rows_identical=True, independent_python_rows_identical=True,
         negative_rejected=[label for _, label in mutations], checker_tests=len(tests),
         inapplicable_mutations=['maskedoff', 'tail', 'dropped_accumulator']))


def build(case, name, first):
    prepared = case / 'prepared'
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror', '-nostdlib', '-static',
             '-Wl,--build-id=none', '-Wl,--gc-sections', '-T', prepared / 'replay.ld', '-DSEW=8',
             '-I' + str(prepared / 'original')]
    entries = {}
    for backend in ('soc', 'spike'):
        out = case / backend; out.mkdir(); elf = out / (name + '.elf')
        command = [original.CC, *flags]
        if backend == 'spike': command.append('-DSPIKE_REFERENCE=1')
        run(command + [prepared / 'case.c', prepared / 'original/scenario.S', prepared / 'main.c',
                       prepared / 'startup.S', prepared / 'runtime.c', '-lgcc', '-o', elf], out / 'compile.log')
        run([original.CC.with_name('riscv64-unknown-elf-objdump'), '-d', elf], out / 'program.dis')
        nm = subprocess.check_output([original.CC.with_name('riscv64-unknown-elf-nm'), '-n', elf], text=True, timeout=15)
        symbols = {m[3]: int(m[1], 16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$', nm, re.M)}
        require(symbols['__bss_end'] < 0x800f0000, 'Memory bound')
        save(out / 'symbols.json', symbols)
        body = (out / 'program.dis').read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        parent_body = (PARENT / backend / 'program.dis').read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        bits = lambda s: re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{4,8})\s', s, re.M)
        require(bits(body) == bits(parent_body) and len(bits(body)) == 13, 'Original helper bytes changed')
        target = re.search(r'^\s*([0-9a-f]+):\s+b5042c57\s+vmacc.vv\s+v24,v8,v16,v0.t', body, re.M)
        require(target is not None, 'Original target missing')
        entries[backend] = dict(path=str(elf), sha256=sha(elf), cases=[name], configurations=482-first,
             selected_original_trials=list(range(first, 482)), original_prefix_acceptance=False,
             target_pc=int(target[1], 16), target_opcode='b5042c57', target_count=482-first,
             pass_markers=markers(name, first), helper_13_instruction_bytes_identical=True)
    return entries


def reference(case, name, first):
    out = case / 'reference'; out.mkdir()
    symbols = json.loads((case / 'spike/symbols.json').read_text())
    commands = out / 'debug.cmd'
    commands.write_text(f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]:x}\nrs\n')
    elf = case / 'spike' / (name + '.elf'); log = out / 'spike.log'
    seconds = run([original.SPIKE, '-d', '--debug-cmd=' + str(commands), '--isa=' + original.ISA, '-m2', elf], log, timeout=60)
    text = log.read_text(); values = re.findall(r'^0x([0-9a-f]{16})$', text, re.M)
    require(len(values) == 3 and int(values[0], 16) == 0, 'Spike exit/counters')
    require(accepted(text, 0, name, first), 'Spike scalar oracle/markers failed')
    result = dict(name=name, status='SPIKE_PASS_SOURCE_SELECTION_NOT_PREFIX', calls=482-first,
         original_trials=list(range(first, 482)), isa=original.ISA, instructions_to_replay_exit=int(values[1], 16),
         cycles_to_replay_exit=int(values[2], 16), elapsed_s=seconds, elf_sha256=sha(elf), log_sha256=sha(log),
         original_prefix_acceptance=False, DUT_started=False)
    save(out / 'status.json', result)
    return result


def main():
    pins = json.loads((PARENT / 'input_pins.json').read_text())
    pins.update({str(p): sha(p) for p in PARENT.rglob('*') if p.is_file()})
    require(all(sha(Path(p)) == digest for p, digest in pins.items()), 'Immutable prefix input drift')
    original.helper.prepare.check(PARENT / 'prepared')
    require(json.loads((PARENT / 'status.json').read_text())['status'] == 'READY_ORIGINAL_MACC_PREFIX482_HOST_SPIKE_NOT_DUT', 'Prefix not ready')
    OUT.mkdir(exist_ok=False)
    sys.path.insert(0, str(original.helper.ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    cc, probe = probe_paths(original.helper.ROOT)
    require(check_spike_vstart(original.SPIKE, cc, OUT / 'vstart_probe', probe)['status'] == 'PASS', 'Spike vstart unsupported')
    all_entries = {b: {} for b in ('soc', 'spike')}; costs = []
    tuples = json.loads((PARENT / 'expected_inputs.json').read_text())
    source_parent = PARENT / 'prepared' / original.ID
    for name, first in CASES:
        case = OUT / name; prepared = case / 'prepared'
        shutil.copytree(source_parent / 'original', prepared / 'original')
        for file in ('startup.S', 'runtime.c', 'replay.ld'):
            shutil.copyfile(PARENT / 'prepared' / file, prepared / file)
        runtime = (source_parent / 'runtime_only.c').read_text(); source = source_select(runtime, first)
        (prepared / 'case.c').write_text(source)
        (prepared / 'selection.diff').write_text(''.join(difflib.unified_diff(runtime.splitlines(True), source.splitlines(True))))
        main_text = (source_parent / 'main.c').read_text().replace(original.ID, name)
        main_text = original.replace(main_text, 'MACC_PREFIX_PASS ' + name + ' trials=482', markers(name, first)[1])
        (prepared / 'main.c').write_text(main_text)
        save(case / 'scope.json', dict(name=name, selected_original_calls=tuples[first:482], original_calls_skipped=first,
             skipped_vector_calls_executed=False, fabricated_warmup=False, full_original_oracle_per_selected_call=True,
             original_source_initialization_and_rng=True, prefix482_acceptance=False, original_linux_replayed=False,
             old_c_text_recovered=False, whole_original_elf_byte_reconstructed=True,
             original_linux_elf_sha256=original.EXPECTED, csr_scope='Original vstart low32 and returned high32 container only; no new fflags/vxrm/vxsat sampling'))
        host(case, name, first)
        for backend, entry in build(case, name, first).items(): all_entries[backend][name] = entry
        costs.append(reference(case, name, first))
    for backend, entries in all_entries.items():
        directory = OUT / backend; directory.mkdir()
        save(directory / 'programs.json', dict(schema_version=1, backend=backend, programs=entries,
             compiler=dict(path=str(original.CC), sha256=sha(original.CC)), vcs_started=False))
    require(all(sha(Path(p)) == digest for p, digest in pins.items()), 'Parent changed during preparation')
    save(OUT / 'costs.json', dict(status='REFERENCE_COSTS_ONLY_NO_DUT', rows=costs,
         full_prefix_instructions=json.loads((PARENT / 'reference/status.json').read_text())['instructions_to_replay_exit']))
    pins.update({str(p): sha(p) for p in OUT.rglob('*') if p.is_file()})
    pins[str(Path(__file__).resolve())] = sha(Path(__file__))
    save(OUT / 'pins.json', pins)
    save(OUT / 'complete.json', dict(status='READY_SINGLE481_PAIR480_481_HOST_SPIKE_NOT_DUT',
         parent482_pins_unchanged=True, pin_count=len(pins), pins_sha256=sha(OUT / 'pins.json'),
         original_prefix482_acceptance=False, DUT_started=False, reference_costs=costs))
    print((OUT / 'complete.json').read_text())


if __name__ == '__main__':
    main()
