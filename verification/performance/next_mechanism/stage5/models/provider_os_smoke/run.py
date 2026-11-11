#!/usr/bin/env python3
"""One real Linux provider callback smoke, never AKV/model/S3 evidence."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=Path('/home/wangwy/openproject/ara_dsa')
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
LINK=OUT/'stage5_models_execution_link_v2_20261110_01'
BASE=LINK/'inputs/run.py'
BASE_SHA='f09948cffe64a9154eb075482e24bd90283faec54f4f64661d51ba0e189fe838'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise ValueError('Sealed utility drift')
loader=importlib.util.spec_from_file_location('provider_smoke_utilities',BASE)
b=importlib.util.module_from_spec(loader);loader.loader.exec_module(b)
BUILD=OUT/'stage5_libraries_build_20261110_01'
READ_STATE=BUILD/'build/ggml/src/CMakeFiles/ggml-cpu.dir/ggml-cpu/arch/riscv/read_state.S.o'
QEMU=OUT/'qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
OWN=('run.py','smoke.c','call.S')
NAMES=('state_ready','small_acquire','small_release','large_acquire','large_release',
       'readonly_acquire','readonly_release','readonly_write_denied','unknown_file_denied','hole_denied',
       'state_bad_vstart','acquire_bad_vstart','cleanup_acquire','release_bad_vstart','final_acquire','final_release')
POSITIVES=('small_acquire','large_acquire','readonly_acquire','cleanup_acquire','final_acquire')
NEGATIVES=('readonly_write_denied','unknown_file_denied','hole_denied','acquire_bad_vstart')


def prepare(out):
    b.require(out.parent==OUT and not out.exists() and out.name.startswith('stage5_models_provider_os_'),'Fresh output required')
    b.require(b.sha(LINK/'prepare.json')=='16894c46ddd63dfdb8296e9ef7b1b93374f3fcfb5c66d365e9c519ee80ee202f','Frozen provider link receipt')
    lr=b.read(LINK/'prepare.json');b.require(b.sha(LINK/'source-pins.json')==lr['source_pins_sha256'],'Link inventory')
    b.require(b.sha(BUILD/'build.json')=='f47864d88068b2aec18b7f63c9578d2bfeabd9e59f3fde5c5b0b386ece3b21fd','Frozen library receipt')
    library=b.read(BUILD/'build.json');old=b.read(b.MODELS/'source-pins.json');lpins=b.read(LINK/'source-pins.json')
    pins={str(BASE):BASE_SHA,str(LINK/'prepare.json'):b.sha(LINK/'prepare.json'),
          str(LINK/'source-pins.json'):lr['source_pins_sha256'],str(BUILD/'build.json'):b.sha(BUILD/'build.json'),
          str(READ_STATE):library['artifacts'][str(READ_STATE)]}
    for name in ('provider.o','inputs/provider.c','inputs/execution_contract.h','commands.json'):
        pins[str(LINK/name)]=lpins[str(LINK/name)]
    for p in (QEMU,b.BIOS,b.KERNEL,b.CC,b.CPIO):
        b.require(old[str(p)]==b.sha(p),'Frozen OS/tool drift: '+str(p));pins[str(p)]=old[str(p)]
    b.verify(pins);out.mkdir();(out/'inputs').mkdir();commands=[]
    def run(name,argv):
        argv=list(map(str,argv));commands.append(dict(label=name,argv=argv))
        with (out/(name+'.log')).open('x') as log:
            rc=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,cwd=out,timeout=120,
                env=dict(PATH=str(b.CC.parent)+':/usr/bin:/bin',HOME=str(out),LC_ALL='C')).returncode
        b.require(rc==0,'Build failed: '+name)
    report=dict(state='FAIL',model_executed=False,native_akv_executed=False)
    try:
        for name in OWN:
            pins[str(HERE/name)]=b.sha(HERE/name);shutil.copyfile(HERE/name,out/'inputs'/name)
        include=['-I'+p for p in library['frontend_include_dirs']]
        for source in ('smoke.c','call.S'):
            run('compile-'+source,[b.CC,'-std=gnu11',*b.FLAGS,*include,'-Wall','-Wextra','-Werror',
                '-MD','-MF',out/(source+'.d'),'-c',out/'inputs'/source,'-o',out/(source+'.o')])
        run('link',[b.CC,*b.FLAGS,'-static','-no-pie',out/'smoke.c.o',out/'call.S.o',LINK/'provider.o',READ_STATE,
            '-Wl,-Map='+str(out/'link.map'),'-o',out/'test'])
        run('disassembly',[b.CC.with_name('riscv64-linux-objdump'),'-d','--disassemble=provider_measure_call',out/'test'])
        text=(out/'disassembly.log').read_text()
        b.require('ecall' not in text and '.word' not in text and '.insn' not in text and
            len(re.findall(r'\bjalr\b',text))==1,'Measurement must call the actual callback once, without custom work')
        run('symbols',[b.CC.with_name('riscv64-linux-nm'),'-S',out/'test'])
        names=(out/'symbols.log').read_text()
        for name in ('akv_resident_platform_read_state_v1','stage5_provider_setup_v2','akv_resident_platform_current_v1'):
            b.require(re.search(r'\bT '+name+r'$',names,re.M),'Missing actual provider/read_state symbol')
        b.require('akv_experimental_resident_' not in names and 'qbs_native_execute' not in names,'Numerical kernels must not be linked')
        (out/'initramfs.list').write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /proc 755 0 0\n'+
            ''.join(f'file /{name} {out/"test"} {mode} 0 0\n' for name,mode in [('init','755'),('test','755'),('unapproved.bin','444')]))
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([b.CPIO,out/'initramfs.list'],stdout=f,check=True,timeout=30)
        command=[str(QEMU),'-M','virt','-cpu','rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
            '-smp','1','-m','4G','-display','none','-monitor','none','-serial','stdio','-bios',str(b.BIOS),
            '-kernel',str(b.KERNEL),'-initrd',str(out/'initramfs.cpio'),'-append','console=ttyS0 rdinit=/init']
        b.save(out/'qemu-command.json',command);b.save(out/'commands.json',commands)
        deps=[]
        for p in out.glob('*.d'):deps+=shlex.split(p.read_text().replace('\\\n','').split(':',1)[1])
        deps+=re.findall(r'(?m)^LOAD (\S+)',(out/'link.map').read_text())
        for p in [*map(Path,deps),b.CC.resolve(),b.CC.with_name('riscv64-linux-objdump'),b.CC.with_name('riscv64-linux-nm')]:
            b.merge(pins,{str(p.resolve()):b.sha(p)})
        for p in out.rglob('*'):
            if p.is_file():b.merge(pins,{str(p):b.sha(p)})
        b.verify(pins);b.save(out/'source-pins.json',pins)
        report.update(state='PREPARED_PROVIDER_OS_ONLY',pins=len(pins),source_pins_sha256=b.sha(out/'source-pins.json'),
            image_sha256=b.sha(b.KERNEL),qemu_sha256=b.sha(QEMU),elf_sha256=b.sha(out/'test'),
            provider_object_sha256=b.sha(LINK/'provider.o'),read_state_object_sha256=b.sha(READ_STATE),post_pins_match=True)
    except BaseException as e:report['error']=repr(e);raise
    finally:b.save(out/'prepare.json',report)
    print(json.dumps(report,sort_keys=True))


def check(text):
    rows=[];maps=[];active=None;failures=[]
    for line in text.splitlines():
        if line.startswith('PROVIDER_MAPS_BEGIN stage='):
            b.require(active is None,'Nested maps dump');active=dict(stage=line.split('=',1)[1],lines=[])
        elif line.startswith('PROVIDER_MAPS_END stage='):
            b.require(active is not None and active['stage']==line.split('=',1)[1] and active['lines'],'Invalid maps dump')
            maps.append(active);active=None
        elif active is not None:active['lines'].append(line)
        elif line.startswith('PROVIDER_CALL '):
            row={}
            for item in line.split()[1:]:
                k,v=item.split('=');b.require(k not in row,'Duplicate field')
                if k!='name':b.require(re.fullmatch('-?[0-9]+',v),'Invalid integer');v=int(v)
                row[k]=v
            b.require(set(row)=={'name','result','ok',*[f'{s}{i}' for s in ('before','after','restored') for i in range(3)]},'Call fields')
            rows.append(row)
    if [r['name'] for r in rows]!=list(NAMES):failures.append('Missing/reordered callbacks; no all-fallback positive')
    if [m['stage'] for m in maps]!=['small','large','readonly','unapproved','hole','cleanup'] or active is not None:
        failures.append('Incomplete real /proc/self/maps snapshots')
    for row in rows:
        name=row['name'];b.require(name in NAMES,'Unknown callback')
        seed=[1,6,104] if name=='state_bad_vstart' else [7,7,65] if name in ('acquire_bad_vstart','release_bad_vstart') else [0,5,9]
        if any([row[f'{part}{i}'] for i in range(3)]!=seed for part in ('before','after')) or \
           [row[f'restored{i}'] for i in range(3)]!=[0,3,8] or row['ok']!=1:failures.append(name+': CSR changed')
        if name in POSITIVES and row['result']<=0:failures.append(name+': required real lease denied')
        if name in NEGATIVES and row['result']!=0:failures.append(name+': rejection failed')
        if name=='state_ready' and row['result']!=1:failures.append(name+': not READY')
        if name=='state_bad_vstart' and row['result']!=-1:failures.append(name+': not BAD_VSTART')
    cookies=[r['result'] for r in rows if r['name'] in POSITIVES]
    if len(cookies)!=5 or any(a>=b for a,b in zip(cookies,cookies[1:])):failures.append('Lease lifetime/generation failure')
    for marker in ('PROVIDER_SETUP result=1','PROVIDER_STATE vlenb=128 vstart=0 vcsr=5 fcsr=9',
                   'PROVIDER_COMPLETE failures=0 calls=16 native_akv=0 model=0','PROVIDER_CHILD_EXIT=0'):
        if text.splitlines().count(marker)!=1:failures.append('Missing exact terminal/state: '+marker)
    return dict(calls=rows,map_snapshots=maps,failures=failures,passed=not failures,
                callback_object_is_frozen=True,software_fallback_used=False,algorithm_or_s3_claim=False)


def execute(out,review):
    b.require(HERE==out/'inputs' and b.sha(out/'source-pins.json')==review,'Frozen reviewed smoke required')
    b.require(not (out/'attempt.json').exists() and not (out/'result.json').exists(),'Only one boot; no retry')
    unit='stage5-provider-os-'+out.name+'.service'
    owner=subprocess.check_output(['systemctl','--user','show',unit,'--property=MainPID','--value'],text=True).strip()
    group=Path('/proc/self/cgroup').read_text()
    b.require(owner==str(os.getpid()) and '/'+unit in group,'Direct service required')
    b.save(out/'attempt.json',dict(pid=os.getpid(),unit=unit,invocation=os.environ.get('INVOCATION_ID'),automatic_retry=False))
    result=dict(state='FAIL',model_executed=False,native_akv_executed=False,automatic_retry=False);child=None
    try:
        pins=b.read(out/'source-pins.json');b.verify(pins)
        with (out/'guest.log').open('xb') as log:
            child=subprocess.Popen(b.read(out/'qemu-command.json'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                cwd=out,env=dict(PATH='/usr/bin:/bin',LC_ALL='C',HOME=str(out)))
            child_group=Path(f'/proc/{child.pid}/cgroup').read_text();b.require(child_group==group,'Guest outside service')
            b.save(out/'qemu-process.json',dict(pid=child.pid,cgroup=child_group))
            rc=child.wait(timeout=180)
        b.require(rc==0,'Nonzero QEMU exit')
        proof=check((out/'guest.log').read_text());b.verify(pins)
        result.update(state='PROVIDER_OS_CALLBACKS_PASS' if proof['passed'] else 'PROVIDER_OS_CALLBACKS_FAIL',proof=proof,
            post_pins_match=True,guest_sha256=b.sha(out/'guest.log'),source_pins_sha256=review)
    except BaseException as e:
        if child is not None and child.poll() is None:child.kill();child.wait()
        result['error']=repr(e)
    b.save(out/'result.json',result);print(json.dumps(result,sort_keys=True));return result['state']=='PROVIDER_OS_CALLBACKS_PASS'


def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--review-sha256')
    a=p.parse_args();out=a.output.resolve()
    if a.action=='prepare':prepare(out);return 0
    return 0 if execute(out,a.review_sha256) else 1


if __name__=='__main__':sys.exit(main())
