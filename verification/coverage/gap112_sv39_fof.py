"""One RAM-contained GAP112 Sv39 FOF preflight and reviewed 180s runner."""
import argparse
import inspect
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import gap112_fof_flush as prior

life, shared, require = prior.life, prior.shared, prior.require
ROOT, OUT = prior.ROOT, prior.OUT
NAME = 'vgap112_sv39_fof'
APP = ROOT / 'apps/riscv-tests/isa/rv64uv' / (NAME + '.c')
CHECKS, BUDGET = 2294, 180
PRIOR_SHA = '57beea3850e3f7745f80b61b8d1203862e58df623441e7cbfa6794bda63ea9cb'
START = prior.START
SYMBOLS = ('_start', '_end', 'tohost', 'trap_fail', 'g75_trap', 'g75_result', 'num_failed',
    'sf_pages', 'sf_guard_lo', 'sf_guard_hi', 'sf_source', 'sf_div', 'sf_neighbor',
    'sf_prefix', 'sf_recovery', 'sf_post', 'sf_record', 'sf_count', 'sf_before', 'sf_after',
    'sf_handler', 'sf_handler_end', 'sf_s_entry', 'sf_s_end', 'sf_m_resume',
    'sf_long_div', 'sf_fof', 'sf_read_vl', 'sf_recovery_load', 'sf_ecall')
SIZES = dict(sf_pages=16384, sf_guard_lo=64, sf_guard_hi=64, sf_source=264,
    sf_div=264, sf_neighbor=136, sf_prefix=12, sf_recovery=40, sf_post=24,
    sf_record=80, sf_count=8, sf_before=120, sf_after=120, g75_result=8,
    num_failed=4, g75_trap=24)


def linked(s, dis):
    require(set(SYMBOLS).issubset(s), 'Missing exact linked symbol')
    require(s['_start'] == 0x80000000 and s['_end'] < 0x80100000 and
            s['sf_pages'] % 4096 == 0 and s['sf_guard_lo'] + 64 == s['sf_pages'] and
            s['sf_guard_hi'] == s['sf_pages'] + 16384, 'ELF/page/guard bounds differ')
    require(all(0x80000000 <= s[n] and s[n] + size <= s['_end'] for n, size in SIZES.items()),
            'Oracle object outside ELF/RAM')
    ranges = sorted((s[n], s[n]+size, n) for n, size in SIZES.items())
    require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])), 'Oracle object overlap')
    rvv = prior.rvv_inventory(dis)
    require(len(rvv) == 17, 'Exact17 explicit RVV opcodes required; no implicit lowering')
    words = dict(rvv)
    require(words.get(s['sf_fof']) == 0x0103e407 and
            s['sf_read_vl'] == s['sf_fof'] + 4 and
            words.get(s['sf_long_div']) == 0x838eec57 and
            words.get(s['sf_recovery_load']) == 0x0203e607,
            'Exact FOF/DIV/recovery opcodes differ')
    return dict(status='LINKED_RAM_CONTAINED_SV39_PROOF_NOT_DUT', symbols=s,
        RVV_opcodes=rvv, VA_first=0x40000ffc, VA_invalid=0x40001000,
        PA_first=s['sf_pages']+4092, PT_pages=[s['sf_pages']+4096*i for i in (1,2,3)],
        leaf_flags=0xc3, second_leaf=0, identity_code_leaf=0x200000cf,
        stack=0x801ff000, MMU_exception_before_AXI=True,
        virtual_address_need_not_be_in_physical_RAM=True, raw78_hit_claimed=False)


def expected_memory(s):
    mem = {}
    def put(a, value, width):
        for i, byte in enumerate(value.to_bytes(width, 'little')):
            require(a+i not in mem, 'Oracle overlap'); mem[a+i] = byte
    def array(name, values, width=4):
        for i, value in enumerate(values): put(s[name]+i*width, value, width)
    page = s['sf_pages']
    data = [prior.WORD if i == 1023 else 0x91700000 ^ i for i in range(1024)]
    array('sf_pages', data)
    ptes = {1: ((page+8192) >> 12 << 10) | 1, 2: 0x200000cf,
            512: ((page+12288) >> 12 << 10) | 1, 1024: (page >> 12 << 10) | 0xc3}
    for i in range(1536): put(page+4096+8*i, ptes.get(i,0), 8)
    array('sf_guard_lo', [prior.G0 ^ i for i in range(16)])
    array('sf_guard_hi', [prior.G1 ^ i for i in range(16)])
    array('sf_source', [prior.G0]+[1000+17*i for i in range(64)]+[prior.G1])
    array('sf_div', [prior.G0]+[(1000+17*i)//3 for i in range(64)]+[prior.G1])
    array('sf_neighbor', [prior.G0]+[0x89abc000+i for i in range(32)]+[prior.G1])
    array('sf_prefix', [prior.G0,prior.WORD,prior.G1])
    array('sf_recovery', [prior.G0]+data[16:24]+[prior.G1])
    array('sf_post', [1,0,17],8); array('sf_count',[1],8)
    ledger=[9,s['sf_ecall'],0,None,(8 << 60)|((page+4096) >> 12),8,16,0,117,5]
    for i, value in enumerate(ledger):
        if value is not None: put(s['sf_record']+8*i,value,8)
    array('g75_result',[CHECKS,0]); array('num_failed',[0]); array('g75_trap',[0,0,0],8)
    return mem


def validate(commits, s, trace):
    events = [(n,int(pc,16)) for n,pc in re.findall(r'exception ([^,\n]+), epc (0x[0-9a-fA-F]+)',trace)]
    require(events == [('trap_supervisor_ecall',s['sf_ecall'])] and trace.count('exception ') == 1,
            'FOF must suppress later-element page fault; exactly one S ecall expected')
    mem, terminal, handler_stores = {}, [], []
    for c in commits:
        require(c.pc != s['trap_fail'] and not c.fpr_writes, 'Default trap/implicit FP rejected')
        for a,v in c.memory_accesses:
            if v is None: continue
            width = shared.store_width(c.instruction)
            require(0x80000000 <= a and a+width <= 0x80200000, 'Software write outside frozen RAM')
            for i in range(width): mem[a+i]=(v >> (8*i)) & 255
            if a == s['tohost']: terminal.append(v)
            if s['sf_handler'] <= c.pc < s['sf_handler_end']: handler_stores.append((a,width))
    want=expected_memory(s)
    require(all(mem.get(a)==b for a,b in want.items()), 'Full independent page/source/guard/result oracle differs')
    def read(name, offset=0):
        a=s[name]+offset
        require(all(a+i in mem for i in range(8)), 'Missing context/ledger bytes')
        return int.from_bytes(bytes(mem[a+i] for i in range(8)), 'little')
    before=[read('sf_before',i*8) for i in range(15)]
    after=[read('sf_after',i*8) for i in range(15)]
    require(before==after and before[0]==0 and before[2]==s['trap_fail'], 'Exact M context restoration differs')
    require(read('sf_record',24) & 0x8000021888 == 0x800, 'Trap did not originate in S context')
    require(handler_stores == [(s['sf_count'],8)]+[(s['sf_record']+8*i,8) for i in range(10)],
            'Exact one handler ledger footprint required')
    require(terminal==[1], 'One successful terminal tohost required')
    for name in ('sf_long_div','sf_fof','sf_read_vl','sf_recovery_load'):
        sites=[c for c in commits if c.pc==s[name]]
        require(len(sites)==1, 'Missing/duplicate payload site '+name)
        require(len(re.findall(r'^core\s+0:\s+1\s+0x%016x\s+\(0x' % s[name],trace,re.M))==1,
                'Payload site not retired exactly once in S mode')
    fof=next(c for c in commits if c.pc==s['sf_fof'])
    require(fof.vector_sew==32 and fof.vector_lmul=='m2' and fof.vector_vstart==0 and
            fof.vector_writes.get(8,0) & 0xffffffff == prior.WORD and
            fof.memory_accesses==((0x40000ffc,None),), 'Defined FOF prefix/access differs')
    recovery=next(c for c in commits if c.pc==s['sf_recovery_load'])
    require(recovery.memory_accesses==tuple((0x40000040+4*i,None) for i in range(8)),
            'Recovery virtual memory addresses differ')
    require(not any(c.memory_accesses and any(a==0x40001000 for a,v in c.memory_accesses)
                    for c in commits), 'Invalid second page unexpectedly accessed')
    return dict(status='GAP112_SV39_INDEPENDENT_HOST_SPIKE_PASS_NOT_DUT',checks=CHECKS,
        independent_defined_bytes=len(want)+240+8,context_csrs_restored=15,ecall_traps=1,
        fof_traps=0,fof_VL=1,vstart=0,invalid_second_PTE=0,source_div_elements=64,
        strict_non_destination_v10_elements=32,fof_tail_not_read_or_uniquely_compared=True,
        coverage_admitted=False,raw78_hit_claimed=False)


def binding():
    require(life.digest(Path(prior.__file__))==PRIOR_SHA,'Frozen predecessor drift')
    pins,target=prior.binding()
    book=json.loads((prior.BUILD/'build-source-pins.json').read_bytes())
    for rel in ('hardware/src/ara.sv','hardware/src/ara_system.sv','hardware/src/vlsu/vlsu.sv',
                'hardware/src/vlsu/addrgen.sv','hardware/deps/cva6/core/load_store_unit.sv',
                'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv'):
        f=ROOT/rel; require(life.digest(f)==book[str(f)],'Frozen MMU source mismatch: '+rel)
        pins[str(f)]=book[str(f)]
    tb=(ROOT/'hardware/tb/ara_tb.sv').read_text()
    addr=(ROOT/'hardware/src/vlsu/addrgen.sv').read_text()
    require('AXI read address 0x%016h exceeds' in tb and
        'if ((mmu_valid_i && !mmu_exception_i.valid) || !en_ld_st_translation_i)' in addr and
        'axi_addrgen_queue_push = ~(axi_addrgen_q.fault_only_first' in addr and
        "aligned_end_addr        = {aligned_start_addr[AxiAddrWidth-1:12], 12'hFFF};" in addr,
        'TB/MMU-before-AXI/FOF gate differs')
    reference=OUT/'sv39-masked-offline-admitted-736-parent-20261006-01/admission-manifest.json'
    pins[str(reference)]='a46222989c3c88436c5e2f431eaafa3b8790ffa9fa05bd65920dc695b6088784'
    target=dict(target,hypothesis='RAM-contained Sv39 later-page masked FOF plus independent DIV and immediate CSR; timing and gains must be measured')
    return pins,target


def build(out):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh software output required')
    pins,target=binding(); plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image'])==66 and plan['image'][str(life.IMAGE)]==prior.IMAGE_SHA,'Exact frozen66 image required')
    files=[APP,START,ROOT/'verification/tests/gap75.ld',Path(__file__).resolve(),
        Path(__file__).with_name('test_gap112_sv39_fof.py'),ROOT/'verification/tests/gap112_sv39_fof_review.txt',
        Path(prior.__file__),Path(prior.frozen.__file__),Path(shared.__file__),Path(prior.strict.__file__),
        shared.LLVM/'clang',shared.LLVM/'ld.lld',shared.LLVM/'llvm-readelf',shared.LLVM/'llvm-objdump',
        shared.SPIKE,Path('/usr/bin/cc').resolve()]+list((ROOT/'verification/ara_verify').glob('*.py'))
    pins=life.merge_pins(pins,plan['image'])
    pins=life.merge_pins(pins,{str(f):life.digest(f) for f in files})
    pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL})
    life.check(pins); out.mkdir(); life.save(out/'target-before.json',target)
    try:
        host=['/usr/bin/cc','-std=c11','-Wall','-Wextra','-Werror','-DG112_SV39_HOST',str(APP),'-o',str(out/'host')]
        life.save(out/'host-command.json',host)
        with (out/'host-compile.log').open('x') as f: subprocess.run(host,check=True,stdout=f,stderr=f,timeout=30)
        host_result=subprocess.check_output([str(out/'host')],text=True,timeout=10)
        require(host_result==f'G112_SV39_HOST checks={CHECKS} failures=0\n','Host full oracle differs')
        (out/'host.log').write_text(host_result)
        cmd=[str(shared.LLVM/'clang'),'--target=riscv64-unknown-elf','-march=rv64gcv_zfh_zvfh',
            '-mabi=lp64d','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-O2','-mno-implicit-float',
            '-fno-vectorize','-fno-slp-vectorize','-fno-unroll-loops','-ffreestanding','-fuse-ld=lld',
            '-nostdlib','-T',str(ROOT/'verification/tests/gap75.ld'),str(START),str(APP),'-o',str(out/'input.elf')]
        life.save(out/'compile-command.json',cmd)
        with (out/'compile.log').open('x') as f: subprocess.run(cmd,check=True,stdout=f,stderr=f,timeout=90)
        s={n:shared._elf_symbol(out/'input.elf',shared.LLVM/'llvm-readelf',n) for n in SYMBOLS}
        dis=subprocess.check_output([str(shared.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],text=True,timeout=30)
        proof=linked(s,dis); life.save(out/'linked-proof.json',proof);life.save(out/'symbols.json',s)
        cmd=[str(shared.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',prior.RAM,
             '-l','--log-commits',str(out/'input.elf')]
        life.save(out/'spike-command.json',cmd)
        with (out/'spike.trace').open('x') as f,(out/'spike.stdout').open('x') as stdout:
            subprocess.run(cmd,check=True,stdout=stdout,stderr=f,timeout=60)
        commits=shared.parse_spike_commits(out/'spike.trace'); result=validate(commits,s,(out/'spike.trace').read_text())
        counts=prior.strict.reference_counts(commits,s); life.save(out/'validation.json',result)
        life.check(pins);pins=life.merge_pins(pins,{str(f):life.digest(f) for f in out.iterdir() if f.is_file()})
        p=dict(status='GAP112_SV39_PREFLIGHT_PASS_NOT_DUT',input_elf=str(out/'input.elf'),
            elf_sha256=life.digest(out/'input.elf'),pins=pins,symbols=s,validation=result,reference_counts=counts,
            target=target,baseline=740,baseline_seal=prior.BASE_SEAL,VCS_started=False,coverage_admitted=False)
        life.save(out/'preflight-manifest.json',p)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight-manifest.json'),ELF=p['elf_sha256'],validation=result,reference_counts=counts)))
    except Exception as exc:
        life.save(out/'failure.json',dict(status='SOFTWARE_PREFLIGHT_FAILED_NOT_DUT',reason=str(exc)));raise


def prepared(out,prepath,seal):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh run only; no retry')
    p=life.read_bound(prepath,seal)
    require(p['status']=='GAP112_SV39_PREFLIGHT_PASS_NOT_DUT' and p['baseline_seal']==prior.BASE_SEAL and
            p['VCS_started'] is False and p['coverage_admitted'] is False,'Exact preflight contract required')
    life.check(p['pins']);require(life.digest(Path(prior.frozen.__file__))==prior.FROZEN_SHA,'Lifecycle drift')
    require(p['target']==binding()[1],'740 shape/source target drift')
    s=p['symbols'];require(validate(shared.parse_spike_commits(prepath.parent/'spike.trace'),s,
        (prepath.parent/'spike.trace').read_text())==p['validation'],'Software replay differs')
    command=[str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+p['input_elf'],
        '+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(out/'commit_trace.csv'),
        '+VECTOR_TRACE='+str(out/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch',
        '-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]
    return dict(case=NAME,output=str(out),command=command,pins=life.merge_pins(p['pins'],{str(prepath):seal}),
        timeout_s=BUDGET,image_sha256=prior.IMAGE_SHA,elf_sha256=p['elf_sha256'],preflight=str(prepath),
        preflight_seal=seal,old_image_files_checked=66,software_checks=CHECKS,target=p['target'],
        foreground_lifetime=True,automatic_retry=False,coverage_admitted=False,admission_performed=False,
        terminal_oracle_verified=False,systemd_policy=dict(RuntimeMaxSec=240,TimeoutStopSec=10,KillMode='control-group'),
        qualification_required='Full scalar/native-vector/lifecycle/one S-ecall/page+context oracle; no outside-RAM AXI; raw78 and other gains measured only')


def namespace(prepath,p,record):
    require(life.digest(Path(prior.frozen.__file__))==prior.FROZEN_SHA,'Frozen lifecycle drift')
    ns=dict(prior.frozen.__dict__)
    ns.update(PRE=prepath.parent,ELF_SEAL=p['elf_sha256'],BUDGET=BUDGET,IMAGE_SEAL=prior.IMAGE_SHA,
        preflight=SimpleNamespace(NAME=NAME),command=lambda out:record['command'])
    exec(compile(inspect.getsource(prior.frozen.run),str(Path(__file__))+':frozen-foreground','exec'),ns)
    return ns


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('build','prepare','verify','run'));ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--preflight',type=Path);ap.add_argument('--seal');ap.add_argument('--prepared-seal')
    ap.add_argument('--parent-authorized',action='store_true');a=ap.parse_args();out=a.output.absolute()
    if a.mode=='build':
        require(not(a.preflight or a.seal or a.prepared_seal or a.parent_authorized),'Software-only build');build(out);return
    require(a.preflight and a.seal and (a.mode!='prepare')==bool(a.prepared_seal) and
            (a.mode=='run')==a.parent_authorized,'Separate exact parent authorization required')
    path=a.preflight.absolute();record=prepared(out,path,a.seal);sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not sidecar.exists(),'Duplicate prepare rejected');life.save(sidecar,record)
        print(json.dumps(dict(prepared=str(sidecar),seal=life.digest(sidecar),timeout_s=BUDGET)));return
    require(life.read_bound(sidecar,a.prepared_seal)==record,'Reviewed run record drift')
    if a.mode=='verify': print('GAP112_SV39_PREPARED_VERIFY_PASS_NO_VCS')
    else: namespace(path,life.read_bound(path,a.seal),record)['run'](out,record)


if __name__=='__main__': main()
