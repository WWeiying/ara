#!/usr/bin/env python3
"""One Linux CSR/getpid observation; no model, AKV, or S3 acceptance."""
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
BASE=OUT/'stage5_models_execution_link_20261110_04/inputs/run.py'
BASE_SHA='dc4e61f05db744fa17424bc68a1218415117646e143ec20085c33d9214d155a1'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA: raise ValueError('Sealed utility drift')
loader=importlib.util.spec_from_file_location('sealed_execution_utilities',BASE)
b=importlib.util.module_from_spec(loader);loader.loader.exec_module(b)
QEMU=OUT/'qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
OWN=('probe.py','csr_probe.c','csr_probe.S')


def prepare(out):
    b.require(out.parent==OUT and not out.exists() and out.name.startswith('stage5_models_oscsr_'),'Fresh probe output')
    old=b.read(b.MODELS/'source-pins.json')
    b.require(b.sha(b.MODELS/'result.json')==b.MODELS_SHA,'Models04 ancestry')
    pins={str(BASE):BASE_SHA,str(b.MODELS/'result.json'):b.MODELS_SHA,
          str(b.MODELS/'source-pins.json'):b.sha(b.MODELS/'source-pins.json')}
    for p in (QEMU,b.BIOS,b.KERNEL,b.CC,b.CPIO):
        b.require(old[str(p)]==b.sha(p),'Frozen OS/tool drift: '+str(p));pins[str(p)]=old[str(p)]
    b.verify(pins)
    out.mkdir();(out/'inputs').mkdir();commands=[]
    def run(name,argv):
        argv=list(map(str,argv));commands.append(dict(label=name,argv=argv))
        with (out/(name+'.log')).open('x') as log:
            r=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,cwd=out,timeout=120,
                env=dict(PATH=str(b.CC.parent)+':/usr/bin:/bin',HOME=str(out),LC_ALL='C'))
        b.require(r.returncode==0,'Probe build failed: '+name)
    report=dict(state='FAIL',model_executed=False,native_akv_executed=False)
    try:
        for name in OWN:
            pins[str(HERE/name)]=b.sha(HERE/name);shutil.copyfile(HERE/name,out/'inputs'/name)
        for suffix in ('c','S'):
            run('compile-'+suffix,[b.CC,'-std=gnu11',*b.FLAGS,'-Wall','-Wextra','-Werror',
                '-MD','-MF',out/('probe-'+suffix+'.d'),'-c',out/('inputs/csr_probe.'+suffix),
                '-o',out/('probe-'+suffix+'.o')])
        run('link',[b.CC,*b.FLAGS,'-static','-no-pie',out/'probe-c.o',out/'probe-S.o',
            '-Wl,-Map='+str(out/'probe.map'),'-o',out/'init'])
        run('disassembly',[b.CC.with_name('riscv64-linux-objdump'),'-d','--disassemble=stage5_csr_syscall_probe',out/'init'])
        text=(out/'disassembly.log').read_text()
        b.require(len(re.findall(r'\becall\b',text))==1 and 'vsetvli' in text and 'vsetvl' in text,'Probe instruction inventory')
        b.require('.word' not in text and '.insn' not in text,'Unknown/custom probe instruction')
        (out/'initramfs.list').write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+f'file /init {out/"init"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([b.CPIO,out/'initramfs.list'],stdout=f,check=True,timeout=30)
        command=[str(QEMU),'-M','virt','-cpu','rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
            '-smp','1','-m','4G','-display','none','-monitor','none','-serial','stdio','-bios',str(b.BIOS),
            '-kernel',str(b.KERNEL),'-initrd',str(out/'initramfs.cpio'),'-append','console=ttyS0 rdinit=/init']
        b.save(out/'qemu-command.json',command);b.save(out/'commands.json',commands)
        deps=[]
        for p in out.glob('*.d'):deps+=shlex.split(p.read_text().replace('\\\n','').split(':',1)[1])
        deps+=re.findall(r'(?m)^LOAD (\S+)',(out/'probe.map').read_text())
        for p in [*map(Path,deps),b.CC.resolve(),b.CC.with_name('riscv64-linux-objdump')]:pins[str(p.resolve())]=b.sha(p)
        for p in out.rglob('*'):
            if p.is_file():pins[str(p)]=b.sha(p)
        b.verify(pins);b.save(out/'source-pins.json',pins)
        report.update(state='PREPARED_OS_CSR_ONLY',pins=len(pins),source_pins_sha256=b.sha(out/'source-pins.json'),
            image_sha256=b.sha(b.KERNEL),qemu_sha256=b.sha(QEMU),elf_sha256=b.sha(out/'init'),post_pins_match=True)
    except BaseException as e:report['error']=repr(e);raise
    finally:b.save(out/'prepare.json',report)
    print(json.dumps(report,sort_keys=True))


def check(text):
    rows=[]
    for line in text.splitlines():
        if not line.startswith('CSR_SYSCALL_SAMPLE '):continue
        fields={}
        for item in line.split()[1:]:
            k,v=item.split('=');b.require(k not in fields and re.fullmatch('[0-9]+',v),'Malformed sample');fields[k]=int(v)
        b.require(set(fields)=={'case','syscall','pid',*[f'{s}{i}' for s in ('before','after','restored') for i in range(5)]},'Sample fields')
        rows.append(fields)
    b.require([(r['case'],r['syscall']) for r in rows]==[(i,s) for i in range(3) for s in range(2)],'Missing/duplicate/reordered samples')
    b.require(text.splitlines().count('CSR_PROBE_COMPLETE samples=6 native_akv=0 model=0')==1 and
        text.splitlines().count('CSR_PROBE_CHILD_EXIT=0')==1,'Incomplete probe/child')
    b.require(len(re.findall(r'^CSR_PROBE_OS ',text,re.M))==1,'OS preauthorization missing')
    b.require(len(re.findall(r'^CSR_PROBE_CHILD_EXIT=',text,re.M))==1,'Duplicate child result')
    for r in rows:
        i=r['case'];b.require([r[f'before{j}'] for j in range(5)]==[[0,1,7][i],[5,6,7][i],[9,104,65][i],13,200],'Seed mismatch')
        b.require([r[f'restored{j}'] for j in range(3)]==[0,3,8],'C ABI restore failed')
        if not r['syscall']:
            b.require(r['pid']==0 and all(r[f'before{j}']==r[f'after{j}'] for j in range(5)),'No-syscall control changed')
        else:b.require(r['pid']>=2,'Not a real child syscall')
    return dict(samples=rows,syscall_preserves={name:all(r[f'before{i}']==r[f'after{i}'] for r in rows if r['syscall'])
        for i,name in enumerate(('vstart','vcsr','fcsr','vl','vtype'))})


def execute(out,review):
    b.require(HERE==out/'inputs' and b.sha(out/'source-pins.json')==review,'Frozen reviewed probe required')
    b.require(not (out/'attempt.json').exists() and not (out/'result.json').exists(),'Only one OS probe execution')
    unit='stage5-oscsr-'+out.name+'.service'
    owner=subprocess.check_output(['systemctl','--user','show',unit,'--property=MainPID','--value'],text=True).strip()
    b.require(owner==str(os.getpid()) and '/'+unit in Path('/proc/self/cgroup').read_text(),'Direct service required')
    b.save(out/'attempt.json',dict(pid=os.getpid(),unit=unit,invocation=os.environ.get('INVOCATION_ID'),automatic_retry=False))
    result=dict(state='FAIL',model_executed=False,native_akv_executed=False,automatic_retry=False)
    try:
        pins=b.read(out/'source-pins.json');b.verify(pins)
        with (out/'guest.log').open('xb') as log:
            completed=subprocess.run(b.read(out/'qemu-command.json'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                timeout=180,cwd=out,env=dict(PATH='/usr/bin:/bin',LC_ALL='C',HOME=str(out)))
        b.require(completed.returncode==0,'Nonzero QEMU exit')
        proof=check((out/'guest.log').read_text());b.verify(pins)
        result.update(state='OS_CSR_SYSCALL_OBSERVED',proof=proof,post_pins_match=True,
            guest_sha256=b.sha(out/'guest.log'),source_pins_sha256=review)
    except BaseException as e:result['error']=repr(e)
    b.save(out/'result.json',result);print(json.dumps(result,sort_keys=True));return result['state']=='OS_CSR_SYSCALL_OBSERVED'


def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--review-sha256')
    a=p.parse_args();out=a.output.resolve()
    if a.action=='prepare':prepare(out);return 0
    return 0 if execute(out,a.review_sha256) else 1


if __name__=='__main__':sys.exit(main())
