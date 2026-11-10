#!/usr/bin/env python3
"""One frozen SDK-chain VCS attempt. prepare/preflight/service-command never launch.

Prepare: vcs_run.py prepare --soc-build OUT/stage3_soc_20261110_02 --output
OUT/stage4_projection_chain_vcs_20261110_01. Review source-pins.json, then obtain
service-command with --review-sha256. Only the parent launches that command.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=Path('/home/wangwy/openproject/ara_dsa')
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
ORIGINAL=ROOT/'verification/performance/next_mechanism/stage4/projection_graph'
SHARED=ROOT/'verification/performance/resident_rvv/qk_shared'
SOFTWARE=OUT/'stage4_projection_chain_build_20261110_02'
BUILDER_SHA='ad6cfb879e5ee61344a92591f2d78dd290e4a649b543e09b7f179ce88c3337b2'
BUILD_SHA='09312eaf6faa496bc5b8f4e7ee138df530b24b865d5d8aac86973a68b703849d'
FW_PINS_SHA='66c16cd2d87c6703eb2b8808c3299935f42c8840fcc1d6e6bcdbe27f89032580'
ELF_SHA='328a4b93e6f9847d756b8178688534d8a3a494a7fac4491feedceb7fda6db34c'
CHECKER={
    'check.py':'925e2b491eb098c9874f7892f20a4b3a358b9ede75eccc94f69292d3f17ce071',
    'contract.py':'b765409b67a686dc66bdf31d145d3586677913b7c166b392e685ca3f6aa56837',
    'elf_reader.py':'3317b30d500bef0cbeff9299001310ebe464ad4d1e53383aff0288f39af6dbb3',
}
IMAGE_CHECK=ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
IMAGE_CHECK_SHA='6b715db42be1baaf8fb6d7bb2714246786b99f3610ce2c74993950fcdef6bc08'
OWN=('vcs_run.py','test_vcs_run.py')
SIM_SECONDS,CHECK_SECONDS,PROTOCOL_SECONDS,SERVICE_SECONDS=9000,300,900,10800
STEPS=(('image_contract','image-contract',180),('simulation','console',SIM_SECONDS),
       ('chain','chain',CHECK_SECONDS),('protocol','protocol',PROTOCOL_SECONDS))
PREP_FILES=('selection.json','launch-receipt.json','runner-inventory.json',
            'host-tests.log','host-tests.command.json','image-contract.log',
            'image-contract.command.json','runtime-link.log','runtime-link.command.json')


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


builder=HERE/'build_soc.py' if (HERE/'build_soc.py').exists() else SHARED/'build_soc.py'
if hashlib.sha256(builder.read_bytes()).hexdigest()!=BUILDER_SHA:
    raise ValueError('Unreviewed Stage3 SoC contract')
b=load(builder,'stage4_projection_run_soc_contract')


def merge(pins,extra):
    for path,digest in extra.items():
        path=str(path)
        b.require(path not in pins or pins[path]==digest,'Conflicting pin: '+path)
        pins[path]=digest


def checker(local=None):
    local=SOFTWARE/'inputs' if local is None else Path(local)
    b.verify({local/name:digest for name,digest in CHECKER.items()})
    module=load(local/'check.py','stage4_projection_run_frozen_check')
    b.require(Path(module.c.__file__).resolve()==(local/'contract.py').resolve() and
              b.sha(module.c.__file__)==CHECKER['contract.py'],'Wrong checker contract import')
    return module


def protocol_inventory():
    root=ROOT/'verification/ara_verify'
    paths=sorted(root.rglob('*.py'))
    b.require(root/'uvm_dut.py' in paths and all(not p.is_symlink() for p in paths),
              'Incomplete/linked independent protocol checker')
    return {str(p):b.sha(p) for p in paths}


def source_layout(socdir):
    # Copies are an execution closure, not imports of another gate's checker.
    layout={name:(ORIGINAL/name) for name in OWN}
    layout.update({name:socdir/'inputs'/name for name in ('build_soc.py',*b.HELPERS)})
    layout.update({'checker/'+name:SOFTWARE/'inputs'/name for name in CHECKER})
    layout['image-check.sh']=IMAGE_CHECK
    layout.update({'verification/'+str(Path(p).relative_to(ROOT/'verification')):Path(p)
                   for p in protocol_inventory()})
    return layout


def collect(socdir):
    socdir=b.output_path(Path(socdir))
    soc,pins=b.checked_build(socdir)
    b.verify({socdir/'inputs/build_soc.py':BUILDER_SHA,SOFTWARE/'build.json':BUILD_SHA,
              SOFTWARE/'source-pins.json':FW_PINS_SHA,IMAGE_CHECK:IMAGE_CHECK_SHA})
    sw=checker().checked_build(SOFTWARE)
    b.require(sw['elf']==str(SOFTWARE/'projection_chain.elf') and sw['elf_sha256']==ELF_SHA and
              sw['commands']==256 and sw['calls']==4 and sw['outputs_per_call']==8192 and
              sw['expected_entries']==dict(stage4_baseline_produce=2,stage4_candidate_produce=2,
                                            qbs_native_execute_command=256),
              'Wrong frozen SDK-chain firmware/work')
    merge(pins,b.read(SOFTWARE/'source-pins.json'))
    merge(pins,sw['artifacts'])
    merge(pins,{SOFTWARE/'build.json':BUILD_SHA})
    merge(pins,{str(p):b.sha(p) for p in source_layout(socdir).values()})
    tools=(sys.executable,'/usr/bin/bash','/usr/bin/readelf','/usr/bin/ldd',
           '/usr/bin/systemctl','/usr/bin/systemd-run','/usr/bin/awk','/usr/bin/sed',
           '/usr/bin/grep','/usr/bin/tail')
    merge(pins,{str(Path(p).resolve()):b.sha(Path(p).resolve()) for p in tools})
    b.verify(pins)
    return soc,sw,pins


def environment(socdir,out):
    source=b.read(socdir/'plan.json')['environment']
    needed=('VCS_HOME','VCS_ARCH_OVERRIDE','SNPSLMD_LICENSE_FILE','HOME')
    b.require(all(source.get(k) for k in needed),'Missing accepted VCS environment')
    env={k:source[k] for k in (*needed,'LM_LICENSE_FILE') if source.get(k)}
    paths=[str(Path(env['VCS_HOME'])/'linux64/lib'),*source.get('LD_LIBRARY_PATH','').split(':')]
    env['LD_LIBRARY_PATH']=':'.join(dict.fromkeys(p for p in paths if p))
    env.update(PATH='/usr/bin:/bin',LC_ALL='C',TMPDIR='/tmp',
               PYTHONPATH=str(out/'inputs/verification'),PYTHONDONTWRITEBYTECODE='1',
               READELF='/usr/bin/readelf')
    b.require(all(isinstance(v,str) and '\n' not in v and '\0' not in v for v in env.values()),
              'Malformed execution environment')
    return env


def recipes(out,soc,sw,python):
    work=out/'work';simv=soc['simv'];elf=sw['elf']
    return dict(
        image_contract=['/usr/bin/bash',str(out/'inputs/image-check.sh'),str(Path(simv).parent),elf,'qbs'],
        simulation=[simv,'-no_save','-l',str(work/'run.vcs.log'),'+PRELOAD='+elf,
            '+TESTCASE=stage4_projection_chain','+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF',
            '+COMMIT_TRACE='+str(work/'commit.csv'),'+VECTOR_TRACE='+str(work/'vector_trace.csv'),
            '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],
        chain=[python,'-B',str(out/'inputs/checker/check.py'),'--build',str(SOFTWARE),
               '--log',str(work/'run.vcs.log'),'--vector',str(work/'vector_trace.csv'),
               '--commit',str(work/'commit.csv')],
        protocol=[python,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
            '--require-axi','--require-axi-write','--vector-trace',str(work/'vector_trace.csv'),
            '--log',str(work/'run.vcs.log'),'--simv',simv,'--elf',elf,
            '--output',str(work/'uvm_result.json')])


def selection(out,socdir,soc,sw):
    python=str(Path(sys.executable).resolve())
    return dict(schema='stage4-projection-chain-vcs-v1',soc_build=str(socdir),software_build=str(SOFTWARE),
        soc_receipt_sha256=b.sha(socdir/'build.json'),software_receipt_sha256=BUILD_SHA,
        firmware_pins_sha256=FW_PINS_SHA,elf_sha256=ELF_SHA,configuration=soc['configuration'],
        image_contract=soc['image_contract'],cpu_overlay=soc['cpu_overlay'],image_pins=soc['image_pins'],
        checker_sha256=CHECKER,protocol_inventory=protocol_inventory(),scope=sw['scope'],
        roi_included=sw['roi_included'],roi_excluded=sw['roi_excluded'],
        python=python,environment=environment(socdir,out),commands=recipes(out,soc,sw,python),
        sim_seconds=SIM_SECONDS,checker_seconds=CHECK_SECONDS,protocol_seconds=PROTOCOL_SECONDS,
        service_seconds=SERVICE_SECONDS,automatic_retry=False,fsdb=False,full_ggml=False,
        performance_acceptance=False)


def output_path(path):
    return b.output_path(Path(path),'stage4_projection_chain_vcs_')


def service_unit(out):
    return 'stage4-projection-chain-'+out.name+'.service'


def service_argv(out,s,review):
    return ['/usr/bin/systemd-run','--user','--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'work'),'--property=RuntimeMaxSec='+str(SERVICE_SECONDS),
        '--property=KillMode=control-group','--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        *['--setenv='+k+'='+v for k,v in sorted(s['environment'].items())],
        s['python'],'-B','-u',str(out/'inputs/vcs_run.py'),'run','--output',str(out),
        '--parent-reviewed','--review-sha256',review]


def host_command(out,name,argv,env,seconds):
    with (out/(name+'.log')).open('x') as stream:
        proc=subprocess.run(argv,cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=seconds)
    b.save(out/(name+'.command.json'),dict(argv=argv,cwd=str(out),timeout_seconds=seconds,returncode=proc.returncode))
    b.require(proc.returncode==0,'Preparation failed: '+name)
    return (out/(name+'.log')).read_text()


def prepare(out,socdir):
    b.require(HERE==ORIGINAL,'Prepare with the original reviewed runner')
    out,socdir=output_path(out),b.output_path(Path(socdir))
    b.require(not out.exists(),'Preserve every prior output/attempt')
    out.mkdir();(out/'inputs').mkdir();(out/'work').mkdir()
    report=dict(state='FAIL',execution='NOT_RUN',simulation_started=False,automatic_retry=False)
    try:
        soc,sw,pins=collect(socdir)
        for name,src in source_layout(socdir).items():
            dest=out/'inputs'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dest)
        checker(out/'inputs/checker')
        inventory=b.files(out/'inputs');b.save(out/'runner-inventory.json',inventory)
        s=selection(out,socdir,soc,sw);b.save(out/'selection.json',s)
        b.save(out/'launch-receipt.json',dict(environment=s['environment'],execution='NOT_RUN',
            service_command=service_argv(out,s,'{SOURCE_PINS_SHA256}')))
        host_command(out,'host-tests',[s['python'],'-B',str(out/'inputs/test_vcs_run.py'),'-v'],s['environment'],180)
        text=host_command(out,'image-contract',s['commands']['image_contract'],s['environment'],180)
        checked_image_log(text)
        linked=host_command(out,'runtime-link',['/usr/bin/ldd',soc['simv']],s['environment'],30)
        b.require('not found' not in linked,'Unresolved simulator library')
        libraries=re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)',linked,re.M)
        b.require(libraries,'Missing runtime loader evidence')
        merge(pins,{str(Path(p).resolve()):b.sha(Path(p).resolve()) for p in libraries})
        merge(pins,inventory);merge(pins,{str(out/n):b.sha(out/n) for n in PREP_FILES})
        b.verify(pins);b.save(out/'source-pins.json',pins)
        report.update(state='PREPARED_NOT_EXECUTED',host_tests_passed=True,
                      source_pins_sha256=b.sha(out/'source-pins.json'))
        b.save(out/'prepared.json',report);verify_prepared(out)
    except BaseException as exc:
        report.update(state='FAIL',error=repr(exc))
    b.save(out/'prepare-report.json',report)
    b.require(report['state']=='PREPARED_NOT_EXECUTED','Preparation failed; retained '+str(out))
    return report


def verify_prepared(out):
    out=output_path(out)
    s,pins,prepared=(b.read(out/n) for n in ('selection.json','source-pins.json','prepared.json'))
    b.require(prepared==dict(state='PREPARED_NOT_EXECUTED',execution='NOT_RUN',simulation_started=False,
        automatic_retry=False,host_tests_passed=True,source_pins_sha256=b.sha(out/'source-pins.json')),
        'Prepared receipt drift')
    b.verify(pins);b.exact_files(out/'inputs',b.read(out/'runner-inventory.json'))
    checker(out/'inputs/checker')
    socdir=Path(s['soc_build']);soc,sw,required=collect(socdir)
    expected={str(out/'inputs'/name):b.sha(src) for name,src in source_layout(socdir).items()}
    b.require(b.read(out/'runner-inventory.json')==expected,'Frozen runner/checker inventory drift')
    merge(required,expected);merge(required,{str(out/n):b.sha(out/n) for n in PREP_FILES})
    b.require(all(pins.get(p)==h for p,h in required.items()),'Missing mandatory pin')
    b.require(s==selection(out,socdir,soc,sw),'Selection/configuration/recipe drift')
    b.require(b.read(out/'launch-receipt.json')==dict(environment=s['environment'],execution='NOT_RUN',
        service_command=service_argv(out,s,'{SOURCE_PINS_SHA256}')),'Launch recipe drift')
    return s,pins,soc,sw


def service_command(out,review):
    s,*_=verify_prepared(out)
    b.require(review==b.sha(out/'source-pins.json') and
              not any((out/n).exists() for n in ('attempt.json','owner.json','result.json')) and
              not any((out/'work').iterdir()),'Review mismatch or already attempted')
    return service_argv(out,s,review)


def checked_image_log(text):
    rows=text.splitlines()
    b.require(rows.count('sim_qbs_enabled=1')==1 and rows.count('sim_l2_bytes=16777216')==1,
              'QBS/image capacity contract evidence missing')


def successful_log(text):
    b.require(text.count('Core Test *** SUCCESS ***')==1 and
              not re.search(r'Fatal:|Error:|Error-|\bFAILED\b',text),'Firmware/assertion/EOC failure')


def checked_chain(proof,sw):
    b.require(proof.get('state')=='SDK_CHAIN_LOG_CHECKED' and proof.get('scope')==sw['scope'] and
        proof.get('protocol_checked') is False and proof.get('post_image_checked') is False and
        proof.get('performance_acceptance') is False and proof.get('full_ggml') is False and
        proof.get('whole_model') is False and proof.get('commands')==256 and
        proof.get('outputs_checked_by_target')==32768 and proof.get('independent_oracle_hashes_checked') is True and
        len(proof.get('trials',[]))==4 and
        proof.get('vector_work')==dict(commands=256,result_bytes=131072,alloc_write_done_checked=True) and
        proof.get('actual_entries')==dict(counts=sw['expected_entries'],
            abba_producer_then_native64=True,elf_pc_insn_bound=True),'Incomplete frozen SDK-chain result')


def checked_protocol(proof,soc,sw,log,vector):
    image={p:h for p,h in soc['image_pins'].items() if p==soc['simv'] or p.endswith('.so')}
    b.require(any(p.endswith('.so') for p in image),'No compiled design library')
    b.require(proof.get('status')=='PASS' and proof.get('issues')==[] and
        proof.get('elf_sha256')==sw['elf_sha256'] and proof.get('simv_sha256')==b.sha(soc['simv']) and
        proof.get('sim_image_sha256')==image and proof.get('log_sha256')==b.sha(log) and
        proof.get('vector_trace_sha256')==b.sha(vector),'Independent protocol identity/evidence mismatch')
    counts=proof.get('contract_counts') or {}
    b.require(all(type(counts.get(k)) is int and counts[k]==0 for k in
                  ('exceptions','protocol_errors','outstanding')),'Zero exceptions/errors/outstanding required')


def execution_receipts(out,s):
    for command,name,seconds in STEPS:
        b.require(b.read(out/'work'/(name+'.command.json'))==dict(argv=s['commands'][command],
            cwd=str(out/'work'),timeout_seconds=seconds),'Executed recipe differs: '+command)
    owner=b.read(out/'owner.json')
    b.require(owner['unit']==service_unit(out) and b.read(out/'attempt.json')==
        dict(review_sha256=b.sha(out/'source-pins.json'),**owner),'Attempt/ownership identity mismatch')
    b.direct_owner(owner['cgroup'],owner['unit'],owner['main_pid'],owner['owner_pid'])


def run(out,review,parent_reviewed):
    out=output_path(out)
    b.require(parent_reviewed and Path(__file__).resolve()==out/'inputs/vcs_run.py',
              'Parent-reviewed frozen worker required')
    owner=b.claim_attempt(out,review,service_unit(out),terminal='result.json')
    report=dict(state='FAIL',numerical_checked=False,independent_protocol_checked=False,
        actual_entries_checked=False,work_checked=False,automatic_retry=False,full_ggml=False,
        whole_model=False,performance_measured=False,performance_acceptance=False,deployment_approved=False)
    status=dict(state='PREFLIGHT',child_pid=None,**owner)
    base,_=b.helpers(out/'inputs')
    try:
        b.require(not any((out/'work').iterdir()),'Stale work; never retry')
        s,pins,soc,sw=verify_prepared(out)
        os.environ.clear();os.environ.update(s['environment'])
        start=time.monotonic();simulation_wall=None
        log,vector,commit=(out/'work'/n for n in ('run.vcs.log','vector_trace.csv','commit.csv'))
        for command,name,seconds in STEPS:
            tick=time.monotonic()
            base.execute(s['commands'][command],out/'work',out/'work'/(name+'.log'),
                         seconds,status,out/'status.json',command.upper())
            if command=='image_contract':checked_image_log((out/'work/image-contract.log').read_text())
            if command=='simulation':
                simulation_wall=time.monotonic()-tick;successful_log(log.read_text())
                io_pins={str(p):b.sha(p) for p in (Path(sw['elf']),log,vector,commit,out/'work/console.log')}
            if command in ('chain','protocol'):b.verify(io_pins)
        proof=b.read(out/'work/chain.log');checked_chain(proof,sw)
        checked_protocol(b.read(out/'work/uvm_result.json'),soc,sw,log,vector)
        execution_receipts(out,s);verify_prepared(out)
        b.require(b.sha(out/'source-pins.json')==review,'Reviewed pins changed')
        report.update(state='PASS',numerical_checked=True,independent_protocol_checked=True,
            actual_entries_checked=True,work_checked=True,post_pins_match=True,post_image_match=True,
            performance_measured=True,scope=sw['scope'],source_pins_sha256=review,
            soc_build=s['soc_build'],software_build=str(SOFTWARE),soc_receipt_sha256=s['soc_receipt_sha256'],
            software_receipt_sha256=BUILD_SHA,elf_sha256=ELF_SHA,image_pins=soc['image_pins'],
            configuration=soc['configuration'],checked=proof,simulation_wall_seconds=simulation_wall,
            execution_wall_seconds=time.monotonic()-start,
            checker_io_sha256=io_pins|{str(out/'work'/n):b.sha(out/'work'/n) for n in
                                      ('chain.log','protocol.log','uvm_result.json')})
    except BaseException as exc:
        report.update(state='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'FAIL',error=repr(exc))
    report['artifacts']=b.files(out,exclude=('status.json','service.stdout.log','service.stderr.log'))
    b.save(out/'result.json',report)
    status.update(state=report['state'],child_pid=None);base.save(out/'status.json',status)
    print(json.dumps(dict(state=report['state'],output=str(out))),flush=True)
    return int(report['state']!='PASS')


def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    sub=parser.add_subparsers(dest='action',required=True)
    for name in ('prepare','preflight','service-command','run'):
        p=sub.add_parser(name,allow_abbrev=False);p.add_argument('--output',type=Path,required=True)
        if name=='prepare':p.add_argument('--soc-build',type=Path,required=True)
        if name in ('service-command','run'):p.add_argument('--review-sha256',required=True)
        if name=='run':p.add_argument('--parent-reviewed',action='store_true')
    args=parser.parse_args();out=output_path(args.output)
    if args.action=='prepare':print(json.dumps(prepare(out,args.soc_build),indent=2))
    elif args.action=='preflight':verify_prepared(out);print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif args.action=='service-command':print(shlex.join(service_command(out,args.review_sha256)))
    else:return run(out,args.review_sha256,args.parent_reviewed)
    return 0


if __name__=='__main__':
    def interrupted(sig,_frame):raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    raise SystemExit(main())
