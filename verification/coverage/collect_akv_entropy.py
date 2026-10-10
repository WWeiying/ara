"""Bounded independent native ISA/AKV collector; no Spike custom or admission claim."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import time

import akv_lifecycle_scalar_oracle as isa
import build_akv_descriptor_entropy_preflight as fixture
import run_gap95_simulation as life
import coverage_bitmap_delta as bitmap

require = fixture.require
CONVERTER = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')
CONVERTER_SHA = '195fae31e4cbacabcbbd97bfd61c98a333f68ff2fd013002ab322e5108f97002'


def expected_regions(s):
    bases = [s['entropy_sources']+i*256+64 for i in range(3)]
    return {
        'entropy_seed': struct.pack('<8Q', *range(0xa100,0xa108))+fixture.frame(0)[64:-64]+struct.pack('<8Q', *range(0xa200,0xa208)),
        'entropy_sources': fixture.source_bytes(),
        'entropy_descriptors': b'\xff'*64+fixture.descriptor(bases,128)+fixture.descriptor(bases,0xfffffffe),
        'entropy_snapshots': b''.join(fixture.frame(i) for i in range(6)),
        'entropy_csrs': struct.pack('<36Q', *([21,0,64,8,2,1]*6)),
        'entropy_status': struct.pack('<6I',0,1,0,0,0,0),
        'entropy_scan': struct.pack('<12I', *([512,0]*6)),
        'entropy_trap_count': struct.pack('<Q',1),
        'entropy_trap': struct.pack('<3Q',2,s['entropy_site_1'],0),
        'entropy_semantic_error': bytes(4), 'g75_trap': bytes(24),
        'g75_result': struct.pack('<2I',3932,0), 'num_failed': bytes(4), 'tohost': struct.pack('<Q',1)}


class Model(isa.Model):
    def __init__(self, blob, symbols):
        fixture.native_sites(blob,symbols)
        isa.base.Model.__init__(self,blob,symbols)
        self.requests = []

    def vector(self, word):
        op, reg, rs1 = word&127, word>>7&31, word>>15&31
        if op == 0x57:
            return isa.base.Model.vector(self,word)
        require(op in (7,0x27) and word & ~(31<<15|31<<7) ==
                (0x02005007 if op == 7 else 0x02005027) and
                (self.csr[0xc20],self.csr[0xc21],self.csr[8]) == (64,8,0), 'Vector opcode/state differs')
        address = self.gpr[rs1]
        if op == 7:
            require(reg == self.counts['vload'] < 32 and address == self.symbols['entropy_seed']+64+reg*128,
                    'Seed address/order differs')
            data = self.read(address,128)
            require(data == fixture.frame(0)[64+reg*128:64+(reg+1)*128], 'Seed bytes differ')
            self.vrf[reg] = bytearray(data)
            self.vector_effects.append(dict(kind='seed',vd=reg,data=data.hex(),pc=self.pc))
            self.counts['vload'] += 1
        else:
            phase, expected_reg = divmod(self.counts['vstore'],32)
            require(phase < 6 and reg == expected_reg and len(self.commands) == phase+1 and
                    address == self.symbols['entropy_snapshots']+phase*4224+64+reg*128,
                    'Snapshot address/order differs')
            data = bytes(self.vrf[reg])
            require(data == fixture.frame(phase)[64+reg*128:64+(reg+1)*128], 'Full VRF oracle differs')
            self.write(address,data)
            self.counts['vstore'] += 1
        self.dirty(True)

    def custom(self, word):
        phase = len(self.commands)
        require(phase < 6 and word == fixture.WORDS[phase] and
                self.pc == self.symbols['entropy_site_'+str(phase)] and self.counts['vload'] == 32 and
                self.counts['vstore'] == phase*32 and
                (self.csr[8],self.csr[0xc20],self.csr[0xc21]) == (0,64,8), 'Custom PC/opcode/state differs')
        a,b = self.gpr[10:12]
        require(b == 0 and a == (self.symbols['entropy_descriptors']+(phase-1)*64 if phase in (1,2,3) else 0),
                'Custom operands differ')
        error,data = 0,b''
        if phase in (0,5):
            self.context = None
        elif phase == 1:
            require(self.read(a,64) == b'\xff'*64, 'Invalid descriptor differs')
            error = 3
            self.context = None
        elif phase in (2,3):
            bases = [self.symbols['entropy_sources']+i*256+64 for i in range(3)]
            require(self.read(a,64) == fixture.descriptor(bases,128 if phase == 2 else 0xfffffffe),
                    'Valid descriptor differs')
            self.context = [self.read(base,128) for base in bases]
        else:
            require(self.context is not None, 'Missing recovered context')
            data = self.context[0]
            self.vrf[8] = bytearray(data)
            self.vector_effects.append(dict(kind='custom',vd=8,data=data.hex(),phase=4,pc=self.pc))
        self.commands.append(dict(phase=phase,word=word,pc=self.pc,fault=bool(error),validation_error=error,
                                  write_bytes=len(data),context_ready_after=self.context is not None))
        if error:
            require(self.csr[0x302] == self.csr[0x304] == 0 and
                    self.csr[0x305] == self.symbols['entropy_handler'], 'Trap environment differs')
            self.csr.update({0x341:self.pc,0x342:2,0x343:0})
            status = self.csr[0x300]
            self.csr[0x300] = (status & ~((1<<3)|(1<<7)|(3<<11))) | ((status>>3&1)<<7) | (3<<11)
            self.traps.append(dict(pc=self.pc,cause=2,tval=0,handler=self.csr[0x305]))
            return self.csr[0x305]
        self.dirty(True)
        return self.pc+4


def replay(blob, symbols, rows=None):
    model = Model(blob,symbols)
    retires = None if rows is None else [r for r in rows if r['event'] == 'retire']
    if retires is not None:
        require(retires and [r['order'] for r in retires] == list(range(len(retires))), 'Retirement order differs')
    index,writes = 0,0
    deadline = time.monotonic()+120
    while not model.terminal:
        require(model.steps < 300000 and time.monotonic() < deadline, 'Independent replay bound exceeded')
        word = int.from_bytes(model.read(model.pc,4),'little')
        if isa.base.native.request_instruction(word):
            model.requests.append(dict(pc=model.pc,word=word,
                response_value=model.csr[word>>20] if word&127 == 0x73 else 64 if word&127 == 0x57 else 0))
        effect = model.step()
        if retires is None:
            continue
        if effect['trap']:
            require(index < len(retires) and retires[index]['pc'] == model.pc, 'Precise trap missing handler')
            continue
        require(index < len(retires), 'Truncated retirements')
        isa.base.compare_retirement(effect,retires[index],index)
        writes += bool(effect['rd'])
        index += 1
    if retires is not None:
        require(index == len(retires), 'Post-terminal retirements')
    require(model.counts['vload'] == 32 and model.counts['vstore'] == 192 and
            model.counts['vset'] == 7 and model.counts['mret'] == 1 and len(model.commands) == 6 and
            sum(c['write_bytes'] for c in model.commands) == 128 and
            [c['validation_error'] for c in model.commands] == [0,3,0,0,0,0], 'Independent workload differs')
    for name,data in expected_regions(symbols).items():
        require(model.read(symbols[name],len(data)) == data, 'Independent final region differs: '+name)
    return model,dict(status='INDEPENDENT_NATIVE_ISA_MODEL_MATCH' if rows is not None else 'DRY_NATIVE_MODEL_ONLY',
        steps=model.steps,matched_retirements=index,GPR_writes=writes,skipped_retirements=0,
        native_Spike_comparison=False,software_adapter_only=True,coverage_admitted=False)


def lifecycle(rows, model):
    starts,pending,responses,alloc,done,active = {},{},{},{},{},{}
    commands = []
    for r in rows:
        seq,event = r['order'],r['event']
        if event == 'arch_start':
            i = len(starts)
            require(i < len(model.requests) and seq not in starts and r['insn'] == model.requests[i]['word'],
                    'Unexpected request/order')
            starts[seq] = dict(r,expected=model.requests[i])
        elif event == 'cvx_req':
            matches = [s for s in starts.values() if s['trans_id'] == r['trans_id'] and
                       s['insn'] == r['insn'] and s['order'] not in responses and
                       s['order'] not in {p['order'] for p in pending.values()}]
            require(len(matches) == 1 and r['trans_id'] not in pending and matches[0]['cycle'] <= r['cycle'],
                    'Duplicate/unbound request')
            pending[r['trans_id']] = dict(matches[0],begin=r['cycle'])
        elif event == 'cvx_resp':
            require(r['trans_id'] in pending, 'Orphan response')
            s = pending.pop(r['trans_id']); seq = s['order']
            require(seq not in responses and s['begin'] <= r['cycle'], 'Duplicate/early response')
            fault = False
            if s['insn']&127 == 0x5b:
                phase = len(commands)
                require(phase < 6 and s['insn'] == model.commands[phase]['word'], 'Custom response order')
                fault = model.commands[phase]['fault']
                commands.append(dict(model.commands[phase],seq=seq,response_cycle=r['cycle']))
            require(r['trap'] == int(fault) and r['rd_wdata'] == s['expected']['response_value'],
                    'Response exception/data differs')
            responses[seq] = r
        elif event in ('uop_alloc','uop_done'):
            require(seq in starts and r['insn'] == starts[seq]['insn'] and
                    r['trans_id'] == starts[seq]['trans_id'] and starts[seq]['cycle'] <= r['cycle'] and
                    0 <= r['port'] < 8 and r['rd_wdata'] == 0, 'Foreign backend event')
            if event == 'uop_alloc':
                require(seq not in alloc and r['port'] not in active and r['insn']&127 in (7,0x27,0x5b),
                        'Duplicate/live allocation')
                alloc[seq] = r; active[r['port']] = seq
            else:
                require(seq in alloc and seq not in done and active.get(r['port']) == seq and
                        alloc[seq]['cycle'] <= r['cycle'], 'Orphan/early done')
                done[seq] = r; del active[r['port']]
    require(len(starts) == len(responses) == len(model.requests) and not pending and not active and
            set(alloc) == set(done) and len(commands) == 6 and
            [r['insn'] for r in alloc.values()] == [r['word'] for r in model.requests if r['word']&127 in (7,0x27,0x5b)],
            'Incomplete request/backend conservation')
    probes = [r for r in rows if r['event'] == 'retire' and r['insn']&127 == 0x73 and
              r['insn']>>20 in (1,8,0xc20,0xc21,10,9) and r['insn']>>12&7 == 2 and r['insn']>>15&31 == 0]
    vsets = [r for r in rows if r['event'] == 'retire' and r['insn'] == 0x0082f057]
    require(len(probes) == 36 and len(vsets) == 7, 'Missing CSR/VSET observations')
    for phase,c in enumerate(commands):
        frame = probes[phase*6:phase*6+6]
        require([r['insn']>>20 for r in frame] == [1,8,0xc20,0xc21,10,9] and
                [r['rd_wdata'] for r in frame] == [21,0,64,8,2,1] and all(r['rd'] for r in frame) and
                max(c['response_cycle'],done[c['seq']]['cycle']) <= frame[0]['cycle'] and
                frame[-1]['cycle'] < vsets[phase+1]['cycle'], 'CSR completion/consumer boundary differs')
    return dict(commands=commands,starts=starts,allocations=alloc,done=done,requests=len(starts))


def vectors(rows, model, arch):
    require(rows and rows[0]['event'] == 'config' and sum(r['event'] == 'config' for r in rows) == 1 and
            all(int(r['nr_lanes']) == 4 and int(r['vlen_bits']) == 1024 for r in rows), 'Vector config differs')
    require(all(int(rows[0][key],16 if key in ('insn','be','wdata') else 10) == 0
                for key in ('cycle','arch_seq','vid','lane','source','insn','use_vd','vd','eew','vl','vstart','addr','be','wdata')),
            'Foreign config metadata')
    seeds = [s for s,r in arch['allocations'].items() if r['insn']&127 == 7]
    expected = {}
    for effect in model.vector_effects:
        seq = seeds[effect['vd']] if effect['kind'] == 'seed' else arch['commands'][4]['seq']
        expected[seq] = {(effect['vd'],i):v for i,v in enumerate(bytes.fromhex(effect['data']))}
    accepted = {s:{} for s in expected}
    metadata,mirrors,active = {},set(),{}
    previous = -1
    custom = {c['seq']:c for c in arch['commands']}
    for r in rows[1:]:
        event,seq,cycle,vid = r['event'],int(r['arch_seq']),int(r['cycle']),int(r['vid'])
        meta = tuple(int(r[k]) for k in ('use_vd','vd','eew','vl','vstart'))
        require(event in ('alloc','done','write') and cycle >= previous and seq in arch['allocations'] and
                int(r['insn'],16) == arch['allocations'][seq]['insn'] and vid == arch['allocations'][seq]['port'],
                'Vector identity/order differs')
        previous = cycle
        if event in ('alloc','done'):
            require(all(int(r[k],16 if k in ('be','wdata') else 10) == 0 for k in ('lane','source','addr','be','wdata')),
                    'Lifecycle has side effects')
            reference = arch['allocations'] if event == 'alloc' else arch['done']
            require((event,seq) not in mirrors and cycle == reference[seq]['cycle'], 'Mirror differs')
            mirrors.add((event,seq))
            if event == 'alloc':
                require(seq not in metadata and vid not in active, 'Duplicate vector allocation')
                op = int(r['insn'],16)&127
                use = int(custom[seq]['phase'] == 4) if op == 0x5b else int(op == 7)
                require(meta[0] == use and meta[2:] == (1,64 if op != 0x5b or use else 1,0) and
                        (not use or meta[1] == (8 if op == 0x5b else int(r['insn'],16)>>7&31)),
                        'Reservation config differs')
                metadata[seq] = meta; active[vid] = seq
            else:
                require(metadata.get(seq) == meta and active.get(vid) == seq, 'Done metadata differs')
                del active[vid]
        else:
            require(metadata.get(seq) == meta and seq in expected and
                    arch['allocations'][seq]['cycle'] <= cycle <= arch['done'][seq]['cycle'], 'Rejected/late writer')
            lane,addr,be,data = int(r['lane']),int(r['addr']),int(r['be'],16),int(r['wdata'],16)
            require(0 <= lane < 4 and 0 < be < 256 and 0 <= data <= isa.MASK and int(r['source']) == 4,
                    'Writer source/BE differs')
            reg,chunk = divmod(addr,4)
            for byte in range(8):
                if be>>byte&1:
                    slot,within = divmod(byte,2); natural = ((slot&1)<<1)|(slot>>1)
                    key = (reg,chunk*32+(natural*4+lane)*2+within)
                    require(key in expected[seq] and key not in accepted[seq] and data>>(byte*8)&255 == expected[seq][key],
                            'Wrong/duplicate/neighbor byte')
                    accepted[seq][key] = expected[seq][key]
    require(not active and set(metadata) == set(arch['allocations']) and len(mirrors) == 2*len(metadata) and
            accepted == expected, 'Missing vector effects')
    return dict(seed_bytes=4096,custom_bytes=128,snapshot_bytes=24576,full_frames=6,rejected_write_bytes=0)


def perf(log, arch):
    lines = [l for l in log.splitlines() if l.startswith('[AKV_PERF] ')]
    require(len(lines) == 6, 'Missing PERF ledger')
    result = []
    for phase,line in enumerate(lines):
        fields = [re.fullmatch(r'([a-z_][a-z_0-9]*)=([0-9]+)',t) for t in line.split()[1:]]
        require(all(fields), 'Malformed PERF')
        row = {m[1]:int(m[2]) for m in fields}
        require(len(row) == len(fields) and set(row) == set(isa.base.native.legacy.PERF_KEYS), 'PERF schema differs')
        full,invalid = phase in (1,2,3),phase == 1
        expected = dict(seq=phase+1,command=[3,0,0,0,2,3][phase],success=int(not invalid),fault=int(invalid),
            validation_fault=int(invalid),validation_error=3 if invalid else 0,read_fault=0,
            context_ready=int(phase in (2,3,4)),full=int(full),refill=0,load=int(phase == 4),release=int(phase in (0,5)),
            v2_full=0,v2_refill=0,v2_row_load=0,v2_column_load=0,v2_column_panel=0,v2_logical_column=0,
            v2_bank_conflict_cycles=0,v2_rejected=0,q_external_bytes=128 if phase in (2,3) else 0,
            kv_external_bytes=256 if phase in (2,3) else 0,replay_bytes=128 if phase == 4 else 0,
            read_ranges=1 if invalid else 4 if phase in (2,3) else 0,
            translations=0,read_payload_bytes=64 if invalid else 448 if phase in (2,3) else 0)
        require(all(row[k] == v for k,v in expected.items()) and row['busy_cycles'] > 0 and
                row['id'] == arch['allocations'][arch['commands'][phase]['seq']]['port'], 'PERF outcome differs')
        if not full:
            require(row['ar'] == row['r_beats'] == 0, 'Unexpected external read')
        result.append(row)
    return result


def range_wave(path, symbols):
    names = {k: fixture.SCOPE+'.'+k for k in ('clk_i','rst_ni','read_range_fire','read_range_vaddr','read_range_bytes','read_range_tag')}
    ids,widths,scopes,state,changes = {},{},[],{},{}
    body = False; last = -1; observed = []
    def consume():
        before = dict(state); state.update(changes); changes.clear()
        def val(values,key):
            bits = values.get(ids[key],'x')
            return int(bits,2) if set(bits) <= {'0','1'} else None
        if val(before,'clk_i') == 0 and val(state,'clk_i') == 1:
            reset = val(before,'rst_ni')
            require(reset in (0,1), 'Unknown reset at sample')
            if reset == 1:
                fire = val(before,'read_range_fire')
                require(fire in (0,1), 'Unknown range handshake')
                if fire:
                    values = [val(before,k) for k in ('read_range_vaddr','read_range_bytes','read_range_tag')]
                    require(all(v is not None for v in values), 'Unknown accepted range')
                    address,size,tag = values
                    observed.append((tag>>6,tag&63,address,size))
    with Path(path).open() as stream:
        for raw in stream:
            line = raw.strip()
            if not body:
                if line.startswith('$scope '): scopes.append(line.split()[2])
                elif line.startswith('$upscope'): scopes.pop()
                elif line.startswith('$var '):
                    parts = line.split(); name = '.'.join(scopes+[parts[4].lstrip('\\')])
                    if name in names.values():
                        key = next(k for k,v in names.items() if v == name)
                        require(key not in ids, 'Duplicate range declaration')
                        ids[key] = parts[3]; widths[key] = int(parts[2])
                elif line.startswith('$enddefinitions'):
                    require(set(ids) == set(names) and len(set(ids.values())) == len(ids) and
                            widths == dict(clk_i=1,rst_ni=1,read_range_fire=1,read_range_vaddr=64,
                                           read_range_bytes=16,read_range_tag=8), 'Range field layout differs')
                    body = True
            elif line.startswith('#'):
                stamp = int(line[1:]); require(stamp > last, 'Nonmonotonic waveform')
                consume(); last = stamp
            elif line.startswith(('b','B')):
                bits,code = line[1:].split()
                if code in ids.values():
                    key = next(k for k,v in ids.items() if v == code)
                    require(set(bits.lower()) <= set('01xz') and len(bits) <= widths[key], 'Malformed/oversize range value')
                    changes[code] = bits.lower()
            elif line and line[0].lower() in '01xz' and line[1:] in ids.values():
                key = next(k for k,v in ids.items() if v == line[1:])
                require(widths[key] == 1, 'Scalar encoding of vector')
                changes[line[1:]] = line[0].lower()
    require(body, 'Missing VCD header'); consume()
    expected = []
    bases = [symbols['entropy_sources']+i*256+64 for i in range(3)]
    for phase in (1,2,3):
        expected.append((0,0,symbols['entropy_descriptors']+(phase-1)*64,64))
        if phase != 1:
            expected.extend((role,0,address,size) for role,address,size in fixture.ranges(bases,128 if phase == 2 else 0xfffffffe))
    require(observed == expected, 'Actual range addresses/roles/length/order differ')
    return dict(accepted_ranges=observed,invalid_descriptor_payload_ranges=0,high_stride_actual_legal_addresses=True,
                sampling='pre-timebucket values at posedge',native_subfields_claimed=False)


def terminal_gate(status,started,manifest,run,image,elf):
    require(set(status) == {'status','returncode','timeout','pid','coverage_admitted'} and
            status['status'] == 'SIMULATION_EXITED_NOT_ADMITTED' and type(status['returncode']) is int and
            status['returncode'] == 0 and status['timeout'] is False and status['coverage_admitted'] is False and
            type(status['pid']) is int and status['pid'] > 0, 'Nonterminal/failed/typed runtime')
    require(type(started.get('pid')) is int and started['pid'] == status['pid'] and
            type(started.get('starttime')) is int and started['starttime'] > 0 and
            started.get('live_identity_verified') is True and started.get('cwd') == str(run) and
            started.get('exe') == str(image) and started.get('executable_sha256') == manifest['pins'][str(image)] and
            started.get('input_elf') == str(elf) and started.get('elf_sha256') == manifest['pins'][str(elf)] and
            started.get('command') == manifest['command'] and type(started.get('budget_s')) is int and
            started['budget_s'] == 600, 'Actual execution identity differs')


def contract(log,requests):
    lines = [l for l in log.splitlines() if l.startswith('[ARA_CONTRACT]')]
    require(len(lines) == 1 and lines[0].startswith('[ARA_CONTRACT] '), 'Unique native contract required')
    fields = [re.fullmatch(r'([a-z_]+)=(0|[1-9][0-9]*)',t) for t in lines[0].split()[1:]]
    require(all(fields), 'Malformed native contract')
    row = {m[1]:int(m[2]) for m in fields}
    expected = dict(requests=requests,responses=requests,exceptions=1,mmu_request_cycles=0,
                    protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0)
    require(len(fields) == len(row) and row == expected, 'Native contract schema/conservation differs')
    return row


def independent_or(before, single, combined):
    require(before['design'] == single['design'] == combined['design'] and
            combined['tests'] == before['tests']+single['tests'] and len(single['tests']) == 1 and
            len(set(combined['tests'])) == len(combined['tests']), 'Raw membership/design differs')
    for metric,rows in before['metrics'].items():
        require(set(rows) == set(single['metrics'][metric]) == set(combined['metrics'][metric]), 'Raw universe differs')
        for name,row in rows.items():
            add = single['metrics'][metric][name]; result = combined['metrics'][metric][name]
            require((row['width'],row['checksum']) == (add['width'],add['checksum']) ==
                    (result['width'],result['checksum']) and
                    int(result['bits'],16) == int(row['bits'],16)|int(add['bits'],16), 'Independent raw OR differs')


def raw_gain(run,manifest,output,pins):
    base = life.read_bound(Path(manifest['baseline'])/'admission-manifest.json',manifest['baseline_sha256'])
    bits_path = Path(manifest['baseline'])/'combined-bits.json'
    before = life.read_bound(bits_path,base['output_pins'][str(bits_path)])
    ledger_path = Path(manifest['baseline'])/'combined-inputs.txt'
    require(fixture.sha(ledger_path) == base['output_pins'][str(ledger_path)], 'Baseline ledger drift')
    ledger = ledger_path.read_text().splitlines()
    require(before['tests'] == ledger[1:] and len(before['tests']) == 775 and
            str(run/'code.vdb') not in ledger, 'Formal775 unique extension required')
    single_inputs = output/'single-inputs.txt'
    with single_inputs.open('x') as stream:
        stream.write(ledger[0]+'\n'+str(run/'code.vdb')+'\n')
    single = bitmap.collect(single_inputs)
    pins = life.merge_pins(pins,single['input_hashes'])
    for relative,h in single['design'].items():
        path = Path(ledger[0])/'snps/coverage/db'/relative
        require(base['input_pins'].get(str(path)) == h, 'Unbound compiled raw input')
        pins = life.merge_pins(pins,{str(path):h})
    after = bitmap.combine(before,single)
    independent_or(before,single,after)
    require(sum(len(rows) for rows in before['metrics'].values()) == 6162, 'Exact6162 raw instances required')
    cache_path = fixture.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
    cache = life.read_bound(cache_path,manifest['pins'][str(cache_path)])
    scope = fixture.SCOPE
    t_before = {scope:{k:cache['instances'][scope][k] for k in ('width','checksum','bits')}}
    for vdb in ledger[742:]:
        files = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Ambiguous admitted Toggle XML')
        path = files[0]
        require(str(path) in base['input_pins'], 'Unbound admitted Toggle input')
        rows,h = fixture.toggle.rows(path,[scope])
        require(h == base['input_pins'][str(path)], 'Admitted Toggle input drift')
        pins = life.merge_pins(pins,{str(path):h})
        t_before = fixture.toggle.union(t_before,rows)
    files = list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files) == 1, 'Ambiguous singleton Toggle XML')
    t_single,h = fixture.toggle.rows(files[0],[scope])
    pins = life.merge_pins(pins,{str(files[0]):h})
    t_after = fixture.toggle.union(t_before,t_single)
    old,new = t_before[scope],t_after[scope]
    require(old['checksum'] == new['checksum'] == '4015856550', 'Toggle compiled identity differs')
    gain = int(new['bits'],16)&~int(old['bits'],16)
    diagnostic = dict(baseline_tests=775,not_official_percent=True,coverage_admitted=False,
        scope=scope,width=old['width'],checksum=old['checksum'],before=old,single=t_single[scope],after=new,
        new_positions=bin(gain).count('1'),new_serialized_indices=[i for i in range(old['width']) if gain>>(old['width']-1-i)&1])
    for name,value in [('single-bits.json',single),('combined-bits-diagnostic.json',after),
                       ('raw-delta.json',bitmap.delta(before,after)),('toggle-gain775.json',diagnostic)]:
        life.save(output/name,value)
    return pins


def collect(run, seal, output):
    import run_akv_entropy as runner
    run,output = Path(run).absolute(),Path(output).absolute()
    require(output.parent == life.OUT and not output.exists(), 'Fresh collector output')
    manifest = life.read_bound(run/'manifest.json',seal)
    require(life.read_bound(run.with_name(run.name+'.prepared.json'),seal) == manifest and
            runner.prepare(run,existing=True)[1] == manifest, 'Prepared/executed contract differs')
    terminal = json.loads((run/'simulation-status.json').read_bytes())
    started = json.loads((run/'started.json').read_bytes())
    terminal_gate(terminal,started,manifest,run,life.IMAGE,runner.ELF)
    inputs = [run/n for n in ('manifest.json','simulation-status.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv','entropy-ranges.vpd')]
    inputs += [p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    require((run/'code.vdb').is_dir() and all(p.is_file() and not p.is_symlink() for p in inputs), 'Incomplete/aliased artifacts')
    pins = life.merge_pins(manifest['pins'],{str(p):fixture.sha(p) for p in inputs})
    life.check(pins); output.mkdir()
    try:
        require(fixture.sha(CONVERTER) == CONVERTER_SHA and pins.get(str(CONVERTER)) == CONVERTER_SHA,
                'Unbound fixed converter')
        vcd = output/'entropy-ranges.vcd'
        conversion = [str(CONVERTER),str(run/'entropy-ranges.vpd'),str(vcd)]
        life.save(output/'conversion-command.json',conversion)
        with (output/'conversion.log').open('x') as log:
            subprocess.run(conversion,stdout=log,stderr=subprocess.STDOUT,timeout=120,check=True)
        require(vcd.is_file() and not vcd.is_symlink() and vcd.stat().st_size <= 256*1024*1024,
                'Missing/oversize converted range evidence')
        pins = life.merge_pins(pins,{str(vcd):fixture.sha(vcd)})
        rows = isa.base.native.commit_rows(run/'commit_trace.csv')
        model,scalar = replay(Path(manifest['preflight']['input_elf']).read_bytes(),manifest['preflight']['symbols'],rows)
        arch = lifecycle(rows,model)
        vector = vectors(isa.base.native.common.read_csv(run/'vector_trace.csv',isa.base.native.common.VECTOR_FIELDS),model,arch)
        log = (run/'run.vcs.log').read_text()
        require(log.count('Core Test *** SUCCESS ***') == 1 and not re.search(r'(?m)^.*UVM_(?:ERROR|FATAL)(?!\s*:\s*0\s*$)',log), 'Runtime failure')
        native_contract = contract(log,arch['requests'])
        console = (run/'console.log').read_text().splitlines()
        require(console.count('ENTROPY_RANGE_READY') == 1 and
                sorted(l for l in console if l.startswith('ENTROPY_RANGE_OBJECT ')) ==
                sorted('ENTROPY_RANGE_OBJECT '+fixture.SCOPE+'.'+k for k in
                       ('clk_i','rst_ni','read_range_fire','read_range_vaddr','read_range_bytes','read_range_tag')) and
                not any(l.startswith('ENTROPY_RANGE_ERROR ') for l in console), 'Probe markers differ')
        observations = range_wave(vcd,manifest['preflight']['symbols'])
        perf_rows = perf(log,arch)
        for name,value in [('scalar.json',scalar),('lifecycle.json',arch),('vector.json',vector),('ranges.json',observations),('perf.json',perf_rows),('contract.json',native_contract)]:
            life.save(output/name,value)
        pins = raw_gain(run,manifest,output,pins)
        life.check(pins)
        life.save(output/'qualification.json',dict(status='AKV_ENTROPY_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED',
            input_pins=pins,output_pins={str(p):fixture.sha(p) for p in output.iterdir()},baseline_tests=775,
            native_Spike_comparison=False,software_adapter_not_native=True,scalar_model_skips=0,coverage_admitted=False))
    except Exception as error:
        life.save(output/'failure.json',dict(reason=str(error),coverage_admitted=False)); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--run-seal',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); collect(args.run,args.run_seal,args.output)
