"""Preserve the original mask trial order and stop after its first failing trial."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
import masks


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def instrument(source):
    old='            if(functions[raw_op](a,b,output+1,vl,cap,predicate,start))++errors;'
    assert source.count(old)==1
    source=source.replace(old,'            unsigned long returned=functions[raw_op](a,b,output+1,vl,cap,predicate,start);\n            if(returned)++errors;')
    source=source.replace('    unsigned cap=capacity(),errors=0,cases=0;',
                          '    unsigned cap=capacity(),errors=0,cases=0,printed=0;')
    source=source.replace('            for(unsigned i=0;i<cap;++i) {',
                          '            for(unsigned i=0;i<cap;++i) {\n                unsigned before_element=errors;')
    point='                } else if(op==18 || op==19) {'
    assert source.count(point)==1
    detail='''                    if(errors!=before_element && !printed++) {
                        text("RVV_MASK_BIT seed=");num(seed);text(" op=");num(raw_op);
                        text(" vl=");num(vl);text(" mask=");num(mode);text(" vstart=");num(start);
                        text(" element=");num(i);text(" active=");num(active);
                        text(" old=");num(old);text(" expected=");num(active ? expected:old);
                        text(" actual=");num(actual);text("\\n");
                    }
'''
    source=source.replace(point,detail+point)
    source=source.replace('            ++cases;', '''            ++cases;
            if(errors) {
                text("RVV_MASK_FIRST seed=");num(seed);text(" op=");num(raw_op);
                text(" vl=");num(vl);text(" mask=");num(mode);text(" vstart=");num(start);
                text(" returned_vstart=");num(returned);text(" errors=");num(errors);
                text(" guard_before=");num(output[0]);text(" guard_after=");num(output[1025]);
                text("\\n");goto probe_done;
            }''')
    source=source.replace('    text(errors ? "RVV_MASK_FAIL', 'probe_done:\n    text(errors ? "RVV_MASK_FAIL')
    return source


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--cross',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    raw=json.loads(a.report.read_text());report=raw.get('report',raw)
    names={r['name'] for r in report['results'] if r['status']=='failed' and
           r['name'].startswith(('rvv_masks_cmp_alias_restart_','rvv_masks_scalar_restart_'))}
    inputs={c['name']:c for c in report['inputs']['cases']}
    a.out.mkdir(exist_ok=False)
    binaries=a.out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    manifest=dict(scope='First failing mask trial with original preceding order',cases=[],
        original_report_sha256=sha(a.report),source_sha256={p.name:sha(p) for p in
            (TOOLS/'mask_oracle.c',TOOLS/'masks.py',Path(__file__))},board_tested=False)
    for family,scalar in [('rvv_mask_scalar_restart01',True),('rvv_mask_alias_restart01',False)]:
        root=a.campaign/family
        original=json.loads((root/'manifest.json').read_text())
        for case in original['cases']:
            if case['name'] not in names:continue
            assert case['sha256']==inputs[case['name']]['sha256']
            name=case['name'].replace('rvv_','rvv_trace_',1)
            d=a.out/name;d.mkdir()
            asm=root/(case['name']+'.S')
            assert asm.read_text()==masks.assembly(case['sew'],case['lmul'],scalar_forms=scalar,
                                                  comparison_aliases=not scalar,restart=True)
            for f in ('operations.h',):shutil.copy2(root/f,d/f)
            shutil.copy2(asm,d/'scenario.S')
            flags=[a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
                '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
                '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
                '-Wall','-Wextra','-Werror',f'-DSEW={case["sew"]}',f'-DSCALAR_FORMS={int(scalar)}',
                '-DALIASES=0',f'-DCOMPARISON_ALIASES={int(not scalar)}','-DCARRY_FORMS=0',
                '-DRESTART_MASKS=1','-I'+str(d)]
            rebuilt=d/'original_rebuilt.elf'
            subprocess.run(flags+[str(TOOLS/'mask_oracle.c'),str(d/'scenario.S'),'-o',str(rebuilt)],check=True)
            assert sha(rebuilt)==case['sha256'], 'Current source does not recreate original ELF: '+case['name']
            c=d/'scenario.c';c.write_text(instrument((TOOLS/'mask_oracle.c').read_text()))
            binary=binaries/name
            subprocess.run(flags+[str(c),str(d/'scenario.S'),'-o',str(binary)],check=True)
            manifest['cases'].append(dict(case,name=name,sha256=sha(binary),original_name=case['name'],
                original_elf_sha256=case['sha256'],original_rebuild_byte_identical=True,
                scenario_role='first_failure_prefix_trace',scenario_sources={f:sha(d/f)
                    for f in ('scenario.c','scenario.S','operations.h')}))
    assert len(manifest['cases'])==len(names) and names
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (a.out/'overlay.cpio').open('wb') as output:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('opt\nopt/ara-tests\n'+''.join('opt/ara-tests/'+c['name']+'\n' for c in manifest['cases'])).encode(),
            stdout=output,check=True)
    print('CASES',len(names))


if __name__=='__main__':main()
