#!/usr/bin/env python3
"""Pin selected reconstructed fixtures; build five bounded architectural ports."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent / 'integration'
ROOT = HERE.parents[3]
SOURCE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_fp_compare_reconstructed01')
PINS = {
    'prepare.py': 'c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8',
    'run.py': 'c1c3804dbe36fa981ea7b6cbcfa5d7b69fb793b2a14c37831fb96e866f2d2a78',
    'reference.py': '9fe24c0d48c0a5311f360fa2f99d03412b01137ad323ce93e0b7d5c44a8f4a85',
    'startup.S': '3ab886ee55bf807790e0c17e982d3142e5207f317bbde593d2b5d8cc4f151582',
    'runtime.c': '91aecf556bf3f17f1e3b21241099c81fdca2e624eff3a1a37986dc9629dae5db',
    'replay.ld': '6478bcdc036d6fa64beec95c51748e4778a2e0c49a74efcabc0fdb537ad3a82a',
}
CASES = [
    ('all_off', 'rvv_small_fp_compare_e16_mf4', 0, []),
    ('active_snan', 'rvv_small_fp_compare_e16_mf4', 1, []),
    ('no_snan', 'rvv_small_fp_compare_e16_mf4', 2, []),
    ('tail_vl15', 'rvv_small_fp_compare_unmasked_alias_v0_e16_mf4', 0,
     ['UNMASKED_COMPARISONS=1', 'DESTINATION_KIND=3']),
    ('prestart_snan', 'rvv_small_fp_compare_restart_e16_mf4', 0,
     ['RESTART_COMPARISONS=1']),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('adaptation drift: ' + old)
    return text.replace(old, new)


def prepare():
    for name, digest in PINS.items():
        if sha(INTEGRATION / name) != digest:
            raise ValueError('integration helper drift: ' + name)
    sys.path.insert(0, str(INTEGRATION))
    from prepare import adapt
    manifest = SOURCE / 'manifest.json'
    if sha(manifest) != 'a10c7ef148758defbe6042bfaa61e462e028235b58d5422daba1bfa902b64bb8':
        raise ValueError('reconstructed manifest drift')
    entries = json.loads(manifest.read_text())['cases']
    out = HERE / 'prepared'
    out.mkdir(exist_ok=False)
    shutil.copyfile(manifest, out / 'source_manifest.json')
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(INTEGRATION / name, out / name)
    for name in ('audit.h', 'capture.S'):
        shutil.copyfile(HERE / name, out / name)
    records = []
    for name, source_name, control, defines in CASES:
        entry, = [c for c in entries if c['name'] == source_name]
        original = out / name / 'original'
        original.mkdir(parents=True)
        for filename, digest in entry['scenario_sources'].items():
            src = SOURCE / source_name / filename
            if sha(src) != digest:
                raise ValueError('source drift: ' + str(src))
            shutil.copyfile(src, original / filename)
        linux = SOURCE / 'overlay/opt/ara-tests' / source_name
        if sha(linux) != entry['sha256']:
            raise ValueError('reduced Linux ELF drift')
        src = adapt((original / 'scenario.c').read_text(), name)
        src = replace_once(src, 'int ' + name + '_main(void)', '#include "audit.h"\nint ' + name + '_main(void)')
        src = replace_once(src, 'if(!cap || cap>1024)', 'if(cap != 16)')
        src = replace_once(src, 'inputs[lhs_index(seed,i)]', 'inputs[mapped(lhs_index(seed,i))]')
        src = replace_once(src, 'inputs[rhs_index(seed,i,op)]', 'inputs[mapped(rhs_index(seed,i,op))]')
        src = replace_once(src, 'struct fixture wanted=', 'ai=mapped(ai);bi=mapped(bi);\n            struct fixture wanted=')
        src = replace_once(src, 'for(unsigned i=0;i<130;++i)output[i]=0x5b;',
                           'for(unsigned i=0;i<130;++i)output[i]=0x5b;\n'
                           '        if(CONTROL == 1)mask[0]=32;\n'
                           '        audit_before(cap,op,vl,start);')
        src = replace_once(src, 'if((uint32_t)status)++errors;',
                           'capture_vectors(seen_a,seen_b,seen_mask);\n        if((uint32_t)status)++errors;')
        src = replace_once(src, '++cases;',
                           'unsigned extra=audit_after(cap,op,vl,start,status,errors-prior);\n'
                           '        errors+=extra;\n        ++cases;')
        if name == 'prestart_snan':
            src = replace_once(src, 'unsigned start=4;', 'unsigned start=6;')
        (out / name / 'case.c').write_text(src)
        records.append(dict(id=name, source_directory=str(SOURCE / source_name), original_case=entry,
                            control=control, defines=defines, linux_elf=str(linux),
                            derivative=name in ('active_snan', 'no_snan', 'prestart_snan')))
    provenance = dict(schema_version=1, vlen=1024, nr_lanes=4, cases=records,
                      integration_pins=PINS, generator_sha256=sha(Path(__file__)),
                      scope='archived assembly plus reconstructed C oracle; not full original Linux replay')
    provenance['files'] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    save(out / 'provenance.json', provenance)
    # Dedicated wrapper retains all checks and uses explicit vector half support.
    ref = (INTEGRATION / 'reference.py').read_text()
    ref = replace_once(ref, 'from prepare import ROOT, check, save, sha',
                       'sys.dont_write_bytecode = True\nsys.path.insert(0, ' + repr(str(INTEGRATION)) + ')\n'
                       'from prepare import ROOT, check, save, sha')
    ref = replace_once(ref, '--isa=rv64gcv_zvl1024b', '--isa=rv64gcv_zvfh_zvl1024b')
    (HERE / 'reference.py').write_text(ref)
    return out, provenance


def build(prepared, provenance, spike, out=None):
    out = out or HERE / ('spike' if spike else 'soc')
    out.mkdir(exist_ok=False)
    cc = ROOT / 'install/riscv-gcc/bin/riscv64-unknown-elf-gcc'
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
             '-msmall-data-limit=0', '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror']
    if spike:
        flags.append('-DSPIKE_REFERENCE=1')
    commands = []

    def execute(command, log=None):
        command = list(map(str, command))
        commands.append(command)
        save(out / 'commands.json', commands)
        if log:
            with log.open('w') as stream:
                subprocess.run(command, check=True, stdout=stream)
        else:
            subprocess.run(command, check=True)

    common = []
    for filename in ('startup.S', 'runtime.c', 'capture.S'):
        obj = out / (filename + '.o')
        execute([cc, *flags, '-c', prepared / filename, '-o', obj])
        common.append(obj)
    programs = {}
    for case in provenance['cases']:
        name = case['id']
        original = prepared / name / 'original'
        defines = [f'-DSEW={case.get("sew", 16)}', f'-DCONTROL={case["control"]}', f'-DCASE_NAME="{name}"',
                   *['-D' + d for d in case['defines']], '-I' + str(original), '-I' + str(prepared)]
        obj = out / (name + '.o')
        asm = out / (name + '_asm.o')
        execute([cc, *flags, *defines, '-c', prepared / name / 'case.c', '-o', obj])
        execute([cc, *flags, '-c', original / 'scenario.S', '-o', asm])
        main = out / (name + '_main.c')
        main.write_text('extern void replay_text(const char *);\nextern int ' + name + '_main(void);\n'
                        'int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));\n'
                        'if(n!=128){return 90;}\nreplay_text("BOARD_CASE_BEGIN ' + name + '\\n");\n'
                        'if(' + name + '_main()){replay_text("BOARD_CASE_FAIL ' + name + '\\n");return 1;}\n'
                        'replay_text("BOARD_CASE_PASS ' + name + '\\nBOARD_REPLAY_PASS\\n");return 0;}\n')
        elf = out / (name + '.elf')
        execute([cc, *flags, '-nostdlib', '-static', '-Wl,--build-id=none', '-Wl,--gc-sections',
                 '-Wl,-Map=' + str(out / (name + '.map')), '-T', prepared / 'replay.ld',
                 main, obj, asm, *common, '-lgcc', '-o', elf])
        execute([cc.with_name('riscv64-unknown-elf-objdump'), '-d', elf], out / (name + '.dis'))
        programs[name] = dict(path=str(elf), sha256=sha(elf), cases=[name],
                             pass_markers=['BOARD_CASE_PASS ' + name, 'BOARD_REPLAY_PASS',
                                           case.get('pass_marker', 'RVV_FP_COMPARE_PASS sew=16 cases=1 errors=0')])
    save(out / 'programs.json', dict(schema_version=1, programs=programs,
         compiler=dict(path=str(cc.resolve()), sha256=sha(cc)), prepared=str(prepared),
         provenance_sha256=sha(prepared / 'provenance.json'), vcs_started=False,
         backend='spike-htif' if spike else 'vcs-soc'))


if __name__ == '__main__':
    prepared, provenance = prepare()
    build(prepared, provenance, True)
    build(prepared, provenance, False)
