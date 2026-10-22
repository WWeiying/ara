#!/usr/bin/env python3
"""Independent half oracle and exact illegal-word/architectural Spike audit."""
import csv
import gzip
import io
import re
import struct
import xml.etree.ElementTree as ET

NAME = 'rvv:vgap69_vf_odd_vd'
REGS = (7, 8, 9, 10, 11, 15, 16, 17, 18)
INPUT_VALUES = (1., -1., 1.5, -2.5, .5, 4., 16., -.25)
BOX = 0xffffffffffff4000
WORDS = {'gap69_illegal_site': 0x930054d7, 'gap69_legal_site': 0x93005457}
CHECK_PARTS = dict(images=3*(9*64+16), trap=9, states=3*6, vlenb=1,
                   no_second_trap=1, restored_machine_csrs=6, completed=1, harness=3)
CHECKS = sum(CHECK_PARTS.values())
MAX_RETIRED = 70000
BUFFERS = dict(gap69_seed=1184, gap69_rejected=1184, gap69_recovered=1184,
               gap69_state=144, gap69_traps=72)
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'


def target_shapes(design, bits):
    result = []
    for metric in ('line', 'branch'):
        row = bits['metrics'][metric][SCOPE]
        with gzip.open(design / 'snps/coverage/db/shape' / (metric+'.verilog.shape.xml'), 'rb') as f:
            root = ET.parse(f).getroot()
        definition = next(n for n in root.iter('linedef' if metric == 'line' else 'branch_def')
                          if n.get('chksum') == row['checksum'])
        if metric == 'line':
            point = next(n for n in definition.iter('linebb') if n.get('id') == '1137')
            require(point.get('index') == '1145' and point.get('line_num') == '4059' and
                    point.get('bbsig') == 'illegal_insn = ara_req.use_vd;', 'line target semantics differ')
            raw, description = 1145, dict(point.attrib)
        else:
            specs = list(definition.iter('branch_spec'))
            spec = next(n for n in specs if n.get('id') == '25')
            vectors = list(spec.findall('branch_vector'))
            vector = next(n for n in vectors if n.get('id') == '659')
            raw = sum(int(n.get('totalbranches')) for n in specs[:specs.index(spec)]) + len(vectors)-1-vectors.index(vector)
            expr = next(n for n in spec.iter('branch_expr') if n.get('id') == '4058')
            require(raw == 470 and 'mask_result' in expr.get('exprstr'), 'branch reversal/path differs')
            description = dict(spec=dict(spec.attrib), vector=dict(vector.attrib), expression=dict(expr.attrib))
        value = format(int(row['bits'],16), '0%db'%row['width'])
        require(value[raw] == '0', 'target already covered in selected baseline')
        result.append(dict(metric=metric, scope=SCOPE, raw_index=raw, baseline_bit=0,
                           checksum=row['checksum'], width=row['width'], native=description))
    return result


def require(ok, why):
    if not ok:
        raise ValueError(why)


def half(value):
    return int.from_bytes(struct.pack('<e', value), 'little')


def decode_vf(word):
    return dict(opcode=word & 127, funct6=(word >> 26)&63, vm=(word >> 25)&1,
                vs2=(word >> 20)&31, rs1=(word >> 15)&31, funct3=(word >> 12)&7, vd=(word >> 7)&31)


def check_vf(word, vd):
    require(decode_vf(word) == dict(opcode=0x57,funct6=0x24,vm=1,vs2=16,rs1=0,funct3=5,vd=vd),
            'not exact unmasked vfmul.vf v%d,v16,f0 encoding'%vd)


def expected_half(reg, i, recovered=False):
    if reg == 16 and i < 8:
        return half(INPUT_VALUES[i])
    if recovered and reg == 8 and i < 8:
        return half(INPUT_VALUES[i]*2)
    return (0x69a5 ^ reg*0x151 ^ i*0x35) & 0xffff


def guard(id_, high, i):
    return (0x6900 ^ id_*0x111 ^ (0xffff if high else 0) ^ i) & 0xffff


def image(id_, recovered):
    values = [guard(id_, False, i) for i in range(8)]
    values += [expected_half(r, i, recovered) for r in REGS for i in range(64)]
    values += [guard(id_, True, i) for i in range(8)]
    return b''.join(v.to_bytes(2, 'little') for v in values)


def metadata(obj, blob):
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in obj['Symbols']}
    wanted = [*WORDS, *BUFFERS, 'gap69_handler']
    selected = {n: symbols[n]['Value'] for n in wanted}
    for n, size in BUFFERS.items():
        require(symbols[n]['Size'] == size and selected[n] % 64 == 0, 'wrong buffer layout: '+n)
    require(all(0x80000000 <= p < 0x80200000 for p in selected.values()), 'symbol outside L2')
    sites = {}
    for name, word in WORDS.items():
        address = selected[name]
        matches = []
        for row in obj['Sections']:
            s = row['Section']
            if s['Flags']['Value'] & 4 and s['Address'] <= address < address+4 <= s['Address']+s['Size']:
                offset = s['Offset']+address-s['Address']
                matches.append(int.from_bytes(blob[offset:offset+4], 'little'))
        require(address % 4 == 0 and matches == [word], 'exact raw instruction differs: '+name)
        sites[name] = dict(pc=hex(address), word=hex(word))
    return dict(symbols=selected, sites=sites)


def check_log(log, source):
    require(re.findall(r'^gap35 checks=(\d+) failures=0$', log, re.M) == [str(CHECKS)],
            'wrong selfcheck count')
    require(log.splitlines().count('PASSED: '+source+'!') == 1 and
            sum(s.startswith('PASSED:') for s in log.splitlines()) == 1, 'wrong PASS source')
    require(not re.search(r'(?im)^\s*(?:FAIL|check=|Fatal:|Error:)', log), 'selfcheck failure')


def expected_memory(info):
    sym = info['symbols']
    payloads = {n: image(i, i == 2) for i, n in enumerate(
        ('gap69_seed', 'gap69_rejected', 'gap69_recovered'))}
    payloads['gap69_state'] = b''.join(v.to_bytes(8, 'little') for v in (8,9,0,117,5,BOX)*3)
    payloads['gap69_traps'] = b''.join(v.to_bytes(8, 'little') for v in
        (1,2,WORDS['gap69_illegal_site'],sym['gap69_illegal_site'],0,8,9,117,5))
    return {sym[n]+i: b for n, data in payloads.items() for i, b in enumerate(data)}


def trace_check(trace, info):
    sym = info['symbols']
    for n, word in WORDS.items():
        require(info['sites'][n] == dict(pc=hex(sym[n]), word=hex(word)), 'site metadata mismatch')
        check_vf(word,9 if n == 'gap69_illegal_site' else 8)
    pc_bad, pc_good = sym['gap69_illegal_site'], sym['gap69_legal_site']
    attempts = [(int(m[1],16), int(m[2],16)) for m in re.finditer(
        r'(?m)^core\s+0:\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)', trace)]
    require([w for p,w in attempts if p == pc_bad] == [WORDS['gap69_illegal_site']],
            'illegal attempt missing/duplicate/wrong raw word')
    require([w for p,w in attempts if p == pc_good] == [WORDS['gap69_legal_site']],
            'legal attempt missing/duplicate/wrong raw word')
    exceptions = re.findall(r'(?m)^core\s+0:\s+exception ([^,\n]+), epc 0x([0-9a-f]+)([^\n]*)', trace)
    require(len(exceptions) == 1 and exceptions[0][:2] == ('trap_illegal_instruction', f'{pc_bad:016x}'),
            'not exactly the expected illegal trap/EPC')
    require(not re.search(r'(?m)^core\s+[1-9][0-9]*:', trace), 'unexpected hart')
    commits = [(int(m[1]),int(m[2],16),int(m[3],16),m[4]) for m in re.finditer(
        r'(?m)^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)([^\n]*)$', trace)]
    require(0 < len(commits) <= MAX_RETIRED, 'empty/oversized trace')
    require(not any(pc == pc_bad for _,pc,_,_ in commits), 'illegal instruction retired')
    require([(m,w) for m,p,w,_ in commits if p == pc_good] == [(3,WORDS['gap69_legal_site'])],
            'legal recovery commit differs')
    require(sum(w == WORDS['gap69_legal_site'] for _,_,w,_ in commits) == 1 and
            sum(w == WORDS['gap69_illegal_site'] for _,_,w,_ in commits) == 0,
            'hidden multiply site')
    want = expected_memory(info)
    memory, read_bytes, vectors = {}, set(), {}
    box_seen, setup_loads, captures, legal = False, [], [], False
    for mode, pc, word, tail in commits:
        vec = {int(r):int(v,16) for r,v in re.findall(r'\bv([0-9]+)\s+0x([0-9a-f]+)', tail)}
        vectors.update(vec)
        for r, value in re.findall(r'\bf([0-9]+)\s+0x([0-9a-f]+)', tail):
            if int(r) == 0:
                if setup_loads:
                    require(int(value,16) == BOX, 'scalar is not the exact NaN-boxed half two')
                    box_seen = True
        opcode, width = word & 0x7f, (word >> 12) & 7
        accesses = [(int(a,16), int(v,16) if v else None) for a,v in
                    re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?', tail)]
        if opcode == 0x07 and width == 5:
            setup_loads.append((word >> 7) & 31)
        if pc == pc_good:
            require(box_seen, 'no boxed f0 before recovery')
            require(setup_loads == list(REGS), 'source/destination setup must be exactly nine EEW16 loads')
            for r in REGS:
                want_vec = sum(expected_half(r,i,True) << (16*i) for i in range(64))
                require(vectors.get(r) == want_vec, 'recovery full vector/tail/source differs: v'+str(r))
            legal = True
        if opcode == 0x27 and width == 5:
            r = (word >> 7) & 31
            captures.append(r)
            want_vec = sum(expected_half(r,i,legal) << (16*i) for i in range(64))
            require(r in REGS and vectors.get(r) == want_vec, 'full vector capture mismatch')
        for address, value in accesses:
            if word & 3 != 3 and word & 3 in (0,2) and (word >> 13)&7 in (2,3,6,7):
                size = 4 if (word >> 13)&7 in (2,6) else 8
            elif opcode in (0x23,0x03):
                size = 1 << (width & 3)
            elif opcode in (0x27,0x07) and width == 5:
                size = 2
            else:
                continue
            if value is not None:
                for i,b in enumerate(value.to_bytes(size, 'little')):
                    if address+i in want:
                        memory[address+i] = b
            else:
                read_bytes.update(a for a in range(address,address+size) if a in want)
    require(legal and captures == list(REGS)*2, 'must capture each register before and after recovery')
    require(memory == want, 'independent full buffer/CSR/trap byte oracle differs')
    require(set(want) <= read_bytes, 'checker did not read every buffer/CSR/trap byte')
    return dict(status='PASS', retired=len(commits), illegal_attempts=1, illegal_retirements=0,
                illegal_word=hex(WORDS['gap69_illegal_site']), illegal_epc=hex(pc_bad),
                illegal_traps=1, legal_commits=1, checked_memory_bytes=len(want),
                checked_registers=list(REGS), checks=CHECKS, tail_halfwords=120)


def vcs_stdout(log, source):
    check_log(log,source)
    require(log.count('Core Test *** SUCCESS *** (tohost = 0)') == 1 and
            len(re.findall(r'^\$finish at simulation time\s+\d+',log,re.M)) == 1,
            'missing/ambiguous VCS tohost completion')
    require(re.findall(r'^UVM_ERROR\s*:\s*(\d+)',log,re.M) == ['0'] and
            re.findall(r'^UVM_FATAL\s*:\s*(\d+)',log,re.M) == ['0'], 'nonzero/missing UVM severity totals')
    contract = re.findall(r'^\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+) '
                         r'mmu_request_cycles=\d+ protocol_errors=(\d+) outstanding=(\d+)',log,re.M)
    require(len(contract) == 1 and contract[0][0] == contract[0][1] and
            tuple(map(int,contract[0][2:])) == (1,0,0), 'wrong exception/protocol/completion contract')
    return dict(status='PASS',checks=CHECKS,tohost=0,exceptions=1)


def vcs_vector(vector_text, commit_text, info):
    """Decode accepted VRF bytes independently of the test's stdout selfcheck."""
    rows = list(csv.DictReader(io.StringIO(vector_text)))
    require(rows and rows[0]['event'] == 'config' and all(
        (int(r['nr_lanes']),int(r['vlen_bits'])) == (4,1024) for r in rows), 'wrong VRF config')
    require(all(r['event'] in ('config','alloc','write','done') for r in rows), 'reset/unknown vector event')
    state, groups, initialized = {}, {}, []
    legal_count, legal_seq, last_cycle = 0, None, -1
    seed = {(r,i): expected_half(r,i//2).to_bytes(2,'little')[i%2] for r in REGS for i in range(128)}
    result = {(r,i): expected_half(r,i//2,True).to_bytes(2,'little')[i%2] for r in REGS for i in range(128)}
    for row in rows[1:]:
        cycle, seq, vid = (int(row[n]) for n in ('cycle','arch_seq','vid'))
        require(cycle >= last_cycle,'unordered vector events'); last_cycle = cycle
        word = int(row['insn'],16)
        require(word != WORDS['gap69_illegal_site'], 'illegal odd vd reached backend')
        event, key = row['event'], (seq,vid)
        if event == 'alloc':
            require(key not in groups,'duplicate allocation')
            group = dict(insn=word,done=False,vd=int(row['vd']),eew=int(row['eew']),
                         vl=int(row['vl']),vstart=int(row['vstart']),use_vd=int(row['use_vd']))
            groups[key] = group
            if word == WORDS['gap69_legal_site']:
                check_vf(word,8)
                require(state == seed and initialized == list(REGS), 'not fully known EEW16 initial register state')
                require((group['vd'],group['eew'],group['vl'],group['vstart'],group['use_vd']) == (8,1,8,0,1),
                        'wrong legal recovery metadata')
                legal_count += 1; legal_seq = seq
            elif group['use_vd']:
                require(legal_seq is None and word & 127 == 7 and (word>>12)&7 == 5 and
                        (word>>20)&0xfff == 0x20 and
                        ((word>>7)&31,group['eew'],group['vl'],group['vstart']) == (group['vd'],1,64,0),
                        'unexpected register writer or wrong initialization EEW')
                initialized.append(group['vd'])
        else:
            require(key in groups and groups[key]['insn'] == word,'untracked/inconsistent backend event')
            group = groups[key]
            require((int(row['vd']),int(row['eew']),int(row['vl']),int(row['vstart'])) ==
                    (group['vd'],group['eew'],group['vl'],group['vstart']), 'backend metadata drift')
            if event == 'done':
                require(not group['done'],'duplicate completion'); group['done'] = True
                continue
            require(group['use_vd'] == 1 and int(row['use_vd']) == 1,'write without destination')
            lane, addr, be = int(row['lane']), int(row['addr']), int(row['be'],16)
            require(0 <= lane < 4 and 0 <= int(row['source']) < 5 and 0 < be <= 255, 'invalid accepted write')
            reg, chunk = divmod(addr,4)
            require(reg in REGS and group['eew'] == 1,'unowned register or non-EEW16 write')
            if seq == legal_seq: require(reg in (8,9),'recovery wrote non-destination')
            else: require(reg == group['vd'],'initialization wrote adjacent register')
            data = row['wdata'].lower().rjust(16,'0')
            require(len(data) == 16,'invalid write word size')
            for byte in range(8):
                if not (be >> byte)&1: continue
                text = data[14-2*byte:16-2*byte]
                require(re.fullmatch('[0-9a-f]{2}',text) is not None,'unknown accepted byte')
                slot, within = divmod(byte,2)
                natural_slot = ((slot & 1) << 1) | (slot >> 1)
                index = chunk*32+(natural_slot*4+lane)*2+within
                state[reg,index] = int(text,16)
                expected = result if seq == legal_seq else seed
                require(state[reg,index] == expected[reg,index],'independent VRF byte mismatch')
    require(legal_count == 1 and state == result and all(g['done'] for g in groups.values()),
            'missing recovery/full-register oracle/completion')
    commits = list(csv.DictReader(io.StringIO(commit_text)))
    bad, good = WORDS.values()
    requests = [r for r in commits if r['event'] == 'cvx_req' and int(r['insn'],16) == bad]
    require(len(requests) == 1,'not exactly one rejected accelerator request')
    check_vf(int(requests[0]['insn'],16),9)
    responses = [r for r in commits if r['event'] == 'cvx_resp' and int(r['trap'])]
    require(len(responses) == 1 and responses[0]['trans_id'] == requests[0]['trans_id'] and
            int(responses[0]['cycle']) >= int(requests[0]['cycle']), 'wrong rejection response')
    retired_bad = [r for r in commits if r['event'] == 'retire' and int(r['insn'],16) == bad]
    require(len(retired_bad) <= 1 and all(int(r['trap']) == 1 and
            int(r['pc'],16) == info['symbols']['gap69_illegal_site'] for r in retired_bad),
            'illegal multiply retired without trap or wrong EPC')
    retired_good = [r for r in commits if r['event'] == 'retire' and int(r['insn'],16) == good]
    require(len(retired_good) == 1 and int(retired_good[0]['trap']) == 0 and
            int(retired_good[0]['pc'],16) == info['symbols']['gap69_legal_site'], 'wrong legal recovery retirement')
    want = expected_memory(info)
    addresses = {a:b for a,b in want.items() if any(info['symbols'][n] <= a < info['symbols'][n]+BUFFERS[n]
                for n in ('gap69_traps','gap69_state'))}
    captured = {}
    for row in commits:
        if row['event'] != 'retire': continue
        mask = int(row['mem_wmask'],16)
        address, data = int(row['mem_addr'],16), int(row['mem_wdata'],16)
        for byte in range(8):
            if (mask >> byte)&1 and address+byte in addresses:
                captured[address+byte] = (data >> (byte*8))&255
    require(captured == addresses,'independent VCS trap cause2/EPC/tval or immediate CSR snapshot differs')
    return dict(status='PASS',illegal_requests=1,illegal_backend_events=0,legal_allocations=1,
                vector_register_bytes=len(state),trap_and_csr_bytes=len(captured),
                initialized_registers=initialized,all_backend_complete=True)
