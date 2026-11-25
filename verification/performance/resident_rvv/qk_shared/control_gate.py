#!/usr/bin/env python3
"""Small central resident ownership gate. Freeze and VCS require parent review."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = Path('/home/wangwy/openproject/ara_dsa')
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
DEFAULT = OUT/'stage3_control_gate_20261110_01'
AKV = 'hardware/src/vlsu/akv/'
LOCAL = ('control_gate.py', 'control_gate.sv', 'control_gate_test.py', 'control_gate_PLAN.md')
PRODUCTION = tuple(AKV+n+'.sv' for n in (
    'akv_resident_pv_group', 'akv_resident_pv_import', 'akv_resident_pv_reader',
    'resident_payload_fanout', 'akv_resident_pv_control'))
DOCS = ('hardware/docs/INFERENCE_STAGE3_RVV_RESIDENT_ATTENTION_20261110.md',
        'verification/performance/resident_rvv/qk_shared/PLAN.md')
SCOPE = ('Real central control/group/import/reader/fanout with deterministic tagged stub lanes '
         'and minimal synchronous memory model. No arithmetic, real SRAM, engine, native FPU '
         'coexistence, SoC, performance or FPGA acceptance.')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for path, digest in pins.items():
        if sha(path) != digest:
            raise ValueError('Source/image identity drift: '+path)


def infrastructure():
    path = HERE/'reader_gate.py'
    if not path.exists():
        path = HERE/'control_gate_reader_infra.py'
    spec = importlib.util.spec_from_file_location('control_gate_reader_infra', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return path, module


def selection():
    path, infra = infrastructure()
    sources, defines, inherited = infra.source_selection()
    selected = [p for p in sources if p.name.endswith('_pkg.sv')]
    if len(selected) != 9:
        raise ValueError('Unexpected accepted package closure')
    # Preserve provenance documents, but pin only the dependency bytes consumed
    # here. This is not reacceptance of any predecessor live-source inventory.
    pins = {p: digest for p, digest in inherited.items()
            if p in {str(s) for s in selected} or Path(p).name in
            ('report.json', 'source-pins.json', 'sources.f')}
    pins[str(path)] = sha(path)
    return selected, defines, pins, path, infra.FROZEN


def expected_cases():
    cases = []
    def add(qk, t, h, d, b, phase=0):
        cases.append(dict(id=len(cases)+1, phase=phase, qk=qk, tokens=t,
                          heads=h, dimensions=d, base=b))
    add(0,3,2,64,0)
    for i,t in enumerate((1,2,3,17,64)):
        for h in (1,2):
            add(1,t,h,64,8-h if i%2 else 3)
    add(1,17,2,96,3)
    add(1,64,2,128,6)
    for phase in range(1,11):
        add(int(phase not in (8,10)),64 if phase in (2,3) else 17,2,64,
            7 if phase==6 else 3,phase)
        add(1,1,1,64,7)
        add(0,3,1,64,0)
    return cases


def work(case):
    qk,t,h,d = (case[k] for k in ('qk','tokens','heads','dimensions'))
    elements = [max(0,(t+3-l)//4) for l in range(4)]
    seeds = sum((n+1)//2*h for n in elements) if qk else 4*(d//16)*h
    return dict(sources=0 if qk else 96, seeds=seeds,
                coefficients=d*min(t,4) if qk else 4*t,
                values=d*sum((n+3)//4 for n in elements) if qk else 4*t*(d//16),
                results=seeds, acks=seeds, queries=d//16*h if qk else 0,
                columns=d//4 if qk else 0, reads=0 if qk else t*d//16)


def fields(line):
    pairs = re.findall(r'(\w+)=(\d+)',line)
    if ' '.join(k+'='+v for k,v in pairs)!=line or len(dict(pairs))!=len(pairs):
        raise ValueError('Malformed receipt: '+line)
    return {k:int(v) for k,v in pairs}


def check_log(log):
    if re.search(r'(?im)^\s*(?:Error|Fatal|Warning-\[|\$fatal|Assertion.*fail)',log):
        raise ValueError('Simulator diagnostic')
    cases = [fields(s) for s in re.findall(r'^CONTROL_GATE_CASE (.+)$',log,re.M)]
    expected = expected_cases()
    if len(cases)!=len(expected):
        raise ValueError('Missing/extra case receipts')
    metrics = {'error','launches','sources','seeds','coefficients','values','results','acks',
               'queries','columns','reads','barrier_hold','debt_hold','busy_hold','abort_busy',
               'stalls','checks','cycles'}
    for actual, identity in zip(cases,expected):
        if set(actual)!=set(identity)|metrics or any(actual[k]!=v for k,v in identity.items()):
            raise ValueError('Wrong/reordered/malformed case identity')
        phase = identity['phase']
        full = work(identity)
        if actual['error']!=int(phase!=0) or actual['sources']!=full['sources']:
            raise ValueError('Wrong status or source drain')
        if actual['launches']!=int(phase not in (1,5,6,7,9,10)):
            raise ValueError('Wrong launch count')
        if not 1<=actual['cycles']<=12000:
            raise ValueError('Case cycle bound')
        if actual['checks']!=sum(actual[k] for k in ('seeds','coefficients','values','results')):
            raise ValueError('Comparison ledger mismatch')
        if phase==0:
            if any(actual[k]!=v for k,v in full.items()):
                raise ValueError('Successful case work mismatch')
            if actual['barrier_hold']<2 or actual['debt_hold']<12 or actual['stalls']==0:
                raise ValueError('Missing barrier, delayed final ack or backpressure')
        else:
            if actual['results'] or actual['acks'] or actual['debt_hold']:
                raise ValueError('Failed case committed writes')
            for key in ('seeds','coefficients','values','queries','columns','reads'):
                if actual[key]>full[key]:
                    raise ValueError('Failed case exceeded admitted work')
            if phase in (1,5,6,7,9,10) and any(actual[k] for k in
                ('seeds','coefficients','values','queries','columns','reads')):
                raise ValueError('Prelaunch failure mutated private state')
            if phase in (2,8) and not 0<actual['seeds']<full['seeds']:
                raise ValueError('Seed abort did not interrupt seeds')
            if phase==3 and (actual['busy_hold']<1 or actual['abort_busy']<3):
                raise ValueError('Missing fast-lane K-busy drain discriminator')
            if phase==4 and (actual['barrier_hold']<1 or any(actual[k]!=full[k] for k in
                ('seeds','coefficients','values','queries','columns','reads'))):
                raise ValueError('Missing full-input precommit abort')
        if phase!=3 and (actual['busy_hold'] or actual['abort_busy']):
            raise ValueError('Unexpected busy-abort phase')
    totals = [fields(s) for s in re.findall(r'^CONTROL_GATE_PASS (.+)$',log,re.M)]
    if len(totals)!=1 or set(totals[0])!={'cases','checks','cycles'}:
        raise ValueError('Missing/duplicate/malformed completion')
    total=totals[0]
    if total['cases']!=len(expected) or total['checks']!=sum(c['checks'] for c in cases) or not (
        sum(c['cycles'] for c in cases)<total['cycles']<500000):
        raise ValueError('Completion totals mismatch')
    markers = re.findall(r'^CONTROL_GATE_\S+',log,re.M)
    if len(markers)!=len(expected)+1 or markers[-1]!='CONTROL_GATE_PASS':
        raise ValueError('Unexpected receipt or misplaced completion')
    return dict(cases=cases,totals=total)


def prepare(out):
    sources,defines,pins,infra_path,frozen = selection()
    for root,branch in ((REPO,'ara_dsa'),(OUT.parents[1],'ara_dsa_signoff_integration')):
        if subprocess.check_output(['git','-C',str(root),'branch','--show-current'],text=True).strip()!=branch:
            raise ValueError('Wrong branch: '+str(root))
    vcs=shutil.which('vcs')
    if not vcs:
        raise ValueError('VCS unavailable')
    out.mkdir(exist_ok=False)
    inputs=out/'inputs'
    inputs.mkdir()
    def copy(source,dest):
        digest=pins.get(str(source),sha(source))
        if sha(source)!=digest:
            raise ValueError('Source changed before copy: '+str(source))
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
        dest.chmod(0o444)
        pins[str(source)]=pins[str(dest)]=digest
        if sha(dest)!=digest:
            raise ValueError('Copy identity mismatch')
    selected=[]
    for source in sources:
        dest=inputs/source.relative_to(frozen)
        copy(source,dest)
        selected.append(str(dest))
    for relative in PRODUCTION:
        copy(REPO/relative,inputs/relative)
        selected.append(str(inputs/relative))
    for name in LOCAL:
        copy(HERE/name,inputs/name)
    copy(infra_path,inputs/'control_gate_reader_infra.py')
    for relative in DOCS:
        copy(REPO/relative,inputs/'audit'/relative)
    copy(REPO/AKV/'akv_engine.sv',inputs/'audit/akv_engine.sv')
    if any('`include' in Path(p).read_text() for p in selected):
        raise ValueError('Unpinned include in compilation closure')
    filelist=inputs/'sources.f'
    filelist.write_text('\n'.join(defines+selected+[str(inputs/'control_gate.sv')])+'\n')
    pins[str(filelist)]=sha(filelist)
    pins[str(Path(vcs).resolve())]=sha(vcs)
    save(out/'selection.json',dict(vcs=vcs,top='control_gate_tb',scope=SCOPE,sources=selected,
         inherited_scope='Selected accepted package bytes, not predecessor live-source reacceptance',
         parent_reviewed=True,compile_seconds=240,simulation_seconds=60,cases=expected_cases()))
    pins[str(out/'selection.json')]=sha(out/'selection.json')
    verify(pins)
    save(out/'source-pins.json',pins)
    save(out/'prepared.json',dict(state='PREPARED_NOT_EXECUTED'))


def command(argv,cwd,log,seconds):
    with log.open('x') as stream:
        process=subprocess.Popen(argv,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            rc=process.wait(timeout=seconds)
        except BaseException:
            os.killpg(process.pid,signal.SIGKILL)
            process.wait()
            raise
    text=log.read_text(errors='replace')
    if rc:
        raise ValueError(f'Command exited {rc}: {log}')
    return text


def execute(out):
    pins=json.loads((out/'source-pins.json').read_text())
    config=json.loads((out/'selection.json').read_text())
    workdir=out/'work'
    workdir.mkdir(exist_ok=False)
    report=dict(state='FAIL',scope=config['scope'])
    try:
        verify(pins)
        commands=dict(tests=[sys.executable,'-B',str(out/'inputs/control_gate_test.py')],
            compile=[config['vcs'],'-full64','-sverilog','-timescale=1ns/1ps','-j4','-top',
                     'control_gate_tb','+define+SIMULATION','-f',str(out/'inputs/sources.f'),'-o','simv'],
            run=[str(workdir/'simv'),'-no_save'])
        save(out/'commands.json',commands)
        command(commands['tests'],workdir,out/'tests.log',30)
        print('CONTROL_GATE_COMPILING '+str(out),flush=True)
        build=command(commands['compile'],workdir,out/'compile.log',config['compile_seconds'])
        if re.search(r'(?im)^\s*(Error|Warning-\[)',build):
            raise ValueError('Compile diagnostic requires review')
        verify(pins)
        image={str(p):sha(p) for p in (workdir/'simv.daidir').rglob('*') if p.is_file()}
        image[str(workdir/'simv')]=sha(workdir/'simv')
        save(out/'image-pins.json',image)
        print('CONTROL_GATE_RUNNING '+str(out),flush=True)
        checked=check_log(command(commands['run'],workdir,out/'run.log',config['simulation_seconds']))
        verify(pins)
        verify(image)
        save(out/'source-pins-after.json',pins)
        save(out/'image-pins-after.json',image)
        report.update(state='PASS',post_pins_match=True,post_image_match=True,**checked)
    except Exception as exc:
        report['error']=str(exc)
    report['artifacts']={str(out/n):sha(out/n) for n in (
        'source-pins.json','selection.json','prepared.json','commands.json','tests.log','compile.log',
        'run.log','image-pins.json','source-pins-after.json','image-pins-after.json') if (out/n).is_file()}
    save(out/'report.json',report)
    print('CONTROL_GATE_'+report['state']+' '+str(out/'report.json'),flush=True)
    return int(report['state']!='PASS')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',nargs='?',type=Path,default=DEFAULT)
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--parent-reviewed',action='store_true')
    args=parser.parse_args()
    if args.list:
        sources,defines,_,_,_=selection()
        print('\n'.join(defines+[str(p) for p in sources]+[str(REPO/p) for p in PRODUCTION]+[str(HERE/'control_gate.sv')]))
        return 0
    out=args.output.resolve()
    if out.parent!=OUT or not out.name.startswith('stage3_control_gate_'):
        parser.error('Use a fresh stage3_control_gate_* direct child of signoff verification/out')
    if not args.parent_reviewed or args.prepare==args.execute:
        parser.error('Explicit parent review and exactly one of --prepare/--execute required')
    if args.execute:
        if Path(__file__).resolve()!=out/'inputs/control_gate.py':
            parser.error('Execute only the frozen runner')
        return execute(out)
    prepare(out)
    print('CONTROL_GATE_PREPARED_NOT_EXECUTED '+str(out))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
