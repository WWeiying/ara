"""Known old-vd/adjacent-register discriminator; software-only successor."""
import argparse
from pathlib import Path
from types import FunctionType
import preflight_mask_compare_restart785 as old

life, require, build, template = old.life, old.require, old.build, old.template
ROOT, OUT, STARTS = old.ROOT, old.OUT, old.STARTS
APP = ROOT/'apps/riscv-tests/isa/rv64uv/mask_compare_restart_known_old.c'
BASE = OUT/'qbs-two-phase-m4-offline-admitted786-agent-20261008-01'
BASE_SHA = '384c2b5b364f41a49968aac913b8e0904b5fe2f83c5af818af3afe535d864904'
SYMBOLS = old.SYMBOLS + ('mc_old','mc_adjacent','mc_load2','mc_v2_read')
source_bytes = old.source_bytes


def old_bytes(source):
    require(source in (0,1), 'Exact old-register identity')
    return bytes(((37*i+0x53)^((i>>3)*0x31)^(source*0xA6))&255 for i in range(128))


def mask_gold(start):
    require(start in STARTS, 'Exact restart case')
    previous=int.from_bytes(old_bytes(0), 'little')
    a,b=source_bytes(0),source_bytes(1)
    return sum(((previous>>i&1) if i<start else int(a[i]<b[i]))<<i for i in range(64)).to_bytes(8,'little')


def target_binding():
    binding,pins=old.target_binding()
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    lp=BASE/'combined-inputs.txt'
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,
        str(lp):manifest['output_pins'][str(lp)]})
    life.check(pins)
    ledger=lp.read_text().splitlines()
    require(manifest['coverage_admitted'] is True and manifest['baseline']==str(old.BASE) and
        manifest['baseline_seal']==old.BASE_SHA and len(ledger)==len(set(ledger))==787 and
        ledger[:-1]==(old.BASE/'combined-inputs.txt').read_text().splitlines(), 'Exact786 prefix')
    require(binding['whole_field_zero_after785'], 'No guessed bit mapping after prior hits')
    files=list((Path(ledger[-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1, 'Unique786 suffix')
    rows,h=old.inventory.t.rows(files[0],{t['scope'] for t in binding['targets']})
    require(manifest['input_pins'][str(files[0])]==h, 'Sealed786 native bytes')
    pins[str(files[0])]=h
    for t in binding['targets']:
        row=rows[t['scope']]
        require(row['checksum']==t['checksum'], 'Exact compiled requester')
        t['missing_coordinates']=[i for i in t['original783_coordinates']
            if not(int(row['bits'],16)>>(row['width']-1-i)&1)]
        t['logical_bits']=[0,1,2] if len(t['missing_coordinates'])==22 else None
    zero=all(len(t['missing_coordinates'])==22 for t in binding['targets'])
    binding.update(population=786,manifest_sha=BASE_SHA,whole_field_zero_after786=zero,
        proposed_target_directions=48 if zero else None,
        status='FRESH_WHOLE_FIELD_ZERO' if zero else 'HOLD_REQUIRES_NATIVE_LOGICAL_BINDING')
    for p in (Path(old.__file__),Path(__file__),Path(__file__).with_name('test_preflight_mask_compare_restart_known786.py')):
        pins[str(p.resolve())]=life.digest(p)
    life.check(pins)
    return binding,pins


def linked(dis):
    import re
    vector=[m for m in re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{8}|[0-9a-f]{4}|(?:[0-9a-f]{2}\s+){1,3}[0-9a-f]{2})\s+([\w.]+)',dis,re.M) if m.startswith('v')]
    wanted=['vsetvli']*3+['vle8.v']*4+['vmv.v.i','vmsltu.vv','vsm.v','vxor.vv']+['vs1r.v']*4
    require(sorted(vector)==sorted(wanted), 'Only15 explicit RVV operations: '+repr(vector))
    return vector


def validate(path,symbols):
    commits=build.parse_spike_commits(path)
    require('exception ' not in path.read_text() and not any(c.pc==symbols['trap_fail'] for c in commits),
            'Unexpected Spike trap; HOLD_NOT_DUT_FAILURE')
    names=('mc_init_a','mc_init_b','mc_clear24','mc_load2','mc_clear1','mc_compare','mc_xor')
    writes={n:[] for n in names}
    snapshots={n:{} for n in ('mc_mask_store','mc_a_read','mc_b_read','mc_x_read','mc_v2_read')}
    memory={}
    for c in commits:
        for n in writes:
            if c.pc==symbols[n]: writes[n].append(c)
        for address,value in c.memory_accesses:
            if value is None: continue
            decoded=old.mature.old.rvc.decode(c.instruction)
            if decoded:
                require(decoded['kind']=='write','No write effect on scalar load'); width=decoded['size']
            elif c.instruction&0x7f==0x23:
                f3=c.instruction>>12&7; require(f3<=3,'Known scalar store'); width=1<<f3
            else:
                require(c.instruction&0x7f==0x27,'Known vector store'); width=1
            for i in range(width): memory[address+i]=value>>(8*i)&255
            for n,observed in snapshots.items():
                if c.pc==symbols[n]:
                    require(width==1 and address not in observed,'Unique snapshot byte')
                    observed[address]=value
    def data(name,size,offset=0):
        start=symbols[name]+offset
        require(all(start+i in memory for i in range(size)), 'Missing witness '+name)
        return bytes(memory[start+i] for i in range(size))
    guard=bytes([0x96])*16
    for s in (0,1):
        require(data('mc_sources',160,s*160)==guard+source_bytes(s)+guard,'Immutable source/guards')
        require(data('mc_old',160,s*160)==guard+old_bytes(s)+guard,'Immutable old-vd/adjacent seed')
    require([len(writes[n]) for n in names]==[1,1,1,1,3,3,3] and
        sum(bool(c.vector_writes) for c in commits)==13,'All13 writers; no implicit RVV')
    for s,n in enumerate(('mc_init_a','mc_init_b')):
        require(writes[n][0].vector_writes=={8 if s==0 else 16:int.from_bytes(source_bytes(s),'little')},'Full source initialization')
    require(writes['mc_clear24'][0].vector_writes=={24:0} and
        writes['mc_load2'][0].vector_writes=={2:int.from_bytes(old_bytes(1),'little')} and
        all(c.vector_writes=={1:int.from_bytes(old_bytes(0),'little')} for c in writes['mc_clear1']),
        'Full128B v1/v2 initialization; no unknown old data')
    xor=bytes(a^b for a,b in zip(source_bytes(0)[:64],source_bytes(1)[:64]))+bytes(64)
    for case,start in enumerate(STARTS):
        c=writes['mc_compare'][case]
        require(list(c.vector_writes)==[1] and c.vector_writes[1]&((1<<64)-1)==int.from_bytes(mask_gold(start),'little'),
            'Prestart preserved and active strict independent gold')
        require(writes['mc_xor'][case].vector_writes=={24:int.from_bytes(xor,'little')},'Strict restored consumer')
        require(data('mc_masks',40,case*40)==guard+mask_gold(start)+guard,'Defined64 mask bits/guards; no tail consumption')
        for s in (0,1):
            require(data('mc_readback',160,(case*2+s)*160)==guard+source_bytes(s)+guard,'Source register unchanged')
        require(data('mc_adjacent',160,case*160)==guard+old_bytes(1)+guard,'Adjacent v2 unchanged/guards')
        require(data('mc_xors',160,case*160)==guard+xor+guard,'Whole xor/guards')
        ledger=[int.from_bytes(data('mc_ledger',8,case*64+i*8),'little') for i in range(8)]
        require(ledger==[128,64,start,64,0,0,0,0],'Exact CSR ledger')
    require([len(snapshots[n]) for n in snapshots]==[24,384,384,384,384],'All1536 source/xor/v2 snapshot bytes plus24mask bytes')
    require(data('mc_init_vl',8)==(128).to_bytes(8,'little') and
        data('g75_result',8)==(2705).to_bytes(4,'little')+bytes(4) and
        data('num_failed',4)==bytes(4) and data('mc_checks',4)==(2705).to_bytes(4,'little') and
        data('tohost',8)==(1).to_bytes(8,'little'),'Complete2705 checks/terminal')
    return dict(checks=2705,cases=3,defined_mask_bits=192,mask_tail_bits_not_compared=2880,
        whole_source_register_bytes=768,whole_xor_register_bytes=384,whole_adjacent_register_bytes=384,
        full_old_register_initialization_bytes=256,unknown_active_bits_skipped=0,
        explicit_VRF_writers=13,retirements=len(commits),DUT_result_claimed=False)


def prepare(out):
    # Reuse the frozen software compile/Spike lifecycle with a private namespace.
    ns=dict(old.prepare.__globals__,APP=APP,SYMBOLS=SYMBOLS,__file__=__file__,
        target_binding=target_binding,linked=linked,validate=validate)
    return FunctionType(old.prepare.__code__,ns,argdefs=old.prepare.__defaults__)(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    try: prepare(out)
    except Exception as error:
        if out.exists(): life.save(out/'failure.json',dict(error=str(error),no_retry=True,VCS_started=False))
        raise
