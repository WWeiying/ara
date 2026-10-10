"""Software-only mask comparison restart preflight; exact formal785 target rebind."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from elftools.elf.elffile import ELFFile

import preflight_vfirst_long_mask as mature
import audit_rr_disabled_formats783 as inventory

life, require, build, template = mature.life, mature.require, mature.build, mature.template
ROOT, OUT = life.ROOT, life.OUT
APP = ROOT/'apps/riscv-tests/isa/rv64uv/mask_compare_restart.c'
BASE = OUT/'valu-restart-offline-admitted785-agent-20261008-01'
BASE_SHA = '10273c45e4a4eb21929e0599a2bfc27bfb76afb2b36fe547de0198b5ee918cf5'
PLAN = OUT/'rvv-mask-compare-restart783-static-plan-agent-20261008-01.json'
PLAN_SHA = 'f0b5e634453bc1844f76faeb89338b5fb084985a67604b43fe0038e171631394'
STARTS = (4,8,16)
SYMBOLS = ('tohost','trap_fail','num_failed','g75_result','mc_checks','mc_init_vl','mc_sources',
           'mc_readback','mc_masks','mc_xors','mc_ledger','mc_init_a','mc_init_b','mc_clear24',
           'mc_clear1','mc_compare','mc_xor','mc_mask_store','mc_a_read','mc_b_read','mc_x_read')


def source_bytes(s):
    require(s in (0,1),'Source identity')
    return bytes(((17 if s==0 else 29)*i+(5 if s==0 else 3))%256 for i in range(128))


def mask_gold(start):
    require(start in STARTS,'Exact supported restart case')
    a,b=source_bytes(0),source_bytes(1)
    return sum(int(i>=start and a[i]<b[i])<<i for i in range(64)).to_bytes(8,'little')


def target_binding():
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(manifest['coverage_admitted'] is True,'Formal785 admitted')
    cp=inventory.POLICY/'config.json'; c=life.read_bound(cp,inventory.CONFIG_SHA)
    lp=BASE/'combined-inputs.txt'; pins={str(cp):inventory.CONFIG_SHA,str(BASE/'admission-manifest.json'):BASE_SHA,
                                     str(lp):manifest['output_pins'][str(lp)]}
    life.check(pins); ledger=lp.read_text().splitlines()
    require(len(ledger)==len(set(ledger))==786 and ledger[:-2]==c['input_ledger'],'Exact783 prefix plus784/785')
    rank_path=OUT/'rr-disabled-formats783-residual-agent-20261008-01.json'
    rank=life.read_bound(rank_path,'72fa095bde6587789258359f12e8f7ddf921b7769e00734e6755918c5fe899e5')
    pins=life.merge_pins(pins,rank['pins']); pins[str(rank_path)]=life.digest(rank_path)
    fields=['operand_request_i[%d].vstart'%i for i in (0,1)]
    groups=[next(g for g in rank['residual_groups'] if g['module_family']=='operand_requester' and g['field']==f)
            for f in fields]
    scopes={m['scope'] for g in groups for m in g['members']}; require(len(scopes)==4,'Exact four lanes')
    union=None
    for vdb in ledger[-2:]:
        files=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique admitted native suffix')
        rows,h=inventory.t.rows(files[0],scopes)
        require(manifest['input_pins'][str(files[0])]==h,'Bound785 suffix native bytes')
        pins[str(files[0])]=h; union=rows if union is None else inventory.t.union(union,rows)
    targets=[]
    for g in groups:
        for m in g['members']:
            require(m['raw_missing']==22 and m['checksum']=='553408029' and
                    m['attributes']['left']=='10' and m['attributes']['right']=='0','Whole783 field zero authority')
            row=union[m['scope']]; require(row['checksum']==m['checksum'],'Same compiled requester')
            bits=format(int(row['bits'],16),'0%db'%row['width'])
            missing=[p for p in m['coordinates'] if bits[p]=='0']
            targets.append(dict(scope=m['scope'],field=g['field'],checksum=m['checksum'],
                missing_coordinates=missing,original783_coordinates=m['coordinates'],
                logical_bits=[0,1,2] if len(missing)==22 else None))
    all_zero=all(len(t['missing_coordinates'])==22 for t in targets)
    life.check(pins)
    return dict(population=785,manifest_sha=BASE_SHA,exact783_prefix=True,targets=targets,
                whole_field_zero_after785=all_zero,proposed_target_directions=48 if all_zero else None,
                serial_bit_direction_mapping_inferred=False,status='FRESH_WHOLE_FIELD_ZERO' if all_zero else
                'HOLD_PRIOR_HIT_REQUIRES_EXACT_LOGICAL_BIT_BINDING'),pins


def linked(dis):
    mnemonics=re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{8}|[0-9a-f]{4}|(?:[0-9a-f]{2}\s+){1,3}[0-9a-f]{2})\s+([\w.]+)',dis,re.M)
    vector=[m for m in mnemonics if m.startswith('v')]
    wanted=['vsetvli']*3+['vle8.v']*2+['vmv.v.i']*2+['vmsltu.vv','vsm.v','vxor.vv']+['vs1r.v']*3
    require(sorted(vector)==sorted(wanted),'Exact explicit RVV inventory; no compiler generated vector ops: '+repr(vector))
    return vector


def validate(path,symbols):
    commits=build.parse_spike_commits(path)
    require('exception ' not in path.read_text() and not any(c.pc==symbols['trap_fail'] for c in commits),
            'Spike restart unsupported or unexpected trap: HOLD_NOT_DUT_FAILURE')
    memory={}; target=[]; writes={name:[] for name in ('mc_init_a','mc_init_b','mc_clear24','mc_clear1','mc_compare','mc_xor')}
    snapshots={name:{} for name in ('mc_mask_store','mc_a_read','mc_b_read','mc_x_read')}
    for c in commits:
        for name in writes:
            if c.pc==symbols[name]: writes[name].append(c)
        if c.pc==symbols['mc_compare']: target.append(c)
        for address,value in c.memory_accesses:
            if value is None: continue
            decoded=mature.old.rvc.decode(c.instruction)
            if decoded:
                require(decoded['kind']=='write','Store effect on load'); width=decoded['size']
            elif c.instruction&0x7f==0x23:
                f3=c.instruction>>12&7; require(f3<=3,'Known scalar store'); width=1<<f3
            else:
                require(c.instruction&0x7f==0x27,'Known vector memory writer'); width=1
            for i in range(width): memory[address+i]=value>>(8*i)&255
            for name,observed in snapshots.items():
                if c.pc==symbols[name]:
                    require(width==1 and address not in observed,'Exact unique byte snapshot')
                    observed[address]=value
    def data(name,size,offset=0):
        start=symbols[name]+offset
        require(all(start+i in memory for i in range(size)),'Missing fully defined witness '+name)
        return bytes(memory[start+i] for i in range(size))
    for s in range(2):
        require(data('mc_sources',160,s*160)==bytes([0x96])*16+source_bytes(s)+bytes([0x96])*16,
                'Immutable whole source/guards')
    require(len(target)==3 and [len(writes[n]) for n in writes]==[1,1,1,3,3,3], 'Exact explicit writer cardinality')
    require(sum(bool(c.vector_writes) for c in commits)==12,'No implicit/unknown extra writer')
    for s,name in enumerate(('mc_init_a','mc_init_b')):
        require(writes[name][0].vector_writes=={8 if s==0 else 16:int.from_bytes(source_bytes(s),'little')},
                'Complete source register initialization')
    require(writes['mc_clear24'][0].vector_writes=={24:0} and
            all(c.vector_writes=={1:0} for c in writes['mc_clear1']), 'All initial/prestart bits defined zero')
    xor=bytes(a^b for a,b in zip(source_bytes(0)[:64],source_bytes(1)[:64]))+bytes(64)
    for case,start in enumerate(STARTS):
        require(list(target[case].vector_writes)==[1] and
                target[case].vector_writes[1]&((1<<64)-1)==int.from_bytes(mask_gold(start),'little'),
                'Active bits strict; prestart preserved; no unknown defined mask bit')
        require(writes['mc_xor'][case].vector_writes=={24:int.from_bytes(xor,'little')},'Strict xor restoration')
        require(data('mc_masks',40,case*40)==bytes([0x96])*16+mask_gold(start)+bytes([0x96])*16,
                'Defined64 mask bits plus guards; tail not consumed')
        for s in range(2):
            require(data('mc_readback',160,(case*2+s)*160)==bytes([0x96])*16+source_bytes(s)+bytes([0x96])*16,
                    'Whole source register unchanged plus guards')
        require(data('mc_xors',160,case*160)==bytes([0x96])*16+xor+bytes([0x96])*16,'Whole xor and guards')
        ledger=[int.from_bytes(data('mc_ledger',8,case*64+i*8),'little') for i in range(8)]
        require(ledger==[128,64,start,64,0,0,0,0],'Strict pre/post CSR ledger')
    require([len(snapshots[n]) for n in snapshots]==[24,384,384,384],'All snapshots complete and no extra bytes')
    require(int.from_bytes(data('mc_init_vl',8),'little')==128 and
            data('g75_result',8)==(1905).to_bytes(4,'little')+bytes(4) and
            data('num_failed',4)==bytes(4) and data('mc_checks',4)==(1905).to_bytes(4,'little') and
            data('tohost',8)==(1).to_bytes(8,'little'),'Complete1905-check selfcheck and terminal')
    return dict(checks=1905,cases=3,defined_mask_bits=192,mask_tail_bits_not_compared=3*960,
                whole_source_register_bytes=768,whole_xor_register_bytes=384,
                unknown_active_bits_skipped=0,explicit_VRF_writers=12,retirements=len(commits))


def prepare(out):
    require(out.parent==OUT and not out.exists(),'Fresh independent software-only output')
    plan=life.read_bound(PLAN,PLAN_SHA); pins=dict(plan['source_pins']); pins[str(PLAN)]=PLAN_SHA
    life.check(pins)
    binding,bp=target_binding(); pins=life.merge_pins(pins,bp)
    command=json.loads(template.TEMPLATE.read_bytes())
    command=[str(APP) if a.endswith('/vgap99_csr_satp_mprv.c') else str(out/'input.elf') if a.endswith('/input.elf') else a
             for a in command]+['-fno-unroll-loops','-mno-implicit-float']
    for p in (APP,template.TEMPLATE,template.START,ROOT/'verification/tests/gap75.ld',Path(__file__),
              Path(__file__).with_name('test_preflight_mask_compare_restart785.py'),Path(mature.__file__),
              Path(template.__file__),Path(build.__file__),Path(mature.old.rvc.__file__),Path(command[0]),
              build.SPIKE,build.LLVM/'llvm-objdump',build.LLVM/'llvm-readelf'):
        pins[str(p.resolve())]=life.digest(p)
    life.check(pins); out.mkdir(); life.save(out/'target-binding785.json',binding); life.save(out/'compile-command.json',command)
    with (out/'build.log').open('x') as stream:
        subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=120,check=True)
    with (out/'input.elf').open('rb') as stream:
        segments=[(p['p_paddr'],p['p_paddr']+p['p_memsz']) for p in ELFFile(stream).iter_segments() if p['p_type']=='PT_LOAD']
    require(segments and all(0x80000000<=a<b<=0x8003f000 for a,b in segments),'Frozen RAM/stack envelope')
    symbols={n:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',n) for n in SYMBOLS}
    require(symbols['tohost']==0x80001000,'Frozen tohost ABI')
    dis=subprocess.check_output([str(build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],text=True,timeout=30)
    (out/'disassembly.txt').write_text(dis); vector=linked(dis)
    spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
           '-m0x80000000:0x200000','-l','--log-commits',str(out/'input.elf')]
    life.save(out/'spike-command.json',spike)
    with (out/'spike.trace').open('x') as stream:
        completed=subprocess.run(spike,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    life.save(out/'spike-terminal.json',dict(returncode=completed.returncode))
    require(completed.returncode==0,'Spike rejected or software oracle failed: HOLD_NOT_DUT_FAILURE')
    counts=validate(out/'spike.trace',symbols)
    counts['runtime']=template.runtime(build.parse_spike_commits(out/'spike.trace'),symbols,segments)
    life.check(pins); pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
    result=dict(status='MASK_COMPARE_RESTART_HOST_SPIKE_PASS_NOT_DUT',input_pins=pins,symbols=symbols,
                ELF=str(out/'input.elf'),reference=str(out/'spike.trace'),counts=counts,baseline=binding,
                static_vector_instructions=vector,tail_policy='Only64 defined mask bits exported; tail never enters scalar checks',
                VCS_started=False,coverage_admitted=False,DUT_launch_authorized=False)
    life.save(out/'preflight.json',result)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight.json'),ELF_sha=life.digest(out/'input.elf'),
                         counts=counts,baseline=binding['status'],VCS_started=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    try: prepare(out)
    except Exception as error:
        if out.exists(): life.save(out/'failure.json',dict(error=str(error),no_retry=True,VCS_started=False))
        raise
