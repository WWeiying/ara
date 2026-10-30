#!/usr/bin/env python3
"""Build/test a register-only Q8_0/PV candidate; never measure QEMU performance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PLATFORM=Path('/home/wangwy/llama/platforms/cva6-qemu')


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def save(path,value):
    temp=path.with_suffix(path.suffix+'.partial')
    temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();out=args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Fresh independent output required')
    out.mkdir(parents=True)
    pins,commands={},[]
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,
               functional_only=True,rtl_performance=False,production_enabled=False)
    env=dict(HOME='/home/wangwy',PATH='/usr/bin:/bin',LANG='C.UTF-8')
    def pin(path):
        path=Path(path).resolve(strict=True);h=digest(path)
        if str(path) in pins and pins[str(path)]!=h:raise ValueError('Input drift: '+str(path))
        pins[str(path)]=h
    def unchanged():
        for p,h in pins.items():
            if digest(p)!=h:raise ValueError('Input drift: '+p)
    def run(argv,name,bound=180,stdout=None):
        argv=list(map(str,argv));pin(argv[0]);unchanged()
        commands.append(dict(label=name,argv=argv,timeout=bound));save(out/'commands.json',commands)
        state['state']=name.upper();save(out/'status.json',state)
        with (out/(name+'.log')).open('wb') as log:
            child=subprocess.Popen(argv,cwd=out,env=env,stdout=log if stdout is None else stdout,
                                   stderr=log,start_new_session=True)
            state['child_pid']=child.pid;save(out/'status.json',state)
            try:code=child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                raise
            finally:state['child_pid']=None
            if code:raise RuntimeError(name+' returned '+str(code))
        unchanged();return (out/(name+'.log')).read_text(errors='replace')
    try:
        cc=PLATFORM/'tools/bin/riscv64-linux-gcc'
        init=HERE.parent/'ggml_live/init.c'
        for p in (Path(__file__),HERE/'candidate.h',HERE/'test_candidate.c',init,cc):pin(p)
        base=[cc,'-O3','-static','-march=rv64gcv_zfh_zvfh','-mabi=lp64d',
              '-fno-tree-vectorize','-fno-fast-math','-ffp-contract=off','-frounding-math',
              '-Wall','-Wextra','-Werror','-I'+str(ROOT)]
        for program in ('cc1','as','ld'):
            pin(run([cc,'-print-prog-name='+program],'locate-'+program).strip())
        for library in ('libm.a','libc.a','libgcc.a','libgcc_eh.a'):
            pin(run([cc,'-print-file-name='+library],'locate-'+library).strip())
        deps=run([*base,'-M','-MT','object',HERE/'test_candidate.c'],'dependencies')
        for p in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):pin(p)
        audit=ROOT/'verification/out/quant-prefill-capture-audit-20261028-01'
        pin(audit/'manifest.json');pin(audit/'result.json')
        if json.loads((audit/'result.json').read_text())['state']!='PASS':raise ValueError('Capture audit')
        audited=json.loads((audit/'manifest.json').read_text())
        assembly=['.section .rodata,"a",@progbits']
        for kind in ('q4_0','q8_0'):
            data=ROOT/'verification/out/quant-prefill-capture-20261028-01'/kind/'prefill/block/attn_v_input-0.bin'
            if audited.get(str(data))!=digest(data):raise ValueError('Real V capture drift')
            if data.stat().st_size!=136*256*8:raise ValueError('Real V shape')
            pin(data);symbol='real_'+kind[:2]+'_value'
            assembly.extend(['.balign 64','.global '+symbol,symbol+':',f'.incbin "{data}"'])
        data_s=out/'data.S';data_s.write_text('\n'.join(assembly)+'\n');pin(data_s)
        run([*base,HERE/'test_candidate.c',data_s,'-lm','-o',out/'test'],'build')
        pin(out/'test')
        dis=run([cc.with_name('riscv64-linux-objdump'),'-d','--disassemble=register_pv_probe',out/'test'],'candidate-disassembly')
        for op in ('vle8.v','vsext.vf4','vfcvt.f.x.v','vfmul.vf','vfmacc.vf','vse32.v'):
            if op not in dis:raise ValueError('Missing candidate vector operation: '+op)
        run([cc,'-O2','-static','-march=rv64gc','-mabi=lp64d',init,'-o',out/'init'],'init-build')
        pin(out/'init')
        cpio=PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            f'file /init {out/"init"} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        pin(listing)
        with (out/'initramfs.cpio').open('xb') as stream:run([cpio,listing],'cpio',60,stream)
        pin(out/'initramfs.cpio')
        qemu=ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
        kernel,firmware=PLATFORM/'images/Image',PLATFORM/'images/fw_dynamic.bin'
        for p in (qemu,kernel,firmware):pin(p)
        save(out/'input-pins.json',pins)
        if args.execute_reviewed:
            started=time.monotonic()
            text=run([qemu,'-M','virt','-cpu','rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true',
                '-smp','1','-m','512M','-display','none','-monitor','none','-serial','stdio',
                '-bios',firmware,'-kernel',kernel,'-initrd',out/'initramfs.cpio',
                '-append','console=ttyS0 rdinit=/init'],'qemu',600).replace('\r\n','\n')
            expected='REGISTER_PV_PASS cases=12928 invalid=16 real_cases=640 exact=1 flags=1 guards=1'
            if ([l for l in text.splitlines() if l.startswith('REGISTER_PV_PASS')]!=[expected] or
                text.splitlines().count('GUEST_TEST_EXIT=0')!=1 or
                re.search(r'REGISTER_PV_FAIL|Kernel panic|GUEST_TEST_EXIT=[1-9]',text)):
                raise ValueError('Missing numerical/CSR/guest completion')
            state.update(state='PASS',marker=expected,seconds=time.monotonic()-started,
                         log_sha256=digest(out/'qemu.log'))
        else:state['state']='BUILT_NOT_EXECUTED'
        unchanged();state.update(elf_sha256=digest(out/'test'),source_pre_post_match=True,
            input_pins_sha256=digest(out/'input-pins.json'))
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save(out/'status.json',state);save(out/'result.json',state)


if __name__=='__main__':main()
