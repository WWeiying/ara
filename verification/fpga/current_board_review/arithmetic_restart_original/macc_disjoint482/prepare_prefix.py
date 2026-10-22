#!/usr/bin/env python3
"""Prepare exactly one original482-call prefix, host+Spike only, never VCS."""
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from recover_identity import HERE, CAMP, ARCH, SOURCE, NAME, EXPECTED
spec = importlib.util.spec_from_file_location('immutable_port_helper', HERE.parent.parent / 'mask_alias_original/port.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
sha, save, run, require = helper.sha, helper.save, helper.run, helper.require
CC, SPIKE, ISA = helper.CC, helper.SPIKE, helper.ISA
IDENTITY = HERE / 'identity02'
ID = 'macc_disjoint_e8_m4_prefix482'
COUNT, CAP = 482, 512
MARKER = 'RVV_MATRIX_PASS sew=8 vlmax=512 cases=482 elements=246784 errors=0 seeds=5 guard_tail_mask_vstart=checked'
MARKERS = [MARKER, f'MACC_PREFIX_PASS {ID} trials=482', f'BOARD_CASE_PASS {ID}', 'BOARD_REPLAY_PASS']
TRACE_RE = r'RVV_TRIAL seed=(\d+) vl=(\d+) mask=(\d+) vstart=(\d+) completed=(\d+)'
FAIL = re.compile(r'RVV_MATRIX_FAIL(?:ED)?|BOARD_\w*(?:FAIL|TRAP|MISMATCH)|\b(?:FATAL|ERROR)\b|UNSUPPORTED', re.I)


def replace(s, old, new):
    require(s.count(old) == 1, 'Unexpected source shape: ' + old)
    return s.replace(old, new)


def adapt(s):
    first, last = s.index('static long syscall3('), s.index('static void text(')
    s = s[:first] + 'extern long replay_write(long,long,long,long);\n#define syscall3 replay_write\n' + s[last:]
    s = replace(s, 'static void finish(long code) {\n    syscall3(94,code,0,0);for(;;){}\n}\n', '')
    s = replace(s, 'void probe_main(void)', 'int macc_main(void)')
    # Bare-metal UART writes have no Linux tty-drain service; keep every trace print.
    s = replace(s, '''                        /* TCSBRK with nonzero argument drains the tty output. */
                        if(syscall3(29,1,0x5409,1)) {
                            text("RVV_TRACE_TTY_DRAIN_FAILED\\n");finish(2);
                        }''', '                        /* Linux tty drain omitted; OS timing is not reproduced. */')
    s = replace(s, 'finish(2);', 'return 2;')
    s = replace(s, 'finish(errors ? 1:0);', 'return errors ? 1:0;')
    s = s[:s.index('__asm__(".global _start')]
    require('ecall' not in s and 'finish(' not in s and 'syscall3(29' not in s, 'Unadapted OS service')
    return s


def bound(s):
    s = replace(s, '                    ++checks;',
                '                    ++checks;\n                    if(checks==482) goto prefix_complete;')
    return replace(s, '    text(errors ? "RVV_MATRIX_FAILED',
                   'prefix_complete:\n    text(errors ? "RVV_MATRIX_FAILED')


def expected():
    rng, m64 = 0x937ad68de41c725f, (1 << 64) - 1
    a, b = [], []
    for i in range(CAP):
        rng ^= (rng << 13) & m64; rng ^= rng >> 7; rng ^= (rng << 17) & m64
        x, y = rng & 255, (rng >> 19) & 255
        if i % 8 == 0: x = y = 0
        elif i % 8 == 1: x, y = 255, 1
        elif i % 8 == 2: x, y = 128, 255
        elif i % 8 == 3: y = 8
        a.append(x); b.append(y)
    b[0] = 0  # Original INTEGER_SCALAR_SUITE scalar table, seed0.
    rows, tuples, prints = [], [], []
    for vl in (0, 1, 2, 3, 256, 511, 512):
        for accumulator in range(5):
            old = [0 if accumulator == 0 else 255 if accumulator == 1 else 128 if accumulator == 2
                   else (170 if i & 1 else 85) if accumulator == 3 else
                   (0x937ad68de41c725f + 0x9e3779b97f4a7c15 * i) & 255 for i in range(CAP)]
            for mode in range(4):
                mask = bytearray(128)
                for i in range(CAP):
                    if mode == 0 or (mode == 1 and i & 1) or (mode == 2 and i % 7 == 2): mask[i // 8] |= 1 << (i % 8)
                for start in (1, vl // 2, vl, 511):
                    n = len(rows)
                    h = helper.fnv(bytes(a + b) + mask + bytes([91] + old + [91]))
                    result = list(old)
                    for i in range(start, vl):
                        if mask[i // 8] & (1 << (i % 8)): result[i] = (old[i] + a[i] * b[i]) & 255
                    after = helper.fnv(bytes([91] + result + [91]))
                    rows.append(f'CALL {n} 0 {vl} {start} 0 {h:016x} {after:016x}')
                    tuples.append(dict(trial=n, seed=0, op=0, accumulator=accumulator, mode=mode,
                                       vl=vl, vstart=start, rm=0, input_fnv64=f'{h:016x}', output_fnv64=f'{after:016x}'))
                    if accumulator == 0 and mode == 0: prints.append(('0', str(vl), '0', str(start), str(n)))
                    if len(rows) == COUNT:
                        return rows, tuples, prints
    raise ValueError('Prefix counter not reached')


def oracle(text, returncode):
    return returncode == 0 and not FAIL.search(text) and all(text.splitlines().count(m) == 1 for m in MARKERS)


def host(case, out, want):
    folder = out / 'host'; folder.mkdir()
    positives, negatives = [], []
    for label, source in [('prefix', case / 'case.c'), ('full_capture', case / 'runtime_only.c')]:
        text = replace(source.read_text(), '__asm__ volatile("csrr %0,vlenb":"=r"(max_start));',
                       'max_start=128; /* Host-only VLENB substitution. */')
        host_source = folder / (label + '.c'); host_source.write_text(text)
        exe = folder / label
        cmd = ['/usr/bin/cc', '-O2', '-Wall', '-Wextra', '-Werror', '-DSEW=8', '-I' + str(case / 'original')]
        if label == 'full_capture': cmd.append('-DFULL_CAPTURE=1')
        run(cmd + [host_source, HERE / 'host_model.c', '-o', exe], folder / (label + '.compile.log'))
        log = folder / (label + '.log'); run([exe], log)
        text = log.read_text()
        require([s for s in text.splitlines() if s.startswith('CALL ')] == want, 'Independent input/result/order mismatch')
        require('RVV_MATRIX_FAIL' not in text and 'HOST_END calls=482 injected=0 result=0' in text, 'Original host oracle failed')
        if label == 'prefix': require(text.splitlines().count(MARKER) == 1, 'Missing original count marker')
        positives.append(dict(mode=label, status='PASS', calls=COUNT, log_sha256=sha(log)))
    for number, label in enumerate(['active', 'prestart', 'maskedoff', 'tail', 'left_guard', 'right_guard',
                                    'vstart_low', 'return_high', 'dropped_accumulator'], 1):
        log = folder / ('negative_' + label + '.log')
        run([folder / 'prefix', str(number)], log, expected=1)
        require('RVV_MATRIX_FAIL' in log.read_text() and 'HOST_END calls=482 injected=1 result=1' in log.read_text(),
                'Original oracle did not reject ' + label)
        negatives.append(dict(mutation=label, rejected=True, log_sha256=sha(log)))
    valid = '\n'.join(MARKERS) + '\n'
    checker_tests = [oracle(valid, 0), not oracle(valid + 'RVV_MATRIX_FAIL op=vmacc.vv\n', 0),
                     not oracle(valid, 1), not oracle(valid.replace('cases=482', 'cases=481'), 0),
                     not oracle(valid.replace('BOARD_REPLAY_PASS', ''), 0),
                     not oracle(valid + 'BOARD_REPLAY_TRAP\n', 0)]
    require(all(checker_tests), 'Terminal checker negative failed')
    save(folder / 'status.json', dict(status='HOST_PASS_NOT_DUT', positive=positives, negative=negatives,
                                     checker_tests=len(checker_tests)))


def build(prepared, out):
    case = prepared / ID
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror', '-nostdlib', '-static',
             '-Wl,--build-id=none', '-Wl,--gc-sections', '-T', prepared / 'replay.ld', '-DSEW=8',
             '-I' + str(case / 'original')]
    for backend in ('soc', 'spike'):
        folder = out / backend; folder.mkdir(); elf = folder / (ID + '.elf')
        cmd = [CC, *flags]
        if backend == 'spike': cmd.append('-DSPIKE_REFERENCE=1')
        run(cmd + [case / 'case.c', case / 'original/scenario.S', case / 'main.c',
                   prepared / 'startup.S', prepared / 'runtime.c', '-lgcc', '-o', elf], folder / 'compile.log')
        run([CC.with_name('riscv64-unknown-elf-objdump'), '-d', elf], folder / 'program.dis')
        nm = subprocess.check_output([CC.with_name('riscv64-unknown-elf-nm'), '-n', elf], text=True, timeout=15)
        symbols = {m[3]: int(m[1], 16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$', nm, re.M)}
        require(symbols['__bss_end'] < 0x800f0000, 'Memory bound')
        save(folder / 'symbols.json', symbols)
        body = (folder / 'program.dis').read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        target = re.search(r'^\s*([0-9a-f]+):\s+b5042c57\s+vmacc.vv\s+v24,v8,v16,v0.t', body, re.M)
        require(target is not None, 'Wrong target opcode')
        old_body = []
        for line in (IDENTITY / 'original.dis').read_text().splitlines():
            m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+', line)
            if m and 0x108c0 <= int(m[1], 16) <= 0x108f0: old_body.append(m[2])
        new_body = re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]+)\s+', body, re.M)
        require(old_body == new_body and len(old_body) == 13, 'Original op0 setup/target/store bytes changed')
        entry = dict(path=str(elf), sha256=sha(elf), cases=[ID], configurations=COUNT, pass_markers=MARKERS,
                     target_pc=int(target[1], 16), target_opcode='b5042c57', original_routine_encoding_equal=True,
                     original_routine_instructions=len(old_body))
        save(folder / 'programs.json', dict(schema_version=1, backend='vcs-soc' if backend == 'soc' else 'spike-htif',
              prepared=str(prepared), provenance_sha256=sha(prepared / 'provenance.json'), programs={ID: entry},
              compiler=dict(path=str(CC), sha256=sha(CC)), vcs_started=False))


def reference(out, traces):
    folder = out / 'reference'; folder.mkdir()
    sys.path.insert(0, str(helper.ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    cc, source = probe_paths(helper.ROOT)
    probe = check_spike_vstart(SPIKE, cc, folder / 'vstart_probe', source)
    require(probe['status'] == 'PASS', 'Spike does not support nonzero vstart')
    symbols = json.loads((out / 'spike/symbols.json').read_text())
    elf = out / 'spike' / (ID + '.elf')
    cmdfile = folder / 'debug.cmd'
    cmdfile.write_text(f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]:x}\nrs\n')
    log = folder / 'spike.log'
    elapsed = run([SPIKE, '-d', '--debug-cmd=' + str(cmdfile), '--isa=' + ISA, '-m2', elf], log, timeout=180)
    text = log.read_text(); values = re.findall(r'^0x([0-9a-f]{16})$', text, re.M)
    require(len(values) == 3 and int(values[0], 16) == 0, 'Spike nonzero exit/counter failure')
    require(oracle(text, 0), 'Spike original scalar oracle or raw markers failed')
    require(re.findall(TRACE_RE, text) == traces, 'Spike trace differs from original482-call prefix')
    result = dict(status='SPIKE_PASS_NOT_DUT', name=ID, configurations=COUNT, isa=ISA,
                  instructions_to_replay_exit=int(values[1], 16), cycle_counter=int(values[2], 16),
                  elapsed_s=elapsed, elf_sha256=sha(elf), log_sha256=sha(log), historical_prints_matched=len(traces))
    save(folder / 'status.json', result)
    return result


def main(out):
    out = out.resolve(); require(out.is_relative_to(HERE) and out != HERE and not out.exists(), 'Fresh owned output required')
    out.mkdir()
    try:
        report = json.loads((IDENTITY / 'report.json').read_text())
        require(report['whole_elf_byte_equal'] and sha(IDENTITY / NAME) == EXPECTED, 'Original ELF identity not proven')
        require(sha(IDENTITY / 'reconstructed_oracle.c') == report['reconstructed_c_sha256'], 'Identity source drift')
        pins = dict(report['input_pins'])
        for p in [IDENTITY / 'report.json', IDENTITY / 'reconstructed_oracle.c', IDENTITY / NAME,
                  IDENTITY / 'scenario.S', IDENTITY / 'operations.h', HERE / 'recover_identity.py',
                  HERE / 'prepare_prefix.py', HERE / 'host_model.c', Path(helper.__file__),
                  Path(helper.prepare.__file__), CC, SPIKE]: pins[str(p)] = sha(p)
        want, tuples, traces = expected()
        require(tuples[-1] == dict(trial=481, seed=0, op=0, accumulator=0, mode=0, vl=512, vstart=256,
                                  rm=0, input_fnv64=tuples[-1]['input_fnv64'], output_fnv64=tuples[-1]['output_fnv64']), 'Wrong last tuple')
        scene = CAMP / 'rvv_recovery08_14/terminal_scene'
        old_report = json.loads((scene / 'report.json').read_text())
        rows = [r for r in old_report['results'] if r['name'] == NAME]
        require(len(rows) == 1 and re.findall(TRACE_RE, rows[0]['output']) == traces, 'Historical trace linkage failed')
        require(sha(scene / NAME) == EXPECTED, 'Scene ELF differs')
        for p in [scene / 'report.json', scene / NAME, scene / 'uart.bin', ARCH / 'reference_1024.json']:
            pins[str(p)] = sha(p)
        save(out / 'expected_inputs.json', tuples)
        save(out / 'historical_identity.json', dict(original_elf_sha256=EXPECTED, source_text_recovered=False,
             whole_original_elf_byte_reconstructed=True, source_report_sha256=sha(IDENTITY / 'report.json'),
             scene_result=rows[0], trace_matches=traces, first_trial=0, last_trial=481,
             target_original_pc='0x108e0', target_opcode='b5042c57', internal_acceptance_proven=False))
        prepared = out / 'prepared'; prepared.mkdir(); case = prepared / ID; original = case / 'original'; original.mkdir(parents=True)
        parent = HERE.parent / 'prepared02/prepared'
        helper.prepare.check(parent)
        for name in ('startup.S', 'runtime.c', 'replay.ld'):
            shutil.copyfile(parent / name, prepared / name); pins[str(parent / name)] = sha(parent / name)
        for src, dst in [('reconstructed_oracle.c', 'binary_equivalent_oracle.c'), ('scenario.S', 'scenario.S'), ('operations.h', 'operations.h')]:
            shutil.copyfile(IDENTITY / src, original / dst)
        original_text = (IDENTITY / 'reconstructed_oracle.c').read_text()
        runtime = adapt(original_text); source = bound(runtime)
        (case / 'runtime_only.c').write_text(runtime); (case / 'case.c').write_text(source)
        for label, before, after in [('runtime_adaptation', original_text, runtime), ('prefix', runtime, source)]:
            (case / (label + '.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='before', tofile='after')))
        (case / 'main.c').write_text('\n'.join([
            'extern int macc_main(void);', 'extern void replay_text(const char *);',
            'extern volatile unsigned long replay_case;', 'int main(void) { unsigned long vlenb;',
            '__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));',
            'if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\\n"); return 90; }', 'replay_case=1;',
            f'replay_text("BOARD_CASE_BEGIN {ID}\\n");', 'int result=macc_main();',
            f'if(result) {{ replay_text("BOARD_CASE_FAIL {ID}\\n"); return result; }}',
            f'replay_text("MACC_PREFIX_PASS {ID} trials=482\\nBOARD_CASE_PASS {ID}\\nBOARD_REPLAY_PASS\\n");',
            'return 0;', '}']) + '\n')
        save(out / 'input_pins.json', pins)
        save(prepared / 'provenance.json', dict(schema_version=1, cases=[dict(id=ID, original=NAME, configurations=COUNT,
             sew=8, lmul='m4', first_trial=0, last_trial=481, source_text_recovered=False)], vlen=1024, nr_lanes=4,
             scope='Original482-call prefix; exact original full ELF rebuilt; not whole22400 or Linux execution',
             input_pins_sha256=sha(out / 'input_pins.json'), historical_identity_sha256=sha(out / 'historical_identity.json'),
             files={str(p.relative_to(prepared)): sha(p) for p in prepared.rglob('*') if p.is_file()}))
        host(case, out, want)
        build(prepared, out)
        result = reference(out, traces)
        for p, digest in pins.items(): require(sha(Path(p)) == digest, 'Pinned input changed: ' + p)
        helper.prepare.check(prepared)
        status = dict(status='READY_ORIGINAL_MACC_PREFIX482_HOST_SPIKE_NOT_DUT', reference=result,
                      original_elf_sha256=EXPECTED, soc_programs=str(out / 'soc/programs.json'),
                      soc_programs_sha256=sha(out / 'soc/programs.json'), VCS_launched=False, RTL_modified=False,
                      full22400_executed=False, prefixes5_modified=False)
        save(out / 'status.json', status); print(json.dumps(status, indent=2))
    except Exception as error:
        save(out / 'failure.json', dict(status='NOT_READY', reason=repr(error)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args().out)
