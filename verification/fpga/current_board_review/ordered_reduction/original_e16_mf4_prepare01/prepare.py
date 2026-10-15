#!/usr/bin/env python3
"""Software-only, single original reduction; never invokes an RTL tool."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
INTEGRATION = BASE / 'integration'
WORK = BASE.parents[2]
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
NAME = 'rvv_small_fp_redspecial_e16_mf4'
SOURCE = CAMPAIGN / 'rvv_verified_handoff03/rvv_small_redspecial02' / NAME
CC = WORK / 'install/riscv-gcc/bin/riscv64-unknown-elf-gcc'
OBJDUMP = CC.with_name('riscv64-unknown-elf-objdump')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ISA = 'rv64gcv_zfh_zvfh_zvl1024b'
IDENTITY = 'original_e16_mf4'
MARKER = 'RVV_FP_REDSPECIAL_PASS sew=16 cases=1 flags_seen=16 errors=0'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def execute(cmd, output):
    save(str(output) + '.command.json', list(map(str, cmd)))
    proc = subprocess.run(list(map(str, cmd)), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=60)
    Path(output).write_bytes(proc.stdout)
    if proc.returncode:
        raise RuntimeError(f'{cmd[0]} exit {proc.returncode}; see {output}')
    return proc.stdout.decode()


def disassemble(elf):
    return subprocess.check_output([str(OBJDUMP), '-d', str(elf)], text=True)


def instructions(text):
    return [(int(m[1], 16), m[2].lower(), m[3]) for m in re.finditer(
        r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)', text, re.M)]


def symbols(elf):
    text = subprocess.check_output([str(OBJDUMP), '-t', str(elf)], text=True)
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and re.fullmatch('[0-9a-f]{16}', parts[0]):
            out[parts[-1]] = int(parts[0], 16)
    return out


def prepare():
    out = HERE / 'prepared'
    out.mkdir(exist_ok=False)
    case = json.loads((SOURCE / 'case.json').read_text())['case']
    pins = {}
    old_equal = {}
    for name, expected in case['scenario_sources'].items():
        actual = sha(SOURCE / name)
        assert actual == expected, name
        pins[str(SOURCE / name)] = actual
        shutil.copyfile(SOURCE / name, out / name)
        old_equal[name] = {}
        for generation in ('01', '02'):
            path = CAMPAIGN / ('rvv_small_redspecial' + generation) / NAME / name
            pins[str(path)] = sha(path)
            old_equal[name][generation] = pins[str(path)] == actual
            assert old_equal[name][generation]
    for name, digest in [('scenario.elf', case['sha256']),
                         ('original.elf', case['original_elf_sha256'])]:
        assert sha(SOURCE / name) == digest
        pins[str(SOURCE / name)] = digest
        shutil.copyfile(SOURCE / name, out / name)
    for generation in ('01', '02'):
        path = CAMPAIGN / ('rvv_small_redspecial' + generation) / 'overlay/opt/ara-tests' / NAME
        pins[str(path)] = sha(path)
        assert pins[str(path)] == case['sha256']
    original_c = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/fp_reduction_oracle.c')
    assert sha(original_c) == 'f92ffb3af070febf3dfebb85b0a25f6c5612b95044e2aa1262d600687926eb4f'
    selector = '                if(!(scenario==3 && l==4 && mode==3 && rm==0 && op==0 && sticky==0))continue;\n'
    assert (out / 'scenario.c').read_text().replace(selector, '', 1) == original_c.read_text()
    fixtures = [(int(a, 16), int(b)) for a, b in re.findall(
        r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}', (out / 'fixtures.h').read_text())]
    assert len(fixtures) == 6720, len(fixtures)
    assert fixtures[1545] == (0x7c00, 0)
    assert fixtures[3360 + 1545] == (0x7e00, 16)
    for path in [original_c, SOURCE / 'case.json', SOURCE.parent / 'source_manifest.json',
                 HERE.parent / 'original11_inventory01/REVIEW.md',
                 CAMPAIGN / 'rvv_small_redspecial01/manifest.json',
                 CAMPAIGN / 'rvv_small_redspecial02/manifest.json',
                 CAMPAIGN / 'rvv_small_redspecial02' / NAME / 'fixtures.json']:
        pins[str(path)] = sha(path)
    helper = INTEGRATION / 'prepare.py'
    assert sha(helper) == 'c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8'
    spec = importlib.util.spec_from_file_location('sealed_integration_prepare', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    adapted = module.adapt((out / 'scenario.c').read_text(), IDENTITY)
    (out / 'case.c').write_text(adapted)
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(INTEGRATION / name, out / name)
        pins[str(INTEGRATION / name)] = sha(INTEGRATION / name)
    for path in (helper, CC, OBJDUMP, SPIKE, HERE / 'prepare.py', HERE / 'host.c'):
        pins[str(path)] = sha(path)
    assert sha(SPIKE) == 'c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2'
    main = '''extern int original_e16_mf4_main(void);
extern void replay_text(const char *);
int main(void) {
 unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
 if(n!=128) {replay_text("BOARD_VLEN_FAIL\\n"); return 2;}
 replay_text("BOARD_CASE_BEGIN original_e16_mf4\\n");
 int status=original_e16_mf4_main();
 if(status) {replay_text("BOARD_CASE_FAIL original_e16_mf4\\n"); return status;}
 replay_text("BOARD_CASE_PASS original_e16_mf4\\nBOARD_REPLAY_PASS\\n");
 return 0;
}
'''
    (out / 'main.c').write_text(main)
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
             '-DSEW=16', '-DCAP512=8', '-DCAP1024=16', '-I' + str(out)]
    for kind in ('soc', 'spike'):
        dest = HERE / kind
        dest.mkdir()
        cmd = [CC, *flags, *(['-DSPIKE_REFERENCE=1'] if kind == 'spike' else []),
               '-nostdlib', '-static', '-Wl,--build-id=none', '-Wl,--gc-sections',
               '-Wl,-Map=' + str(dest / 'program.map'), '-T', out / 'replay.ld',
               *[out / f for f in ('startup.S', 'runtime.c', 'main.c', 'case.c', 'operations.S')],
               '-lgcc', '-o', dest / 'program.elf']
        execute(cmd, dest / 'compile.log')
        text = disassemble(dest / 'program.elf')
        (dest / 'program.dis').write_text(text)
        save(dest / 'symbols.json', symbols(dest / 'program.elf'))
    archive = instructions(disassemble(out / 'scenario.elf'))
    windows = {}
    for kind in ('soc', 'spike'):
        ins = instructions((HERE / kind / 'program.dis').read_text())
        windows[kind] = {}
        for name, encoding in [('op_0', '0c881c57'), ('op_1', '14881c57'), ('op_2', '1c881c57')]:
            oi, = [i for i, row in enumerate(archive) if row[1] == encoding]
            ni, = [i for i, row in enumerate(ins) if row[1] == encoding]
            old, new = archive[oi-11:oi+10], ins[ni-11:ni+10]
            assert len(old) == len(new) == 21
            assert [x[1] for x in old] == [x[1] for x in new]
            windows[kind][name] = {'original': old, 'new': new}
    save(HERE / 'sourceproof.json', {
        'scope': 'one original reduced single, not full6720/Linux/DUT',
        'canonical': str(SOURCE), 'original_case': case, 'old01_02_sources_equal': old_equal,
        'original_C_change': 'only archived inner selector; SoC changes only integration.adapt wrapper',
        'fixture_bank': 1, 'fixture_row': 1545, 'flattened': 4905,
        'bank0': fixtures[1545], 'bank1': fixtures[4905], 'fixture_pairs': len(fixtures),
        'helper_windows': windows, 'external_pins': pins,
        'prepared_pins': {str(p): sha(p) for p in out.iterdir() if p.is_file()},
        'isa': ISA, 'reference_bound': {'seconds': 120, 'steps': 1000000, 'raw_bytes': 134217728}})
    host = HERE / 'host'
    host.mkdir()
    old = 'unsigned long vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));'
    assert adapted.count(old) == 1
    (host / 'case.c').write_text(adapted.replace(old, 'unsigned long vlenb=128;'))
    execute(['/usr/bin/gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
             '-fno-tree-vectorize', '-DSEW=16', '-DCAP512=8', '-DCAP1024=16',
             '-I' + str(out), host / 'case.c', HERE / 'host.c', '-o', host / 'host'], host / 'compile.log')
    modes = ['positive', 'missing_nv', 'extra_flag', 'wrong_nan', 'vstart',
             'left_guard', 'right_guard', 'last_guard', 'first_tail', 'last_tail',
             'wrong_type', 'bank0', 'missing_write']
    rows = []
    for mode in modes:
        cmd = [str(host / 'host'), mode]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        (host / (mode + '.log')).write_text(proc.stdout + proc.stderr)
        assert proc.returncode == (0 if mode == 'positive' else 1), (mode, proc.returncode)
        assert ('HOST_SETUP_FULL_PASS' in proc.stdout), mode
        assert (MARKER in proc.stdout) == (mode == 'positive'), mode
        if mode != 'positive':
            assert 'RVV_FP_REDSPECIAL_FAIL' in proc.stdout
        rows.append({'mode': mode, 'returncode': proc.returncode, 'PASS': True})
    save(HERE / 'host.json', {'status': 'PASS_13', 'tests': rows})


if __name__ == '__main__':
    prepare()
