"""Offline strict qualification and742 delta; never run EDA or admit."""
import argparse
from collections import Counter
import json
from pathlib import Path

import rvv_lmul8_payload_walk as runner
import collect_opivx_vsbc_strict as common
import coverage_bitmap_delta as bitmap
from qualify_store_fault_flush_terminal import elf_instruction
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log

life,require=runner.life,runner.require

def lifecycle(rows,vectors):
    starts,pending,alloc,done={}, {}, Counter(),Counter()
    req,resp=Counter(),Counter()
    retired=[r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retired]==list(range(len(retired))),'Retirement gap')
    for r in rows:
        event,seq,tid=r['event'],int(r['order']),int(r['trans_id'])
        require(int(r['trap'])==0,'Unexpected trap/response exception')
        if event=='arch_start':
            require(seq not in starts and tid not in pending,'Duplicate live request')
            starts[seq]=r;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1],'Unknown/duplicate request')
            owner=pending[tid][0]
            require(r['insn']==starts[owner]['insn'],'Request opcode mismatch')
            pending[tid][1]=True;req[owner]+=1
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1],'Unowned response')
            resp[pending.pop(tid)[0]]+=1
        elif event in ('uop_alloc','uop_done'):
            require(seq in starts and r['insn']==starts[seq]['insn'],'Backend owner/opcode mismatch')
            (alloc if event=='uop_alloc' else done)[seq,int(r['port'])]+=1
        else:require(event=='retire','Unknown commit event')
    require(starts and not pending and req==resp==Counter(starts.keys()) and alloc==done and alloc,
            'Incomplete/no backend lifecycle')
    va,vd=Counter(),Counter()
    for r in vectors:
        seq,event=int(r['arch_seq']),r['event']
        require(int(r['nr_lanes'])==4 and int(r['vlen_bits'])==1024,'Vector config drift')
        if event=='config':
            require(int(r['cycle'])==0 and int(r['insn'],16)==0 and
                    int(r['be'],16)==0 and int(r['wdata'],16)==0,
                    'Invalid initial observer configuration')
            continue
        require(seq in starts and r['insn']==starts[seq]['insn'],'Native vector owner mismatch')
        if event in ('alloc','done'):(va if event=='alloc' else vd)[seq,int(r['vid'])]+=1
        else:require(event in ('config','write'),'Unknown vector event')
    require(va==vd==alloc,'Commit/native backend conservation differs')
    return dict(requests=sum(req.values()),responses=sum(resp.values()),exceptions=0,backend=sum(alloc.values()))

def footprint(rows,symbols,elf):
    wanted={}
    def add(name,data):
        wanted.update({symbols[name]+i:b for i,b in enumerate(data)})
    for kind in ('source','shift','narrow','wide'):
        add('pw_'+kind,b''.join(runner.expected(cell,kind) for cell in range(2)))
    add('pw_control',b''.join(runner.control_expected(cell) for cell in range(3)))
    add('pw_bytes',bytes([0xa5]*16+[(i^(i//8))&255 for i in range(1024)]+[0xa5]*16))
    add('pw_mask',bytes([0xaa]*128))
    required=set(wanted);observed={};reads=set()
    values=[]
    for cell,vl in enumerate((64,128)):
        values += [vl,26+cell,0,vl,17+cell,0,vl,26+cell,0]
    add('pw_csr',b''.join(x.to_bytes(8,'little') for x in values))
    add('pw_control_csr',b''.join(x.to_bytes(8,'little') for vl in (3,33,1024) for x in (vl,3,0)))
    add('g75_result',runner.CHECKS.to_bytes(4,'little')+bytes(4));add('num_failed',bytes(4))
    terminals=[]
    for r in rows:
        if r['event']!='retire':continue
        pc,word=int(r['pc'],16),int(r['insn'],16)
        require(elf_instruction(elf,pc,4)==word,'Retirement instruction/ELF mismatch')
        access=common.scalar_memory(word)
        rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        if access is None:
            require(not rm and not wm,'Unknown scalar memory effect');continue
        kind,size=access;a=int(r['mem_addr'],16);mask=((1<<size)-1)<<(a&7)
        require(a%size==0 and rm==(mask if kind=='read' else 0) and wm==(mask if kind=='write' else 0),
                'Scalar memory alignment/mask mismatch')
        v=int(r['rd_wdata'] if kind=='read' else r['mem_wdata'],16)&((1<<(8*size))-1)
        if a==symbols['tohost'] and kind=='write':terminals.append((r,v))
        for j in range(size):
            if a+j in wanted:
                observed[a+j]=v>>(8*j)&255
                if kind=='read':reads.add(a+j)
    retired=[r for r in rows if r['event']=='retire']
    require(retired and terminals==[(retired[-1],1)],'Terminal is not final exact tohost')
    require(required<=reads and observed==wanted,'Incomplete/mismatched independent footprint')
    return dict(strict_snapshot_bytes=len(required),csr_values=27,checks=runner.CHECKS,failed=0)

def collect(run,prepared_seal,out):
    require(not out.exists() and out.parent==life.OUT,'Fresh qualification output only')
    side=run.with_name(run.name+'.prepared.json');record=life.read_bound(side,prepared_seal)
    require(record['case']==runner.NAME and record['timeout_s']==600,'Wrong prepared case/budget')
    life.check(record['pins'])
    status=json.loads((run/'simulation-status.json').read_bytes())
    started=json.loads((run/'started.json').read_bytes())
    require(status['status']=='SIMULATION_EXITED_NOT_ADMITTED' and status['returncode']==0 and
            status['timeout'] is False and status['case']==runner.NAME,'Not successful bounded terminal')
    require(json.loads((run/'manifest.json').read_bytes())==record and started['command']==record['command'] and
            started['pid']==started['process_group']==status['pid'] and started['budget_s']==600 and
            started['elf_sha256']==record['elf_sha256'] and started['image_sha256']==runner.IMAGE_SHA,
            'Actual command/process/image mismatch')
    pre=Path(record['preflight']);symbols=json.loads((pre/'symbols.json').read_bytes())
    commits=runner.shared.parse_spike_commits(pre/'spike.log')
    rows=common.read_csv((run/'commit_trace.csv').read_bytes(),common.COMMIT_FIELDS)
    vectors=common.read_csv((run/'vector_trace.csv').read_bytes(),common.VECTOR_FIELDS)
    control=lifecycle(rows,vectors)
    require(not check_contract_log(run/'run.vcs.log'),'UVM/protocol/CoreSUCCESS gate failed')
    memory=footprint(rows,symbols,(pre/'input.elf').read_bytes())
    scalar=common.spike_trace.compare_commit_prefix(pre/'spike.log',run/'commit_trace.csv',0x80000000,
        terminal_tohost_address=symbols['tohost'],rvfi_store_data_layout='unshifted')
    common.scalar_exact(scalar,common.reference_counts(commits,symbols))
    vector=compare_vector_commits(pre/'spike.log',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
    require(vector['status']=='PASS' and vector['skipped_unknown_bytes']==0 and
            vector['compared_instructions']>=24 and vector['compared_bytes']>0,'Incomplete strict vector comparison')
    pins=dict(record['pins']);pins[str(side)]=prepared_seal
    files=[p for p in run.rglob('*') if p.is_file()]
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    out.mkdir();inputs=out/'singleton-inputs.txt'
    inputs.write_text(str(life.IMAGE)+'.vdb\n'+str(run/'code.vdb')+'\n')
    single=bitmap.collect(inputs);admission=life.read_bound(runner.BASE/'admission-manifest.json',runner.BASE_SHA)
    before=life.read_bound(runner.BASE/'combined-bits.json',admission['output_pins'][str(runner.BASE/'combined-bits.json')])
    combined=bitmap.combine(before,single)
    require(combined['tests']==before['tests']+[str(run/'code.vdb')],'Exact742 prefix/unique successor mismatch')
    raw=bitmap.delta(before,combined)
    targets=json.loads((pre/'target-before742.json').read_bytes());scopes=sorted({x['scope'] for x in targets})
    tglfiles=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(tglfiles)==1,'Missing native Toggle test')
    tgl,_=runner.toggle.rows(tglfiles[0],scopes);changes=[]
    for x in targets:
        r=tgl[x['scope']];bits=bin(int(r['bits'],16))[2:].zfill(r['width'])
        sample=bits[x['raw_offset']:x['raw_offset']+len(x['before742'])]
        fresh=[i for i,(a,b) in enumerate(zip(x['before742'],sample)) if a=='0' and b=='1']
        if fresh:changes.append(dict(x,singleton=sample,fresh_relative_positions=fresh))
    outputs=dict(scalar=scalar,vector=vector,lifecycle=control,footprint=memory,
                 singleton=single,combined=combined,raw_delta=raw,target_toggle_gain=changes)
    for name,value in outputs.items():life.save(out/(name+'.json'),value)
    pins[str(Path(__file__).resolve())]=life.digest(Path(__file__))
    life.check(pins)
    result=dict(status='STRICT_FUNCTIONAL_PASS_RAW_DIAGNOSTIC_NOT_ADMITTED',case=runner.NAME,
        pins=pins,outputs={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},
        baseline=742,primary_data_zero_claim=False,coverage_admitted=False,application_approval=False)
    life.save(out/'qualification.json',result)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'qualification.json'),target_fields_gained=len(changes))))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True)
    ap.add_argument('--prepared-seal',required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();collect(a.run.resolve(),a.prepared_seal,a.output.resolve())
