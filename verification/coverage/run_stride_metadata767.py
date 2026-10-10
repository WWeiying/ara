"""One VL1 full64 stride case: Spike preflight, bounded run, automatic strict audit."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import subprocess
from types import FunctionType, SimpleNamespace

from elftools.elf.elffile import ELFFile
import build_pure_war_preflight as resources
import precheck_stride_metadata766 as host
import run_pure_war_simulation as runner
import qualify_pure_war_parent_terminal as generic
import targeted_toggle_evidence_v2 as toggle
import coverage_bitmap_delta as bitmap

shared, common = resources.shared, generic.common
life, require = resources.life, resources.require
ROOT, OUT, NAME = life.ROOT, life.OUT, 'vgap_stride_metadata_full64'
BASE = OUT / 'qbs-payload-residual4-offline-admitted-767-agent-20261007-01'
BASE_SHA = 'a4dac6fb073fc665cb8f274557d04c8d2bf3ad9291a70bda03bcfdce3542b405'
SOURCE = OUT / 'stride-metadata-full64-source-precheck766-agent-20261007-01/precheck.json'
SOURCE_SHA = '3ea6ca85e1c36af0c201165d38301d76a8d8f178112c8cf85353da97be5f235b'
SYMBOLS = ('tohost', 'trap_fail', 'num_failed', 'stride_checks', 'source_guard', 'stored', 'vrf')
CSR = {0xc20: 2, 0xc21: 0, 0x008: 0, 0x00f: 0, 0x003: 0}
STATUS = 'STRIDE_FULL64_SPIKE_PREFLIGHT_PASS_NOT_DUT'


def baseline():
    m = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(m['coverage_admitted'] is True, 'Not formal767')
    for name in ('combined-inputs.txt', 'combined-bits.json', 'status.json'):
        path = BASE / name
        require(life.digest(path) == m['output_pins'][str(path)], '767 output drift')
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 768, 'Not exact767 membership')
    evidence=dict(m['input_pins'])
    for p,h in list(evidence.items()):
        if p.endswith('/evidence-pins.json'):
            require(life.digest(Path(p))==h,'Historical evidence ledger drift')
            evidence=life.merge_pins(evidence,json.loads(Path(p).read_bytes()))
    return ledger, evidence


def signatures(memory, reads, symbols, csr):
    actual = {}
    for name, key, size in (('source_guard', 'source', 128), ('stored', 'stored', 544), ('vrf', 'vrf_guarded', 4128)):
        addresses = set(range(symbols[name], symbols[name] + size))
        require(addresses <= reads and addresses <= set(memory), 'Full readback missing: ' + name)
        actual[key] = bytes(memory[a] for a in sorted(addresses))
    def word(name):
        return int.from_bytes(bytes(memory[symbols[name] + b] for b in range(4)), 'little')
    require(word('num_failed') == 0 and word('stride_checks') == 605, 'Failures/check count differs')
    actual['csrs'] = dict(zip(('vl', 'vtype', 'vstart', 'vcsr', 'fcsr'), (csr[k] for k in CSR)))
    actual['checks'] = word('stride_checks')
    host.validate(actual)
    return dict(checks=605, failed_checks=0, fullVRF_bytes=4096, guards_and_sources_bytes=704,
                explicit_read_bytes=4800, csrs=actual['csrs'])


def validate_reference(commits, symbols, text):
    require('exception ' not in text and not any(c.pc == symbols['trap_fail'] for c in commits), 'Unexpected Spike trap')
    memory, reads, gpr, csr, terminal, operations, writes = {}, set(), {}, {}, [], [], []
    for c in commits:
        word = c.instruction
        op, mop = word & 127, (word >> 26) & 3
        if op in (7, 0x27) and (word >> 12) & 7 == 0 and mop == 2:
            ordinal = len(operations)
            isload = op == 7
            require(ordinal < 32 and isload == (ordinal % 2 == 0), 'Strided load/store sequence differs')
            require(c.vector_vl == 1 and c.vector_vstart == 0, 'Huge stride must have actual VL1/vstart0')
            base = symbols['source_guard'] + 64 if isload else symbols['stored'] + 32 * (ordinal // 2) + 16
            require(gpr.get((word >> 15) & 31) == base and
                    gpr.get((word >> 20) & 31) == host.PATTERNS[ordinal // 8], 'Actual rs1/rs2 stride differs')
            require(c.memory_accesses == ((base, None if isload else 0x3c),), 'VL1 formed extra/wrong addresses')
            operations.append(dict(pc=hex(c.pc), insn=hex(word), base=hex(base), stride=hex(host.PATTERNS[ordinal // 8])))
        if op in (7, 0x27) and mop == 0 and (word >> 20) & 31 == 0 and (word >> 12) & 7 == 0:
            require(c.vector_vl == 2 and c.vector_vstart == 0, 'Recovery must execute VL2')
            base = symbols['source_guard'] + 64 if op == 7 else symbols['stored'] + 528
            require(c.memory_accesses == tuple((base + b, None if op == 7 else 0x3c) for b in range(2)),
                    'Unit-stride two-byte recovery differs')
        if op == 0x73 and (word >> 12) & 7 == 2 and (word >> 15) & 31 == 0 and word >> 20 in CSR:
            k = word >> 20
            require(k not in csr and c.gpr_writes.get((word >> 7) & 31) == CSR[k], 'CSR read identity/value differs')
            csr[k] = CSR[k]
        for address, value in c.memory_accesses:
            access = common.scalar_memory(word)
            if value is None:
                if access:
                    require(access[0] == 'read', 'Wrong scalar access')
                    reads.update(range(address, address + access[1]))
                    if any(symbols[n]<=address<symbols[n]+size for n,size in
                           (('source_guard',128),('stored',544),('vrf',4128))):
                        rd=(word>>7)&31 if word&3==3 else ((word>>2)&7)+8 if word&3==0 else (word>>7)&31
                        require(rd in c.gpr_writes,'Missing scalar loaded value')
                        value=c.gpr_writes[rd]&((1<<(8*access[1]))-1)
                        memory.update({address+b:v for b,v in enumerate(value.to_bytes(access[1],'little'))})
                else:
                    require(op == 7, 'Unknown memory read')
                continue
            width = shared.store_width(word)
            require(0 <= value < 1 << (8 * width), 'Store width/value mismatch')
            memory.update({address + b: v for b, v in enumerate(value.to_bytes(width, 'little'))})
            if address == symbols['tohost']: terminal.append(value)
            require(0x80000000 <= address < 0x80200000, 'UART/out-of-L2 memory effect')
        if c.vector_writes: writes.append(c)
        gpr.update(c.gpr_writes)
    require(terminal == [1] and len(operations) == 32 and set(csr) == set(CSR), 'Incomplete reference contract')
    require(len(writes) == 21, 'Full VRF seed/load writer population differs')
    state = {}
    for i, c in enumerate(writes):
        if i < 4:
            require(set(c.vector_writes) == set(range(8*i, 8*i+8)) and
                    all(v == int.from_bytes(bytes([0x5a])*128, 'little') for v in c.vector_writes.values()),
                    'Complete known VRF initialization differs')
        else:
            expected = bytearray([0x5a]*128); expected[:(2 if i == 20 else 1)] = bytes([0x3c])*(2 if i == 20 else 1)
            require(c.vector_writes == {8: int.from_bytes(expected, 'little')}, 'Load full destination/tail differs')
        state.update(c.vector_writes)
    require(len(state) == 32, 'Not all32 VRF known')
    result = signatures(memory, reads, symbols, csr)
    result.update(operations=operations, strided_loads=16, strided_stores=16, VL1_only_base=True,
                  VL2_recovery_bytes=2, vector_writers=21, skipped_unknown_bytes=0, exceptions=0,
                  interpretation='Full64 stride metadata, not traversal of huge-stride addresses')
    return result


def fit(elf):
    with elf.open('rb') as f:
        e = ELFFile(f)
        require(e.elfclass == 64 and e.little_endian and e.header.e_entry == 0x80000000, 'ELF entry/format')
        segments = [(s['p_vaddr'], s['p_memsz']) for s in e.iter_segments() if s['p_type'] == 'PT_LOAD']
        require(segments and all(0x80000000 <= a and a+n <= 0x80100000 for a,n in segments), 'ELF/stack fit')
    return segments


def verify(prepath, seal):
    pre = life.read_bound(prepath, seal); life.check(pre['pins'])
    require(pre['status'] == STATUS and pre['case'] == NAME and pre['baseline_seal'] == BASE_SHA and
            pre['budget_seconds'] == 600 and not pre['coverage_admitted'], 'Preflight scope drift')
    baseline()
    commits = shared.parse_spike_commits(prepath.parent / 'spike.trace')
    require(validate_reference(commits, pre['symbols'], (prepath.parent / 'spike.trace').read_text()) == pre['validation'], 'Reference replay differs')
    require(common.reference_counts(commits, pre['symbols']) == pre['reference_counts'], 'Reference counts drift')
    fit(prepath.parent / 'input.elf')
    return pre


def build(out):
    require(out.parent == OUT and not out.exists(), 'Fresh direct preflight output')
    source = life.read_bound(SOURCE, SOURCE_SHA); ledger, evidence = baseline()
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    pins = life.merge_pins(source['pins'], image['image'])
    files = [Path(__file__).resolve(), Path(__file__).with_name('test_run_stride_metadata767.py'),
        Path(runner.__file__), Path(generic.__file__), Path(common.__file__), Path(shared.__file__),
        Path(host.__file__), Path(resources.__file__), Path(toggle.__file__), Path(bitmap.__file__),
        Path(life.__file__), ROOT/'verification/tests/gap75_start.S', ROOT/'verification/tests/gap75.ld',
        resources.LLVM/'clang', resources.LLVM/'ld.lld', resources.LLVM/'llvm-readelf', resources.SPIKE,
        SOURCE, life.PLAN, BASE/'admission-manifest.json', BASE/'combined-inputs.txt', BASE/'combined-bits.json']
    files += [Path(p) for p in evidence if p.endswith('/evidence-pins.json')]
    files += sorted((ROOT/'verification/ara_verify').glob('*.py'))
    pins = life.merge_pins(pins, {str(p):life.digest(p) for p in files})
    require(not any('ZCC' in p or 'Terapines' in p for p in pins), 'Forbidden tool')
    life.check(pins); host.validate(host.golden()); host.ring_proof()
    out.mkdir(); life.save(out/'input-pins.json', pins)
    includes=ROOT/'verification/tests'
    cmd=[str(resources.LLVM/'clang'),'--target=riscv64-unknown-elf','-march=rv64gcv_zfh_zvfh','-mabi=lp64d',
         '-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-O2','-fno-vectorize','-fno-slp-vectorize',
         '-ffreestanding','-fuse-ld=lld','-nostdlib','-T'+str(includes/'gap75.ld'),
         str(includes/'gap75_start.S'),str(host.APP),'-o',str(out/'input.elf')]
    life.save(out/'compile-command.json',cmd)
    with (out/'compile.log').open('x') as log: subprocess.run(cmd,check=True,timeout=120,stdout=log,stderr=subprocess.STDOUT)
    symbols={n:shared._elf_symbol(out/'input.elf',resources.LLVM/'llvm-readelf',n) for n in SYMBOLS}
    require(symbols['tohost']==0x80001000,'Terminal address')
    segments=fit(out/'input.elf'); elfhash=life.digest(out/'input.elf')
    elfs={p:h for p,h in evidence.items() if p.endswith('.elf')}
    require(elfs and elfhash not in elfs.values(),'Duplicate existing767 ELF')
    life.save(out/'elf-dedup.json',dict(baseline=767,existing_elf_pins=len(elfs),new_elf_hash=elfhash,duplicate=False))
    cmd=[str(resources.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(out/'input.elf')]
    life.save(out/'spike-command.json',cmd)
    with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as trace:
        subprocess.run(cmd,check=True,timeout=120,stdout=stdout,stderr=trace)
    commits=shared.parse_spike_commits(out/'spike.trace')
    validation=validate_reference(commits,symbols,(out/'spike.trace').read_text())
    counts=common.reference_counts(commits,symbols)
    life.save(out/'spike-validation.json',validation)
    life.check(pins)
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
    pre=dict(status=STATUS,case=NAME,pins=pins,symbols=symbols,validation=validation,reference_counts=counts,
             baseline_seal=BASE_SHA,baseline=767,targets=source['targets'],budget_seconds=600,
             ELF_fit=segments,no_UART=True,coverage_admitted=False,VCS_started=False,ZCC_used=False)
    life.save(out/'preflight-manifest.json',pre)
    print(json.dumps(dict(preflight=str(out/'preflight-manifest.json'),seal=life.digest(out/'preflight-manifest.json'),counts=counts)))


def observed(rows, symbols):
    memory, reads, csr, terminal = {}, set(), {}, []
    ranges=[(symbols[n],symbols[n]+size) for n,size in (('source_guard',128),('stored',544),('vrf',4128))]
    for r in rows:
        if r['event']!='retire': continue
        word=int(r['insn'],16); address=int(r['mem_addr'],16)
        require(not int(r['trap']), 'Unexpected DUT trap')
        if word & 127 == 0x73 and (word>>12)&7 == 2 and (word>>15)&31 == 0 and word>>20 in CSR:
            k=word>>20; require(k not in csr and int(r['rd_wdata'],16)==CSR[k], 'DUT CSR mismatch');csr[k]=CSR[k]
        access=common.scalar_memory(word)
        rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        if not access: require(rm==wm==0,'Unknown scalar effect');continue
        kind,width=access;mask=((1<<width)-1)<<(address&7)
        require(address%width==0 and rm==(mask if kind=='read' else 0) and wm==(mask if kind=='write' else 0),'DUT scalar mask mismatch')
        if kind=='write':
            value=int(r['mem_wdata'],16)&((1<<(width*8))-1)
            if address==symbols['tohost']:terminal.append(value)
        elif any(a<=address and address+width<=b for a,b in ranges):
            require(int(r['rd'])!=0,'Unobserved read');value=int(r['rd_wdata'],16)&((1<<(width*8))-1)
            reads.update(range(address,address+width))
        else:continue
        memory.update({address+b:v for b,v in enumerate(value.to_bytes(width,'little'))})
    require(terminal==[1] and set(csr)==set(CSR),'DUT terminal/CSR incomplete')
    return signatures(memory,reads,symbols,csr)


def lifecycle(rows, vectors):
    starts,pending,current,history={}, {}, {},defaultdict(list)
    req,resp,ba,bd,va,vd=Counter(),Counter(),Counter(),Counter(),Counter(),Counter()
    last=-1
    for r in rows:
        cycle,seq,tid,event=int(r['cycle']),int(r['order']),int(r['trans_id']),r['event']
        require(cycle>=last,'Commit cycle order');last=cycle
        if event=='arch_start':
            require(seq>=0 and seq not in starts and tid not in pending,'Duplicate owner');starts[seq]=r;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1] and r['insn']==starts[pending[tid][0]]['insn'],'Bad request')
            pending[tid][1]=True;req[pending[tid][0]]+=1
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1] and seq==-1 and int(r['trap'])==int(r['pc'],16)==int(r['insn'],16)==0,'Bad response')
            resp[pending.pop(tid)[0]]+=1
        elif event in ('uop_alloc','uop_done'):
            vid=int(r['port']);require(seq in starts and 0<=vid<8 and tid==int(starts[seq]['trans_id']) and r['insn']==starts[seq]['insn'],'Backend owner')
            if event=='uop_alloc':
                require(vid not in current,'Live SID reused');entry=dict(seq=seq,start=cycle,end=None)
                current[vid]=entry;history[vid].append(entry);ba[seq,vid,cycle]+=1
            else:
                require(vid in current and current[vid]['seq']==seq and cycle>=current[vid]['start'],'Bad completion')
                current.pop(vid)['end']=cycle;bd[seq,vid,cycle]+=1
        else:require(event=='retire' and not int(r['trap']),'Unknown event/trap')
    require(not pending and req==resp==Counter(starts.keys()) and not current and
            Counter((s,v) for s,v,_ in ba.elements())==Counter((s,v) for s,v,_ in bd.elements()),'Lifecycle conservation')
    metadata={};last=-1
    for r in vectors:
        cycle,seq,vid,event=int(r['cycle']),int(r['arch_seq']),int(r['vid']),r['event']
        require(cycle>=last and int(r['nr_lanes'])==4 and int(r['vlen_bits'])==1024,'Native geometry/order');last=cycle
        if event=='config':continue
        require(seq in starts and r['insn']==starts[seq]['insn'],'Native owner/opcode')
        if event=='alloc':
            key=seq,vid,cycle;require(key not in metadata,'Duplicate native alloc');metadata[key]=r;va[key]+=1
        else:
            owners=[a for a in history[vid] if a['start']<cycle] or [a for a in history[vid] if a['start']==cycle]
            require(owners,'No SID history');owner=owners[-1];key=owner['seq'],vid,owner['start']
            require(owner['seq']==seq and owner['end'] is not None and owner['start']<=cycle<=owner['end'] and key in metadata,'Native SID owner')
            require(all(r[k]==metadata[key][k] for k in ('insn','use_vd','vd','eew','vl','vstart')),'Native metadata')
            if event=='done':vd[seq,vid,cycle]+=1
            else:require(event=='write' and int(r['use_vd'])==1 and 0<=int(r['lane'])<4 and 0<=int(r['source'])<5,'Bad native write')
    require(va==ba and vd==bd,'Native/backend exact identities')
    strided=[r for r in metadata.values() if int(r['insn'],16)&127 in (7,0x27) and (int(r['insn'],16)>>26)&3==2]
    require(len(strided)==32 and all(int(r['vl'])==1 and int(r['vstart'])==int(r['eew'])==0 for r in strided),'Actual32 VL1 strided backend operations')
    return dict(requests=sum(req.values()),responses=sum(resp.values()),exceptions=0,backend_uops=sum(ba.values()),
                current_SID_owner_checked=True,actual_VL1_strided_operations=32)


def vector_gate(result, reference):
    for k,v in dict(status='PASS',skipped_unknown_bytes=0,non_bit_exact_instructions=0,nr_lanes=4,vlen_bits=1024,
                    trapped_requests=[],first_mismatch=None,unobservable_instructions=0,incomplete_requests=[],unretired_requests=[]).items():
        require(result.get(k)==v,'Full vector gate: '+k)
    expected=[c for c in reference if c.vector_writes];records=result['instructions']
    require(len(records)==len(expected)==21 and result['compared_instructions']==21,'Vector writer count')
    require([(int(r['pc'],16),int(r['instruction'],16)) for r in records]==[(c.pc,c.instruction) for c in expected],'Vector PC/opcode')
    require(all(r['status']=='PASS' and r['unknown_write_bytes']==r['skipped_unknown_bytes']==r['mismatch_count']==0 for r in records),'Unknown/mismatched vector bytes')
    require(sum(r['compared_bytes'] for r in records)==result['compared_bytes']>=4114,'Full seeds and active load bytes')


def native_gate(run, reference):
    vc=generic.vc
    starts,retires,rejected=vc._parse_architecture_mapping(run/'commit_trace.csv')
    require(not rejected,'Rejected native request')
    mapping=vc._map_spike_commits(vc._map_architecture_retires(starts,retires,rejected),reference)
    lanes,vlen,activities=vc._parse_vector_trace(run/'vector_trace.csv')
    require((lanes,vlen)==(4,1024),'Native geometry')
    expected={s:reference[i] for s,i in mapping.items() if reference[i].vector_writes}
    require(len(expected)==21 and {s for s,a in activities.items() if a.writes}==set(expected),'Native writer set')
    bytes_checked=0
    for seq,commit in expected.items():
        activity=activities[seq];source=4 if commit.instruction&127==7 else 0;seen=set()
        for w in activity.writes:
            require(w.arch_seq==seq and w.instruction==commit.instruction and w.source==source and w.eew==0 and
                    0<=w.lane<4 and 0<=w.be<=255 and w.be&~w.known_be==0,'Native source/owner/unknown')
            for b in range(8):
                if w.be&(1<<b):
                    key=w.addr,w.lane,b;require(key not in seen,'Duplicate native byte');seen.add(key)
        actual=vc._architectural_bytes(activity.writes,4,1024)
        for (reg,b),(value,_) in actual.items():
            require(reg in commit.vector_writes and value==((commit.vector_writes[reg]>>(8*b))&255),'Exact native active/tail byte')
        required={(r,b) for r in commit.vector_writes for b in range(128)} if source==0 else {(8,b) for b in range(commit.vector_vl)}
        require(required<=set(actual),'Missing seed/active load byte');bytes_checked+=len(actual)
    return dict(writers=21,accepted_known_bytes=bytes_checked,all_active_and_written_tail_exact=True,
                source_ALU_or_VLDU_exact=True,duplicates=0,unknown_bytes=0)


def raw_gain(run, pre):
    ledger,evidence=baseline()
    cachepath=OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
    cache=life.read_bound(cachepath,'8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865')
    oldpath=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(life.digest(oldpath)==cache['input_pins'][str(oldpath)] and oldpath.read_text().splitlines()==ledger[:742],'Exact741 cache prefix')
    scopes=sorted({t['scope'] for t in pre['targets']});merged={s:cache['instances'][s] for s in scopes}
    pins={str(cachepath):life.digest(cachepath),str(oldpath):life.digest(oldpath)}
    for name in ledger[742:]:
        files=list((Path(name)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'));require(len(files)==1,'Toggle test identity')
        sample,sha=toggle.rows(files[0],scopes);require(evidence.get(str(files[0]))==sha,'767 Toggle pin')
        pins[str(files[0])]=sha;merged=toggle.union(merged,sample)
    files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'));require(len(files)==1,'Candidate Toggle file')
    sample,sha=toggle.rows(files[0],scopes);pins[str(files[0])]=sha
    after=toggle.union(merged,sample);targets=[]
    for t in pre['targets']:
        s=t['scope'];before=merged[s];row=after[s]
        require(before['checksum']==t['checksum']==row['checksum'],'Target checksum')
        new=[i for i in t['missing_coordinates'] if not int(before['bits'],16)&(1<<(before['width']-1-i)) and int(row['bits'],16)&(1<<(row['width']-1-i))]
        targets.append(dict(scope=s,name=t['name'],new_coordinates=new,new_directions=len(new)))
    inputs=run.with_name(run.name+'-qualified')/'candidate-inputs.txt'
    with inputs.open('x') as f:f.write(str(life.IMAGE)+'.vdb\n'+str(run/'code.vdb')+'\n')
    candidate=bitmap.collect(inputs)
    pins=life.merge_pins(pins,candidate['input_hashes'])
    design=Path(str(life.IMAGE)+'.vdb/snps/coverage/db')
    pins=life.merge_pins(pins,{str(design/p):h for p,h in candidate['design'].items()})
    base=json.loads((BASE/'combined-bits.json').read_bytes());combined=bitmap.combine(base,candidate)
    life.check(pins)
    return dict(baseline=767,targets=targets,target_new_serialized_directions=sum(t['new_directions'] for t in targets),
                scoped_toggle=toggle.gains(merged,after),raw_delta=bitmap.delta(base,combined),pins=pins,
                official_percentage=False,coverage_admitted=False), candidate


def collect(run, prepath, seal, prepared):
    out=run.with_name(run.name+'-qualified');require(not out.exists(),'Fresh qualification output');out.mkdir()
    pins=dict(prepared['pins'])
    try:
        pre=verify(prepath,seal);state=json.loads((run/'simulation-status.json').read_bytes())
        require(state['status']=='SIMULATION_EXITED_NOT_ADMITTED' and state['returncode']==0 and not state['timeout'],'NonPASS terminal')
        require(json.loads((run/'manifest.json').read_bytes())==prepared,'Runtime binding differs')
        started=json.loads((run/'started.json').read_bytes())
        require(started['pid']==started['process_group']==state['pid'] and started['budget_s']==600 and
                started['command']==prepared['command'] and started['image_sha256']==runner.IMAGE_SEAL and
                started['elf_sha256']==life.digest(prepath.parent/'input.elf'),'Actual startup binding')
        for p in run.iterdir():
            if p.is_file():pins[str(p)]=life.digest(p)
        rows=common.read_csv((run/'commit_trace.csv').read_bytes(),common.COMMIT_FIELDS)
        vectors=common.read_csv((run/'vector_trace.csv').read_bytes(),common.VECTOR_FIELDS)
        control=lifecycle(rows,vectors);generic.logs((run/'console.log').read_text(),(run/'run.vcs.log').read_text(),control)
        require(not generic.check_contract_log(run/'run.vcs.log'),'Contract errors')
        sig=observed(rows,pre['symbols']);tracer=generic.tracer_exact((run/'trace_hart_0.log').read_text(),rows)
        scalar=common.spike_trace.compare_commit_prefix(prepath.parent/'spike.trace',run/'commit_trace.csv',0x80000000,
                    terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(out/'scalar-comparison.json',scalar);common.scalar_exact(scalar,pre['reference_counts'])
        vector=common.compare_vector_commits(prepath.parent/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
        life.save(out/'vector-comparison.json',vector)
        reference=shared.parse_spike_commits(prepath.parent/'spike.trace');vector_gate(vector,reference)
        native=native_gate(run,reference);life.save(out/'native-byte-proof.json',native)
        gain,candidate=raw_gain(run,pre);life.save(out/'raw-gain.json',gain);life.save(out/'candidate-bits.json',candidate)
        pins=life.merge_pins(pins,gain['pins']);life.check(pins)
        pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
        life.save(out/'qualification.json',dict(status='STRIDE_FULL64_FULL_ARCHITECTURE_PASS_NOT_ADMITTED',pins=pins,
            signature=sig,lifecycle=control,tracer=tracer,baseline=767,raw_gain=gain,
            qualification_full_scalar_Spike=True,coverage_admitted=False,VCS_rerun=False,RTL_changed=False))
    except Exception as e:
        life.save(out/'failure.json',dict(status='FAIL_OR_HOLD_NOT_ADMITTED',reason=type(e).__name__+': '+str(e),pins=pins,coverage_admitted=False))
        raise


def prepare(run, prepath, seal):
    require(run.parent==OUT and not run.exists(),'Fresh run output');pre=verify(prepath,seal)
    namespace=dict(runner.__dict__);namespace.update(PRE=prepath.parent,BUDGET=600,ELF_SEAL=life.digest(prepath.parent/'input.elf'),
                                                    preflight=SimpleNamespace(NAME=NAME))
    cmd=FunctionType(runner.command.__code__,namespace)(run);namespace['command']=FunctionType(runner.command.__code__,namespace)
    manifest=dict(case=NAME,command=cmd,output=str(run),timeout_s=600,pins=life.merge_pins(pre['pins'],{str(prepath):seal}),
                  authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL',preflight=str(prepath),preflight_seal=seal,
                  coverage_admitted=False,baseline=767,automatic_retry=False)
    return manifest,namespace


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('build','verify','prepare','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--preflight',type=Path);p.add_argument('--seal');p.add_argument('--prepared-seal')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='build':build(out);return
    require(a.preflight is not None and a.seal is not None,'Pinned preflight required')
    if a.mode=='verify':verify(a.preflight.resolve(),a.seal);print('VERIFY_PASS');return
    manifest,namespace=prepare(out,a.preflight.resolve(),a.seal);record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':life.save(record,manifest);print(json.dumps(dict(prepared=str(record),seal=life.digest(record))));return
    require(a.prepared_seal and life.read_bound(record,a.prepared_seal)==manifest,'Prepared seal differs')
    try:FunctionType(runner.run.__code__,namespace)(out,manifest)
    finally:
        if (out/'simulation-status.json').exists():collect(out,a.preflight.resolve(),a.seal,manifest)


if __name__=='__main__':main()
