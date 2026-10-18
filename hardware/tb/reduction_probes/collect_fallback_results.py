#!/usr/bin/env python3
"""Validate completed paired fallback probes and report matching cycle windows."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from gen_exact_seed_fallback_oracle import decode,round_rne


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    directory=args.directory.resolve()
    app='perf_exact_seed_fallback_latency'
    frozen_elf=directory/'elfs'/app
    elf_hash=sha(frozen_elf)
    expected={}
    for scenario,(source,initial) in enumerate(zip((0,0,32,32<<149),(0x40400000,0x40400000,0x3f800000,1))):
        for chain in (0,1):
            seed=initial;flags_or=0;steps=[]
            for iteration in range(8):
                bits,flags=round_rne(source+decode(seed));flags_or|=flags
                steps.append({'bits':hex(bits),'flags':flags})
                if chain:seed=bits
            expected[scenario,chain]=(bits,flags,flags_or,steps)
    results=[]
    for mode in ('baseline','integrated'):
        run=directory/mode
        manifest=json.loads((run/'manifest.json').read_text())
        assert manifest['state']=='COMPLETE' and manifest['expected_apps']==[app]
        assert sha(Path(manifest['simulator']))==manifest['simulator_sha256']
        assert len(manifest['tests'])==1
        test=manifest['tests'][0]
        assert test['pass'] and test['returncode']==0 and not test['failures']
        assert test['elf_sha256']==elf_hash==sha(run/'inputs'/app)
        log=run/app/'stdout.log';text=log.read_text()
        assert 'Core Test *** SUCCESS *** (tohost = 0)' in text
        assert '$finish at simulation time' in text and 'EXACT_SEED_FALLBACK_DONE cases=8 PASS' in text
        assert not re.search(r'Fatal:|Error:|\bFAIL\b|EXACT_SEED_FALLBACK_FAIL',text)
        lines=re.findall(r'^EXACT_SEED_FALLBACK .*$',text,re.M)
        assert len(lines)==8
        windows=[];seen=set()
        for line in lines:
            fields=dict(re.findall(r'(\w+)=(\S+)',line))
            scenario,chain=int(fields['scenario']),int(fields['chain'])
            assert (scenario,chain) in expected and (scenario,chain) not in seen
            seen.add((scenario,chain))
            bits,flags,flags_or,steps=expected[scenario,chain]
            assert line.endswith(' PASS') and fields['vl']=='32' and fields['reductions']=='8'
            assert int(fields['result'],16)==bits and int(fields['flags'],16)==flags and int(fields['flags_or'],16)==flags_or
            cycles=int(fields['cycles']);assert cycles>0
            windows.append({'scenario':scenario,'chain':chain,'cycles':cycles,'cycles_per_reduction':cycles/8,
                            'result':hex(bits),'last_fflags':flags,'fflags_or':flags_or,'integer_oracle_steps':steps})
        assert seen==set(expected)
        results.append({'mode':mode,'simulator':manifest['simulator'],'simulator_sha256':manifest['simulator_sha256'],
                        'elf_sha256':elf_hash,'stdout_sha256':sha(log),'windows':windows,'tohost_success':True})
    baseline={(w['scenario'],w['chain']):w['cycles'] for w in results[0]['windows']}
    for window in results[1]['windows']:
        window['delta_vs_baseline']=window['cycles']-baseline[window['scenario'],window['chain']]
    report={'scope':'Eight serialized exact seed fallback boundaries; eight reductions/window, same frozen ELF, same timed intervals. No SoC-wide timing claim.',
            'all_numeric_fflags_and_tohost_pass':True,'same_elf_hash_verified':True,
            'residual_cycle_increase_observed':any(w['delta_vs_baseline']>0 for w in results[1]['windows']),
            'results':results,'collector_sha256':sha(Path(__file__)),
            'oracle_generator_sha256':sha(Path(__file__).with_name('gen_exact_seed_fallback_oracle.py'))}
    with args.out.open('x') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    for window in results[1]['windows']:
        key=window['scenario'],window['chain']
        print('scenario=%d chain=%d baseline=%d integrated=%d delta=%+d'%(*key,baseline[key],window['cycles'],window['delta_vs_baseline']))


if __name__=='__main__':
    main()
