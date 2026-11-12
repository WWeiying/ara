"""One bounded QEMU boot, actual llama-simple, same observed ELF OFF/ON.

prepare links scalar observation wrappers onto the original simple.cpp object
and exact accepted static libraries. No live source or numerical code changes.
run must be directly owned by systemd; one attempt, no queue or retry.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

ROOT=Path('/home/wangwy/openproject/ara_dsa')
HERE=Path(__file__).resolve().parent
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
PLATFORM=Path('/home/wangwy/llama/platforms/cva6-qemu')
BUILD=OUT/'enablement_software_m4preflight_build_20261111_01'
TARGET=OUT/'enablement_software_m4preflight_target_20261111_02'
GATES=OUT/'stage5_qemu_four_gates_20261110_03/result.json'
MODEL=Path('/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf')
DISK=PLATFORM/'images/qwen2.5-q4km-capture.ext4'
CPU='rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv=true,xaraakv-resident=true'
OWN=('model_m4_run.py','model_m4_init.c','model_m4_observe.cpp','model_m4_test.py')
ORIGINAL_ELF='d08fb68839c1bd7612e374542eb4c297f0e688684e98e4479bffc6304ff018cd'
BUILD_SHA='aacea8c04add356ac09c37c180abe3aa6cd09a40b15a31d40bf65e42f21b8a76'
GATES_SHA='d1fe3d705d1caa1923536eff66a6e4fa51030d180e2db01c1724ccc1a4f211d0'


def require(ok,why):
    if not ok: raise ValueError(why)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''): h.update(data)
    return h.hexdigest()
def read(path): return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as f: json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def verify(pins):
    for path,digest in pins.items(): require(sha(path)==digest,'Pin drift: '+path)
def fields(line):
    result={}
    for word in line.split()[1:]:
        key,value=word.split('=',1);require(key not in result,'Duplicate field');result[key]=value
    return result


def check(lines,symbols,vocab=151936):
    mode=None;sequence=0;previous=None;active=None;bits={};logits={};csr=[[],[]];tokens=[[],[]]
    selected=[Counter(),Counter()];qbs=[{},{}];entries=[Counter(),Counter()];stopped=[Counter(),Counter()]
    pcs={int(value):name for name,value in symbols.items()};exits=0
    for raw in lines:
        line=raw.rstrip('\r\n');last,previous=previous,None
        if line.startswith('Stopped execution of TB chain before '):
            m=re.fullmatch(r'Stopped execution of TB chain before ((?:0x)?[0-9a-f]+) \[([0-9a-f]+)\] .*',line)
            require(m is not None and last is not None and (m[1],int(m[2],16))==last[:2],'Unpaired cancelled TB')
            entries[last[2]][pcs[last[1]]]-=1;stopped[last[2]][pcs[last[1]]]+=1;continue
        if line.startswith('M4_ARM_BEGIN '):
            f=fields(line);require(mode is None and f=={'mode':str(sequence)} and sequence<2,'Arm order')
            mode=sequence
        elif line.startswith('M4_ARM_END '):
            require(mode is not None and active is None and fields(line)==dict(mode=str(mode),status='0'),'Arm failed')
            mode=None;sequence+=1
        elif line.startswith('M4_DECODE '):
            require(mode is not None,'Unscoped decode');f={k:int(v) for k,v in fields(line).items()}
            require(set(f)=={'step','rows','rc','fcsr','vcsr','vstart'} and f['step']==len(csr[mode]) and
                f['rc']==0 and f['vstart']==0 and f['fcsr']>>5==0 and 0<=f['vcsr']<=7,'Decode/CSR failure')
            require((20<=f['rows']<=32) if f['step']==0 else f['rows']==1,'Wrong/long prompt or decode shape')
            csr[mode].append(f)
        elif line.startswith('M4_TOKEN '):
            require(mode is not None,'Unscoped token');f=fields(line)
            require(f.keys()=={'step','token'} and int(f['step'])==len(tokens[mode]),'Token order')
            tokens[mode].append(int(f['token']))
        elif line.startswith('GGML_RISCV_QBS_M4_SELECTED '):
            require(mode is not None,'Unscoped cache');f=fields(line)
            if f.get('source')=='cache':
                require(f.keys()=={'source','tag','event','k'} and f['event'] in ('compute_rvv','compute_generic','hit'),'Cache record')
                tag,k=int(f['tag']),int(f['k']);require(tag in (1,2,3,4),'Unknown producer')
                require(tag!=4 or (mode==1 and k==1536),'Tag4 outside positive')
                selected[mode][(k,tag,f['event'])]+=1
        elif line.startswith('GGML_RISCV_QBS_EXEC '):
            require(mode is not None,'Unscoped QBS');f=fields(line);kind=f.pop('type')
            require(kind not in qbs[mode],'Duplicate QBS summary');r={k:int(v) for k,v in f.items()}
            require(r['native_qbexec']>0 and r['emulated_commands']==0,'Non-native/simulated QBS');qbs[mode][kind]=r
        elif line.startswith('Trace '):
            m=re.fullmatch(r'Trace 0: ((?:0x)?[0-9a-f]+) \[[0-9a-f]+/([0-9a-f]+)/[0-9a-f]+/[0-9a-f]+\].*',line)
            require(m is not None and mode is not None,'Unscoped/wrong-hart trace')
            pc=int(m[2],16);require(pc in pcs,'Unfiltered trace');entries[mode][pcs[pc]]+=1;previous=(m[1],pc,mode)
        elif line.startswith('M4_LOGITS_BEGIN '):
            f=fields(line);key=(mode,int(f['step']))
            require(mode is not None and active is None and f==dict(mode=str(mode),step=str(key[1]),values=str(vocab)) and
                key not in logits and key[1] in (0,1),'Logits begin');active=key;bits[key]=[]
        elif line.startswith('M4_BITS '):
            require(active is not None,'Unscoped logits');words=line.split();index=int(words[1].split('=')[1])
            require(index==len(bits[active]) and len(words[2:])==min(32,vocab-index) and
                all(re.fullmatch('[0-9a-f]{8}',w) for w in words[2:]),'Truncated/reordered logits')
            values=[int(w,16) for w in words[2:]]
            require(all(v&0x7f800000!=0x7f800000 for v in values),'Nonfinite logits');bits[active]+=values
        elif line.startswith('M4_LOGITS_END '):
            require(active is not None and fields(line)==dict(mode=str(active[0]),step=str(active[1])) and
                len(bits[active])==vocab,'Incomplete logits');logits[active]=bits.pop(active);active=None
        elif line.startswith('GUEST_TEST_EXIT='):
            require(line=='GUEST_TEST_EXIT=0' and sequence==2,'Guest failed');exits+=1
    require(mode is None and active is None and sequence==2 and exits==1,'Missing terminal')
    require(len(csr[0])==len(csr[1])==2 and csr[0]==csr[1],'Missing/different CSR or API calls')
    require(len(tokens[0])==len(tokens[1])==2 and tokens[0]==tokens[1],'Missing/different generated tokens')
    require(set(logits)=={(m,s) for m in (0,1) for s in (0,1)},'Incomplete full vocabulary')
    for step in (0,1):
        require(logits[(0,step)]==logits[(1,step)],'Logits not bitwise equal')
        floats=[struct.unpack('<f',struct.pack('<I',v))[0] for v in logits[(0,step)]]
        require(tokens[0][step]==max(range(vocab),key=floats.__getitem__),'Token not actual greedy argmax')
    require(qbs[0] and qbs[0]==qbs[1] and {'Q4_K','Q6_K'}<=qbs[0].keys(),'Unequal/non-K projection work')
    for m in (0,1):
        require(entries[m]['qbs']==sum(r['native_qbexec'] for r in qbs[m].values()),'Native QBS entries differ from summary')
    cold=selected[1][(1536,4,'compute_rvv')];hits=selected[1][(1536,4,'hit')]
    require(cold>0 and hits>0 and not selected[1][(1536,4,'compute_generic')],
        'SELECTION_NOT_HIT: need actual K1536 tag4 cold RVV and warm hits')
    require(entries[0]['producer']==0 and entries[1]['producer']==cold,'Actual retained producer entry count differs')
    normalized=[]
    for counts in selected:
        n=Counter()
        for (k,tag,event),count in counts.items(): n[(k,3 if tag==4 else tag,event)]+=count
        normalized.append(n)
    require(normalized[0]==normalized[1],'Cold/hit work differs between producer arms')
    return dict(logits_compared=2*vocab,bitwise_equal=True,tokens=tokens[0],csr=csr[0],
        tag4_cold=cold,tag4_hits=hits,retained_producer_entries=entries[1]['producer'],
        qbs=qbs[0],native_entries=[dict(c) for c in entries],cancelled_tb=[dict(c) for c in stopped],
        instruction_retirement_claim=False,performance_measured=False)


def prepare(out):
    require(out.parent==OUT and out.name.startswith('enablement_model_m4_') and not out.exists(),'Fresh output required')
    require(sha(BUILD/'build.json')==BUILD_SHA and sha(GATES)==GATES_SHA,'Build/gates receipt drift')
    b=read(BUILD/'build.json');t=read(TARGET/'result.json');g=read(GATES)
    require(b['post_pins_match'] and b['state']=='FRESH_FULL_LLAMA_BUILD_CHECKED_NOT_MODEL_EXECUTED' and
        t['state']=='M4_PREFLIGHT_GNU_SPIKE_CHECKED' and t['post_pins_match'] and
        [r['case'] for r in t['cases']]==list(range(16)),'Target/build not accepted')
    pins=read(BUILD/'source-pins.json');require(sha(BUILD/'source-pins.json')==b['source_pins_sha256'],'Build pins')
    verify(pins)
    require(sha(TARGET/'source-pins.json')==t['source_pins_sha256'],'Target pins');verify(read(TARGET/'source-pins.json'))
    out.mkdir();(out/'inputs').mkdir();commands=[]
    def pin(p): pins[str(Path(p).resolve())]=sha(p)
    def run(label,argv,cwd=out):
        argv=list(map(str,argv));pin(Path(shutil.which(argv[0]) or argv[0]).resolve())
        with (out/(label+'.log')).open('x') as f:
            r=subprocess.run(argv,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=300)
        commands.append(dict(label=label,argv=argv,cwd=str(cwd),returncode=r.returncode));require(r.returncode==0,label+' failed')
        return (out/(label+'.log')).read_text()
    report=dict(state='FAIL',model_executed=False)
    try:
        for name in OWN: pin(HERE/name);shutil.copyfile(HERE/name,out/'inputs'/name)
        for p in (BUILD/'build.json',BUILD/'source-pins.json',TARGET/'result.json',TARGET/'source-pins.json',GATES,MODEL,DISK):pin(p)
        # Inspect real GGUF types/geometry, not the filename or a Q4_0 head tail.
        code="from gguf import GGUFReader; import json; r=GGUFReader("+repr(str(MODEL))+"); print(json.dumps([(t.name,t.shape.tolist(),t.tensor_type.name) for t in r.tensors if t.name.startswith('blk.0.') and t.name.endswith(('attn_q.weight','attn_k.weight','attn_v.weight'))]))"
        inventory=json.loads(run('gguf-inspect',['env','PYTHONPATH=/home/wangwy/llama/llama.cpp/gguf-py',sys.executable,'-c',code]))
        require(sorted(inventory)==sorted([['blk.0.attn_q.weight',[1536,1536],'Q4_K'],['blk.0.attn_k.weight',[1536,256],'Q4_K'],['blk.0.attn_v.weight',[1536,256],'Q6_K']]),'Positive model geometry/type')
        save(out/'model.json',dict(path=str(MODEL),sha256=sha(MODEL),disk=str(DISK),disk_sha256=sha(DISK),qkv=inventory))
        # Verify disk payload byte-for-byte without mounting or writing the disk.
        run('disk-extract',['/usr/sbin/debugfs','-R','dump /models/'+MODEL.name+' '+str(out/'disk-model.gguf'),DISK])
        require(sha(out/'disk-model.gguf')==sha(MODEL),'Disk/model mismatch');(out/'disk-model.gguf').unlink()
        cc=PLATFORM/'tools/bin/riscv64-linux-gcc';cxx=cc.with_name('riscv64-linux-g++');nm=cc.with_name('riscv64-linux-nm')
        elf=BUILD/'bin/llama-simple';require(sha(elf)==ORIGINAL_ELF,'Original simple ELF drift');pin(elf)
        obj=BUILD/'examples/simple/CMakeFiles/llama-simple.dir/simple.cpp.o'
        libs=[BUILD/p for p in ('src/libllama.a','ggml/src/libggml.a','ggml/src/libggml-cpu.a','ggml/src/libggml-base.a')]
        for p in [obj,*libs,BUILD/'compile_commands.json',BUILD/'examples/simple/CMakeFiles/llama-simple.dir/link.txt']:pin(p)
        flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-O2','-static']
        original_link=shlex.split((BUILD/'examples/simple/CMakeFiles/llama-simple.dir/link.txt').read_text())
        original_link[original_link.index('-o')+1]=str(out/'original-relinked')
        run('original-relink',original_link,BUILD/'examples/simple')
        require(sha(out/'original-relinked')==ORIGINAL_ELF,'Accepted objects do not reproduce original ELF')
        run('observe-compile',[cxx,*flags,'-fno-tree-vectorize','-fno-tree-slp-vectorize','-I/home/wangwy/llama/llama.cpp/include','-I/home/wangwy/llama/llama.cpp/ggml/include','-c',out/'inputs/model_m4_observe.cpp','-o',out/'observe.o'])
        run('observe-link',[cxx,*flags,obj,out/'observe.o','-Wl,--wrap=llama_decode','-Wl,--wrap=llama_sampler_sample',*libs,'-ldl','-lm','-o',out/'test'])
        names=run('symbols',[nm,'-S','-C',out/'test']);symbols={}
        for key,name in [('qbs','qbs_native_execute_command'),('producer','qbs_experimental_m4_preflight::quantize(float const*, void*, long)')]:
            matches=[line.split()[0] for line in names.splitlines() if line.endswith(' '+name)]
            require(len(matches)==1,'Missing actual producer/native symbol: '+name);symbols[key]=int(matches[0],16)
        save(out/'symbols.json',symbols)
        run('init-compile',[cc,*flags,'-Wall','-Wextra','-Werror','-fno-tree-vectorize','-fno-tree-slp-vectorize',out/'inputs/model_m4_init.c','-o',out/'init'])
        listing=''.join('dir /'+name+' 0755 0 0\n' for name in ('dev','proc','model'))+'dir /tmp 1777 0 0\n'+''.join('file /'+n+' '+str(out/n)+' 0755 0 0\n' for n in ('init','test'))
        (out/'initramfs.list').write_text(listing);cpio=PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio';pin(cpio)
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([cpio,out/'initramfs.list'],stdout=f,check=True,timeout=30)
        qemu=Path(g['executable']);require(sha(qemu)==g['executable_sha256'],'BUILD07 drift')
        bios=PLATFORM/'images/fw_dynamic.bin';kernel=PLATFORM/'images/Image'
        for p in (qemu,bios,kernel):pin(p)
        command=[str(qemu),'-M','virt','-cpu',CPU,'-smp','1','-m','4G','-display','none','-monitor','none','-serial','stdio','-bios',str(bios),'-kernel',str(kernel),'-initrd',str(out/'initramfs.cpio'),'-drive','file='+str(DISK)+',if=virtio,format=raw,readonly=on','-append','console=ttyS0 rdinit=/init','-d','exec,nochain','-dfilter',','.join(hex(pc)+'+1' for pc in symbols.values())]
        save(out/'qemu-command.json',command);save(out/'commands.json',commands)
        for p in out.rglob('*'):
            if p.is_file():pin(p)
        verify(pins);save(out/'source-pins.json',pins)
        report.update(state='PREPARED_NOT_EXECUTED',source_pins_sha256=sha(out/'source-pins.json'),original_elf_sha256=ORIGINAL_ELF,
            observed_elf_sha256=sha(out/'test'),qemu_sha256=sha(qemu),model_sha256=sha(MODEL),disk_sha256=sha(DISK),timeout_seconds=1800,
            same_elf_two_arms=True,only_policy_difference='GGML_RISCV_QBS_M4_PREFLIGHT=0/1',post_pins_match=True)
    except BaseException as e:report['error']=repr(e);raise
    finally:save(out/'prepare.json',report)
    print(json.dumps(report,sort_keys=True))


def execute(out,review):
    require(HERE==out/'inputs' and sha(out/'source-pins.json')==review,'Unreviewed frozen runner')
    require(not (out/'attempt.json').exists(),'No retry')
    unit='enablement-model-m4-'+out.name+'.service'
    pid=subprocess.check_output(['systemctl','--user','show',unit,'--property=MainPID','--value'],text=True).strip()
    group=Path('/proc/self/cgroup').read_text();require(pid==str(os.getpid()) and '/'+unit in group,'Direct systemd ownership required')
    save(out/'attempt.json',dict(pid=os.getpid(),unit=unit,automatic_retry=False))
    result=dict(state='FAIL',performance_measured=False,fpga_acceptance=False,instruction_retirement_claim=False);child=None
    try:
        pins=read(out/'source-pins.json');verify(pins)
        with (out/'guest.log').open('xb') as log:
            child=subprocess.Popen(read(out/'qemu-command.json'),stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,cwd=out)
            childgroup=Path('/proc/'+str(child.pid)+'/cgroup').read_text();require(childgroup==group,'QEMU cgroup')
            save(out/'qemu-process.json',dict(pid=child.pid,cgroup=childgroup))
            require(child.wait(timeout=1800)==0,'QEMU failed')
        with (out/'guest.log').open() as f:proof=check(f,read(out/'symbols.json'))
        verify(pins);result.update(state='FULL_LLAMA_M4_PREFLIGHT_PAIR_CHECKED',proof=proof,post_pins_match=True,model_executed=True)
    except BaseException as e:
        if child is not None and child.poll() is None:child.kill();child.wait()
        result['error']=repr(e)
    result.update(source_pins_sha256=review,guest_log_sha256=sha(out/'guest.log') if (out/'guest.log').exists() else None)
    save(out/'result.json',result);print(json.dumps(result,sort_keys=True));return result['state']=='FULL_LLAMA_M4_PREFLIGHT_PAIR_CHECKED'


if __name__=='__main__':
    parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--review-sha256')
    args=parser.parse_args();out=args.output.resolve()
    if args.action=='prepare':prepare(out)
    else:sys.exit(0 if execute(out,args.review_sha256) else 1)
