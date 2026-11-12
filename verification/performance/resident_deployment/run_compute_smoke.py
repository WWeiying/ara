#!/usr/bin/env python3
"""One real RTL execution of the exact kernel compute object, not a Linux boot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
PROTOCOL=OUT/'optimization_extension_capability_20261111_05'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as f: json.dump(value,f,indent=2);f.write('\n')
def verify(pins):
    for path,value in pins.items():
        if sha(path)!=value: raise ValueError('Input drift: '+path)
def unit(out):return 'resident-deployment-compute-'+out.name+'.service'


def prepare(out,software,image):
    assert out.parent==software.parent==image.parent==OUT and not out.exists()
    assert out.name.startswith('resident_deployment_compute_vcs_')
    build,hw=read(software/'build.json'),read(image/'build.json')
    assert build['state']=='REAL_KERNEL_COMPUTE_SMOKE_BUILT_NOT_EXECUTED'
    assert hw['post_pins_match'] and hw['configuration']['resident_capability']==0x0000040000040301
    assert sha(software/'source-pins.json')==build['source_pins_sha256']
    verify(read(software/'source-pins.json'));verify(hw['image_pins'])
    out.mkdir();inputs=out/'inputs';inputs.mkdir()
    pins=dict(hw['image_pins'])
    for path in (software/'build.json',software/'source-pins.json',image/'build.json',Path(build['elf'])):
        pins[str(path)]=sha(path)
    shutil.copyfile(__file__,inputs/'run.py');pins[str(inputs/'run.py')]=sha(inputs/'run.py')
    approved=read(PROTOCOL/'source-pins.json')
    for source in (PROTOCOL/'inputs/verification/ara_verify').rglob('*.py'):
        assert sha(source)==approved[str(source)]
        dest=inputs/'verification/ara_verify'/source.relative_to(PROTOCOL/'inputs/verification/ara_verify')
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);pins[str(dest)]=sha(dest)
    env=dict(PATH='/usr/bin:/bin',HOME='/home/wangwy',LC_ALL='C',SNPSLMD_LICENSE_FILE='27000@t7920',
             PYTHONPATH=str(inputs/'verification'),PYTHONDONTWRITEBYTECODE='1',READELF='/usr/bin/readelf')
    work=out/'work'
    command=[hw['simv'],'-no_save','-l',str(work/'run.vcs.log'),'+PRELOAD='+build['elf'],
        '+TESTCASE=resident_kernel_compute','+NO_FSDB','+NO_INSTR_TRACE',
        '+VECTOR_TRACE='+str(work/'vector.csv'),'+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000']
    save(out/'plan.json',dict(command=command,environment=env,software=str(software),image=str(image),
        expected_sim_image={p:h for p,h in hw['image_pins'].items() if p==hw['simv'] or p.endswith('.so')}))
    pins[str(out/'plan.json')]=sha(out/'plan.json');verify(pins)
    save(out/'source-pins.json',pins)
    argv=['systemd-run','--user','--unit='+unit(out),'--property=Type=exec','--property=KillMode=control-group',
        '--property=RuntimeMaxSec=2400','--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        sys.executable,'-B','-u',str(inputs/'run.py'),'execute','--output',str(out),
        '--review-sha256',sha(out/'source-pins.json')]
    save(out/'launch-command.json',argv)
    return argv


def execute(out,review):
    assert Path(__file__).resolve()==out/'inputs/run.py' and sha(out/'source-pins.json')==review
    owner=subprocess.check_output(['systemctl','--user','show',unit(out),'-p','MainPID','--value'],text=True).strip()
    assert owner==str(os.getpid())
    save(out/'attempt.json',dict(pid=os.getpid(),cgroup=Path('/proc/self/cgroup').read_text()))
    plan,pins=read(out/'plan.json'),read(out/'source-pins.json');verify(pins)
    sw=read(Path(plan['software'])/'build.json')
    work=out/'work';work.mkdir()
    report=dict(state='FAIL',kernel_booted=False,linux_module_executed=False,board_executed=False,automatic_retry=False)
    commands=[]
    def run(name,argv,seconds):
        with (work/(name+'.log')).open('x') as log:
            child=subprocess.Popen(list(map(str,argv)),cwd=work,env=plan['environment'],stdout=log,stderr=subprocess.STDOUT)
            save(work/(name+'.process.json'),dict(pid=child.pid,command=list(map(str,argv))))
            try: rc=child.wait(timeout=seconds)
            except BaseException:
                child.terminate()
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                raise
        commands.append(dict(name=name,returncode=rc))
        assert rc==0,(name,rc)
    try:
        run('console',plan['command'],1800)
        text=(work/'run.vcs.log').read_text()
        assert text.count('Core Test *** SUCCESS ***')==1
        assert text.count('RESIDENT_KERNEL_COMPUTE_PASS')==1 and 'RESIDENT_KERNEL_COMPUTE_FAIL' not in text
        assert re.findall(r'^RESIDENT_KERNEL_COMPUTE_RESULT status=([0-9a-f]{8}) flags=([0-9a-f]{8}) errors=([0-9a-f]{8})$',text,re.M)==[
            ('00000000',format(sw['expected_flags'],'08x'),'00000000')]
        values=re.findall(r'^RESIDENT_KERNEL_COMPUTE_OUTPUT index=([0-9a-f]{8}) bits=([0-9a-f]{8})$',text,re.M)
        assert len(values)==256 and [(int(i,16),int(v,16)) for i,v in values]==list(enumerate(sw['expected_outputs']))
        for opcode,count in (('0605705b',2),('0485705b',2),('00b5605b',1),('02a0605b',1),('0000505b',1)):
            assert len(re.findall(r'^\[ARA_CONTRACT_TRACE\].* req=1/1 fire=1 .*insn='+opcode+r' ',text,re.M))==count,opcode
        run('protocol',[sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
            '--require-axi','--require-axi-write','--vector-trace',work/'vector.csv','--log',work/'run.vcs.log',
            '--simv',plan['command'][0],'--elf',sw['elf'],'--output',work/'protocol.json'],300)
        protocol=read(work/'protocol.json')
        assert protocol['status']=='PASS' and not protocol['issues']
        assert protocol['elf_sha256']==sw['elf_sha256'] and protocol['log_sha256']==sha(work/'run.vcs.log')
        assert protocol['sim_image_sha256']==plan['expected_sim_image']
        assert all(protocol['contract_counts'][k]==0 for k in ('exceptions','outstanding','protocol_errors'))
        verify(pins);verify(read(Path(plan['software'])/'source-pins.json'))
        report.update(state='REAL_KERNEL_COMPUTE_RTL_CHECKED',outputs_bit_exact=256,fflags=sw['expected_flags'],
            core_sha256=sw['core_sha256'],elf_sha256=sw['elf_sha256'],post_pins_match=True,
            resident_qk_commands=2,resident_pv_commands=2,full_commands=1,refill_commands=1,release_commands=1,
            protocol_sha256=sha(work/'protocol.json'),contract_counts=protocol['contract_counts'])
    except BaseException as error:report['error']=repr(error)
    save(out/'commands.json',commands);save(out/'result.json',report);print(json.dumps(report),flush=True)
    return int(report['state']=='FAIL')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('prepare-launch','execute'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--software',type=Path)
    p.add_argument('--image',type=Path)
    p.add_argument('--review-sha256')
    a=p.parse_args();out=a.output.resolve()
    if a.action=='prepare-launch':subprocess.run(prepare(out,a.software.resolve(),a.image.resolve()),check=True)
    else:return execute(out,a.review_sha256)
    return 0


if __name__=='__main__':raise SystemExit(main())
