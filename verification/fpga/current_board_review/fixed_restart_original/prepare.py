#!/usr/bin/env python3
"""Faithful original777-call vsmul prefix: source/host/Spike preparation only."""
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from recover import HERE, ARCH, CAMP, SOURCE, NAME, EXPECTED, OLD_C, sha, save

spec = importlib.util.spec_from_file_location('fixed_port_helpers', HERE.parent / 'mask_alias_original/port.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
CC, SPIKE, ISA, run, require = helper.CC, helper.SPIKE, helper.ISA, helper.run, helper.require
OUT = HERE / 'prepared01'
ID = 'fixed_e8_m4_prefix777'
MARKER = 'RVV_MATRIX_PASS sew=8 vlmax=512 cases=777 elements=397824 errors=0 seeds=3 guard_tail_mask_vstart=checked'


def replace(s, old, new):
    require(s.count(old) == 1, 'Source shape differs: ' + old)
    return s.replace(old, new)


def adapt(s):
    begin, end = s.index('static long syscall3('), s.index('static void text(')
    s = s[:begin] + '''extern long replay_write(long,long,long,long);
static long syscall3(long n,long x,long y,long z) {
    /* Original Linux tty drain has no service counterpart in bare metal. */
    if(n==29 && x==1 && y==0x5409 && z==1) return 0;
    return replay_write(n,x,y,z);
}
''' + s[end:]
    begin = s.index('static void finish(')
    end = s.index('#if !defined(INTEGER_MACC_SUITE)', begin)
    s = s[:begin] + s[end:]
    s = replace(s, 'void probe_main(void)', 'int fixed_main(void)')
    s = s.replace('finish(', 'return(')
    s = s[:s.index('__asm__(".global _start')]
    instruction = '    __asm__ volatile("csrr %0,vlenb":"=r"(max_start));'
    s = replace(s, instruction, '#ifdef HOST_REFERENCE\n    max_start=128;\n#else\n' + instruction + '\n#endif')
    require('ecall' not in s and 'finish(' not in s, 'Linux service remained')
    return s


def expected():
    rows, tuples = [], []
    random, mask64 = 0x937ad68de41c725f, (1 << 64) - 1
    a, b = [], []
    for i in range(512):
        random ^= (random << 13) & mask64
        random ^= random >> 7
        random ^= (random << 17) & mask64
        x, y = random & 255, (random >> 19) & 255
        if i % 8 == 0: x = y = 0
        elif i % 8 == 1: x, y = 255, 1
        elif i % 8 == 2: x, y = 128, 255
        elif i % 8 == 3: y = 8
        a.append(x); b.append(y)
    for vl in (0, 1, 2, 3, 256, 511, 512):
        for mode in range(4):
            mask = bytearray(128)
            for i in range(512):
                if mode == 0 or (mode == 1 and i % 2) or (mode == 2 and i % 7 == 2):
                    mask[i // 8] |= 1 << (i % 8)
            h = helper.fnv(bytes(a + b) + mask + bytes([0x5b] * 514))
            for start in (1, vl // 2, vl, 511):
                for rm in range(8):
                    n = len(rows)
                    rows.append(f'CALL {n} 0 {vl} {start} {rm} {h:016x}')
                    tuples.append(dict(trial=n, seed=0, op=0, vl=vl, mask=mode, vstart=start,
                                       control=rm, vxrm=rm & 3, initial_vxsat=rm >> 2, input_fnv64=f'{h:016x}'))
    require(len(rows) == 896, 'Original op0 enumeration changed')
    require(tuples[776] == dict(trial=776, seed=0, op=0, vl=512, mask=0, vstart=256,
                              control=0, vxrm=0, initial_vxsat=0, input_fnv64=tuples[776]['input_fnv64']), 'Wrong boundary')
    return rows[:777], tuples[:777]


def host(prepared):
    out = OUT / 'host'
    out.mkdir()
    want, tuples = expected()
    save(out / 'expected_calls.json', tuples)
    positives, negatives = [], []
    for mode, source in (('prefix', 'case.c'), ('full_capture', 'runtime_only.c')):
        exe = out / mode
        command = ['/usr/bin/cc', '-O2', '-Wall', '-Wextra', '-Werror', '-DSEW=8',
                   '-DFRACTIONAL_SUITE=1', '-DHOST_REFERENCE=1', '-I' + str(prepared / 'original')]
        if mode == 'full_capture': command.append('-DFULL_CAPTURE=1')
        run(command + [prepared / source, HERE / 'host_model.c', '-o', exe], out / (mode + '.build.log'))
        log = out / (mode + '.log')
        run([exe], log)
        text = log.read_text()
        require([s for s in text.splitlines() if s.startswith('CALL ')] == want, 'Original call/data/control ordering differs')
        require('FAIL' not in text and 'HOST_END calls=777 injected=0 result=0' in text, 'Host oracle failed')
        if mode == 'prefix': require(MARKER in text, 'Prefix oracle not completed')
        positives.append(dict(mode=mode, calls=777, status='PASS'))
    for mutation, name in enumerate(('active', 'prestart', 'maskedoff', 'tail', 'left_guard', 'right_guard',
                                     'vstart', 'lost_sticky_vxsat', 'spurious_vxsat'), 1):
        log = out / (name + '.negative.log')
        run([out / 'prefix', str(mutation)], log, expected=1)
        text = log.read_text()
        require('RVV_MATRIX_FAIL' in text and 'HOST_END calls=777 injected=1 result=1' in text, 'Oracle missed ' + name)
        negatives.append(dict(name=name, rejected=True))
    save(out / 'status.json', dict(status='HOST_PASS_NOT_VECTOR_EXECUTION', positive=positives, negative=negatives))


def build(prepared):
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror', '-nostdlib', '-static',
             '-Wl,--build-id=none', '-Wl,--gc-sections', '-T', prepared / 'replay.ld']
    for backend in ('soc', 'spike'):
        out = OUT / backend
        out.mkdir()
        elf = out / (ID + '.elf')
        command = [CC, *flags, '-DSEW=8', '-DFRACTIONAL_SUITE=1', '-I' + str(prepared / 'original')]
        if backend == 'spike': command.append('-DSPIKE_REFERENCE=1')
        command += [prepared / 'case.c', prepared / 'original/scenario.S', prepared / 'main.c',
                    prepared / 'startup.S', prepared / 'runtime.c', '-lgcc', '-o', elf]
        run(command, out / 'compile.log')
        run([CC.with_name('riscv64-unknown-elf-objdump'), '-d', elf], out / (ID + '.dis'))
        nm = subprocess.check_output([CC.with_name('riscv64-unknown-elf-nm'), '-n', elf], text=True, timeout=15)
        symbols = {m[3]: int(m[1], 16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$', nm, re.M)}
        require(symbols['__bss_end'] < 0x800f0000, 'Runtime memory bound')
        save(out / 'symbols.json', symbols)
        body = (out / (ID + '.dis')).read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        target = re.search(r'^\s*([0-9a-f]+):\s+9c880c57\s+vsmul.vv\s+v24,v8,v16,v0.t', body, re.M)
        require(target is not None, 'Original target missing')
        save(out / 'programs.json', dict(schema_version=1, backend='vcs-soc' if backend == 'soc' else 'spike-htif',
            programs={ID: dict(path=str(elf), sha256=sha(elf), cases=[ID], configurations=777,
                target_pc=int(target[1], 16), target_opcode='9c880c57', target_count=777,
                pass_markers=[MARKER, 'FIXED_PREFIX_PASS ' + ID + ' trials=777', 'BOARD_CASE_PASS ' + ID, 'BOARD_REPLAY_PASS'])},
            compiler=dict(path=str(CC), sha256=sha(CC)), vcs_started=False))


def reference():
    out = OUT / 'reference'
    out.mkdir()
    sys.path.insert(0, str(helper.ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    cc, source = probe_paths(helper.ROOT)
    require(check_spike_vstart(SPIKE, cc, out / 'vstart_probe', source)['status'] == 'PASS', 'Spike vstart unsupported')
    symbols = json.loads((OUT / 'spike/symbols.json').read_text())
    commands = out / 'debug.cmd'
    commands.write_text(f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]:x}\nrs\n')
    elf = OUT / 'spike' / (ID + '.elf')
    log = out / 'spike.log'
    seconds = run([SPIKE, '-d', '--debug-cmd=' + str(commands), '--isa=' + ISA, '-m2', elf], log, timeout=180)
    text = log.read_text()
    values = re.findall(r'^0x([0-9a-f]{16})$', text, re.M)
    require(len(values) == 3 and int(values[0], 16) == 0, 'Spike exit/counter failure')
    for marker in json.loads((OUT / 'spike/programs.json').read_text())['programs'][ID]['pass_markers']:
        require(text.count(marker) == 1, 'Reference marker: ' + marker)
    require(not re.search(r'FAIL|TRAP|Error|FATAL', text), 'Reference raw failure')
    require('RVV_TRIAL seed=0 vl=512 mask=0 vstart=256 completed=776' in text, 'Original printed boundary absent')
    save(out / 'status.json', dict(status='SPIKE_PASS_NOT_DUT', configurations=777,
        instructions_to_replay_exit=int(values[1], 16), cycles_to_replay_exit=int(values[2], 16), elapsed_s=seconds,
        elf_sha256=sha(elf), log_sha256=sha(log), isa=ISA, original_linux_replayed=False))


def main():
    recovery = HERE / 'recovery01'
    report = json.loads((recovery / 'report.json').read_text())
    require(report['byte_identical'] and sha(recovery / NAME) == EXPECTED, 'No exact original ELF recovery')
    for path, digest in report['pins'].items(): require(sha(path) == digest, 'Recovery input changed: ' + path)
    OUT.mkdir(exist_ok=False)
    prepared = OUT / 'prepared'
    original = prepared / 'original'
    original.mkdir(parents=True)
    runtime_parent = HERE.parent / 'mask_alias_original/bounded01/prepared'
    helper.prepare.check(runtime_parent)
    for name in ('startup.S', 'runtime.c', 'replay.ld'): shutil.copyfile(runtime_parent / name, prepared / name)
    for name in ('successor_oracle.c', 'operations.h', 'scenario.S'): shutil.copyfile(recovery / name, original / name)
    source = (original / 'successor_oracle.c').read_text()
    runtime = adapt(source)
    bounded = replace(runtime, '                    ++checks;', '                    ++checks;\n                    if(checks==777) goto prefix_complete;')
    bounded = replace(bounded, '    text(errors ? "RVV_MATRIX_FAILED', 'prefix_complete:\n    text(errors ? "RVV_MATRIX_FAILED')
    (prepared / 'runtime_only.c').write_text(runtime)
    (prepared / 'case.c').write_text(bounded)
    for name, before, after in (('runtime_adaptation', source, runtime), ('bound', runtime, bounded)):
        (prepared / (name + '.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))))
    (prepared / 'main.c').write_text('''extern int fixed_main(void);
extern void replay_text(const char *);
extern volatile unsigned long replay_case;
int main(void) {
    unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\\n"); return 90; }
    replay_case=1;
    replay_text("BOARD_CASE_BEGIN fixed_e8_m4_prefix777\\n");
    int result=fixed_main();
    if(result) { replay_text("BOARD_CASE_FAIL fixed_e8_m4_prefix777\\n"); return result; }
    replay_text("FIXED_PREFIX_PASS fixed_e8_m4_prefix777 trials=777\\nBOARD_CASE_PASS fixed_e8_m4_prefix777\\nBOARD_REPLAY_PASS\\n");
    return 0;
}
''')
    _, tuples = expected()
    save(OUT / 'scope.json', dict(original=NAME, original_elf_sha256=EXPECTED, original_c_sha256=OLD_C,
        binary_equivalent_c_sha256=sha(original / 'successor_oracle.c'), original_c_bytes_recovered=False,
        prefix_calls=777, full_original_calls=10752, last_tuple=tuples[-1],
        completed_formula='6 prior VL positions * 4 modes * 4 starts * 8 controls + 1 start * 8 controls = 776',
        historical_record=report['historical_record'], original_linux_replayed=False, DUT_started=False))
    host(prepared)
    build(prepared)
    reference()
    paths = [p for p in OUT.rglob('*') if p.is_file()]
    paths += [Path(__file__), HERE / 'recover.py', HERE / 'host_model.c', recovery / 'report.json', CC, SPIKE,
              Path(helper.__file__), Path(helper.prepare.__file__)]
    pins = dict(report['pins'])
    pins.update({str(p): sha(p) for p in paths})
    save(OUT / 'pins.json', pins)
    save(OUT / 'complete.json', dict(status='READY_ORIGINAL_PREFIX777_SPIKE_PASS_NOT_DUT',
        source_bytes_recovered=False, complete_original_linux_elf_byte_equivalent=True, pins_sha256=sha(OUT / 'pins.json'),
        pin_count=len(pins), reference=json.loads((OUT / 'reference/status.json').read_text()), DUT_started=False))
    print((OUT / 'complete.json').read_text())


if __name__ == '__main__':
    main()
