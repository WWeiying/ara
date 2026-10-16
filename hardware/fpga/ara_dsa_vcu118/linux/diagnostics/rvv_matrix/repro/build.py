"""Build independent Linux RVV reproducer candidates; never operate the board."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

CASES = [
    ('whole_restart', 'RVV-03', 'vmv1r.v v24,v8', 'e16/m1, source loaded as e8, vstart=1'),
    ('fpwide_m8', 'RVV-05', 'vfwredosum.vs v24,v8,v16,v0.t', 'e32/m8, VL=1, vstart=0'),
    ('mask_boundary', 'RVV-02', 'vxor.vv v24,v8,v16,v0.t', 'e8/m4, VL=512, vstart=256, all-on'),
    ('gather_restart', 'RVV-19', 'vrgather.vx v24,v8,t3,v0.t', 'e16/m1, VL=2, vstart=1, index=0'),
    ('slideup_restart', 'RVV-14', 'vslide1up.vx v24,v8,t3,v0.t', 'e16/m1, VL=2, vstart=1, scalar=0'),
    ('slidedown_restart', 'RVV-20', 'vslide1down.vx v24,v8,t3,v0.t', 'e16/m1, VL=2, vstart=1, scalar=0'),
    ('fp_masked_nv', 'RVV-09', 'vmfeq.vv v24,v8,v16,v0.t', 'e32/m1, VL=4, all-off, sNaN in source'),
    ('protected_mask', 'RVV-04', 'vle8.v v24,(a0),v0.t', 'e8/m1, VL=8, all-off, PROT_NONE base'),
    ('fof_page', 'RVV-04', 'vle8ff.v v24,(a0),v0.t', 'e8/m1, VL=8, first 4 bytes mapped, next page PROT_NONE'),
    ('extension_overlap', 'RVV-06', 'vzext.vf2 v24,v25,v0.t', 'e16/m2, VL=2, legal high-end source overlap'),
    ('large_slideup', 'RVV-08', 'vslideup.vx v24,v8,t3,v0.t', 'e8/m4, VL=512, offset=511, all-on'),
    ('slidedown_zero_restart', 'RVV-20', 'vslidedown.vi v24,v8,0,v0.t', 'e16/m1, VL=2, vstart=1'),
]


def assembly(case):
    name, _, instruction, _ = CASES[case - 1]
    lines = ['.text', '.global run_case', '.type run_case,@function', 'run_case:',
             'li t0,-1', 'csrwi vstart,0', 'csrwi fflags,0']
    if case == 1:
        lines += ['vsetvli t1,t0,e8,m1,tu,mu', 'vle8.v v8,(a0)',
                  'vle8.v v24,(a2)', 'vsetivli t1,1,e16,m1,tu,mu', 'csrwi vstart,1']
        readback = ['vsetvli t1,t0,e8,m1,tu,mu', 'vse8.v v24,(a2)']
    elif case == 2:
        lines += ['vsetivli t1,1,e64,m1,tu,mu', 'vle64.v v16,(a1)',
                  'vle64.v v24,(a2)', 'vsetivli t1,1,e32,m8,tu,mu',
                  'vle32.v v8,(a0)', 'vlm.v v0,(a3)']
        readback = ['vsetivli t1,1,e64,m1,tu,mu', 'vse64.v v24,(a2)']
    elif case in (3, 11):
        lines += ['vsetvli t1,t0,e8,m4,tu,mu', 'vle8.v v8,(a0)',
                  'vle8.v v16,(a1)', 'vle8.v v24,(a2)', 'vlm.v v0,(a3)',
                  'li t1,512', 'vsetvli t1,t1,e8,m4,tu,mu',
                  'li t3,' + ('0' if case == 3 else '511'),
                  'li t1,' + ('256' if case == 3 else '0'), 'csrw vstart,t1']
        readback = ['vsetvli t1,t0,e8,m4,tu,mu', 'vse8.v v24,(a2)']
    elif case in (4, 5, 6, 12):
        lines += ['vsetvli t1,t0,e16,m1,tu,mu', 'vle16.v v8,(a0)',
                  'vle16.v v24,(a2)', 'vlm.v v0,(a3)',
                  'vsetivli t1,2,e16,m1,tu,mu', 'li t3,0', 'csrwi vstart,1']
        readback = ['vsetvli t1,t0,e16,m1,tu,mu', 'vse16.v v24,(a2)']
    elif case == 7:
        lines += ['vsetvli t1,t0,e8,m1,tu,mu', 'vle8.v v24,(a2)',
                  'vsetvli t1,t0,e32,m1,tu,mu', 'vle32.v v8,(a0)',
                  'vle32.v v16,(a1)', 'vsetivli t1,4,e32,m1,tu,mu', 'vlm.v v0,(a3)']
        readback = ['vsetvli t1,t0,e8,m1,tu,mu', 'vse8.v v24,(a2)']
    elif case in (8, 9):
        lines += ['vsetvli t1,t0,e8,m1,tu,mu', 'vle8.v v24,(a2)',
                  'vsetivli t1,8,e8,m1,tu,mu', 'vlm.v v0,(a3)']
        readback = ['vsetvli t1,t0,e8,m1,tu,mu', 'vse8.v v24,(a2)']
    elif case == 10:
        lines += ['vsetvli t1,t0,e16,m2,tu,mu', 'vle16.v v24,(a2)',
                  'vsetvli t1,t0,e8,m1,tu,mu', 'vle8.v v25,(a0)',
                  'vsetivli t1,2,e16,m2,tu,mu', 'vlm.v v0,(a3)']
        readback = ['vsetivli t1,2,e16,m2,tu,mu', 'vse16.v v24,(a2)']
    lines += ['.global repro_target', 'repro_target:', instruction,
              '.global repro_after_target', 'repro_after_target:', 'csrr t1,vstart',
              '.global repro_after_vstart', 'repro_after_vstart:', 'sd t1,0(a5)',
              'csrr t1,fflags', 'sd t1,8(a5)', 'csrr t1,vl', 'sd t1,16(a5)',
              *readback, 'ret', '.size run_case,.-run_case']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cross', required=True, help='GCC/binutils prefix')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    binaries = args.out / 'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    source = Path(__file__).with_name('scenario.c')
    manifest = dict(scope='Reduced reproducer candidates, QEMU validation is not board reproduction',
                    required_vlen_bits=1024, board_tested=False, cases=[],
                    source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (source, Path(__file__))})
    for case, (name, issue, instruction, trigger) in enumerate(CASES, 1):
        name = 'rvv_repro_' + name
        asm = args.out / (name + '.S')
        asm.write_text(assembly(case))
        binary = binaries / name
        command = [args.cross + 'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d',
                   '-nostdlib', '-static', '-fno-tree-vectorize', '-fno-builtin',
                   '-fno-strict-aliasing', '-fno-stack-protector', '-no-pie',
                   '-Wl,--build-id=none', '-Wl,-e,_start', f'-DCASE={case}',
                   str(source), str(asm), '-o', str(binary)]
        subprocess.run(command, check=True)
        with (args.out / (name + '.dis')).open('w') as stream:
            subprocess.run([args.cross + 'objdump', '-d', str(binary)], stdout=stream, check=True)
        manifest['cases'].append(dict(name=name, issue=issue, instruction=instruction,
            trigger=trigger, sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_REPRO_PASS', timeout_seconds=30, board_tested=False))
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    files = ['opt', 'opt/ara-tests'] + ['opt/ara-tests/' + c['name'] for c in manifest['cases']]
    with (args.out / 'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'],
                       input=('\n'.join(files) + '\n').encode(),
                       cwd=args.out / 'overlay', stdout=stream, check=True)
    print(args.out)


if __name__ == '__main__':
    main()
