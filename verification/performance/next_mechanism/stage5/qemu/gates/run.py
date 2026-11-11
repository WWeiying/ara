#!/usr/bin/env python3
"""Reviewed one-shot directed gate. prepare/service-command never run guests."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
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
ORIGINAL=ROOT/'verification/performance/next_mechanism/stage5/qemu/gates'
FIRMWARE=OUT/'stage5_akv_directed_build_20261110_03'
FW_SHA='ae70017f636067c87c490175a92c8bbb22227298debc08072893e83fa4f707fe'
FW_PINS_SHA='02cd0f0107b7de33abe8520344aeb783734a9b66713025d1ce531dfb69438e61'
INFO_HOST=OUT/'stage5_akv_directed_info_host_20261110_01'
INFO_HOST_SHA='d9c5af6e6ce76d4959d3af750b83dd3dee9dbc1256b1bd0458ddf2dc42c760a6'
CHECKERS={'check.py':'32ae013e8a2ac995adfd23b2944e80cfe767210a26496d7c8bf85e118a22a31f',
          'check_v2.py':'aadf85a1def6779478a1e5bee962b8970db72075adb8ff4c44bb4a335f9dab06',
          'test_check_v2.py':'4971263350a6a6ac6a581155e591b5f9b57e20bd791c189d7fb6df89ab2c4070'}
VALIDATOR_SHA='0132197b2c192f87a899bbe7efa50e9d80fd653334d78a8d7309a5dc367daeee'
VALIDATOR_ROOT=ORIGINAL.parent
VALIDATOR_FILES=('build_v5.py','test_build_v5.py','BUILD_V5.md',
                 'build_v4.py','test_build_v4.py','BUILD_V4.md')
OWN=('run.py','test_run.py')
GUEST_SECONDS,CHECK_SECONDS,SERVICE_SECONDS=300,120,1800
MODES=(0,1,2)


def require(ok,message):
    if not ok:raise ValueError(message)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(path):
    def pairs(rows):
        value={}
        for k,v in rows:require(k not in value,'Duplicate JSON key');value[k]=v
        return value
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs)
def save(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def status_save(path,value):
    tmp=Path(path).with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');tmp.replace(path)
def merge(pins,extra):
    for path,digest in extra.items():
        path=str(path);require(path not in pins or pins[path]==digest,'Conflicting pin: '+path);pins[path]=digest
def verify(pins):
    require(bool(pins),'Empty inventory')
    for path,digest in pins.items():require(Path(path).is_file() and sha(path)==digest,'Identity drift: '+str(path))
def files(root,exclude=()):
    require(Path(root).is_dir() and not Path(root).is_symlink(),'Missing/linked inventory root')
    result={}
    for p in sorted(Path(root).rglob('*')):
        if str(p.relative_to(root)) in exclude:continue
        require(not p.is_symlink(),'Unexpected runner/artifact symlink')
        if p.is_dir():continue
        require(p.is_file(),'Nonregular runner artifact');result[str(p)]=sha(p)
    return result
def output_path(path):
    p=Path(path).absolute()
    require(p==p.resolve() and p.parent==OUT and re.fullmatch(r'stage5_akv_directed_run_[A-Za-z0-9_]+',p.name),
            'Use a direct owned signoff output')
    return p


def validator(directory=None):
    directory=Path(directory) if directory is not None else VALIDATOR_ROOT
    require(isinstance(VALIDATOR_SHA,str) and re.fullmatch('[0-9a-f]{64}',VALIDATOR_SHA),
            'Build validator not yet frozen; preparation prohibited')
    verify({directory/'build_v5.py':VALIDATOR_SHA})
    spec=importlib.util.spec_from_file_location('directed_frozen_build_validator',directory/'build_v5.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    require(tuple(module.OWN)==VALIDATOR_FILES,'Validator closure changed')
    return module


def collect_firmware():
    verify({FIRMWARE/'build.json':FW_SHA,FIRMWARE/'source-pins.json':FW_PINS_SHA,INFO_HOST/'result.json':INFO_HOST_SHA})
    fw=read(FIRMWARE/'build.json');host=read(INFO_HOST/'result.json')
    require(fw['state']=='DIRECTED_GUESTS_BUILT_NOT_EXECUTED' and fw['post_pins_match'] is True and
            fw['qemu_executed'] is False and [v['mode'] for v in fw['variants']]==list(MODES) and
            [v['cases'] for v in fw['variants']]==[100,4,2],'Wrong immutable directed firmware')
    pins=read(FIRMWARE/'source-pins.json');merge(pins,fw['artifacts'])
    require(set(fw['artifacts'])==set(files(FIRMWARE,exclude=('build.json',))),'Firmware artifact membership')
    require(host['state']=='HOST_INFO_SUCCESSOR_PASS_NOT_EXECUTED' and host['host_tests']==4 and
            host['post_pins_match'] is True and host['qemu_executed'] is False and
            sha(INFO_HOST/'source-pins.json')==host['source_pins_sha256'],'INFO successor host contract')
    merge(pins,read(INFO_HOST/'source-pins.json'));merge(pins,files(INFO_HOST))
    merge(pins,{FIRMWARE/'build.json':FW_SHA,INFO_HOST/'result.json':INFO_HOST_SHA})
    merge(pins,{ORIGINAL/n:h for n,h in CHECKERS.items()})
    for variant in fw['variants']:
        require(sha(variant['elf'])==variant['elf_sha256'] and sha(variant['expected'])==variant['expected_sha256'],
                'Firmware ELF/oracle drift')
    verify(pins)
    return fw,pins


def collect_qemu(build_dir,reviewed_sha,v):
    build_dir=Path(build_dir).resolve(strict=True)
    require(build_dir.parent==OUT,'QEMU build must be under sole signoff output')
    report=v.checked_build(build_dir,reviewed_sha)
    prepared=Path(report['prepared']);preflight=Path(report['preflight'])
    require(report['schema']=='stage5-qemu-build-v5' and report['state']=='BUILT_NOT_EXECUTED' and
            report['guest_executed'] is False and report['post_pins_match'] is True and
            prepared==v.PREPARED and report['prepare_sha256']==v.PREPARE_SHA and
            sha(prepared/'prepare.json')==report['prepare_sha256'],'Wrong reviewed QEMU build/preparation')
    require(preflight.parent==OUT and sha(preflight/'toolenv.json')==report['preflight_sha256'],'Toolenv identity')
    toolenv=read(preflight/'toolenv.json');prep=read(prepared/'prepare.json')
    require(sha(prepared/'source-pins.json')==prep['source_pins_sha256'] and
            sha(preflight/'tool-pins.json')==toolenv['tool_pins_sha256'],'Underlying inventory identity')
    pins=read(prepared/'source-pins.json');merge(pins,read(preflight/'tool-pins.json'));merge(pins,toolenv['artifacts'])
    for p in (prepared/'prepare.json',prepared/'source-pins.json',preflight/'toolenv.json',preflight/'tool-pins.json',
              build_dir/'build.json',build_dir/'configure.log',build_dir/'build.log',Path(report['executable'])):
        merge(pins,{p:sha(p)})
    require(Path(report['executable'])==build_dir/'qemu-system-riscv64' and
            sha(report['executable'])==report['executable_sha256'] and os.access(report['executable'],os.X_OK),
            'Wrong executable image')
    contract={k:report[k] for k in ('prepared','prepare_sha256','preflight','preflight_sha256','executable','executable_sha256')}
    contract.update(build=str(build_dir),build_sha256=reviewed_sha)
    return contract,pins


def environment():
    uid=os.getuid();runtime='/run/user/'+str(uid)
    return dict(PATH='/usr/bin:/bin',HOME=pwd.getpwuid(uid).pw_dir,LC_ALL='C',LANG='C',
        PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',XDG_RUNTIME_DIR=runtime,
        DBUS_SESSION_BUS_ADDRESS='unix:path='+runtime+'/bus')


def recipes(out,qemu,fw,python):
    result=[]
    for mode,variant in zip(MODES,fw['variants']):
        require(variant['mode']==mode,'Mode order drift')
        work=out/'work'/('mode'+str(mode))
        cpu='rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv='+(
            'false' if mode==2 else 'true')+',xaraakv-resident='+('true' if mode==0 else 'false')
        result.append(dict(mode=mode,elf=variant['elf'],elf_sha256=variant['elf_sha256'],
            guest=[qemu['executable'],'-M','virt,x-ara-stage4=on','-accel','tcg','-cpu',cpu,
                '-smp','1','-m','16M','-bios','none','-kernel',variant['elf'],'-display','none',
                '-monitor','none','-serial','none','-chardev','stdio,id=ara-stage4',
                '-trace','enable=akv_arch_*','-D',str(work/'trace.log')],
            checker=[python,'-B',str(out/'inputs/checker/check_v2.py'),'--build',str(FIRMWARE),
                '--mode',str(mode),'--log',str(work/'guest.log'),'--trace',str(work/'trace.log')]))
    return result


def selection(out,qemu,fw,python=None):
    python=str(Path(sys.executable if python is None else python).resolve())
    return dict(schema='stage5-akv-directed-run-v1',qemu=qemu,firmware=str(FIRMWARE),firmware_sha256=FW_SHA,
        validator_sha256=VALIDATOR_SHA,checkers=CHECKERS,python=python,environment=environment(),
        commands=recipes(out,qemu,fw,python),guest_seconds=GUEST_SECONDS,checker_seconds=CHECK_SECONDS,
        service_seconds=SERVICE_SECONDS,automatic_retry=False,guest_executed=False)


def layout(v):
    paths={n:ORIGINAL/n for n in OWN}
    paths.update({'checker/'+n:ORIGINAL/n for n in CHECKERS})
    paths.update({'validator/'+n:Path(v.__file__).parent/n for n in VALIDATOR_FILES})
    return paths


def unit(out):return 'stage5-akv-directed-'+out.name+'.service'
def owner(out):
    name=unit(out);inv=os.environ.get('INVOCATION_ID','')
    require(re.fullmatch('[0-9a-f]{32}',inv),'Direct systemd invocation required')
    cgroup=Path('/proc/self/cgroup').read_text()
    require(any(row.split(':',2)[-1].endswith('/'+name) for row in cgroup.splitlines()),'Wrong service cgroup')
    main=subprocess.check_output(['/usr/bin/systemctl','--user','show',name,'--property=MainPID','--value'],
                                 text=True,timeout=10).strip()
    require(main==str(os.getpid()),'Worker must be direct systemd MainPID')
    return dict(unit=name,main_pid=os.getpid(),owner_pid=os.getpid(),invocation_id=inv,cgroup=cgroup)
def service_argv(out,s,review):
    return ['/usr/bin/systemd-run','--user','--unit='+unit(out),'--property=KillMode=control-group',
        '--property=RuntimeMaxSec='+str(SERVICE_SECONDS),'--property=TimeoutStopSec=20',
        '--property=WorkingDirectory='+str(out/'work'),
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        *['--setenv='+k+'='+v for k,v in sorted(s['environment'].items())],
        s['python'],'-B','-u',str(out/'inputs/run.py'),'run','--output',str(out),
        '--parent-reviewed','--review-sha256',review]


def prepare(out,build_dir,reviewed_sha):
    require(HERE==ORIGINAL,'Prepare from the reviewed original runner')
    out=output_path(out);require(not out.exists(),'Preserve every prior output/attempt');out.mkdir()
    (out/'inputs').mkdir();(out/'work').mkdir();report=dict(state='FAIL',guest_executed=False)
    try:
        v=validator();qemu,pins=collect_qemu(build_dir,reviewed_sha,v);fw,fpins=collect_firmware();merge(pins,fpins)
        for name,source in layout(v).items():
            target=out/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            merge(pins,{source:sha(source)})
        inventory=files(out/'inputs');save(out/'runner-inventory.json',inventory);merge(pins,inventory)
        s=selection(out,qemu,fw);save(out/'selection.json',s)
        save(out/'launch-receipt.json',dict(service_command=service_argv(out,s,'{SOURCE_PINS_SHA256}'),guest_executed=False))
        for p in (Path(sys.executable).resolve(),Path('/usr/bin/systemd-run'),Path('/usr/bin/systemctl'),Path('/usr/bin/ldd')):
            merge(pins,{p:sha(p)})
        for label,argv,seconds in [('host-tests',[s['python'],'-B',str(out/'inputs/test_run.py'),'-v'],120),
                                   ('runtime-link',['/usr/bin/ldd',qemu['executable']],30)]:
            with (out/(label+'.log')).open('x') as log:
                completed=subprocess.run(argv,cwd=out,env=s['environment'],stdout=log,stderr=subprocess.STDOUT,timeout=seconds)
            save(out/(label+'.command.json'),dict(argv=argv,cwd=str(out),timeout_seconds=seconds,returncode=completed.returncode))
            require(completed.returncode==0,'Preparation command failed: '+label)
        linked=(out/'runtime-link.log').read_text();require('not found' not in linked,'Unresolved QEMU runtime library')
        libs=re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)',linked,re.M);require(libs,'No runtime loader evidence')
        for p in libs:merge(pins,{p:sha(p),Path(p).resolve():sha(p)})
        save(out/'runtime-pins.json',{p:pins[p] for p in pins if p in libs or p in [str(Path(x).resolve()) for x in libs]})
        for name in ('selection.json','launch-receipt.json','runner-inventory.json','host-tests.log','host-tests.command.json',
                     'runtime-link.log','runtime-link.command.json','runtime-pins.json'):merge(pins,{out/name:sha(out/name)})
        verify(pins);save(out/'source-pins.json',pins)
        report.update(state='PREPARED_NOT_EXECUTED',source_pins_sha256=sha(out/'source-pins.json'))
        save(out/'prepared.json',report);verify_prepared(out,allow_incomplete=True)
    except BaseException as exc:report.update(state='FAIL',error=repr(exc))
    save(out/'prepare-report.json',report);require(report['state']=='PREPARED_NOT_EXECUTED','Preparation failed; retained '+str(out))
    return report


def verify_prepared(out,allow_incomplete=False):
    out=output_path(out);s=read(out/'selection.json');prepared=read(out/'prepared.json');pins=read(out/'source-pins.json')
    require(prepared==dict(state='PREPARED_NOT_EXECUTED',guest_executed=False,source_pins_sha256=sha(out/'source-pins.json')),
            'Prepared receipt drift')
    if not allow_incomplete or (out/'prepare-report.json').exists():
        require(read(out/'prepare-report.json')==prepared,'Preparation failed or is not finished')
    verify(pins);require(files(out/'inputs')==read(out/'runner-inventory.json'),'Frozen runner inventory drift')
    v=validator(out/'inputs/validator');qemu,required=collect_qemu(s['qemu']['build'],s['qemu']['build_sha256'],v)
    fw,fpins=collect_firmware();merge(required,fpins)
    require(s==selection(out,qemu,fw,s['python']),'Execution recipe/configuration drift')
    wanted={str(out/'inputs'/n):sha(p) for n,p in layout(v).items()}
    require(wanted==read(out/'runner-inventory.json'),'Runner/checker/validator copy drift')
    merge(required,wanted);merge(required,read(out/'runtime-pins.json'))
    for n in ('selection.json','launch-receipt.json','runner-inventory.json','host-tests.log','host-tests.command.json',
              'runtime-link.log','runtime-link.command.json','runtime-pins.json'):merge(required,{out/n:sha(out/n)})
    require(all(pins.get(p)==h for p,h in required.items()),'Missing mandatory source/image/runtime pin')
    require(read(out/'launch-receipt.json')==dict(service_command=service_argv(out,s,'{SOURCE_PINS_SHA256}'),guest_executed=False),
            'Service recipe drift')
    return s,pins,fw


def service_command(out,review):
    s,_,_=verify_prepared(out)
    require(review==sha(out/'source-pins.json') and not any((out/n).exists() for n in ('attempt.json','owner.json','result.json'))
            and not any((out/'work').iterdir()),'Review mismatch or existing attempt/work')
    return service_argv(out,s,review)


def execute(argv,cwd,log,seconds,environment,status,status_path,phase):
    record=dict(argv=argv,cwd=str(cwd),timeout_seconds=seconds,started_ns=time.time_ns(),state='RUNNING')
    process=None
    try:
        with log.open('x') as stream:
            process=subprocess.Popen(argv,cwd=cwd,env=environment,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            record['pid']=process.pid;status.update(state=phase,child_pid=process.pid);status_save(status_path,status)
            record['returncode']=process.wait(timeout=seconds);record['state']='EXITED'
    except BaseException:
        record['state']='INTERRUPTED_OR_TIMEOUT'
        if process is not None:
            try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            except ProcessLookupError:pass
            record['returncode']=process.returncode
        raise
    finally:
        record['ended_ns']=time.time_ns()
        if log.exists():record['log_sha256']=sha(log)
        save(log.with_suffix('.command.json'),record)
        status.update(child_pid=None);status_save(status_path,status)
    require(record['returncode']==0,'Command exit failure: '+str(log))
    return record


def checked_mode(proof,mode,variant):
    m=read(variant['expected']);cases=m['cases'];numbers=proof.get('numerical',{});work=proof.get('work',{})
    require(proof.get('state')=='DIRECTED_GUEST_ARCHITECTURE_CHECKED' and proof.get('checker_successor')=='info-result-v2' and
        proof.get('qemu_image_checked') is False and proof.get('service_owner_checked') is False and proof.get('rtl_timing') is False and
        proof.get('elf_sha256')==variant['elf_sha256'] and variant['mode']==mode,'Incomplete checker/image contract')
    require(numbers==dict(cases=len(cases),traps=sum(bool(c['cause']) for c in cases),
        output_records=sum(len(c['expected']) for c in cases),csr_guards_checked=True),'Directed numerical/trap coverage incomplete')
    require(all(type(numbers[k]) is int for k in ('cases','traps','output_records')) and
            numbers['csr_guards_checked'] is True,'Malformed numerical result types')
    require(work.get('helper_calls')==sum(c['layer']!='decode' and c['op']!='info' for c in cases) and
        work.get('memory_callback_faults')==sum(c['layer']=='memory' for c in cases) and
        work.get('successful_resident')==sum(c['active'] for c in cases) and
        type(work.get('ram_reads')) is int and work['ram_reads']>=0 and work.get('real_no_end_faults_checked') is True,
        'Directed real work/fault coverage incomplete')
    require(all(type(work[k]) is int for k in ('helper_calls','memory_callback_faults','successful_resident')),
            'Malformed architectural count types')
    require(proof.get('info_trace')==dict(records=sum(c['op']=='info' and not c['cause'] for c in cases),trace_results_checked=True),
            'INFO trace result checking missing')
    require(type(proof['info_trace']['records']) is int and proof['info_trace']['trace_results_checked'] is True,
            'Malformed INFO coverage types')


def run_modes(out,s,fw,pins,status,results=None):
    if results is None:results=[]
    require(len(s['commands'])==len(fw['variants'])==3 and not results,'Fresh exact three-mode sequence required')
    env=s['environment']|{'INVOCATION_ID':status['invocation_id']}
    for mode,commands,variant in zip(MODES,s['commands'],fw['variants']):
        require(commands['mode']==variant['mode']==mode,'Missing/extra mode order')
        verify(pins);directory=out/'work'/('mode'+str(mode));directory.mkdir()
        guest=execute(commands['guest'],directory,directory/'guest.log',GUEST_SECONDS,env,status,out/'status.json','MODE'+str(mode)+'_GUEST')
        log,trace=directory/'guest.log',directory/'trace.log'
        require(log.is_file() and trace.is_file(),'Missing real guest/trace evidence')
        io={str(p):sha(p) for p in (log,trace,Path(variant['elf']))}
        checker=execute(commands['checker'],directory,directory/'checked.json',CHECK_SECONDS,env,status,out/'status.json','MODE'+str(mode)+'_CHECK')
        verify(io);proof=read(directory/'checked.json');checked_mode(proof,mode,variant)
        require(proof['log_sha256']==sha(log) and proof['trace_sha256']==sha(trace),'Checker consumed wrong log/trace')
        results.append(dict(mode=mode,state='PASS',returncode=guest['returncode'],elf_sha256=variant['elf_sha256'],
            log_sha256=sha(log),trace_sha256=sha(trace),checker_log_sha256=sha(directory/'checked.json'),
            guest_command=guest,checker_command=checker,checked=proof))
        status.update(completed_modes=len(results));status_save(out/'status.json',status)
    return results


def aggregate_modes(rows,fw):
    require(len(rows)==3 and [r.get('mode') for r in rows]==list(MODES),'All three modes required')
    for mode,row,variant in zip(MODES,rows,fw['variants']):
        require(row.get('state')=='PASS' and type(row.get('returncode')) is int and row['returncode']==0 and
                row.get('elf_sha256')==variant['elf_sha256'],'Mode failure or firmware mismatch')
        checked_mode(row['checked'],mode,variant)


def run(out,review,parent_reviewed):
    out=output_path(out)
    require(parent_reviewed and Path(__file__).resolve()==out/'inputs/run.py','Reviewed frozen worker required')
    require(review==sha(out/'source-pins.json') and not any((out/n).exists() for n in ('attempt.json','owner.json','result.json')),
            'Review mismatch or attempted output')
    ownership=owner(out);save(out/'attempt.json',dict(review_sha256=review,**ownership));save(out/'owner.json',ownership)
    report=dict(state='FAIL',mode_results=[],automatic_retry=False,qbs_successor_smoke_checked=False,
        stage4_elfs_checked=False,performance_acceptance=False,deployment_approved=False,rtl_timing=False,service_owner=ownership)
    status=dict(state='PREFLIGHT',child_pid=None,completed_modes=0,**ownership);status_save(out/'status.json',status)
    try:
        require(not any((out/'work').iterdir()),'Stale work; do not retry')
        s,pins,fw=verify_prepared(out)
        os.environ.clear();os.environ.update(s['environment']);os.environ['INVOCATION_ID']=ownership['invocation_id']
        rows=run_modes(out,s,fw,pins,status,report['mode_results']);aggregate_modes(rows,fw)
        verify_prepared(out);require(review==sha(out/'source-pins.json'),'Reviewed pins changed')
        post_owner=owner(out);require(post_owner==ownership,'Service ownership changed')
        report.update(state='DIRECTED_NATIVE_AKV_CHECKED',mode_results=rows,post_pins_match=True,post_image_match=True,
            post_service_owner=post_owner,source_pins_sha256=review,qemu_build=s['qemu']['build'],
            qemu_build_receipt_sha256=s['qemu']['build_sha256'],qemu_prepare=s['qemu']['prepared'],
            qemu_prepare_receipt_sha256=s['qemu']['prepare_sha256'],executable=s['qemu']['executable'],
            executable_sha256=s['qemu']['executable_sha256'],firmware_build_receipt_sha256=FW_SHA,
            check_v2_sha256=CHECKERS['check_v2.py'],original_checker_sha256=CHECKERS['check.py'])
    except BaseException as exc:report.update(state='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'FAIL',error=repr(exc))
    report['artifacts']=files(out,exclude=('status.json','service.stdout.log','service.stderr.log'))
    save(out/'result.json',report);status.update(state=report['state'],child_pid=None);status_save(out/'status.json',status)
    print(json.dumps(dict(state=report['state'],output=str(out))),flush=True)
    return int(report['state']!='DIRECTED_NATIVE_AKV_CHECKED')


def checked_result(output,reviewed_result_sha256):
    """Read-only prerequisite validation; never reruns a numerical checker."""
    out=output_path(output);require(sha(out/'result.json')==reviewed_result_sha256,'Unreviewed aggregate result')
    report=read(out/'result.json');s,pins,fw=verify_prepared(out)
    require(report.get('state')=='DIRECTED_NATIVE_AKV_CHECKED' and report.get('post_pins_match') is True and
            report.get('post_image_match') is True and report.get('service_owner')==report.get('post_service_owner') and
            report.get('source_pins_sha256')==sha(out/'source-pins.json'),'Incomplete directed aggregate')
    for key,value in dict(qemu_build=s['qemu']['build'],qemu_build_receipt_sha256=s['qemu']['build_sha256'],
        qemu_prepare=s['qemu']['prepared'],qemu_prepare_receipt_sha256=s['qemu']['prepare_sha256'],
        executable=s['qemu']['executable'],executable_sha256=s['qemu']['executable_sha256'],
        firmware_build_receipt_sha256=FW_SHA,check_v2_sha256=CHECKERS['check_v2.py'],original_checker_sha256=CHECKERS['check.py']).items():
        require(report.get(key)==value,'Aggregate identity mismatch: '+key)
    aggregate_modes(report['mode_results'],fw);verify(report['artifacts'])
    require(files(out,exclude=('result.json','status.json','service.stdout.log','service.stderr.log'))==report['artifacts'],
            'Aggregate artifact membership drift')
    own=read(out/'owner.json');require(report['service_owner']==own and own['unit']==unit(out) and
        own['main_pid']==own['owner_pid']>1 and re.fullmatch('[0-9a-f]{32}',own['invocation_id']) and
        read(out/'attempt.json')==dict(review_sha256=report['source_pins_sha256'],**own),'Aggregate ownership mismatch')
    previous_end=0
    for mode,row in enumerate(report['mode_results']):
        directory=out/'work'/('mode'+str(mode))
        require(read(directory/'checked.json')==row['checked'] and sha(directory/'guest.log')==row['log_sha256'] and
                sha(directory/'trace.log')==row['trace_sha256'] and sha(directory/'checked.json')==row['checker_log_sha256'],
                'Mode evidence drift')
        for kind,name,timeout in (('guest','guest',GUEST_SECONDS),('checker','checked',CHECK_SECONDS)):
            receipt=read(directory/(name+'.command.json'))
            require(receipt==row[kind+'_command'] and receipt['argv']==s['commands'][mode][kind] and
                    receipt['cwd']==str(directory) and receipt['timeout_seconds']==timeout and
                    receipt['state']=='EXITED' and type(receipt['returncode']) is int and receipt['returncode']==0 and receipt['pid']>1 and
                    receipt['ended_ns']>receipt['started_ns'] and receipt['log_sha256']==sha(directory/(name+'.json' if kind=='checker' else 'guest.log')),
                    'Executed command receipt drift')
            require(receipt['started_ns']>=previous_end,'Overlapping or misordered execution receipts')
            previous_end=receipt['ended_ns']
    return report,pins|report['artifacts']|{str(out/'result.json'):reviewed_result_sha256}


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('identity')
    for name in ('prepare','preflight','service-command','run'):
        a=sub.add_parser(name,allow_abbrev=False);a.add_argument('--output',type=Path,required=True)
        if name=='prepare':
            a.add_argument('--qemu-build',type=Path,required=True);a.add_argument('--reviewed-build-sha256',required=True)
        if name in ('service-command','run'):a.add_argument('--review-sha256',required=True)
        if name=='run':a.add_argument('--parent-reviewed',action='store_true')
    a=p.parse_args()
    if a.action=='identity':print(json.dumps({n:sha(ORIGINAL/n) for n in OWN},indent=2));return 0
    out=output_path(a.output)
    if a.action=='prepare':print(json.dumps(prepare(out,a.qemu_build,a.reviewed_build_sha256),indent=2))
    elif a.action=='preflight':verify_prepared(out);print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif a.action=='service-command':print(shlex.join(service_command(out,a.review_sha256)))
    else:return run(out,a.review_sha256,a.parent_reviewed)
    return 0


if __name__=='__main__':
    def interrupted(sig,frame):raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    raise SystemExit(main())
