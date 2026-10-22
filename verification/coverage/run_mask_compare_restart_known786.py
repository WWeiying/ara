"""Known old-vd successor: one reviewed360s run with read-only focused VPD."""
import argparse
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace

import preflight_mask_compare_restart_known786 as p
import run_vfirst_long_mask as mature

life, require, worker, toggle, bitmap = mature.life, mature.require, mature.worker, mature.toggle, mature.bitmap
NAME='mask_compare_restart_known_old'
PRE=life.OUT/'mask-compare-restart-known-preflight786-agent-20261008-01/preflight.json'
PRE_SHA='9895bf5b08c552617b438d525ee92c6f406ebbd20c2782a608702486238300a0'
ELF=PRE.parent/'input.elf'
ELF_SHA='acfef995d5e3afa76da43f7938e080b759b98177f647a150e86cd2f6eac10246'
IMAGE_SHA=mature.IMAGE_SHA
BASE=life.OUT/'qbs-two-phase-m4-offline-admitted786-agent-20261008-01'
BASE_SHA='384c2b5b364f41a49968aac913b8e0904b5fe2f83c5af818af3afe535d864904'
BUDGET=360
PROBE=Path(__file__).with_name('mask_compare_restart_known786_probe.tcl')
SERVICE='ara-mask-compare-known786-parent-20261008-01.service'


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(ELF),
        '+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(out/'commit_trace.csv'),
        '+VECTOR_TRACE='+str(out/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch',
        '-cm_dir',str(out/'code.vdb'),'-cm_name',NAME,'-ucli','-do',str(PROBE)]


def preflight():
    q=life.read_bound(PRE,PRE_SHA); life.check(q['input_pins'])
    require(q['status']=='MASK_COMPARE_RESTART_HOST_SPIKE_PASS_NOT_DUT' and q['ELF']==str(ELF) and
        life.digest(ELF)==ELF_SHA and q['counts']['checks']==2705 and q['counts']['cases']==3 and
        q['counts']['explicit_VRF_writers']==13 and q['counts']['defined_mask_bits']==192 and
        q['counts']['unknown_active_bits_skipped']==0 and q['counts']['runtime']['entry_to_tohost_instructions']==58822 and
        q['counts']['runtime']['all_runtime_memory_widths_decoded'] is True and
        q['coverage_admitted'] is False and q['VCS_started'] is False,'Exact sealed preflight')
    require('sim_l2_mb=2' in life.read_bound(mature.COMPILE,mature.COMPILE_SHA)['command'],'Frozen2MiB image')
    return q


def baseline(q):
    a=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    old=life.read_bound(p.old.BASE/'admission-manifest.json',p.old.BASE_SHA)
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(p.old.BASE/'admission-manifest.json'):p.old.BASE_SHA}
    for base,manifest in ((BASE,a),(p.old.BASE,old)):
        for name in ('combined-inputs.txt','combined-bits.json'):
            path=base/name; pins[str(path)]=manifest['output_pins'][str(path)]
    life.check(pins)
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    prior=(p.old.BASE/'combined-inputs.txt').read_text().splitlines()
    require(a['coverage_admitted'] is True and a['baseline']==str(p.old.BASE) and a['baseline_seal']==p.old.BASE_SHA and
        len(ledger)==len(set(ledger))==787 and ledger[:-1]==prior,'Exact formal786 sequential785 prefix')
    bits=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    require(bits['tests']==ledger[1:],'Exact786 bitmap ledger')
    cache=life.read_bound(mature.CACHE,p.old.inventory.rank.old.CACHE_SHA)
    pins[str(mature.CACHE)]=p.old.inventory.rank.old.CACHE_SHA
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
    import collect_mask_compare_restart_known786 as collector
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
    for name in ('run_mask_compare_restart_known786.py','collect_mask_compare_restart_known786.py','test_mask_compare_restart_known786_run_collect.py'):
        path=Path(__file__).with_name(name); fixed[str(path)]=life.digest(path)
    fixed[str(PROBE)]=life.digest(PROBE)
    book=life.ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    book_sha='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
    sources=life.read_bound(book,book_sha); fixed[str(book)]=book_sha
    for rel in ('hardware/src/lane/lane.sv','hardware/src/lane/vector_regfile.sv',
                'hardware/src/lane/operand_requester.sv','hardware/src/masku/masku.sv'):
        path=life.ROOT/rel; fixed[str(path)]=sources[str(path)]
    pins=life.merge_pins(pins,fixed); life.check(pins)
    return dict(schema='MASK_COMPARE_KNOWN_OLD_RUN786_V1',case=NAME,output=str(out),command=command(out),pins=pins,
        preflight=str(PRE),preflight_seal=PRE_SHA,image_sha256=IMAGE_SHA,elf_sha256=ELF_SHA,baseline=786,
        baseline_seal=BASE_SHA,targets=targets,scoped_toggle_before=before,timeout_s=BUDGET,
        scalar_reference_instructions=58822,old_image_files_checked=66,foreground_lifetime=True,
        route_review_required_before_launch=True,authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        service=SERVICE,probe=str(PROBE),probe_read_only=True,
        systemd_policy=dict(RuntimeMaxSec=420,TimeoutStopSec=10,KillMode='control-group'),
        budget_note='360s upfront;58822 retirements / measuredVALU170167*850.9s approximately294s plus margin; no retry.',
        automatic_retry=False,no_FSDB=True,raw_commit=True,raw_vector=True,coverage_admitted=False,
        admission_performed=False,RTL_modified=False,qualification_required='All scalar/memory/CSR;13 native writers; actual known-old legal mask postimage; v2 unchanged; stores; exact786 OR')


def live_identity(pid,out,manifest):
    import os
    proc=Path('/proc')/str(pid)
    exe=(proc/'exe').resolve(strict=True)
    require(exe==life.IMAGE.resolve(strict=True) and life.digest(exe)==IMAGE_SHA,'Live frozen simv SHA')
    require((proc/'cwd').resolve(strict=True)==out,'Live child cwd')
    cmd=[v.decode() for v in (proc/'cmdline').read_bytes().split(b'\0') if v]
    require(cmd==manifest['command'],'Live child command')
    cgroup=(proc/'cgroup').read_text()
    require(any(SERVICE in line.split(':',2)[-1].split('/') for line in cgroup.splitlines()),'Owning systemd cgroup')
    require(os.getpgid(pid)==pid,'Independent child process group')
    return dict(pid=pid,exe=str(exe),executable_sha256=IMAGE_SHA,cwd=str(out),command=cmd,
        cgroup=cgroup,service=SERVICE,runtime66_verified=True)

def invoke_run(out,manifest):
    import subprocess
    import os
    import signal
    def verified_popen(*args,**kwargs):
        child=subprocess.Popen(*args,**kwargs)
        try:
            identity=live_identity(child.pid,out,manifest)
            life.save(out/'live-simv-identity.json',identity)
            print('LIVE_SIMV_VERIFIED',child.pid,flush=True)
        except BaseException:
            try: os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait()
            raise
        return child
    proxy=SimpleNamespace(**dict(vars(subprocess),Popen=verified_popen))
    ns=dict(worker.run.__globals__,BUDGET=BUDGET,PRE=ELF.parent,ELF_SEAL=ELF_SHA,IMAGE_SEAL=IMAGE_SHA,
            preflight=SimpleNamespace(NAME=NAME),command=command,subprocess=proxy)
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
