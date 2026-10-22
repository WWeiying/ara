"""Strict known-tail/SLDU supersession of the preserved byte-count HOLD."""
import argparse
from pathlib import Path
from types import FunctionType
import shlex
import qualify_sv39_alias770_terminal as prior

life,require=prior.life,prior.require
OLD_PLAN=life.OUT/'sv39-alias770-terminal-plan-agent-20261007-01/plan.json'
OLD_SEAL='0c74a1f5374871867491fcde6d9f771707a3a4129fafa3eb8126ffc43e7c486f'
DISPATCH=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'


def source_contract(text):
    statements=('maintenance_req.emul = LMUL_1;',"maintenance_req.vstart = '0;",
        'maintenance_req.vs2           = vs_buffer_q;', 'maintenance_req.eew_vs2       = eew_old_buffer_q;',
        'maintenance_req.vd            = vs_buffer_q;', 'maintenance_req.op            = ara_pkg::VSLIDEDOWN;',
        "maintenance_req.stride        = '0;", "maintenance_req.vm            = 1'b1;",
        'maintenance_req.vtype.vsew    = eew_new_buffer_q;',
        'maintenance_req.vl            = VLENB >> maintenance_req.vtype.vsew;')
    start=text.index('RESHUFFLE: begin');block=text[start:]
    require(all(s in block for s in statements),'Frozen source-derived full unmasked128-byte reshuffle')
    return dict(snapshot=str(DISPATCH),statements=list(statements),source_lines='1519..1560',
        derivation='VLEN1024/VLENB128; full unmasked vreg reshuffle at each known EW8->EW64 destination change; active VL8*8=64. Only two first changes v8/v16. Source3 is frozen SLDU grant.')


def scalar_memory_exact(rows,reference):
    expected=[];started=False
    for c in reference:
        if c.pc==0x80000000:started=True
        if not started:continue
        expected.append(c)
        if (0x80001000,1) in c.memory_accesses:break
    retired=[r for r in rows if r['event']=='retire' and not int(r['trap'])]
    require(len(retired)==len(expected),'Full scalar memory instruction population')
    accesses=compressed=0
    for r,c in zip(retired,expected):
        require((int(r['pc'],16),int(r['insn'],16))==(c.pc,c.instruction),'Scalar memory instruction identity')
        rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        access=prior.common.scalar_memory(c.instruction)
        if access is None:
            require(not rm and not wm,'Unmodeled scalar memory effect');continue
        kind,width=access
        require(kind in ('read','write') and len(c.memory_accesses)==1,'Exact scalar memory model')
        address,value=c.memory_accesses[0];mask=((1<<width)-1)<<(address&7)
        require(int(r['mem_addr'],16)==address and address%width==0 and
            rm==(mask if kind=='read' else 0) and wm==(mask if kind=='write' else 0),'Scalar memory address/mask')
        if kind=='write':
            require(value is not None and (int(r['mem_wdata'],16)&((1<<(width*8))-1))==
                (value&((1<<(width*8))-1)),'Scalar store value including compressed')
        else:require(value is None,'Scalar read reference shape')
        accesses+=1;compressed+=int(c.instruction&3!=3)
    return dict(instructions=len(expected),scalar_memory_accesses=accesses,
                compressed_memory_accesses=compressed,unmodeled_memory_effects=0)


def scalar_exact(result,reference,symbols):
    prior.scalar_exact(result,reference,symbols)
    rows=prior.common.read_csv((prior.RUN/'commit_trace.csv').read_bytes(),prior.common.COMMIT_FIELDS)
    result['complete_scalar_memory_postaudit']=scalar_memory_exact(rows,reference)


def writer_shape(reference):
    writers=[c for c in reference if c.vector_writes]
    require(len(writers)==55 and [c.vector_vl for c in writers]==[1024]*4+[8]*51 and
        [c.vector_sew for c in writers]==[8]*4+[64]*51 and
        all(c.vector_vstart==0 for c in writers),'Exact frozen seed/three-phase writer shape')
    require(writers[4].pc!=writers[5].pc and all(c.pc==writers[5].pc for c in writers[5:] if
        c.instruction&0x7f==7),'Exact first VMV/load maintenance owners')
    return writers


def intervals(reference):
    writers=writer_shape(reference);layout={};result=[]
    for c in writers:
        regs=sorted(c.vector_writes);active=c.vector_vl*c.vector_sew//8
        changed=[r for r in regs if r in layout and layout[r]!=c.vector_sew]
        # Frozen dispatcher RESHUFFLE1519: LMUL1, vstart0, vm1,
        # VSLIDEDOWN stride0, vl=VLENB>>vsew: exactly128 bytes per changed vreg.
        require(not changed or (len(regs)==1 and c.vector_sew==64 and layout[regs[0]]==8),
                'Unexpected format conversion shape')
        maintenance=128*len(changed)
        result.append(dict(active=active,maintenance=maintenance,
                           merged=128 if changed else active,changed=changed))
        layout.update({r:c.vector_sew for r in regs})
    require([i for i,r in enumerate(result) if r['changed']]==[4,5],'Exact source-derived maintenance owners')
    return result


def vector_exact(result,reference):
    writers=writer_shape(reference)
    shapes=intervals(reference)
    fixed=dict(status='PASS',compared_instructions=len(writers),compared_bytes=sum(r['merged'] for r in shapes),
        skipped_unknown_bytes=0,non_bit_exact_instructions=0,nr_lanes=4,vlen_bits=1024,
        selected_index=None,stopped_at_spike_index=None,trapped_requests=[],first_mismatch=None,
        unobservable_instructions=0,incomplete_requests=[],unretired_requests=[])
    for k,v in fixed.items():require(k in result and type(result[k]) is type(v) and result[k]==v,
                                    'Strict active/known-tail vector gate: '+k)
    records=result['instructions'];sizes=[r['merged'] for r in shapes]
    require(len(records)==55 and [(int(r['pc'],16),int(r['instruction'],16),r['compared_bytes']) for r in records]==
        [(c.pc,c.instruction,size) for c,size in zip(writers,sizes)],'Exact55 writer identities/byte populations')
    require(all(r['status']=='PASS' and r['skipped_unknown_bytes']==r['unknown_write_bytes']==r['mismatch_count']==0
        and r['first_mismatch'] is None for r in records),'Unknown/mismatching vector record')


def native_exact(activities,mapping,reference):
    writers=writer_shape(reference);index={id(c):i for i,c in enumerate(writers)}
    shapes=intervals(reference)
    wanted={s:reference[i] for s,i in mapping.items() if reference[i].vector_writes}
    require(len(wanted)==55 and {s for s,a in activities.items() if a.writes}==set(wanted),'Native writer population')
    prestate={};before={}
    for c in reference:
        if c.vector_writes:before[id(c)]=dict(prestate);prestate.update(c.vector_writes)
    maintained=[];normal_total=0;maintenance_total=0
    for seq,c in wanted.items():
        ordinal=index[id(c)];a=activities[seq]
        require(a.instruction==c.instruction,'Native instruction owner')
        ordinary_source=4 if c.instruction&0x7f==7 else 0
        ordinary=[];maintenance=[];seen=set()
        for w in a.writes:
            require(w.arch_seq==seq and w.instruction==c.instruction and w.known_be==255 and
                w.be==255 and w.eew==(0 if ordinal<4 else 3) and 0<=w.lane<4 and
                w.source in (ordinary_source,3),'Exact native source/EEW/known full-byte writes')
            key=w.source,w.addr,w.lane
            require(key not in seen,'Duplicate within native source');seen.add(key)
            (maintenance if w.source==3 else ordinary).append(w)
        def bytes_of(writes):return {k:v for k,(v,_) in prior.vc._architectural_bytes(writes,4,1024).items()}
        active=c.vector_vl*c.vector_sew//8;start=min(c.vector_writes)
        expect={(r,b):(v>>(8*b))&255 for r,v in c.vector_writes.items() for b in range(128)
                if (r-start)*128+b<active}
        require(bytes_of(ordinary)==expect,'Full active result bytes differ/missing/extra')
        normal_total+=len(expect)
        if shapes[ordinal]['maintenance']:
            require(sorted(c.vector_writes)==[8 if ordinal==4 else 16] and len(maintenance)==16,
                    'Only exact first v8/v16 known-seed maintenance')
            reg=start;state=before[id(c)]
            require(reg in state and state[reg]==int.from_bytes(b'\x5a'*128,'little'),'Known full independent pre-state')
            expect_pre={(reg,b):(state[reg]>>(8*b))&255 for b in range(128)}
            require(bytes_of(maintenance)==expect_pre and max(w.cycle for w in maintenance)<min(w.cycle for w in ordinary),
                    'SLDU full known pre-state/order differs')
            maintenance_total+=128;maintained.append(dict(arch_seq=seq,pc=hex(c.pc),register=reg,
                source=3,prestate_bytes=128,normal_source=ordinary_source,active_bytes=64))
        else:require(not maintenance,'Unexpected maintenance owner')
        union=bytes_of(a.writes)
        union_expect=dict(expect)
        if shapes[ordinal]['maintenance']:union_expect.update({(start,b):0x5a for b in range(64,128)})
        require(union==union_expect,'Exact post-state/known neutral tail')
    require(normal_total==7360 and maintenance_total==256,'Native complete active/maintenance byte totals')
    return dict(known_active_bytes=7360,known_maintenance_prestate_bytes=256,merged_compared_bytes=7488,
        accepted_write_bytes=7616,unknown_bytes=0,maintenance=maintained,full_tail_checked_by_3_VRF_snapshots=True)


def siminfo_exact(info,command):
    records=info.findall('srctest')
    require(len(records)==1,'Exact native srctest');s=records[0]
    require(shlex.split(s.get('cmdline',''))==command and s.get('workdir')==str(prior.RUN) and
        int(s.get('finishtime','0'))>int(s.get('starttime','0'))>0,'Native command/cwd/completed time')
    return dict(s.attrib)


def raw_gain(out):
    folders=list((prior.RUN/'code.vdb/snps/coverage/db/testdata').iterdir())
    require(len(folders)==1 and folders[0].name==prior.run.NAME and folders[0].is_dir(),
            'Exact one native candidate test')
    pins={}
    for name in ('siminfo.xml','vcmArguments.xml',*[m+'.verilog.data.xml' for m in (*prior.bitmap.METRICS,'tgl')]):
        p=folders[0]/name
        require(p.resolve()==p and not p.is_symlink() and p.stat().st_size>0,'Native end-member shape')
        pins[str(p)]=life.digest(p);prior.toggle.t.xml(p)
    info=siminfo_exact(prior.toggle.t.xml(folders[0]/'siminfo.xml'),prior.run.command(prior.RUN))
    result=prior.raw_gain(out);life.check(pins)
    result['native_end']=info;result['input_pins']=life.merge_pins(result['input_pins'],pins)
    return result


def prepare(out):
    plan=life.read_bound(OLD_PLAN,OLD_SEAL);life.check(plan['pins'])
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh successor plan')
    pins=life.merge_pins(plan['pins'],{str(OLD_PLAN):OLD_SEAL})
    book_path=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book=life.read_bound(book_path,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    for rel in ('hardware/tb/ara_commit_monitor.sv','hardware/src/lane/operand_requester.sv'):
        p=life.ROOT/rel;pins=life.merge_pins(pins,{str(p):book[str(p)]})
    pins=life.merge_pins(pins,{str(DISPATCH):book[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]})
    source=source_contract(DISPATCH.read_text())
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_qualify_sv39_alias770_known_tail.py'),book_path):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    failure=life.OUT/'sv39-alias770-terminal-qualified-agent-20261007-01/failure.json'
    pins=life.merge_pins(pins,{str(failure):life.digest(failure)})
    life.check(pins);out.mkdir();record=dict(plan,pins=pins,
        maintenance_source_contract=source,
        supersession='Exact two SLDU known-seed128 maintenance owners; active64/neutral tail, no skip/unknown. Add all compressed scalar memory address/mask/data checks. Original HOLD preserved.')
    life.save(out/'plan.json',record);print('PLAN',life.digest(out/'plan.json'))


def collect(plan,seal,out):
    bound=life.read_bound(plan,seal)
    require(str(Path(__file__).resolve()) in bound['pins'],'Successor implementation must be pinned')
    fn=FunctionType(prior.collect.__code__,dict(prior.collect.__globals__,scalar_exact=scalar_exact,
        vector_exact=vector_exact,native_exact=native_exact,raw_gain=raw_gain))
    return fn(plan,seal,out)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','verify','collect'))
    p.add_argument('--output',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--seal');a=p.parse_args()
    if a.action=='prepare':prepare(a.output.absolute())
    elif a.action=='verify':life.check(life.read_bound(a.plan,a.seal)['pins']);print('VERIFY_PASS')
    else:collect(a.plan,a.seal,a.output.absolute())
