#!/usr/bin/env python3
"""Bounded VMFPU compare-NV producer contract regression, without MASKU/CPU."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
FROZEN = Path('/home/wangwy/fpga_runs/current_board_integration_final02/frozen/sources')
MANIFEST = Path('/tmp/ordered-reduction-extended-after-20261010-01/command.json')
WORDS = 12
FORMATS = {8:(5,2),16:(5,10),32:(8,23),64:(11,52)}


def properties(bits, width):
    eb, mb = FORMATS[width]
    exp = (bits >> mb) & ((1 << eb)-1)
    mant = bits & ((1 << mb)-1)
    nan = exp == (1 << eb)-1 and mant != 0
    snan = nan and not (mant >> (mb-1))
    if exp == (1 << eb)-1:
        value = math.nan if nan else math.inf
    else:
        value = math.ldexp((1 if exp else 0) + mant / (1 << mb),
                           (exp if exp else 1) - ((1 << (eb-1))-1))
    if bits >> (width-1):
        value = -value
    return nan, snan, value


def constants(width):
    eb, mb = FORMATS[width]
    bias = (1 << (eb-1))-1
    inf = ((1 << eb)-1) << mb
    return dict(one=bias << mb, two=(bias+1) << mb,
                three=((bias+1) << mb) | (1 << (mb-1)),
                snan=inf | 1, qnan=inf | (1 << (mb-1)),
                inf=inf, ninf=inf | (1 << (width-1)),
                zero=0, nzero=1 << (width-1), negone=(bias << mb) | (1 << (width-1)))


def oracle(a, b, width, kind):
    c = constants(width)
    an, ass, av = properties(a, width)
    bn, bs, bv = properties(b, width)
    nv = ass or bs
    if kind < 6:
        nv = nv if kind < 2 else an or bn
        boolean = [av == bv, av != bv, av < bv, av <= bv, av > bv, av >= bv][kind]
        return int(boolean), int(nv)
    if kind == 6:
        invalid_sum = math.isinf(av) and math.isinf(bv) and av != bv
        if an or bn or invalid_sum:
            return c['qnan'], int(nv or invalid_sum)
        if math.isinf(av): return a, int(nv)
        if math.isinf(bv): return b, int(nv)
        return c['three'], int(nv)  # finite VFADD fixtures are exactly 1+2
    if kind == 7:
        if an and bn: return c['qnan'], int(nv)
        if an: return b, int(nv)
        if bn: return a, int(nv)
        return (a if av < bv else b), int(nv)
    if an: return c['qnan'], int(ass)
    # Both seven-bit estimates of 1.0 are 1.1111111 * 2^-1.
    eb, mb = FORMATS[width]
    return ((((1 << (eb-1))-2) << mb) | (127 << (mb-7))), 0


def cases():
    result = []

    def add(width, kind, pattern, stalls, scalar=False, unboxed=False):
        c = constants(width)
        choices = dict(finite=('one','two'), snan_a=('snan','two'),
            snan_b=('one','snan'), qnan_a=('qnan','two'), qnan_b=('one','qnan'),
            both_snan=('snan','snan'), both_qnan=('qnan','qnan'),
            infinity=('inf','ninf'), zeros=('nzero','zero'), negative=('negone','one'))
        ka, kb = choices[pattern]
        scalar_raw = c[kb]
        if scalar and not unboxed:
            scalar_raw |= ((1 << 64)-1) ^ ((1 << width)-1)
        scalar_normalized = c['qnan'] if unboxed and width in (16,32) else c[kb]
        words = []
        flags = 0
        for n in range(WORDS):
            a = b = exp = nv = 0
            for e in range(64//width):
                aa = c[ka] if e == n % (64//width) else c['one']
                bb = scalar_normalized if scalar else c[kb] if e == n % (64//width) else c['two']
                if kind >= 8: bb = c['one']
                answer, invalid = oracle(aa, bb, width, kind)
                a |= aa << (e*width)
                b |= bb << (e*width)
                exp |= answer << (e*width)
                nv |= invalid << e
            flags |= 16 if nv else 0
            words.append(dict(a=a,b=b,result=exp,nv=nv))
        result.append(dict(id=len(result),name=f'w{width}_op{kind}_{pattern}_scalar{int(scalar)}_unboxed{int(unboxed)}_stall{stalls}',
            width=width,kind=kind,scalar=int(scalar),stalls=stalls,scalar_raw=scalar_raw,
            scalar_bits=scalar_normalized,flags=flags if kind>=6 else 0,words=words))

    for width in FORMATS:
        for kind in range(6):
            for pattern in ('finite','snan_a','snan_b','qnan_a','qnan_b',
                            'both_snan','both_qnan','infinity','zeros','negative'):
                for stalls in (0,1): add(width,kind,pattern,stalls)
            for pattern in ('snan_b','qnan_b','finite'):
                add(width,kind,pattern,1,scalar=True)
            if width in (16,32):
                add(width,kind,'snan_b',1,scalar=True,unboxed=True)
        for kind in (6,7,8,9):
            if width==8 and kind>=8: continue
            for pattern in ('finite','snan_a','qnan_a'):
                add(width,kind,pattern,1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--vmfpu',type=Path,default=FROZEN/'hardware/src/lane/vmfpu.sv')
    parser.add_argument('--metadata-checks',action='store_true')
    args=parser.parse_args()
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    pins={}

    def snapshot(relative, source):
        data=source.read_bytes(); target=out/'inputs'/relative
        target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data); target.chmod(0o444)
        pins[relative]=dict(source=str(source),sha256=hashlib.sha256(data).hexdigest())
        return str(target)

    manifest=json.loads(MANIFEST.read_text())
    relatives=[s.split('/inputs/')[1] for s in manifest if '/inputs/hardware/' in s and s.endswith(('.sv','.v'))]
    sources=[snapshot(s,args.vmfpu.resolve() if s=='hardware/src/lane/vmfpu.sv' else FROZEN/s) for s in relatives]
    for directory in ('hardware/include/ara','hardware/deps/common_cells/include/common_cells'):
        for p in sorted((FROZEN/directory).glob('*.svh')): snapshot(str(p.relative_to(FROZEN)),p)
    sources.append(snapshot('test/producer_tb.sv',HERE/'producer_tb.sv'))
    for name in ('run.py','README.md'): snapshot('test/'+name,HERE/name)
    suite=cases()
    (out/'cases.json').write_text(json.dumps(suite,indent=2)+'\n')
    lines=[]
    for c in suite:
        lines.append(f'{c["id"]} {c["width"]} {c["kind"]} {c["scalar"]} {c["stalls"]} {c["scalar_bits"]:016x} {c["flags"]:02x}')
        lines += [f'{w["a"]:016x} {w["b"]:016x} {w["result"]:016x} {w["nv"]:02x}' for w in c['words']]
    (out/'cases.txt').write_text('\n'.join(lines)+'\n')
    (out/'pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    vcs='/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    verdi='/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1'
    env=dict(os.environ,VCS_HOME=vcs,VERDI_HOME=verdi,SNPSLMD_LICENSE_FILE='27000@t7920')
    env['PATH']=vcs+'/bin:'+env['PATH']
    command=['vcs','-full64','-sverilog','-timescale=1ns/1ps','-debug_access+all','-top','producer_tb',
        '+incdir+'+str(out/'inputs/hardware/deps/common_cells/include'),
        '+incdir+'+str(out/'inputs/hardware/include'),*sources,'-o',str(out/'simv'),'-l',str(out/'compile.log')]
    if args.metadata_checks: command.insert(1,'+define+COMPARE_METADATA')
    run=[str(out/'simv'),'-no_save','+FSDB']
    (out/'command.json').write_text(json.dumps(command,indent=2)+'\n')
    (out/'run_command.json').write_text(json.dumps(run,indent=2)+'\n')
    status=dict(state='STARTED',case_count=len(suite),vmfpu=pins['hardware/src/lane/vmfpu.sv'],
                scope='real VMFPU/FPnew producer only; no MASKU, dispatcher, CSR or CPU')
    try:
        with (out/'compile.console.log').open('w') as log:
            subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300,check=True)
        with (out/'run.console.log').open('w') as log:
            subprocess.run(run,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
        log=(out/'run.console.log').read_text()
        with (out/'results.csv').open() as stream: rows=list(csv.DictReader(stream))
        if f'PRODUCER_COMPLETE cases={len(suite)}' not in log or re.search(r'(?m)^(Error|Fatal)(-|:)',log):
            raise RuntimeError('Harness/simulator failure')
        if [int(r['id']) for r in rows]!=list(range(len(suite))): raise RuntimeError('Case accounting mismatch')
        failures=[r for r in rows if any(int(r[k]) for k in ('data_errors','nv_errors','raw_errors','tag_errors','flag_data_errors')) or
                  r['flags']!=r['expected_flags'] or r['flag_events']!=r['expected_events']]
        status.update(state='FAIL_PRODUCER_CONTRACT' if failures else 'PASS_PRODUCER_ONLY',failures=failures,
                      metadata_failures=sum(int(r['nv_errors'])>0 for r in rows),
                      data_failures=sum(int(r['data_errors'])>0 for r in rows))
        if args.metadata_checks and 'CLASSIFICATION_BANK_PASS' not in log:
            raise RuntimeError('Missing classification bank result')
        if args.metadata_checks and 'QUEUED_MIXED_PASS' not in log:
            raise RuntimeError('Missing queued ownership result')
        for relative,pin in pins.items():
            if hashlib.sha256((out/'inputs'/relative).read_bytes()).hexdigest()!=pin['sha256']:
                raise RuntimeError('Input snapshot changed: '+relative)
    except Exception as error: status.update(state='ERROR',error=repr(error))
    (out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps({k:v for k,v in status.items() if k!='failures'} | {'failure_count':len(status.get('failures',[]))},indent=2))
    return int(status['state']!='PASS_PRODUCER_ONLY')


if __name__=='__main__': raise SystemExit(main())
