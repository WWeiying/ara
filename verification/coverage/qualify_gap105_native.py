"""Complete bounded software/native evidence; NOT a scalar ISA emulator/admission."""
import argparse
import csv
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
import run_gap105_simulation as runner
life = runner.life
sys.path.insert(0,str(life.ROOT/'verification'))
from ara_verify.contract import check_contract_log, parse_contract_summary
from ara_verify.trace import validate_trace
from ara_verify.vector_commit import (_parse_vector_trace, _architectural_bytes,
    _parse_architecture_mapping, _map_architecture_retires)
from ara_verify.spike_trace import _scalar_memory_access

WORD = 0x0eb5045b
DISPATCHER_SHA = '9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'


def require(ok, message):
    if not ok: raise ValueError(message)


def elf_view():
    metadata = json.loads((runner.PRE/'dut.metadata.log').read_bytes())[0]
    symbols = {}
    for row in metadata['Symbols']:
        s = row['Symbol']; name = s['Name']['Name']
        if name and not name.startswith('$'):
            require(name not in symbols,'Duplicate ELF symbol: '+name)
            symbols[name] = (s['Value'],s['Size'])
    blob = runner.ELF.read_bytes()
    sections = [r['Section'] for r in metadata['Sections']]
    def data(address, size):
        candidates = [s for s in sections if s['Type']['Name'] != 'SHT_NOBITS' and
                      s['Address'] <= address and address+size <= s['Address']+s['Size']]
        require(len(candidates)==1,'Ambiguous/unmapped ELF bytes')
        s = candidates[0]; offset = s['Offset']+address-s['Address']
        raw = blob[offset:offset+size]
        require(len(raw)==size,'Truncated ELF bytes')
        return raw
    sites = []
    for phase in (0,1):
        address,size = symbols['gap105_exec%d'%phase]
        raw = data(address,size); offset = 0; memory = []
        while offset < size:
            half = int.from_bytes(raw[offset:offset+2],'little')
            width = 4 if half & 3 == 3 else 2
            require(offset+width <= size,'Truncated instruction')
            word = int.from_bytes(raw[offset:offset+width],'little')
            if width == 4 and word & 0x7f in (7,39) and (word>>12)&7 == 6:
                memory.append(dict(pc=address+offset,word=word,store=word&0x7f==39,
                                   register=(word>>7)&31))
            offset += width
        require([(s['store'],s['register']) for s in memory] ==
                [(False,r) for r in (0,8,16,24)]+[(True,r) for r in (0,8,16,24)],
                'Exact four seed loads/four snapshot stores differ')
        sites.append(memory)
        pc = symbols['gap105_qbexec_site%d'%phase][0]
        require(int.from_bytes(data(pc,4),'little')==WORD,'Actual custom ELF word differs')
    return symbols,data,sites


def independent_native():
    weight = (runner.PRE/'weight-native.bin').read_bytes()
    rows = (runner.PRE/'activation-row-native.bin').read_bytes()
    require(len(weight)==176 and len(rows)==2336,'Native fixture sizes differ')
    d,dmin = struct.unpack_from('<ee',weight)
    require((d,dmin)==(1.,0.),'Only exact known finite scale fixture supported')
    packed = bytearray(2336); outputs = []
    for c in range(8):
        row = rows[c*292:(c+1)*292]
        ad = struct.unpack_from('<f',row)[0]
        require(ad==1.,'Exact native activation scale differs')
        qs = struct.unpack_from('<256b',row,4)
        sums = struct.unpack_from('<16h',row,260)
        require(all(sum(qs[g*16:g*16+16])==sums[g] for g in range(16)),
                'Independent Q8 bsums mismatch')
        dot = correction = 0
        for g in range(8):
            s = weight[4:16]
            scale = s[g]&63 if g<4 else (s[g+4]&15)|((s[g-4]>>6)<<4)
            minimum = s[g+4]&63 if g<4 else (s[g+4]>>4)|((s[g]>>6)<<4)
            for i in range(32):
                quant = ((weight[48+(g//2)*32+i]>>(4*(g&1)))&15)|(((weight[16+i]>>g)&1)<<4)
                dot += scale*quant*qs[g*32+i]
                correction += minimum*qs[g*32+i]
        require(dot==256*(c+1) and correction==0,'Known fixture independent MAC differs')
        outputs.append(struct.unpack('<I',struct.pack('<f',float(dot)))[0])
        for b,value in enumerate(row):
            offset = 4*c+b if b<4 else 32+(b-4)*8+c if b<260 else 2080+((b-260)//2*8+c)*2+(b&1)
            packed[offset] = value
    return weight,bytes(packed),outputs


def seed_image(phase):
    return b''.join(struct.pack('<I',0x41000100+phase*0x10000+17*w) for w in range(1024))


def regions(phase, symbols, data, native):
    weight,activation,outputs = native
    seed = seed_image(phase); actual = bytearray(seed)
    for c,bits in enumerate(outputs): struct.pack_into('<I',actual,1024+c*128,bits)
    before = b''.join(struct.pack('<I',0x13570000+i) for i in range(16))
    after = b''.join(struct.pack('<I',0x24680000+i) for i in range(16))
    w = bytes([0xa5])*64+weight+bytes([0xa5])*(800-64-176)
    a = bytes([0x5a])*(68+4*phase)+activation+bytes([0x5a])*(2496-68-4*phase-2336)
    for name,expected in [('gap105_weights%d'%phase,w),('gap105_activation%d'%phase,a)]:
        address,size = symbols[name]
        require(size==len(expected) and data(address,size)==expected,'ELF source/model bytes differ: '+name)
    # ABI v2/Q5_K/Q8_K/row-major/M8-interleaved/DIRECT, N=K=1.
    descriptor = bytes([0xc3])*64+struct.pack('<QQ',2|(4<<4)|(1<<8)|(1<<12)|(3<<16),
                                             symbols['weights'][0]+64)+bytes([0xc3])*64
    csr = b''.join(struct.pack('<Q',v) for v in
        [0x1234567800000000+i for i in range(4)]+[1,16,0,2,8,5]*2+
        [0x8765432100000000+i for i in range(4)])
    values = dict(initial=before+seed+after,actual=before+actual+after,weights=w,
                  activation=a,descriptor_packet=descriptor,csr_packet=csr)
    require(all(symbols[n][1]==len(b) for n,b in values.items()),'Complete region ELF sizes differ')
    return values


def scalar_access(word):
    if word & 3 == 3: return _scalar_memory_access(word)
    quadrant,funct3 = word&3,word>>13
    if quadrant in (0,2):
        return {2:('read',4),3:('read',8),6:('write',4),7:('write',8)}.get(funct3)
    return None


def readback(rows, begin, end, symbols, expected):
    observed = {n:set() for n in expected}
    for row in rows:
        if row['event']!='retire' or not begin<=int(row['cycle'])<end: continue
        address = int(row['mem_addr'],16); mask = int(row['mem_rmask'],16)
        if not mask: continue
        access = scalar_access(int(row['insn'],16))
        require(access is not None and access[0]=='read','Unknown scalar read encoding')
        size = access[1]
        require(address%size==0 and mask==((1<<size)-1)<<(address&7), 'Read address/mask differs')
        for name,blob in expected.items():
            base = symbols[name][0]
            if address+size<=base or address>=base+len(blob): continue
            require(base<=address and address+size<=base+len(blob) and int(row['rd'])!=0 and
                    not int(row['trap']), 'Partial/unobservable/trapped region read')
            value = int(row['rd_wdata'],16)&((1<<(8*size))-1)
            offset = address-base
            require(value.to_bytes(size,'little')==blob[offset:offset+size],
                    'Readback differs: %s offset%d'%(name,offset))
            observed[name].update(range(offset,offset+size))
    for name,blob in expected.items():
        require(observed[name]==set(range(len(blob))),'Incomplete readback: '+name)
    return {n:len(b) for n,b in expected.items()}


def activity_bytes(activity, expected, start, response, custom=False):
    require(activity.allocations==activity.completions==1 and activity.use_vd and
            activity.eew==2 and activity.vstart==0,'Activity metadata/lifecycle differs')
    if custom:
        require((activity.instruction,activity.vd,activity.vl)==(WORD,8,256),
                'M8 internal reservation differs (not CSR VL1)')
    require(all(start<=w.cycle<=response and w.eew==2 and 0<=w.lane<4 and
                w.be>0 and w.be&~w.known_be==0 and w.source==4
                for w in activity.writes),'Unknown/out-of-window/write source differs')
    values = _architectural_bytes(activity.writes,4,1024)
    require({k:v for k,(v,w) in values.items()}==expected and
            sum(bin(w.be).count('1') for w in activity.writes)==len(expected),
            'Exact bytes differ or duplicate write')
    if custom:
        require(len(activity.writes)==8 and all(w.be==15 and w.lane==0 for w in activity.writes),
                'M8 N1 active-only commit mask differs')


def phase_readback(rows, start, end, symbols, expected):
    descriptor = symbols['descriptor_packet'][0]
    resets = [int(r['cycle']) for r in rows if r['event']=='retire' and start<int(r['cycle'])<end and
              int(r['mem_wmask'],16) and descriptor<=int(r['mem_addr'],16)<descriptor+144]
    if resets: end = min(resets)
    return readback(rows,start,end,symbols,expected)


def software(log):
    text = log.read_text(); lines = text.splitlines()
    expected = ['GAP105 command=0 checks=17 errors=0','GAP105 command=1 checks=17 errors=0',
        'GAP105 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
        'PASSED: qbs_gap105_m8_phase8 checks=41 errors=0']
    require(all(lines.count(line)==1 for line in expected),'Missing/duplicate full software selfcheck')
    require(not check_contract_log(log) and text.count('Core Test *** SUCCESS ***')==1 and
            not re.search(r'FAIL|Error:|Fatal:',text),'TB terminal/contract error')
    summary = [parse_contract_summary(l) for l in lines if '[ARA_CONTRACT]' in l]
    require(len(summary)==1 and summary[0] is not None and summary[0]['exceptions']==0,
            'Unexpected exception/contract')
    return summary[0]


def runtime(run, symbols, data, sites, native):
    contract = software(run/'run.vcs.log')
    trace = validate_trace(run/'commit_trace.csv')
    with (run/'commit_trace.csv').open() as stream: rows = list(csv.DictReader(stream))
    retires = [r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retires]==list(range(len(retires))) and
            all(not int(r['trap']) for r in retires),'Incomplete/trapped retirement prefix')
    pending = {}; starts = {}; responses = {}; request_count = response_count = 0
    for row in rows:
        event = row['event']; key = int(row['trans_id']); cycle = int(row['cycle'])
        if event=='arch_start':
            seq = int(row['order']); require(seq not in starts,'Duplicate arch_start')
            starts[seq] = (int(row['insn'],16),key,cycle)
        elif event=='cvx_req':
            require(key not in pending,'Duplicate transaction')
            pending[key] = (int(row['insn'],16),cycle); request_count += 1
        elif event=='cvx_resp':
            require(key in pending and not int(row['trap']),'Orphan/trapped response')
            word,begin = pending.pop(key); require(begin<=cycle,'Response before request')
            responses.setdefault((word,key),[]).append((begin,cycle)); response_count += 1
    require(not pending and request_count==response_count==contract['requests'],
            'Complete request/response/contract conservation differs')
    arch,retires_mapped,trapped = _parse_architecture_mapping(run/'commit_trace.csv')
    mapping = _map_architecture_retires(arch,retires_mapped,trapped)
    lanes,vlen,activities = _parse_vector_trace(run/'vector_trace.csv')
    require((lanes,vlen)==(4,1024),'Wrong vector configuration')
    wanted = []
    for phase in (0,1):
        wanted += [s['pc'] for s in sites[phase][:4]]+[symbols['gap105_qbexec_site%d'%phase][0]]
        wanted += [s['pc'] for s in sites[phase][4:]]
    selected = sorted(activities,key=lambda s:starts[s][2])
    require(len(selected)==18 and [mapping[s].pc for s in selected]==wanted,
            'Unexpected/missing seed/custom/snapshot activities')
    retire_cycles = {}
    for seq in selected:
        matched = [r for r in retires if int(r['pc'],16)==mapping[seq].pc and
                   int(r['insn'],16)==mapping[seq].instruction]
        require(len(matched)==1,'Ambiguous site retirement')
        retire_cycles[seq] = int(matched[0]['cycle'])
    owners = {}; done = set()
    with (run/'vector_trace.csv').open() as stream:
        for row in csv.DictReader(stream):
            if row['event']=='config': continue
            require(row['event'] in ('alloc','write','done'),'Unexpected vector event/reset')
            seq,vid,cycle = int(row['arch_seq']),int(row['vid']),int(row['cycle'])
            require(seq in activities,'Unbound vector activity')
            if row['event']=='alloc':
                require(seq not in owners and seq not in done,'Duplicate vector allocation')
                owners[seq] = (vid,cycle)
            else:
                require(seq in owners and owners[seq][0]==vid and owners[seq][1]<=cycle,
                        'Vector event outside lifecycle')
                if row['event']=='done':
                    require(cycle<=retire_cycles[seq],'Vector completion after retirement')
                    owners.pop(seq); done.add(seq)
    require(not owners and done==set(selected),'Incomplete vector lifecycle')
    commit_uops = [(r['event'],int(r['order']),int(r['port']),int(r['cycle'])) for r in rows
                  if r['event'] in ('uop_alloc','uop_done')]
    with (run/'vector_trace.csv').open() as stream:
        vector_uops = [('uop_'+r['event'],int(r['arch_seq']),int(r['vid']),int(r['cycle']))
                       for r in csv.DictReader(stream) if r['event'] in ('alloc','done')]
    require(sorted(commit_uops)==sorted(vector_uops),'Commit/vector lifecycle probes differ')
    bindings = []
    for phase in (0,1):
        group = selected[phase*9:(phase+1)*9]; custom_seq = group[4]
        for i,seq in enumerate(group):
            a = activities[seq]; word,key,start = starts[seq]; retired = mapping[seq]
            require(a.instruction==word==retired.instruction,'Opcode/activity/retirement differs')
            match = [(begin,end) for begin,end in responses.get((word,key),[]) if start<=begin<=end<=retire_cycles[seq]]
            require(len(match)==1,'Ambiguous/missing activity response')
            begin,end = match[0]
            if i<4:
                reg = i*8; seed = seed_image(phase)
                require(a.vd==reg and a.vl==256,'Complete seed load configuration differs')
                expected = {(r,b):seed[r*128+b] for r in range(reg,reg+8) for b in range(128)}
                activity_bytes(a,expected,start,end)
            elif i==4:
                expected = {(8+c,b):value for c,bits in enumerate(native[2])
                            for b,value in enumerate(struct.pack('<I',bits))}
                activity_bytes(a,expected,start,end,custom=True)
                require(len(responses.get((WORD,key),[]))==1,'Replayed custom command')
            else:
                require(not a.writes and a.allocations==a.completions==1,'Snapshot store wrote VRF/incomplete')
        require(all(retire_cycles[s]<=starts[custom_seq][2] for s in group[:4]) and
                all(retire_cycles[custom_seq]<=starts[s][2] for s in group[5:]),
                'Seed/custom/snapshot ordering differs')
        if phase:
            require(retire_cycles[selected[8]]<starts[group[0]][2],'Commands overlap')
        start = retire_cycles[custom_seq]
        end = starts[selected[9]][2] if phase==0 else max(int(r['cycle']) for r in rows)+1
        # Stop before the following command reinitializes the shared descriptor.
        evidence = phase_readback(rows,start,end,symbols,regions(phase,symbols,data,native))
        bindings.append(dict(phase=4+4*phase,arch_seq=custom_seq,pc=mapping[custom_seq].pc,
            backend_vl=256,software_vl=1,native_active_write_bytes=32,readback_bytes=evidence))
    require(sum(a.instruction==WORD for a in activities.values())==2,'Custom population differs')
    return dict(status='COMPLETE_SOFTWARE_NATIVE_QUALIFIER_PASS_NOT_FULL_SCALAR_ISA',
        contract=contract,trace=trace,bindings=bindings,custom_write_bytes=64,full_vrf_bytes=8192,
        initial_vrf_bytes=8192,csr_values=24,source_guard_bytes=6880,checks=41,
        full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False)


def prepare(run, reviewed_seal):
    run = Path(run).absolute()
    require(run.parent==life.OUT and run.resolve()==run,'Foreign/aliased run')
    record = run.with_name(run.name+'.prepared.json')
    config = life.read_bound(record,reviewed_seal)
    require(config['command']==runner.command(run) and config['timeout_s']==1200 and
            config['preflight']==life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL),
            'Reviewed run contract differs')
    runner.validate(config['preflight'])
    pins = life.merge_pins({},config['pins'])
    pins = life.merge_pins(pins,{str(record):reviewed_seal})
    build = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    require(str(build) in pins,'Missing historical build source manifest pin')
    build_pins = life.read_bound(build,pins[str(build)])
    dispatcher = life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    require(build_pins[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]==DISPATCHER_SHA,
            'Historical dispatcher source identity differs')
    pins = life.merge_pins(pins,{str(dispatcher):DISPATCHER_SHA})
    sources = [life.ROOT/'hardware/src/vlsu/qbs/qbs_commit.sv',
               life.ROOT/'hardware/tb/ara_commit_monitor.sv']
    for source in sources: pins = life.merge_pins(pins,{str(source):build_pins[str(source)]})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_qualify_gap105_native.py'),
                 Path(sys.modules[validate_trace.__module__].__file__).resolve(),
                 Path(sys.modules[check_contract_log.__module__].__file__).resolve(),
                 Path(sys.modules[_architectural_bytes.__module__].__file__).resolve(),
                 Path(sys.modules[_scalar_memory_access.__module__].__file__).resolve()):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    require("ara_req.vl = vlen_t'(qbs_m * (VLEN / 32));" in dispatcher.read_text(),
            'Historical internal VL formula differs')
    commit_source = sources[0].read_text()
    require("? {{4{high_active}}, {4{low_active}}} : 8'hff;" in commit_source and
            "element < unsigned'(n_q)" in commit_source,'Historical active-only wide mask differs')
    symbols,data,sites = elf_view(); native = independent_native()
    for phase in (0,1): regions(phase,symbols,data,native)
    require(native[2]==config['preflight']['expected_bits_per_command'],'Independent Python/C native oracle differs')
    life.check(pins)
    return dict(status='GAP105_NATIVE_QUALIFIER_PREPARED_NOT_EXECUTED',run=str(run),
        run_prepared_seal=reviewed_seal,pins=pins,native_expected_bits=native[2],
        scope='Complete software/native only; no full scalar ISA claim',coverage_admitted=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','collect'))
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--prepared-seal',required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--config-seal')
    args = parser.parse_args(argv)
    require((args.mode=='collect')==bool(args.config_seal),'Collect alone requires reviewed qualifier seal')
    output = args.output.absolute()
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(),'Fresh independent sidecar required')
    config = prepare(args.run,args.prepared_seal)
    path = output.with_name(output.name+'.prepared.json')
    if args.mode=='prepare':
        life.save(path,config)
        print(json.dumps(dict(config=str(path),seal=life.digest(path),pins=len(config['pins'])))); return
    require(life.read_bound(path,args.config_seal)==config,'Reviewed qualifier config differs')
    run = Path(config['run']); pins = life.merge_pins(config['pins'],{str(path):args.config_seal})
    required = [run/n for n in ('simulation-status.json','manifest.json','started.json',
                               'console.log','run.vcs.log','commit_trace.csv','vector_trace.csv')]
    required += [p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    require(any(p.name=='cond.verilog.data.xml' for p in required),'Missing raw condition bitmap')
    for p in required: pins = life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    status = json.loads((run/'simulation-status.json').read_bytes())
    require(status.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and status.get('returncode')==0 and
            status.get('coverage_admitted') is False,'Not a clean terminal run')
    reviewed = life.read_bound(run.with_name(run.name+'.prepared.json'),args.prepared_seal)
    require(json.loads((run/'manifest.json').read_bytes())==reviewed,'Runtime manifest differs')
    output.mkdir()
    life.save(output/'evidence-pins.json',pins)
    try:
        symbols,data,sites = elf_view()
        audit = runtime(run,symbols,data,sites,independent_native())
        life.check(pins)
        life.save(output/'runtime-audit.json',audit)
        life.save(output/'qualification.json',dict(status='GAP105_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',
            audit_sha256=life.digest(output/'runtime-audit.json'),pins_sha256=life.digest(output/'evidence-pins.json'),
            full_scalar_isa_verified=False,coverage_admitted=False,coverage_increment_measured=False,
            gain_requires_latest_formal_baseline=True,simulation_rerun=False,rtl_changed=False))
    except Exception as error:
        life.save(output/'qualification.json',dict(status='GAP105_NATIVE_QUALIFIER_REJECTED',
            reason=type(error).__name__+': '+str(error),coverage_admitted=False))
        raise
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'qualification.json'))))


if __name__=='__main__': main()
