#!/usr/bin/env python3
"""Strict original integer merge98 CSV gate; no direct vector-payload claims."""
from collections import Counter
import csv
from pathlib import Path
import re
import sys
import subprocess

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'merge_original_prefix98_prepare01'
sys.path.insert(0, str(REF))
import reference_check as source
from reference_check import require, NAME, CAP, BOUND
sys.path.insert(0, str(HERE.parent / 'gather_repair05'))
import regression as common

read, sha = common.read, common.sha
READY_SHA = '8381b90ee089c90be273faca67b8096f802f628f655fd5756a186ef57b3ed175'
VETO = re.compile(common.BAD.pattern + r'|\bRVV_PERMUTE_DETAIL\b|\b(?:FAIL|FAILED|ABORT|ABORTED|TRAP|MISMATCH|DETAIL)\b'
                  r'|RVV_PERMUTE_PASS|RVV_MERGE_PREFIX_FAIL', re.I)


def specification(elf):
    require(sha(REF/'READY.json') == READY_SHA and sha(elf) ==
            read(REF/'source_elf_proof.json')['soc_elf']['sha256'], 'Reference/ELF drift')
    routine = source.instructions(elf, NAME + '_op_4')
    proof = read(REF / 'source_elf_proof.json')
    require(routine == proof['soc_routine'] and len(routine) == 13 and
        [r['insn'] for r in routine] == [r['insn'] for r in proof['original_routine']], 'Original13 ELF drift')
    require(all('e16,m8,tu,mu' in routine[i]['text'] for i in (0, 5, 10)) and
            routine[8]['insn'] == '5c880c57', 'Unexpected actual SEW/LMUL/operation')
    addresses = {n: source.symbol(elf, n, source.OBJDUMP)[0]
                 for n in ('input', 'indices', 'indices16', 'predicate', 'output')}
    exit_code = source.instructions(elf, 'replay_exit')
    store, = [r for r in exit_code if r['text'].startswith('sd\t')]
    park, = [r for r in exit_code if r['pc'] > store['pc']]
    require(park['insn'] == 'a001' and park['text'].startswith('j\t'), 'Not original CTRL park')
    text = subprocess.check_output([str(source.OBJDUMP), '-d', str(elf)], text=True)
    code = {m[1]:dict(pc=int(m[1],16),insn=m[2],text=m[3]) for m in
            re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',text,re.M)}
    symbols = {n:source.symbol(elf,n,source.OBJDUMP)[0] for n in
               ('_start','trap_entry','main','text',NAME+'_main',NAME+'_capacity')}
    unused=[]
    for op in range(21):
        if op==4: continue
        rows=source.instructions(elf,NAME+'_op_'+str(op))
        require(len(rows)==13, 'Unused helper13')
        unused.append([rows[0]['pc'],rows[-1]['pc']+len(rows[-1]['insn'])//2])
    capacity=source.instructions(elf,NAME+'_capacity')
    require([r['insn'] for r in capacity]==['52fd','00b2f557','8082'], 'Original capacity3 e16m8')
    prelude=[r for r in code.values() if is_csr(int(r['insn'],16)) and
             (r['pc']<symbols['trap_entry'] or symbols['main']<=r['pc']<symbols['text'] or
              symbols[NAME+'_main']<=r['pc']<symbols[NAME+'_capacity'])]
    require(len(prelude)==7 and [r['insn'] for r in prelude[:5]]==
            ['30401073','30529073','3002a073','00305073','00805073'] and
            all(int(r['insn'],16)&~0xf80==0xc2202073 for r in prelude[5:]), 'Original seven startup/C CSR')
    encodings=dict(input='00e81023',indices='00f51023',indices16='00f59023',
        pred_clear='00068023',pred_pack='00f70023',output_init='00d71023',
        output_read='002a5683',guard0='fd07d783',guard1='0007d783',filter='20fc1963')
    sites={}
    for name,encoding in encodings.items():
        hits=[r for r in code.values() if r['insn']==encoding and
              symbols[NAME+'_main']<=r['pc']<symbols[NAME+'_capacity']]
        require(len(hits)==1,'Original source site: '+name)
        sites[name]=hits[0]['pc']
    return dict(sew=16, lmul=8, element_bytes=2, routine=routine, addresses=addresses,
                instructions=code, symbols=symbols, unused_ranges=unused, capacity=capacity,
                prelude=prelude, sites=sites, elf_sha256=sha(elf),
                exit_store=store, exit_address=0xd0000000, park=park)


def is_rvv(code):
    return code&127==0x57 or code&127 in (7,39) and (code>>12)&7 in (0,5,6,7)


def is_csr(code):
    return code&127==0x73 and (code>>12)&7!=0


def console_gate(text):
    require(not VETO.search(text), 'Raw failure/abort/parent-marker veto')
    lines = text.splitlines()
    for prefix, exact in (('RVV_MERGE_PREFIX_PASS', 'RVV_MERGE_PREFIX_PASS sew=16 cases=98 errors=0'),
            ('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN ' + NAME), ('BOARD_CASE_PASS', 'BOARD_CASE_PASS ' + NAME),
            ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS'),
            ('Core Test *** SUCCESS ***', 'Core Test *** SUCCESS *** (tohost = 0)')):
        require([s for s in lines if s.startswith(prefix)] == [exact], 'Missing/ambiguous oracle: ' + prefix)
    require('$finish' in text, 'Missing simulator finish')


def setup_events(spec, model, gold=None):
    a,s=spec['addresses'],spec['sites']
    if gold is None:
        for i in range(CAP):
            for n in ('input','indices','indices16'):
                yield s[n],a[n]+2*i,model[n][i],2
        return
    packed=[0]*128
    for i in range(128):
        yield s['pred_clear'],a['predicate']+i,0,1
    for i in range(CAP):
        if (gold['predicate'][i//8]>>(i%8))&1:
            packed[i//8]|=1<<(i%8)
            yield s['pred_pack'],a['predicate']+i//8,packed[i//8],1
    for i in range(CAP+2):
        yield s['output_init'],a['output']+2*i,91,2


def retirement(rows, spec, model):
    routine,a,sites=spec['routine'],spec['addresses'],spec['sites']
    lookup={r['pc']:i for i,r in enumerate(routine)}
    cap_lookup={r['pc']:i for i,r in enumerate(spec['capacity'])}
    prelude=spec['prelude']
    regs,memory={0:0},{}
    counts,rvv_counts,site_counts=Counter(),Counter(),Counter()
    calls=[]
    step=cap_steps=csr_steps=retired=total=parked=setup_pos=0
    last_cycle=-1
    current=None
    exited=False
    initial=list(setup_events(spec,model))
    initial_pos=0
    events=list(setup_events(spec,model,model['rows'][0]))
    setup_pcs={sites[n] for n in ('input','indices','indices16','pred_clear','pred_pack','output_init')}
    oracle_pcs={sites[n] for n in ('output_read','guard0','guard1')}
    areas=[(a[n],a[n]+size) for n,size in
           [('input',1024),('indices',1024),('indices16',1024),('predicate',128),('output',1028)]]

    def finish():
        if current is not None:
            require(step==0 and current['reads']==list(range(1,CAP+1))+[0,CAP+1],
                    'Missing full ordered oracle/guards/asm')
            require(current.get('returned_vstart')==0,'Missing returned vstart')

    for line,row in enumerate(rows,2):
        total+=1
        cycle=int(row['cycle'])
        require(cycle>=last_cycle and row['event']!='cvx_exception','Cycle reversal/exception')
        last_cycle=cycle
        if row['event']!='retire': continue
        require(int(row['order'])==retired and int(row['trap'])==0,'Retirement order/trap')
        retired+=1
        pc,insn=int(row['pc'],16),int(row['insn'],16)
        rd,value=int(row['rd']),int(row['rd_wdata'],16)
        address,rmask,wmask,wdata=(int(row[n],16) for n in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        actual=spec['instructions'].get(f'{pc:x}')
        require(actual is not None and insn==int(actual['insn'],16),'Actual ELF PC/code')
        if exited:
            require(pc==spec['park']['pc'] and rd==rmask==wmask==0,'Post-exit non-original park')
            parked+=1
            continue
        require(not any(lo<=pc<hi for lo,hi in spec['unused_ranges']),'Unused helper complete PC range')
        require(pc!=spec['symbols']['trap_entry'],'Unexpected trap entry')
        if step:
            require(pc==routine[step]['pc'],'Noncontiguous13 helper')
        if 0<cap_steps<3:
            require(pc==spec['capacity'][cap_steps]['pc'],'Noncontiguous capacity3')
        if pc in cap_lookup:
            i=cap_lookup[pc]
            require(i==cap_steps and csr_steps==6 and not calls,'Capacity phase/once')
            if i==0: require((rd,value)==(5,(1<<64)-1),'Capacity AVL')
            if i==1: require((rd,value)==(10,CAP) and regs.get(5)==(1<<64)-1,'Capacity VLMAX')
            cap_steps+=1
        if is_csr(insn) and pc not in lookup:
            require(csr_steps<7 and pc==prelude[csr_steps]['pc'] and not calls,
                    'CSR outside original phase/once')
            require(cap_steps==(3 if csr_steps==6 else 0),'CSR/capacity source phase')
            if csr_steps<5:
                src=(insn>>15)&31
                operand=src if (insn>>12)&4 else regs.get(src)
                require(rd==0 and operand==[0,spec['symbols']['trap_entry'],0x6600,0,0][csr_steps],
                        'Bootstrap CSR operand')
            else:
                require(rd==(insn>>7)&31 and value==128,'Original vlenb result')
            csr_steps+=1
        if is_rvv(insn):
            require(pc in lookup or pc==spec['capacity'][1]['pc'],'RVV outside original window')
            rvv_counts[pc]+=1
        if pc==sites['filter']:
            site_counts['filter']+=1
            require(site_counts['filter']<=3584+98,'Extra original filter iteration')
        if pc in setup_pcs:
            require(step==0 and cap_steps==3 and csr_steps==7,'Setup phase')
            if initial_pos<len(initial):
                wanted=initial[initial_pos]
                initial_pos+=1
            else:
                finish()
                require(setup_pos<len(events),'Extra setup or missing next call')
                wanted=events[setup_pos]
                setup_pos+=1
            wp,wa,wv,width=wanted
            require(pc==wp and address==wa and wmask==((1<<width)-1)<<(address%8)
                    and wdata&((1<<(8*width))-1)==wv,'Original initialization order/value/BE')
            for b in range(width): memory[address+b]=(wdata>>(8*b))&255
            site_counts[next(n for n in sites if sites[n]==pc)]+=1
        elif wmask and insn&127!=0x27:
            require(not any(lo<=address<hi for lo,hi in areas) or
                    pc<spec['symbols']['trap_entry'] and not initial_pos,
                    'Unexpected scalar write into original arrays')
        if pc in lookup:
            i=lookup[pc]
            require(i==step and cap_steps==3 and csr_steps==7,'Original13 order/phase')
            if i==0:
                finish()
                j=len(calls)
                require(j<BOUND and initial_pos==len(initial) and setup_pos==len(events),
                        'Missing full setup or extra call')
                gold=model['rows'][j]
                require(site_counts['filter']==3584+j+1,'Original filtered-loop/count boundary')
                args=[a['input'],a['indices'],a['output']+2,gold['vl'],CAP,a['predicate'],0,gold['vstart']]
                require([regs.get(n) for n in range(10,18)]==args,'Actual original arguments')
                for n,values,width in [('input',model['input'],2),('indices',model['indices'],2),
                        ('indices16',model['indices16'],2),('predicate',gold['predicate'],1),('output',[91]*514,2)]:
                    for k,want in enumerate(values):
                        require([memory.get(a[n]+width*k+b) for b in range(width)]==
                                list(want.to_bytes(width,'little')),'Full original setup: '+n)
                current=dict(ordinal=j+1,original_tuple=gold['tuple'],reads=[],returned_vstart=None)
                calls.append(current)
            if i in (0,5,10):
                require((rd,value)==(5,gold['vl'] if i==5 else CAP),'Original vset return')
                require(regs.get(13 if i==5 else 14)==(gold['vl'] if i==5 else CAP),'Original vset AVL')
            if i==6: require((rd,value)==(28,0),'Unused original scalar move')
            if i==7: require(rd==0 and regs.get(17)==gold['vstart'],'Original vstart write operand')
            if i==8:
                require(regs.get(28)==0 and regs.get(17)==gold['vstart'],'Actual merge controls')
                current['target']=dict(pc=hex(pc),insn=routine[i]['insn'],cycle=cycle,retired=retired,csv_line=line)
            if i==9:
                require((rd,value)==(10,0),'Returned vstart nonzero')
                current['returned_vstart']=0
            if i==11: require(regs.get(12)==a['output']+2,'Full-capacity vector store pointer')
            counts[i]+=1
            step=(step+1)%13
        if pc in oracle_pcs:
            require(current is not None and step==0,'Oracle phase')
            k=len(current['reads'])
            sequence=list(range(1,CAP+1))+[0,CAP+1]
            require(k<len(sequence),'Duplicate oracle')
            index=sequence[k]
            expected_pc=sites['output_read'] if 1<=index<=CAP else sites['guard0' if index==0 else 'guard1']
            require(pc==expected_pc and address==a['output']+2*index and
                    rmask==3<<(address%8) and rd==(insn>>7)&31 and not wmask,'Original oracle PC/order/LHU/BE')
            want=91 if index in (0,CAP+1) else gold['output'][index-1]
            require(value==want,f'Merge full oracle mismatch call{len(calls)} index{index}')
            current['reads'].append(index)
            if len(current['reads'])==CAP+2:
                events=list(setup_events(spec,model,model['rows'][len(calls)])) if len(calls)<BOUND else []
                setup_pos=0
        elif rmask and a['output']<=address<a['output']+1028:
            require(pc in lookup,'Unexpected output read PC')
        if pc==spec['exit_store']['pc'] or address==spec['exit_address'] and wmask:
            require(pc==spec['exit_store']['pc'] and address==spec['exit_address'] and
                    wmask==255 and wdata==0,'Original CTRL exit0')
            finish()
            require(len(calls)==BOUND and step==0,'Incomplete calls at exit')
            exited=True
        if rd: regs[rd]=value
    expected_rvv={r['pc']:98 for r in routine if is_rvv(int(r['insn'],16))}
    expected_rvv[spec['capacity'][1]['pc']]=1
    require(dict(rvv_counts)==expected_rvv and cap_steps==3 and csr_steps==7,
            'Missing exact RVV/capacity/CSR')
    require(exited and len(calls)==BOUND and dict(counts)=={i:98 for i in range(13)},'Missing calls/asm/exit')
    finish()
    for call in calls: del call['reads']
    return dict(status='PASS_RAW_MERGE98_FULL_SOURCE_ORACLE',target_hits=98,calls=calls,
        routine_retire_counts=[counts[i] for i in range(13)],returned_vstart_zero=98,
        fullcap_checks=50176,guards=196,actual_output_scalar_loads=50372,
        initialization_counts=dict(site_counts),capacity_instructions=3,prelude_csr_instructions=7,
        unused_helper_retirements=0,rvv_retirements=sum(rvv_counts.values()),
        all_retired_pc_code_verified=True,csv_rows=total,csv_last_cycle=last_cycle,retired_rows=retired,
        post_exit_park_retired=parked,soc_ctrl_exit=0,exact_historical_stopped_tuple=None,
        vector_payload_scope='Actual scalar full oracle; no direct DUT vector-port/wave claim')


def artifacts(result, case, ledger, spec, validator):
    require(result.status == 'PASS' and result.name == NAME and not result.reason, 'Not exact case PASS')
    common.check_artifacts(result, case, ledger)
    for path in (result.artifact_dir/'console.log', result.artifact_dir/'work/run.vcs.log'):
        console_gate(path.read_text())
    path = result.artifact_dir/'commit_trace.csv'
    generic = validator(path)
    require(generic['cvx_exception_count'] == 0 and generic['rows'] > 0, 'Generic trace/exception')
    with path.open(newline='') as stream:
        raw = retirement(csv.DictReader(stream), spec, source.model())
    require((raw['csv_rows'], raw['csv_last_cycle'], raw['retired_rows']) ==
            (generic['rows'], generic['last_cycle'], generic['retire_count']), 'Independent trace counts differ')
    return dict(generic=generic, strict=raw, csv_sha256=sha(path))

