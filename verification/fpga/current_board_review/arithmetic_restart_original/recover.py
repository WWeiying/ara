#!/usr/bin/env python3
"""Recover the original basic matrix C semantics and test archived binary identity.

The old C bytes were not archived beside these manifests. This is explicitly a
reconstruction from the surviving successor, never a claimed old source hash.
"""
import difflib
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
CAMP = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def reconstruct(s):
    prefix = s[:s.index('#ifndef INPUT_SEEDS')]
    data = s[s.index('static word a[1024]'):s.index('#if !defined(INTEGER_MACC_SUITE)')]
    data = data.replace('static unsigned accumulator_trial;\n', '')
    data = data.replace('const uint8_t *, unsigned long, unsigned long);', 'const uint8_t *, unsigned long);')
    signed = s[s.index('static int64_t signed_word'):s.index('#endif\n#if !INTEGER_EXTENSION')]
    value = s[s.index('static word value('):s.index('#endif\n#ifdef INTEGER_SCALAR_SUITE')]
    selected = s[s.index('static unsigned selected'):s.index('#if INTEGER_EXTENSION\nstatic __int128')]
    failure = s[s.index('static void failure'):s.index('void probe_main')]
    failure = failure.replace('#ifdef MACC_ACCUMULATORS\n    text(" accumulator=");number(accumulator_trial);\n#endif\n', '')
    main = '''void probe_main(void) {
    unsigned cap=capacity();
    if(!cap || cap>1024){text("RVV_MATRIX_UNSUPPORTED_CAPACITY\\n");finish(2);}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<3;++seed) {
        uint64_t random=UINT64_C(0x937ad68de41c725f)^seed;
        for(unsigned i=0;i<cap;++i) {
            random^=random<<13;random^=random>>7;random^=random<<17;
            a[i]=random;b[i]=random>>19;
            switch(i%8) {
            case 0:a[i]=0;b[i]=0;break;
            case 1:a[i]=(word)-1;b[i]=1;break;
            case 2:a[i]=(word)(UINT64_C(1)<<(SEW-1));b[i]=(word)-1;break;
            case 3:b[i]=SEW;break;
            }
        }
        for(unsigned op=0;op<OPERATION_COUNT;++op)
        for(unsigned li=0;li<7;++li) {
            unsigned vl=lengths[li];if(vl>cap)continue;
            for(unsigned mode=0;mode<3;++mode) {
                for(unsigned i=0;i<128;++i)mask[i]=0;
                for(unsigned i=0;i<cap;++i)
                    if(selected(mode,i))mask[i/8]|=1u<<(i%8);
                unsigned trials=kinds[op]==0 ? 3:1;
                for(unsigned si=0;si<trials;++si) {
                    unsigned start=si==0 ? 0:si==1 ? vl/2:(vl<cap ? vl:cap-1);
                    word sentinel=(word)0x5b;
#if SEW >= 32
                    if(op>=25)
                        for(unsigned i=0;i<cap;++i) {
                            a[i]=fp_inputs[(i+seed)%8];
                            b[i]=fp_inputs[(i*3+seed)%8];
                        }
#endif
                    for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;
#ifdef TRACE_OP0
                    if(op==0) {
                        text("RVV_TRIAL seed=");number(seed);
                        text(" vl=");number(vl);text(" mask=");number(mode);
                        text(" vstart=");number(start);
                        text(" completed=");number(checks);text("\\n");
                        syscall3(29,1,0x5409,1);
                    }
#endif
                    unsigned long vs=functions[op](a,b,out+1,vl,cap,mask,start);
                    if(vs)failure(op,seed,vl,mode,start,cap+2,0,vs);
                    unsigned packed=0;
                    word reduced=b[0];
                    if(kinds[op]==2)
                        for(unsigned i=0;i<vl;++i)
                            if(selected(mode,i))reduced+=a[i];
                    for(unsigned i=0;i<cap;++i) {
                        word expected=sentinel;
                        if(kinds[op]==2) {
                            if(i==0 && vl)expected=reduced;
                        } else if(kinds[op]==3) {
                            while(packed<vl && !selected(mode,packed))++packed;
                            if(packed<vl)expected=a[packed++];
                        } else if(i<vl && i>=start && selected(mode,i)) {
                            if(op<19)expected=value(op,a[i],b[i]);
                            else if(op==19) {if(i>=2)expected=a[i-2];}
                            else if(op==20)expected=i+2<cap ? a[i+2]:0;
                            else if(op==21)expected=b[i]<cap ? a[b[i]]:0;
                            else if(op==24)expected=a[i];
#if SEW >= 32
                            else if(op>=25)expected=fp_expected[op-25][((i+seed)%8)*8+(i*3+seed)%8];
#endif
                        }
                        if(out[i+1]!=expected)
                            failure(op,seed,vl,mode,start,i,expected,out[i+1]);
                        ++elements;
                    }
                    if(out[0]!=sentinel || out[cap+1]!=sentinel)
                        failure(op,seed,vl,mode,start,cap+1,sentinel,out[cap+1]);
                    ++checks;
                }
            }
        }
    }
    text(errors ? "RVV_MATRIX_FAILED sew=":"RVV_MATRIX_PASS sew=");number(SEW);text(" vlmax=");number(cap);
    text(" cases=");number(checks);text(" elements=");number(elements);
    text(" errors=");number(errors);
    text(" seeds=3 guard_tail_mask_vstart=checked\\n");finish(errors ? 1:0);
}
'''
    return prefix + data + signed + value + selected + failure + main + s[s.index('__asm__(".global _start'):]


def main(all_shapes=False):
    out = HERE / ('recovery22' if all_shapes else 'recovery01')
    out.mkdir(exist_ok=False)
    current = SOURCE / 'oracle.c'
    (out / 'successor_oracle.c').write_bytes(current.read_bytes())
    recovered = out / 'reconstructed_oracle.c'
    recovered.write_text(reconstruct(current.read_text()))
    manifest = json.loads((CAMP / 'rvv_extended04/manifest.json').read_text())
    results = []
    # Repeat the same successful reconstruction, without compiler tuning.
    for name in ([c['name'] for c in manifest['cases']] if all_shapes else ('rvv_matrix_e8_m4',)):
        entry = next(c for c in manifest['cases'] if c['name'] == name)
        cmd = entry['command'].copy()
        cmd[cmd.index(str(current))] = str(recovered)
        elf = out / name
        cmd[-1] = str(elf)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        (out / (name + '.build.log')).write_text(p.stdout + p.stderr)
        if p.returncode:
            raise RuntimeError(p.stderr)
        original = CAMP / 'rvv_extended04/overlay/opt/ara-tests' / name
        assert sha(original) == entry['sha256']
        objdump = Path(cmd[0]).with_name('riscv64-buildroot-linux-gnu-objdump')
        directory = out / (name + '_decode')
        directory.mkdir()
        for path, label in ((original, 'original'), (elf, 'reconstructed')):
            dis = subprocess.check_output([objdump, '-d', path], text=True)
            (directory / (label + '.dis')).write_text(dis)
        old = (directory / 'original.dis').read_text().splitlines(True)[2:]
        new = (directory / 'reconstructed.dis').read_text().splitlines(True)[2:]
        (directory / 'binary.diff').write_text(''.join(difflib.unified_diff(old, new)))
        results.append(dict(name=name, original_sha256=sha(original), reconstructed_sha256=sha(elf),
                            exact_elf_equal=sha(original)==sha(elf), disassembly_equal=old==new))
    report = dict(source_bytes_recovered=False, successor_sha256=sha(current),
                  expected_original_c_sha256=manifest['source_sha256']['oracle.c'],
                  reconstructed_c_sha256=sha(recovered), results=results)
    (out / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all', action='store_true')
    main(parser.parse_args().all)
