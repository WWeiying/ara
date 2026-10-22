"""Independent v1 descriptor/half/ELF/custom-contract oracle; no simulator invocation."""
import csv
import io
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
NAME = 'akv_gap73_v1_onehot'
TEST = 'app:'+NAME
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine'
RAW = (113,114,115,119,120,121)
TERMS = (0,1,2,6,7,8)
WORDS = [0x00b5205b]*7+[0x0005345b]*3+[0x0000505b]
HOST_CHECKS, DUT_CHECKS, NEGATIVES = 79,97,1678
SCHEMA = 'gap73-akv-v1-stdout-perf-vector-commit-v1'
BUFFERS = dict(gap73_source=768,gap73_descriptor=448,gap73_initial=4928,
               gap73_got=4928,gap73_snapshot=528,gap73_trap=336)
PERF_KEYS = ('seq id command success fault validation_fault validation_error read_fault '
    'context_ready busy_cycles full refill load release v2_full v2_refill v2_row_load '
    'v2_column_load v2_column_panel v2_logical_column v2_k_view_bank_cycles '
    'v2_bank_conflict_cycles v2_rejected q_external_bytes kv_external_bytes replay_bytes '
    'replay_backpressure_cycles read_ranges translations ar r_beats read_payload_bytes '
    'store_wait_cycles read_backpressure_cycles read_outstanding_occ_sum read_outstanding_max '
    'read_outstanding_full_cycles').split()


def require(ok, message):
    if not ok: raise ValueError(message)


def scalar_store_bytes(address, value, mask):
    # CVA6 reports the effective address and bus-lane byte enables, but the
    # STORE writeback value is the unshifted LSU operand (store_unit.result_o).
    offset = address & 7
    width = bin(mask).count('1')
    require(width in (1, 2, 4, 8) and offset + width <= 8 and
            mask == ((1 << width) - 1) << offset,
            'invalid scalar store byte enables')
    return [(address + i, (value >> (8 * i)) & 255) for i in range(width)]


def half(s, i):
    return int.from_bytes(struct.pack('<e',s*64+i+1),'little')


def seed(p, r, i):
    return (0x7300 ^ p*0x113 ^ r*0x151 ^ i*0x35)&65535


def frame(p, recovered=False):
    values = [(0x7310 ^ p*0x111 ^ i)&65535 for i in range(16)]
    values += [half(p-7,i) if recovered and 7<=p<=9 and r==1 else seed(p,r,i)
               for r in range(3) for i in range(64)]
    values += [(0x73ef ^ p*0x111 ^ i)&65535 for i in range(16)]
    return struct.pack('<224H',*values)


def source():
    result = bytearray()
    for s in range(3):
        data = bytearray((0x73 ^ s*0x19 ^ i)&255 for i in range(256))
        data[64:192] = struct.pack('<64H',*(half(s,i) for i in range(64)))
        result.extend(data)
    return bytes(result)


def descriptor(p, address):
    strides = [128]*3
    bases = [address+256*s+64 for s in range(3)]
    if p<3: strides[p] += 1
    elif p<6: bases[p-3] += 1
    return struct.pack('<4B2H4I5Q',1,1,1,0,64,1,*strides,0,*bases,0,0)


def predicates(blob):
    v,f,q,flags,dim,kv,qs,ks,vs,r0,qb,kb,vb,r1,r2 = struct.unpack('<4B2H4I5Q',blob)
    require((v,f,q,flags,dim,kv,r0,r1,r2)==(1,1,1,0,64,1,0,0,0),'preceding v1 guard differs')
    require(all(base+127 < 1<<64 for base in (qb,kb,vb)),'range overflow')
    return tuple(int(x) for x in (qs&1,ks&1,vs&1,qs<128,ks<128,vs<128,qb&1,kb&1,vb&1))


def host_oracle(log):
    expected = ['H %d %d %04x'%(s,i,half(s,i)) for s in range(3) for i in range(64)]
    for p in range(7):
        values = [128+int(p==i) for i in range(3)]+[int(p==i+3) for i in range(3)]
        expected.append('D %d '%p+' '.join(map(str,values)))
    require(log.splitlines()==expected+['NEGATIVE %d PASS'%NEGATIVES],'independent C oracle differs')
    return dict(status='PASS',finite_half_values=192,one_hot_descriptors=6,
                byte_and_state_mutations_rejected=NEGATIVES,scope='Host reference only, no custom execution')


def native_targets(proof, inventory_path):
    from reviewed_20261004.audit_readonly import xml,tree_digest
    inventory_path = Path(inventory_path).resolve()
    inventory = proof.read(inventory_path)
    require(inventory['status']=='DIAGNOSTIC_NOT_SIGNOFF' and inventory['passed']==654 and
            inventory['waivers_applied'] is False,'require latest completed654 zero inventory')
    proof.hashes(inventory['report_pins'])
    baseline = Path(inventory['baseline'])
    checkpoint,collection = proof.read(baseline/'checkpoint.json'),proof.read(baseline/'collection.json')
    require(checkpoint['coverage_status']=='COMPLETE' and checkpoint['aggregate_passed']==inventory['passed'] and
            collection['status']=='PASS' and collection['passed']==inventory['passed'],'unfinished latest baseline')
    proof.hashes(collection['reports'])
    bits,ledger,plan = (proof.read(baseline/n) for n in ('combined-bits.json','all-passed-outcomes.json','plan.json'))
    inputs = proof.pin(baseline/'combined-dve/inputs.txt').read_text().splitlines()
    require(len(ledger)==inventory['passed'] and bits['tests']==[r['vdb'] for r in ledger]==inputs[1:] and
            inputs[0]==plan['design_vdb'] and all(r['status']=='PASS' and r['passed_only'] and r['vdb_valid']
            for r in ledger),'baseline aggregate membership differs')
    design = Path(plan['design_vdb']); db = design/'snps/coverage/db'
    proof.hashes({str(db/p):h for p,h in bits['design'].items()})
    definition = next(d for d in xml(proof.pin(db/'shape/cond.verilog.shape.xml'))
                      if d.tag=='conddef' and d.get('chksum')==bits['metrics']['cond'][SCOPE]['checksum'])
    expressions = sorted(definition.iter('expr_monitored'),key=lambda e:int(e.get('condregid')))
    target = next(e for e in expressions if e.get('condregid')=='47')
    table = target.find('truth_table')
    base = sum(int(e.find('truth_table').get('nrows')) for e in expressions[:expressions.index(target)])
    require(base==113 and (table.get('nrows'),table.get('ncols'))==('10','9'),'C47 shape/layout differs')
    row = bits['metrics']['cond'][SCOPE]
    rawbits = format(int(row['bits'],16),'0%db'%row['width'])
    points = []
    for p,index in enumerate(RAW):
        vector = ''.join(str(int(i==TERMS[p])) for i in range(9))
        matches = [i for i in range(10) if table.get('vecs')[9*i:9*(i+1)]==vector]
        require(len(matches)==1 and base+9-matches[0]==index and rawbits[index]=='0','one-hot diagnostic mapping/zero differs')
        candidates = [v for v in inventory['source_points'] if v['scope']==SCOPE and
                      v['metric']=='cond' and v['raw_index']==index]
        require(len(candidates)==1,'latest inventory target missing/ambiguous')
        point = candidates[0]
        require(point['native_id']=='47' and point['vector']==vector and point['native_dve_qualified'] is False and
                point['attributes']==dict(target.attrib) and point['truth_table']==dict(table.attrib),
                'inventory/source native attributes differ')
        proof.pin(point['source'],point['source_sha256'])
        require(predicates(descriptor(p,0x80010000))==tuple(map(int,vector)),'one-hot stimulus not reachable')
        points.append(dict(phase=p+1,raw_index=index,vector=vector,baseline_bit=0,
                           field=('q_stride','k_stride','v_stride','q_base','k_base','v_base')[p],
                           native_dve_qualified=False,source=point['source'],line=point['line']))
    proof.pin(inventory_path.parent/'zeros.csv')
    manifest = proof.read(ROOT/'verification/out/repaired-aligned-build-20260930-01/sim/vcs_source_manifest.json')
    compiled = {v['path']:v['sha256'] for v in manifest['files']}
    for rel in ('hardware/src/ara_dispatcher.sv','hardware/src/vlsu/akv/akv_engine.sv',
                'hardware/src/vlsu/vlsu.sv','hardware/src/vlsu/qbs/qbs_read_engine.sv',
                'hardware/tb/ara_commit_monitor.sv','hardware/include/akv_pkg.sv'):
        path = str(ROOT/rel); proof.pin(path,compiled[path])
    return dict(status='STATIC_REACHABLE_DIAGNOSTIC_NOT_NATIVE_QUALIFIED',baseline=str(baseline),
                passed=inventory['passed'],inventory=str(inventory_path),design_vdb=str(design),
                scope=SCOPE,metric='cond',checksum=row['checksum'],width=row['width'],
                definition_sha256=tree_digest(definition),points=points,
                mapping='Diagnostic only: condregid ascending, reverse within truth table',
                validation_path='dispatcher v1 FULL -> descriptor64 fetch -> VALIDATE C47 -> FAULT -> cause2/tval0',
                distinguishing_signals=['active_command_q=AKV_COMMAND_FULL','descriptor_error=AKV_VALIDATION_STRIDE(9)',
                    'state_q=VALIDATE then FAULT, never PAYLOAD','q_external_bytes=kv_external_bytes=replay_bytes=0',
                    'terminal_exception.cause=2, tval=0','no accepted VRF write from rejected command'],
                read_counter_semantics='read_payload_bytes includes descriptor: rejected FULL is exactly64, not zero',
                native_dve_qualified=False,measured_gain=None)


def elf_audit(blob):
    require(blob[:6]==b'\x7fELF\x02\x01','ELF64 little-endian required')
    h = struct.unpack_from('<HHIQQQIHHHHHH',blob,16)
    require(h[1]==243 and h[10]==64,'not RISC-V ELF')
    sections = [struct.unpack_from('<IIQQQQIIQQ',blob,h[5]+64*i) for i in range(h[11])]
    def data(s):
        require(s[4]+s[5]<=len(blob),'truncated ELF')
        return blob[s[4]:s[4]+s[5]]
    symbols = {}
    for s in sections:
        if s[1]!=2: continue
        names = data(sections[s[6]])
        require(s[9]==24,'invalid symbol entry size')
        for off in range(0,s[5],24):
            n,info,_,_,value,size = struct.unpack_from('<IBBHQQ',data(s),off)
            name = names[n:names.index(0,n)].decode()
            if name and info&15!=4 and not name.startswith('$'):
                require(name not in symbols,'duplicate symbol')
                symbols[name] = dict(value=value,size=size)
    def code(pc,n):
        matches = [s for s in sections if s[2]&4 and s[3]<=pc and pc+n<=s[3]+s[5]]
        require(len(matches)==1,'code outside executable section')
        s = matches[0]; off = s[4]+pc-s[3]
        return blob[off:off+n]
    sites = []
    for i,w in enumerate(WORDS):
        pc = symbols['gap73_site_%d'%(i+1)]['value']
        require(pc%4==0 and struct.unpack('<5I',code(pc,20))==
                (w,0x001022f3,0x00802373,0x00573023,0x00673423),'raw custom/immediate CSR words differ')
        sites.append(dict(phase=i+1,pc=pc,word=w))
    customs = []
    for s in sections:
        if not s[2]&4: continue
        b = data(s); off = 0
        while off<len(b):
            low = int.from_bytes(b[off:off+2],'little'); size = 4 if low&3==3 else 2
            if size==4 and low&127==0x5b: customs.append(s[3]+off)
            off += size
    require(sorted(customs)==sorted(s['pc'] for s in sites),'extra/missing custom word')
    selected = {}
    for n,size in BUFFERS.items():
        row = symbols[n]
        require(row['size']==size and row['value']%64==0,'wrong aligned buffer: '+n)
        require(0x80000000<=row['value']<row['value']+size<=0x80200000,'buffer outside L2')
        selected[n] = row['value']
    require(selected['gap73_source']%4096==0,'source page alignment')
    selected['gap73_trap_count'] = symbols['gap73_trap_count']['value']
    selected['gap73_handler'] = symbols['gap73_handler']['value']
    start = symbols['_start']['value']
    reset = code(start,symbols['trap_vector']['value']-start)
    mret = reset.find(bytes.fromhex('73002030')); require(mret>=0,'missing CRT MRET')
    calls = []
    for off in range(0,mret-7,2):
        a,b = struct.unpack_from('<II',reset,off)
        if a&0xfff!=0x297 or b&0xfffff!=0x28293: continue
        high = (a&0xfffff000)-((1<<32) if a&0x80000000 else 0)
        low = (b>>20)-(4096 if b&0x80000000 else 0)
        if start+off+high+low==symbols['rvtest_init']['value']:
            require(reset[off+8:off+14]==bytes.fromhex('638302008292'),'CRT hook call differs')
            calls.append(start+off)
    require(len(calls)==1,'trap hook must run before user mode')
    return dict(status='PASS',sites=sites,symbols=selected,crt_hook_before_mret=calls[0],
                scope='Static ELF only; custom execution pending VCS')


def expected_memory(info):
    sym = info['symbols']
    payloads = dict(gap73_source=source(),
        gap73_descriptor=b''.join(descriptor(p,sym['gap73_source']) for p in range(7)),
        gap73_initial=b''.join(frame(p) for p in range(11)),
        gap73_got=b''.join(frame(p,True) for p in range(11)),
        gap73_snapshot=struct.pack('<66Q',*([21,0,64,8,2,1]*11)),
        gap73_trap=b''.join(struct.pack('<7Q',2,info['sites'][p]['pc'],0,0,64,8,21) for p in range(6)),
        gap73_trap_count=struct.pack('<Q',6))
    return {sym[n]+i:b for n,v in payloads.items() for i,b in enumerate(v)}


def expected_perf(p):
    bad,full,row = p<6,p<=6,7<=p<=9
    cmd = 0 if full else 2 if row else 3
    result = dict(seq=p+1,command=cmd,success=int(not bad),fault=int(bad),validation_fault=int(bad),
        validation_error=9 if bad else 0,read_fault=0,context_ready=int(6<=p<=9),full=int(full),
        refill=0,load=int(row),release=int(p==10),v2_full=0,v2_refill=0,v2_row_load=0,
        v2_column_load=0,v2_column_panel=0,v2_logical_column=0,v2_k_view_bank_cycles=0,
        v2_bank_conflict_cycles=0,v2_rejected=0,q_external_bytes=128 if p==6 else 0,
        kv_external_bytes=256 if p==6 else 0,replay_bytes=128 if row else 0,
        read_ranges=1 if bad else 4 if p==6 else 0,translations=0,
        ar=1 if bad else 4 if p==6 else 0,r_beats=4 if bad else 28 if p==6 else 0,
        read_payload_bytes=64 if bad else 448 if p==6 else 0)
    if not row: result['replay_backpressure_cycles'] = 0
    if not full:
        result.update(store_wait_cycles=0,read_backpressure_cycles=0,read_outstanding_occ_sum=0,
                      read_outstanding_max=0,read_outstanding_full_cycles=0)
    return result


def stdout_audit(log, info):
    require(not re.search(r'(?im)^\s*(?:FAIL(?:ED)?\b|Error:|Fatal:|Assertion\b)|\$fatal',log),'runtime failure')
    passed = 'PASSED: '+NAME+' checks=%d errors=0'%DUT_CHECKS
    require([s for s in log.splitlines() if s.startswith('PASSED:')]==[passed],'exact DUT selfchecks missing')
    require(log.count('Core Test *** SUCCESS *** (tohost = 0)')==1 and
            len(re.findall(r'^\$finish at simulation time\s+\d+',log,re.M))==1,'missing simulator completion')
    for level in ('ERROR','FATAL'):
        require(re.findall(r'^UVM_'+level+r'\s*:\s*(\d+)',log,re.M)==['0'],'missing/nonzero UVM severity')
    contract = re.findall(r'^\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+) '
        r'mmu_request_cycles=\d+ protocol_errors=(\d+) outstanding=(\d+)',log,re.M)
    require(len(contract)==1 and contract[0][0]==contract[0][1] and
            tuple(map(int,contract[0][2:]))==(6,0,0),'protocol/exception summary differs')
    phases = [s for s in log.splitlines() if s.startswith('AKV73_PHASE')]
    csrs = [s for s in log.splitlines() if s.startswith('AKV73_CSR')]
    traps = [s for s in log.splitlines() if s.startswith('AKV73_TRAP')]
    count = 13; expected = []
    for p,w in enumerate(WORDS):
        count += 9 if p<6 else 6
        expected.append('AKV73_PHASE phase=%d word=%08x traps=%d checks=%d errors=0'%(p+1,w,min(p+1,6),count))
    require(phases==expected and log.index(phases[-1])<log.index(passed),'phase order/selfcheck count differs')
    require(csrs==['AKV73_CSR phase=%d fflags=21 vstart=0 vl=64 vtype=8 vxrm=2 vxsat=1'%(p+1)
                   for p in range(11)],'immediate CSR transcript differs')
    require(traps==['AKV73_TRAP phase=%d cause=2 pc=%x expected=%x tval=0'%(p+1,s['pc'],s['pc'])
                   for p,s in enumerate(info['sites'][:6])],'trap cause/EPC/terminal tval0 differs')
    lines = [s for s in log.splitlines() if s.startswith('[AKV_PERF] ')]
    require(len(lines)==11,'exactly eleven PERF records required')
    rows = []
    for p,line in enumerate(lines):
        pairs = [re.fullmatch(r'([a-z_][a-z_0-9]*)=([0-9]+)',t) for t in line.split()[1:]]
        require(all(pairs) and len(pairs)==len(PERF_KEYS),'malformed PERF')
        row = {m[1]:int(m[2]) for m in pairs}
        require(set(row)==set(PERF_KEYS) and all(row[k]==v for k,v in expected_perf(p).items()),'PERF payload/trap/v1 contract differs')
        require(row['busy_cycles']>0,'empty command')
        if p<=6: require(row['read_outstanding_max']>0,'descriptor/payload read witness missing')
        rows.append(row)
    events = [s.split()[0] for s in log.splitlines() if s.startswith(('[AKV_PERF] ','AKV73_'))]
    wanted = []
    for p in range(11):
        wanted += ['[AKV_PERF]']+(['AKV73_TRAP'] if p<6 else [])+['AKV73_CSR','AKV73_PHASE']
    require(events==wanted,'terminal/phase evidence ordering differs')
    return dict(status='PASS',checks=DUT_CHECKS,traps=6,commands=11,perf=rows,
                busy_cycles=sum(r['busy_cycles'] for r in rows),tohost=0,
                descriptor_bytes_on_rejection=64,payload_bytes_on_rejection=0)


def commit_audit(text, info):
    rows = list(csv.DictReader(io.StringIO(text)))
    require(rows,'empty commit trace')
    pending,starts,custom,gpr,memory = {},{},[],{},{}
    wanted = expected_memory(info)
    retired_custom, snapshots = [],[]
    csr_sites = {s['pc']+off:(p,off) for p,s in enumerate(info['sites']) for off in (4,8)}
    reqs = resps = faults = 0
    last = -1
    for r in rows:
        cycle = int(r['cycle']); require(cycle>=last,'commit cycles regress'); last=cycle
        event,word = r['event'],int(r['insn'],16)
        if event=='arch_start':
            seq = int(r['order']); require(seq not in starts,'duplicate arch sequence')
            starts[seq] = dict(word=word,id=int(r['trans_id']),cycle=cycle)
        elif event=='cvx_req':
            id_ = int(r['trans_id']); require(id_ not in pending,'duplicate live transaction')
            pending[id_] = (word,cycle); reqs+=1
            if word&127==0x5b:
                p = len(custom); require(p<11 and word==WORDS[p],'exact custom decoder/sequence differs')
                if p<=6:
                    require(gpr.get(10)==info['symbols']['gap73_descriptor']+64*p and gpr.get(11)==0,
                            'FULL descriptor/tile actual operands differ')
                    addr = info['symbols']['gap73_descriptor']+64*p
                    actual = bytes(memory.get(addr+i,256) for i in range(64))
                    require(actual==descriptor(p,info['symbols']['gap73_source']),'actual descriptor bytes differ')
                    require(predicates(actual)==tuple(int(i==(TERMS[p] if p<6 else -1)) for i in range(9)),
                            'not exactly one target operand')
                elif p<=9: require(gpr.get(10)==p-7,'actual Q/K/V selector differs')
                matching = [(s,v) for s,v in starts.items() if v['id']==id_ and v['word']==word and v['cycle']<=cycle]
                require(matching,'missing custom arch_start')
                seq = max(matching,key=lambda a:a[1]['cycle'])[0]
                custom.append(dict(phase=p+1,word=word,id=id_,seq=seq,request_cycle=cycle))
        elif event=='cvx_resp':
            id_ = int(r['trans_id']); require(id_ in pending,'orphan response')
            word,start = pending.pop(id_); fault = int(r['trap']); resps+=1; faults+=fault
            if word&127==0x5b:
                matches = [c for c in custom if c['id']==id_ and c['request_cycle']==start]
                require(len(matches)==1,'ambiguous custom response')
                matches[0].update(fault=fault,response_cycle=cycle)
            else: require(fault==0,'noncustom exception')
        elif event=='retire':
            pc = int(r['pc'],16)
            if word&127==0x5b: retired_custom.append((pc,word,int(r['trap'])))
            if pc in csr_sites:
                p,off = csr_sites[pc]
                require(word==(0x001022f3 if off==4 else 0x00802373) and
                        int(r['rd_wdata'],16)==(21 if off==4 else 0) and int(r['trap'])==0,'immediate retired CSR differs')
                snapshots.append((p,off))
            if int(r['rd']) and not int(r['trap']): gpr[int(r['rd'])] = int(r['rd_wdata'],16)
            addr,value,mask = (int(r[k],16) for k in ('mem_addr','mem_wdata','mem_wmask'))
            if mask and not int(r['trap']):
                for address, byte in scalar_store_bytes(addr,value,mask):
                    if address in wanted: memory[address]=byte
            # Vector stores are not scalar RVFI retire events. Observe their
            # architectural readback through the test's scalar comparison loop;
            # vector_audit independently checks the underlying VRF writes.
            read_mask = int(r['mem_rmask'],16)
            if read_mask and not int(r['trap']):
                for address, byte in scalar_store_bytes(addr,int(r['rd_wdata'],16),read_mask):
                    if address in wanted: memory[address]=byte
    require(not pending and reqs==resps and faults==6,'unbalanced request/terminal exception trace')
    require(len(custom)==11 and [c.get('fault') for c in custom]==[1]*6+[0]*5,'custom outcomes differ')
    bad = {s['pc']:s['word'] for s in info['sites'][:6]}
    good = [(s['pc'],s['word'],0) for s in info['sites'][6:]]
    require([r for r in retired_custom if r[0] not in bad]==good and
            all(w==bad[pc] and t==1 for pc,w,t in retired_custom if pc in bad),'custom retirement binding differs')
    require(len([r for r in retired_custom if r[0] in bad])<=6,'duplicate illegal retirement')
    require(snapshots==[(p,o) for p in range(11) for o in (4,8)],'CSR pair absent/duplicated/reordered')
    require(memory==wanted,'independent full source/descriptor/frame/CSR/trap memory differs')
    return dict(status='PASS',commands=custom,requests=reqs,responses=resps,exceptions=faults,
                checked_memory_bytes=len(memory),retired=sum(r['event']=='retire' for r in rows),last_cycle=last)


def vector_audit(text, commands):
    rows = list(csv.DictReader(io.StringIO(text)))
    require(rows and rows[0]['event']=='config','missing vector config')
    require(all((int(r['nr_lanes']),int(r['vlen_bits']))==(4,1024) for r in rows),'foreign vector configuration')
    sequence = {c['seq']:c['phase']-1 for c in commands}
    state, groups, seeded, phase_writes, custom_groups = {},{},[],[set() for _ in range(11)],[]
    last = -1
    for r in rows[1:]:
        cycle = int(r['cycle']); require(cycle>=last,'vector cycles regress'); last=cycle
        event = r['event']; require(event in ('alloc','write','done'),'unknown/reset vector event')
        seq,vid,word = int(r['arch_seq']),int(r['vid']),int(r['insn'],16)
        key = (seq,vid)
        if event=='alloc':
            require(key not in groups,'duplicate backend allocation')
            p = sequence.get(seq)
            g = dict(word=word,vd=int(r['vd']),eew=int(r['eew']),vl=int(r['vl']),
                     start=int(r['vstart']),use=int(r['use_vd']),done=False,phase=p)
            groups[key]=g
            require(word&127!=0x5b or p is not None,'unbound custom backend command')
            if p is not None:
                custom_groups.append(dict(phase=p+1,seq=seq,vid=vid,word=word))
                expected = {(reg,b):seed(p,reg-7,b//2).to_bytes(2,'little')[b%2]
                            for reg in (7,8,9) for b in range(128)}
                require(state==expected and seeded[-3:]==[(p,7),(p,8),(p,9)],'not fully initialized EEW16 v7/v8/v9')
                require(word==WORDS[p] and g['start']==0 and g['eew']==1,'custom backend identity differs')
                require(g['use']==int(7<=p<=9),'FULL/RELEASE must not reserve a VRF destination')
                if 7<=p<=9: require((g['vd'],g['vl'])==(8,64),'LOAD dimensions differ')
            elif g['use']:
                p = len(seeded)//3
                require(p<11 and word&127==7 and (word>>12)&7==5 and (word>>20)&4095==32 and
                        ((word>>7)&31,g['eew'],g['vl'],g['start'])==(g['vd'],1,64,0) and
                        g['vd']==7+len(seeded)%3,'unexpected writer/incorrect EEW16 seed')
                g['seed_phase']=p; seeded.append((p,g['vd']))
        else:
            require(key in groups and groups[key]['word']==word,'untracked backend event')
            g=groups[key]
            require((int(r['vd']),int(r['eew']),int(r['vl']),int(r['vstart']),int(r['use_vd']))==
                    (g['vd'],g['eew'],g['vl'],g['start'],g['use']),'backend metadata drift')
            if event=='done':
                require(not g['done'],'duplicate done')
                g['done']=True; g['done_cycle']=cycle; continue
            # The monitor can print done before the last write in the same cycle.
            require(not g['done'] or cycle==g['done_cycle'], 'VRF write after backend completion')
            require(g['use']==1,'VRF side effect from FULL/RELEASE/store')
            p = g.get('seed_phase',g['phase'])
            lane,addr,be = int(r['lane']),int(r['addr']),int(r['be'],16)
            require(0<=lane<4 and 0<be<=255 and g['eew']==1,'invalid VRF accepted bytes')
            reg,chunk = divmod(addr,4)
            require(reg==g['vd'] and reg in (7,8,9),'neighbor/unowned register write')
            value = int(r['wdata'],16)
            for b in range(8):
                if not be>>b&1: continue
                slot,within = divmod(b,2); natural=((slot&1)<<1)|(slot>>1)
                index=chunk*32+(natural*4+lane)*2+within
                require(index<128,'VRF register overflow')
                halfword = half(p-7,index//2) if g['phase'] is not None else seed(p,reg-7,index//2)
                actual=(value>>(8*b))&255
                require(actual==halfword.to_bytes(2,'little')[index%2],'independent exact VRF half byte mismatch')
                state[reg,index]=actual
                if g['phase'] is not None: phase_writes[p].add(index)
    require(seeded==[(p,r) for p in range(11) for r in (7,8,9)] and all(g['done'] for g in groups.values()),
            'missing initialization/completion')
    require([g['phase'] for g in groups.values() if g['phase'] is not None]==list(range(11)),
            'missing/duplicate/reordered custom backend command')
    require(all(w==set(range(128)) if 7<=p<=9 else not w for p,w in enumerate(phase_writes)),
            'incomplete recovery or rejected FULL VRF writes')
    return dict(status='PASS',custom_allocations=11,illegal_vrf_write_bytes=0,
                recovery_write_bytes=384,initialized_registers=33,all_backend_complete=True,
                custom_groups=custom_groups)
