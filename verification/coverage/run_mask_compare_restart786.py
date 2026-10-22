"""One180s frozen-image run prepared against formal786; separate route/run approval."""
import argparse
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace

import preflight_mask_compare_restart785 as p
import run_vfirst_long_mask as mature

life, require, worker, toggle, bitmap = mature.life, mature.require, mature.worker, mature.toggle, mature.bitmap
NAME='mask_compare_restart'
PRE=life.OUT/'mask-compare-restart-preflight785-agent-20261008-01/preflight.json'
PRE_SHA='f2bf92408da3ce248ca5ceee57e9628e5e7375b9f7addbb9a2cb79699f01fdc5'
ELF=PRE.parent/'input.elf'
ELF_SHA='ba86552559f96eb9e7ad377ec5242c7114c57ff844a7a34f17d6804cf939178b'
IMAGE_SHA=mature.IMAGE_SHA
BASE=life.OUT/'qbs-two-phase-m4-offline-admitted786-agent-20261008-01'
BASE_SHA='384c2b5b364f41a49968aac913b8e0904b5fe2f83c5af818af3afe535d864904'
BUDGET=180


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(ELF),
        '+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(out/'commit_trace.csv'),
        '+VECTOR_TRACE='+str(out/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch',
        '-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]


def preflight():
    q=life.read_bound(PRE,PRE_SHA); life.check(q['input_pins'])
    require(q['status']=='MASK_COMPARE_RESTART_HOST_SPIKE_PASS_NOT_DUT' and q['ELF']==str(ELF) and
        life.digest(ELF)==ELF_SHA and q['counts']['checks']==1905 and q['counts']['cases']==3 and
        q['counts']['explicit_VRF_writers']==12 and q['counts']['defined_mask_bits']==192 and
        q['counts']['unknown_active_bits_skipped']==0 and q['counts']['runtime']['entry_to_tohost_instructions']==44559 and
        q['counts']['runtime']['all_runtime_memory_widths_decoded'] is True and
        q['coverage_admitted'] is False and q['VCS_started'] is False,'Exact sealed preflight')
    require('sim_l2_mb=2' in life.read_bound(mature.COMPILE,mature.COMPILE_SHA)['command'],'Frozen2MiB image')
    return q


def baseline(q):
    a=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    old=life.read_bound(p.BASE/'admission-manifest.json',p.BASE_SHA)
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(p.BASE/'admission-manifest.json'):p.BASE_SHA}
    for base,manifest in ((BASE,a),(p.BASE,old)):
        for name in ('combined-inputs.txt','combined-bits.json'):
            path=base/name; pins[str(path)]=manifest['output_pins'][str(path)]
    life.check(pins)
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    prior=(p.BASE/'combined-inputs.txt').read_text().splitlines()
    require(a['coverage_admitted'] is True and a['baseline']==str(p.BASE) and a['baseline_seal']==p.BASE_SHA and
        len(ledger)==len(set(ledger))==787 and ledger[:-1]==prior,'Exact formal786 sequential785 prefix')
    bits=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    require(bits['tests']==ledger[1:],'Exact786 bitmap ledger')
    cache=life.read_bound(mature.CACHE,p.inventory.rank.old.CACHE_SHA)
    pins[str(mature.CACHE)]=p.inventory.rank.old.CACHE_SHA
    prefix=next(Path(f) for f in cache['input_pins'] if f.endswith('/inputs.txt'))
    pins[str(prefix)]=cache['input_pins'][str(prefix)]; life.check({str(prefix):pins[str(prefix)]})
    require(ledger[:742]==prefix.read_text().splitlines(),'Exact sealed741 prefix')
    scopes={t['scope'] for t in q['baseline']['targets']}
    before={s:{k:cache['instances'][s][k] for k in ('width','checksum','bits')} for s in scopes}
    for vdb in ledger[742:]:
        files=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique native admitted suffix')
        rows,h=toggle.rows(files[0],scopes)
        require(a['input_pins'][str(files[0])]==h,'Bound786 suffix native data')
        pins[str(files[0])]=h; before=toggle.union(before,rows)
    targets=[]
    for t in q['baseline']['targets']:
        row=before[t['scope']]; require(row['checksum']==t['checksum'],'Actual compiled requester')
        missing=[i for i in t['original783_coordinates'] if not(int(row['bits'],16)>>(row['width']-1-i)&1)]
        targets.append(dict(t,missing_coordinates=missing,baseline_population=786))
    for name,h in bits['design'].items():
        path=Path(ledger[0])/'snps/coverage/db'/name
        require(a['input_pins'][str(path)]==h,'Design source ownership'); pins[str(path)]=h
    life.check(pins)
    return a,bits,before,targets,pins


def prepare(out,existing=False):
    import collect_mask_compare_restart786 as collector
    require(out.parent==life.OUT and out.resolve()==out and (out.is_dir() if existing else not out.exists()),
        'Fresh run or explicit terminal directory')
    q=preflight(); a,bits,before,targets,bp=baseline(q)
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['image'][str(life.IMAGE)]==IMAGE_SHA,'Exact runtime66')
    pins=life.merge_pins(life.merge_pins(q['input_pins'],bp),image['image'])
    fixed={str(PRE):PRE_SHA,str(life.PLAN):life.PLAN_SEAL,str(mature.COMPILE):mature.COMPILE_SHA}
    modules=[p,worker,toggle,bitmap,collector]; seen=set()
    while modules:
        module=modules.pop()
        if id(module) in seen: continue
        seen.add(id(module)); file=getattr(module,'__file__',None)
        if file:
            path=Path(file).resolve()
            if path.suffix=='.py' and life.ROOT/'verification' in path.parents:
                fixed[str(path)]=life.digest(path)
                modules.extend(v for v in vars(module).values() if isinstance(v,ModuleType))
    for name in ('run_mask_compare_restart786.py','collect_mask_compare_restart786.py','test_mask_compare_restart786_run_collect.py'):
        path=Path(__file__).with_name(name); fixed[str(path)]=life.digest(path)
    pins=life.merge_pins(pins,fixed); life.check(pins)
    return dict(schema='MASK_COMPARE_RESTART_RUN786_V1',case=NAME,output=str(out),command=command(out),pins=pins,
        preflight=str(PRE),preflight_seal=PRE_SHA,image_sha256=IMAGE_SHA,elf_sha256=ELF_SHA,baseline=786,
        baseline_seal=BASE_SHA,targets=targets,scoped_toggle_before=before,timeout_s=BUDGET,
        scalar_reference_instructions=44559,old_image_files_checked=66,foreground_lifetime=True,
        route_review_required_before_launch=True,authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        systemd_policy=dict(RuntimeMaxSec=240,TimeoutStopSec=10,KillMode='control-group'),
        budget_note='180s fixed; 44559 scalar retirements vs prior vfirst9918/63.166s. Linear projection284s is only a risk estimate, not measured runtime; parent must review budget before launch.',
        automatic_retry=False,no_FSDB=True,raw_commit=True,raw_vector=True,coverage_admitted=False,
        admission_performed=False,RTL_modified=False,qualification_required='All scalar/memory/CSR;12 native writers; legal mask postimage; store contexts; exact786 OR')


def invoke_run(out,manifest):
    ns=dict(worker.run.__globals__,BUDGET=BUDGET,PRE=ELF.parent,ELF_SEAL=ELF_SHA,IMAGE_SEAL=IMAGE_SHA,
            preflight=SimpleNamespace(NAME=NAME),command=command)
    return FunctionType(worker.run.__code__,ns,argdefs=worker.run.__defaults__)(out,
        dict(manifest,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


if __name__=='__main__':
    pcli=argparse.ArgumentParser(); pcli.add_argument('mode',choices=('prepare','verify','run'))
    pcli.add_argument('--output',type=Path,required=True); pcli.add_argument('--seal')
    pcli.add_argument('--parent-authorized',action='store_true'); pcli.add_argument('--parent-route-approved',action='store_true')
    args=pcli.parse_args()
    require((args.mode!='prepare')==bool(args.seal),'Verify/run require seal')
    require((args.mode=='run')==args.parent_authorized and (args.mode=='run')==args.parent_route_approved,
            'Separate parent launch and route approval required')
    out=args.output.resolve(); manifest=prepare(out); path=out.with_name(out.name+'.prepared.json')
    if args.mode=='prepare': life.save(path,manifest); print('PREPARED_NO_VCS',life.digest(path),len(manifest['pins']))
    else:
        require(life.read_bound(path,args.seal)==manifest,'Exact prepared manifest')
        if args.mode=='verify': print('VERIFY_PASS_NO_VCS')
        else: invoke_run(out,manifest)
