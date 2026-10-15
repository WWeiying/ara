"""Compile authentic nine software singles and host oracles; no Spike invocation."""
import shutil
import subprocess
from common import *


def prepare_case(c):
    dest = HERE / c['shape']
    dest.mkdir()
    out = dest / 'prepared'
    out.mkdir()
    source = Path(c['source'])
    case = read(source / 'case.json')['case']
    pins = {str(source / 'case.json'): sha(source / 'case.json')}
    old_equal = {}
    for name, digest in case['scenario_sources'].items():
        require(sha(source / name) == digest, 'canonical ' + name)
        shutil.copyfile(source / name, out / name)
        pins[str(source / name)] = digest
        old_equal[name] = {}
        for generation in ('01', '02'):
            old = CAMPAIGN / ('rvv_small_redspecial' + generation) / source.name / name
            pins[str(old)] = sha(old)
            old_equal[name][generation] = sha(old) == digest
            require(old_equal[name][generation], 'generation identity')
    for name, digest in [('scenario.elf', case['sha256']), ('original.elf', case['original_elf_sha256'])]:
        require(sha(source / name) == digest, 'archival ELF')
        pins[str(source / name)] = digest
        shutil.copyfile(source / name, out / name)
    original = Path(read(INVENTORY)['source_identity']['original_c'])
    selector = '                if(!(scenario==3 && l==4 && mode==3 && rm==0 && op==0 && sticky==0))continue;\n'
    text = (out / 'scenario.c').read_text()
    require(text.count(selector) == 1 and text.replace(selector, '', 1) == original.read_text(), 'only original selector delta')
    pairs = fixtures(out / 'fixtures.h')
    require(len(pairs) == 6720 and pairs[4905] == [c['nan'], 16], 'bank1 fixture1545')
    adapted = load_adapter().adapt(text, c['identity'])
    (out / 'case.c').write_text(adapted)
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(INTEGRATION / name, out / name)
        pins[str(INTEGRATION / name)] = sha(INTEGRATION / name)
    ident = c['identity']
    (out / 'main.c').write_text(f'''extern int {ident}_main(void);
extern void replay_text(const char *);
int main(void) {{
 unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
 if(n!=128) {{replay_text("BOARD_VLEN_FAIL\\n"); return 2;}}
 replay_text("BOARD_CASE_BEGIN {ident}\\n");
 int status={ident}_main();
 if(status) {{replay_text("BOARD_CASE_FAIL {ident}\\n"); return status;}}
 replay_text("BOARD_CASE_PASS {ident}\\nBOARD_REPLAY_PASS\\n"); return 0;
}}
''')
    defines = [f"-DSEW={c['sew']}", f"-DCAP512={c['cap']//2}", f"-DCAP1024={c['cap']}"]
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
             '-msmall-data-limit=0', '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
             *defines, '-I' + str(out)]
    archive = instructions(disassemble(out / 'scenario.elf'))
    windows = {}
    for kind in ('soc', 'spike'):
        folder = dest / kind
        folder.mkdir()
        execute([CC, *flags, *(['-DSPIKE_REFERENCE=1'] if kind == 'spike' else []),
                 '-nostdlib', '-static', '-Wl,--build-id=none', '-Wl,--gc-sections',
                 '-Wl,-Map=' + str(folder / 'program.map'), '-T', out / 'replay.ld',
                 *[out / n for n in ('startup.S', 'runtime.c', 'main.c', 'case.c', 'operations.S')],
                 '-lgcc', '-o', folder / 'program.elf'], folder / 'compile.log')
        dis = disassemble(folder / 'program.elf')
        (folder / 'program.dis').write_text(dis)
        syms = symbols(folder / 'program.elf')
        save(folder / 'symbols.json', syms)
        ins = instructions(dis)
        windows[kind] = {}
        for name, encoding in [('op_0', '0c881c57'), ('op_1', '14881c57'), ('op_2', '1c881c57')]:
            oi, = [i for i, r in enumerate(archive) if r[1] == encoding]
            ni, = [i for i, r in enumerate(ins) if r[1] == encoding]
            old, new = archive[oi-11:oi+10], ins[ni-11:ni+10]
            require(len(new) == 21 and new[0][0] == syms[name], '21 helper entry')
            require([r[1] for r in old] == [r[1] for r in new], '21 actual helper bytes')
            windows[kind][name] = {'original': old, 'new': new}
    for p in [original, CC, OBJDUMP, SPIKE, INTEGRATION / 'prepare.py', INVENTORY,
              HERE.parent / 'original11_inventory01/REVIEW.md', CANONICAL / 'source_manifest.json']:
        pins[str(p)] = sha(p)
    require(sha(SPIKE) == 'c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2', 'golden Spike')
    save(dest / 'sourceproof.json', {'config': c, 'original_case': case,
        'scope': 'one original selected single with complete scalar loops; not full6720/Linux/DUT',
        'bank1': pairs[4905], 'bank0': pairs[1545], 'fixture_bank': 1, 'fixture_row': 1545,
        'fixture_pairs': 6720, 'old01_02_sources_equal': old_equal, 'helper_windows': windows,
        'external_pins': pins, 'prepared_pins': {str(p): sha(p) for p in out.iterdir()},
        'profile': ISA, 'limits': LIMITS})
    host = dest / 'host'
    host.mkdir()
    asm = 'unsigned long vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));'
    require(adapted.count(asm) == 1, 'host vlenb wrapper')
    (host / 'case.c').write_text(adapted.replace(asm, 'unsigned long vlenb=128;'))
    execute(['/usr/bin/gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-tree-vectorize',
             *defines, '-DCASE_MAIN=' + ident + '_main', '-I' + str(out), host / 'case.c',
             HERE / 'host.c', '-o', host / 'host'], host / 'compile.log')
    rows = []
    for mode in ('positive', 'missing_nv', 'extra_flag', 'wrong_nan', 'vstart', 'left_guard',
                 'right_guard', 'last_guard', 'first_tail', 'last_tail', 'wrong_type', 'bank0', 'missing_write'):
        p = subprocess.run([str(host / 'host'), mode], capture_output=True, text=True, timeout=10)
        (host / (mode + '.log')).write_text(p.stdout + p.stderr)
        require(p.returncode == (0 if mode == 'positive' else 1), 'host status ' + mode)
        require('HOST_SETUP_FULL_PASS' in p.stdout, 'host setup ' + mode)
        require((marker(c) in p.stdout) == (mode == 'positive'), 'host oracle ' + mode)
        require(mode == 'positive' or 'RVV_FP_REDSPECIAL_FAIL' in p.stdout, 'host failure veto')
        rows.append({'mode': mode, 'returncode': p.returncode, 'passed': True})
    save(dest / 'host.json', {'status': 'PASS_13_HOST_ONLY', 'tests': rows})
    print(c['shape'], 'COMPILED_HOST13_PASS', flush=True)


def main():
    inventory = read(INVENTORY)
    # Mutable current-scope status is not source provenance and is deliberately not pinned anew.
    archival = {p: h for p, h in inventory['fresh_sha256'].items() if '/ara_hw_campaign_20261007_01/' in p}
    checkpins(archival)
    save(HERE / 'manifest.json', {'status': 'AUTHORIZED_SOFTWARE_PREPARATION_ONLY',
        'shapes': [config(s) for s in SHAPES], 'excluded': ['e16_mf4', 'e32_m1'],
        'inventory_sha256': sha(INVENTORY), 'inventory_archival_pins_checked': archival,
        'limits_per_elf': LIMITS, 'profile': ISA, 'reference_attempts_per_elf': 1,
        'dispatch': 'sequential, stop first error; at most one reference active',
        'no_RTL_build': True, 'no_VCS': True, 'no_live_queries': True})
    for shape in SHAPES:
        prepare_case(config(shape))


if __name__ == '__main__':
    main()
