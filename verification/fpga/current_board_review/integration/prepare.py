#!/usr/bin/env python3
"""Freeze five original reduced cases; adapt only their Linux entry/I/O/exit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
CASES = [
    ('maskslide', 'rvv_permute_single01',
     'rvv_trace_permute_single_restart_e16_m1_ops16',
     '622d4dd7137924e7c8e62fb0437d51dcd867dc6add47e5a59183d15e397a6367',
     ['SEW=16', 'RESTART_PERMUTATIONS=1', 'PERMUTE_OP_MASK=65536']),
    ('restart_compare', 'rvv_small_masks01', 'rvv_small_masks_scalar_restart_e64_m1',
     '2845c04b1e7be56576e30abd5aaf016d108bd10ef961db54fb11a409cb0a220c',
     ['SEW=64', 'RESTART_MASKS=1', 'SCALAR_FORMS=1', 'CARRY_FORMS=0',
      'COMPARISON_ALIASES=0', 'ALIASES=0']),
    ('reduction_fflags', 'rvv_small_redspecial01', 'rvv_small_fp_redspecial_e32_m1',
     'cb890017f97fa3c6bfa2e4d45dfb745166d4934b5092b9951ad2b86a1b85aa0c',
     ['SEW=32', 'CAP512=16', 'CAP1024=32']),
    ('m8widen', 'rvv_small_fpwide01', 'rvv_small_fpwide_original_vl0',
     '56538dbf2dbcb425b5dfb6e8f09a92248ec8f68e171217c0f2aac7e4873d687b',
     ['SEW=32', 'DEST_SEW=64', 'FLOAT_REDUCTION=1', 'OP_COUNT=2']),
    ('wholemove', 'rvv_small_whole01', 'rvv_small_whole_restart_first',
     '4953163d1a95815a0c7aecd7456718a6a5973b895a58b5bed83cf969b44e1115',
     ['DETAIL_BYTES=1']),
    ('gather_original', 'rvv_small_gather02', 'rvv_small_gather_restart_e16_m1_ops0',
     'd3240e001a55d0e29db8db126ae47d602e988c585c6e064dcdffb2d91a5ca238',
     ['SEW=16', 'RESTART_PERMUTATIONS=1', 'PERMUTE_OP_MASK=1']),
]
ORACLE_MARKERS = {
    'maskslide': 'RVV_PERMUTE_PASS sew=16 cases=1 errors=0',
    'restart_compare': 'RVV_MASK_PASS sew=64 cases=1 errors=0',
    'reduction_fflags': 'RVV_FP_REDSPECIAL_PASS sew=32 cases=1 flags_seen=16 errors=0',
    'm8widen': 'RVV_REDUCTION_PASS sew=32 cases=1 errors=0',
    'wholemove': 'RVV_WHOLE_PASS cases=1 skips=0 errors=0',
    'gather_original': 'RVV_PERMUTE_PASS sew=16 cases=1 errors=0',
    'gather_prestart': 'RVV_REPRO_PASS errors=0',
    'slide_source_e32': 'EXTENDED_PASS slide_source_e32 cases=8',
    'slide_source_e64': 'EXTENDED_PASS slide_source_e64 cases=8',
    'm8widen_nonzero': 'EXTENDED_PASS m8widen_nonzero cases=10',
    'wholemove_layout': 'EXTENDED_PASS wholemove_layout cases=4',
}
EXTENSIONS = ['slide_source_e32', 'slide_source_e64', 'm8widen_nonzero', 'wholemove_layout']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def adapt(source, identity):
    """Fail closed if the audited freestanding Linux wrapper shape changes."""
    start = source.index('static long syscall3(')
    end = source.index('static void text(', start)
    syscall = source[start:end]
    if syscall.count('ecall') != 1 or syscall.count('return a0;') != 1:
        raise ValueError('unrecognized Linux syscall wrapper')
    source = source[:start] + (
        'extern long replay_write(long, long, long, long);\n'
        '#define syscall3 replay_write\n') + source[end:]
    source, entries = re.subn(r'void probe_main\(void\)\s*\{',
                             f'int {identity}_main(void) {{', source)
    source, capacity = re.subn(r'syscall3\(94,2,0,0\);for\(;;\)\{\}',
                              'return 2;', source)
    source, exits = re.subn(r'syscall3\(94,errors \? 1:0,0,0\);for\(;;\)\{\}',
                           'return errors ? 1 : 0;', source)
    # TIOCOUTQ boundary drains have no Linux equivalent in bare metal.
    source = source.replace('syscall3(29,1,0x5409,1);',
                            '/* Linux TIOCOUTQ omitted; timing is not equivalent. */')
    source, startups = re.subn(r'__asm__\("\.global _start.*?\);\s*$', '', source,
                               flags=re.DOTALL)
    if (entries, capacity, exits, startups) != (1, 1, 1, 1):
        raise ValueError('entry/exit adaptation contract changed')
    if 'ecall' in source or 'syscall3(94' in source or 'syscall3(29' in source:
        raise ValueError('unadapted Linux service')
    return ('/* Architectural port of ' + identity + '; original identity in provenance.json.\n'
            ' * Not an original Linux ELF replay or a fault/restart OS test. */\n' + source)


def freeze(out, campaign):
    out.mkdir(parents=True, exist_ok=False)
    records = []
    for identity, directory, name, manifest_sha, defines in CASES:
        manifest = campaign / directory / 'manifest.json'
        if sha(manifest) != manifest_sha:
            raise ValueError('campaign manifest drift: ' + str(manifest))
        data = json.loads(manifest.read_text())
        case, = [c for c in data['cases'] if c['name'] == name]
        source_dir = campaign / directory / name
        original = out / identity / 'original'
        original.mkdir(parents=True)
        shutil.copyfile(manifest, original / 'manifest.json')
        for filename, digest in case['scenario_sources'].items():
            source = source_dir / filename
            if sha(source) != digest:
                raise ValueError('original source drift: ' + str(source))
            shutil.copyfile(source, original / filename)
        # Verify the Linux ELF separately, but never execute it in the bare-metal TB.
        linux_elf = campaign / directory / 'overlay/opt/ara-tests' / name
        if sha(linux_elf) != case['sha256']:
            raise ValueError('reduced Linux ELF drift: ' + str(linux_elf))
        (out / identity / 'case.c').write_text(adapt(
            (original / 'scenario.c').read_text(), identity))
        assembly, = [f for f in case['scenario_sources'] if f.endswith('.S')]
        records.append(dict(id=identity, defines=defines, assembly=assembly,
                            include_combined=identity != 'gather_original',
                            source_directory=str(source_dir), manifest_sha256=manifest_sha,
                            reduced_linux_elf=str(linux_elf), original_case=case))
    generic = campaign / 'rvv_verification_handoff02'
    pins = {'manifest.json': 'ddaa3f3f49847c39bdc1fcee7661b09cc2b8bfc4149ab27d3e985a7142a035d4',
            'scenario.c': '9d424bb3ac733893805c26314174840ea948c3b9bd000346f8a5632300f5af73',
            'assembly/rvv_repro_gather_restart.S': 'c7ac930f3e189c901f811116db54c1b7728105009ee50ffb40f6e3843ff034d6'}
    original = out / 'gather_prestart/original'
    original.mkdir(parents=True)
    for name, digest in pins.items():
        if sha(generic / name) != digest:
            raise ValueError('generic gather source drift: ' + name)
        shutil.copyfile(generic / name, original / Path(name).name)
    case, = [c for c in json.loads((generic / 'manifest.json').read_text())['cases']
             if c['name'] == 'rvv_repro_gather_restart']
    if sha(generic / 'binaries' / case['name']) != case['sha256']:
        raise ValueError('generic gather ELF drift')
    source = (original / 'scenario.c').read_text()
    start, end = source.index('static long syscall6('), source.index('static void text(')
    source = source[:start] + 'extern long replay_write(long,long,long,long);\n' + source[end:]
    source = source.replace('syscall6(64, 1, (long)s, n, 0, 0, 0);',
                            'replay_write(64, 1, (long)s, n);')
    start, end = source.index('static void finish('), source.index('void probe_main(')
    source = source[:start] + source[end:]
    source = source.replace('void probe_main(void)', 'int gather_prestart_main(void)')
    source = source.replace('finish(77);', 'return 77;').replace('finish(2);', 'return 2;')
    source = source.replace('finish(errors ? 1 : 0);', 'return errors ? 1 : 0;')
    source = source[:source.index('__asm__(".global _start')]
    source = ('/* Handoff02 CASE4 generic gather; board_tested=false, not verified03 original. */\n'
              '#if CASE != 4\n#error Only the nonfault gather case is ported\n#endif\n' + source)
    (out / 'gather_prestart/case.c').write_text(source)
    records.append(dict(id='gather_prestart', defines=['CASE=4'],
                        assembly='rvv_repro_gather_restart.S', include_combined=False,
                        source_directory=str(generic), original_case=case,
                        scope='generic handoff02 pattern [91,1000]; not board-confirmed original'))
    for filename in ('startup.S', 'runtime.c', 'replay.ld', 'slide1up_prestart.c', 'extensions.c', 'extensions.S'):
        shutil.copyfile(HERE / filename, out / filename)
    records.append(dict(id='slide1up_prestart', include_combined=True,
                        scope='directed supplemental, not original FPGA case'))
    for index, name in enumerate(EXTENSIONS, 1):
        records.append(dict(id=name, extension=index, include_combined=False,
                            scope='directed extended integration; not original-case acceptance'))
    provenance = dict(schema_version=1, vlen=1024, nr_lanes=4, cases=records,
                      scope='architectural ports only; original-program acceptance remains open',
                      generator_sha256=sha(Path(__file__)))
    provenance['files'] = {str(p.relative_to(out)): sha(p)
                           for p in sorted(out.rglob('*')) if p.is_file()}
    save(out / 'provenance.json', provenance)
    return provenance


def check(prepared):
    provenance = json.loads((prepared / 'provenance.json').read_text())
    for name, digest in provenance['files'].items():
        if sha(prepared / name) != digest:
            raise ValueError('prepared source drift: ' + name)
    return provenance


def compile_programs(prepared, output, cc, spike_reference=False):
    provenance = check(prepared)
    cc = cc.resolve(strict=True)
    if any(s in str(cc).lower() for s in ('zcc', 'terapines')):
        raise ValueError('forbidden compiler')
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror']
    if spike_reference:
        flags.append('-DSPIKE_REFERENCE=1')

    def execute(command, log=None):
        commands.append([str(x) for x in command])
        save(output / 'commands.json', commands)
        if log:
            with log.open('w') as stream:
                subprocess.run(command, check=True, stdout=stream)
        else:
            subprocess.run(command, check=True)

    objects = []
    for case in provenance['cases']:
        identity = case['id']
        if identity == 'slide1up_prestart':
            sources = [prepared / 'slide1up_prestart.c']
            defines = []
        elif 'extension' in case:
            sources = [prepared / 'extensions.c']
            defines = [f'-DREPLAY_EXT={case["extension"]}', f'-Dextension_main={identity}_main']
            if identity == 'wholemove_layout':
                sources.append(prepared / 'extensions.S')
        else:
            original = prepared / identity / 'original'
            defines = ['-D' + d for d in case['defines']]
            symbols = re.findall(r'^\.global\s+(\w+)\s*$',
                                 (original / case['assembly']).read_text(), re.MULTILINE)
            defines += [f'-D{s}={identity}_{s}' for s in symbols]
            defines += ['-I' + str(original)]
            sources = [prepared / identity / 'case.c', original / case['assembly']]
        for index, source in enumerate(sources):
            obj = output / f'{identity}_{index}.o'
            execute([str(cc), *flags, *defines, '-c', str(source), '-o', str(obj)])
            objects.append(obj)
    for source in ('startup.S', 'runtime.c'):
        obj = output / (source + '.o')
        execute([str(cc), *flags, '-c', str(prepared / source), '-o', str(obj)])
        objects.append(obj)
    names = [c['id'] for c in provenance['cases']]
    combined = [c['id'] for c in provenance['cases'] if c['include_combined']]
    programs = {}
    for name in ['all', 'extended', *names]:
        selected = combined if name == 'all' else EXTENSIONS if name == 'extended' else [name]
        main = output / (name + '_main.c')
        text = ['extern void replay_text(const char *);',
                'extern volatile unsigned long replay_case;',
                *[f'extern int {n}_main(void);' for n in selected],
                'int main(void) {', 'unsigned long vlenb;',
                '__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));',
                'if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\\n"); return 90; }']
        for n in selected:
            text += [f'replay_case = {names.index(n) + 1};',
                     f'replay_text("BOARD_CASE_BEGIN {n}\\n");',
                     f'if ({n}_main()) {{ replay_text("BOARD_CASE_FAIL {n}\\n"); return {names.index(n)+1}; }}',
                     f'replay_text("BOARD_CASE_PASS {n}\\n");']
        text += ['replay_text("BOARD_REPLAY_PASS\\n"); return 0;', '}']
        main.write_text('\n'.join(text) + '\n')
        elf = output / (name + '.elf')
        execute([str(cc), *flags, '-nostdlib', '-static', '-Wl,--build-id=none',
                 '-Wl,--gc-sections', '-Wl,-Map=' + str(output / (name + '.map')),
                 '-T', str(prepared / 'replay.ld'), str(main),
                 *map(str, objects), '-lgcc', '-o', str(elf)])
        objdump = cc.with_name(cc.name.removesuffix('gcc') + 'objdump')
        execute([str(objdump), '-d', str(elf)], output / (name + '.dis'))
        markers = ['BOARD_REPLAY_PASS', *[f'BOARD_CASE_PASS {n}' for n in selected],
                   *[ORACLE_MARKERS[n] for n in selected if n in ORACLE_MARKERS]]
        programs[name] = dict(path=str(elf), sha256=sha(elf), cases=selected, pass_markers=markers)
    save(output / 'programs.json', dict(schema_version=1, programs=programs,
         compiler=dict(path=str(cc), sha256=sha(cc)), prepared=str(prepared),
         provenance_sha256=sha(prepared / 'provenance.json'), vcs_started=False,
         backend='spike-htif' if spike_reference else 'vcs-soc'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    freeze_parser = sub.add_parser('freeze')
    freeze_parser.add_argument('--campaign', type=Path, default=CAMPAIGN)
    freeze_parser.add_argument('--out', type=Path, required=True)
    build = sub.add_parser('compile')
    build.add_argument('--prepared', type=Path, required=True)
    build.add_argument('--out', type=Path, required=True)
    build.add_argument('--spike-reference', action='store_true')
    build.add_argument('--cc', type=Path,
                       default=ROOT / 'install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
    args = parser.parse_args()
    if args.command == 'freeze':
        freeze(args.out.resolve(), args.campaign.resolve())
    else:
        compile_programs(args.prepared.resolve(), args.out.resolve(), args.cc, args.spike_reference)


if __name__ == '__main__':
    main()
