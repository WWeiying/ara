"""GAP108 exact software/native qualification; never full scalar ISA or admission."""
import argparse
from fractions import Fraction
import csv
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
import run_gap108_simulation as runner
import qualify_gap105_native as support
import qualify_gap105_native_v5 as reviewed
import rv64_compressed_memory as compressed

life, require = runner.life, support.require
WORD = 0x00b5045b
RUN = life.OUT/'gap108-subnormal-old-image-parent-20261006-01'
RUN_SEAL = 'ad154bde3b72c06ba41b243e0beac70462ac2e467c1275fa8ba12cff92414666'
BUILD = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BUILD_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
DISPATCHER_SHA = '9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'
seed_image = support.seed_image

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
        address,size = symbols['gap108_exec%d'%phase]
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
        pc = symbols['gap108_qbexec_site%d'%phase][0]
        require(int.from_bytes(data(pc,4),'little')==WORD,'Actual custom ELF word differs')
    return symbols,data,sites


def half_to_single(bits):
    sign, exponent, fraction = (bits & 0x8000) << 16, (bits >> 10) & 31, bits & 1023
    if exponent == 31:
        return sign | 0x7f800000 | ((fraction << 13) | 0x400000 if fraction else 0)
    if exponent:
        return sign | ((exponent + 112) << 23) | (fraction << 13)
    if not fraction:
        return sign
    top = fraction.bit_length() - 1
    return sign | ((top + 103) << 23) | ((fraction - (1 << top)) << (23 - top))


def integer_single(value):
    if not value:
        return 0
    magnitude = abs(value); top = magnitude.bit_length() - 1
    require(top <= 23, 'Bounded exact integer conversion exceeded')
    return (0x80000000 if value < 0 else 0) | ((top + 127) << 23) | ((magnitude - (1 << top)) << (23 - top))


def binary_power(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def finite_value(bits):
    require(type(bits) is int and 0 <= bits <= 0xffffffff, 'Malformed FP32 bits')
    exponent, mantissa = (bits >> 23) & 255, bits & 0x7fffff
    require(exponent != 255, 'Nonfinite value outside GAP108 oracle')
    significand = mantissa | (0x800000 if exponent else 0)
    value = significand * binary_power(exponent - 150 if exponent else -149)
    return -value if bits & 0x80000000 else value


def round_single(value):
    """Exact rational RNE with tininess after rounding; no host float."""
    require(isinstance(value, Fraction) and value.denominator & (value.denominator - 1) == 0,
            'Only exact binary rational arithmetic')
    sign = 0x80000000 if value < 0 else 0
    value = abs(value)
    if not value:
        return 0, 0
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < binary_power(exponent):
        exponent -= 1
    units = value / binary_power(max(-149, exponent - 23))
    floor = units.numerator // units.denominator
    remainder = units - floor
    rounded = floor + int(remainder > Fraction(1,2) or
                          (remainder == Fraction(1,2) and floor & 1))
    flags = int(bool(remainder))
    if exponent < -126:
        if rounded < 0x800000:
            return sign | rounded, flags | (2 if flags else 0)
        exponent = -126
    if rounded >= 0x1000000:
        rounded >>= 1
        exponent += 1
    if exponent > 127:
        return sign | 0x7f800000, 5
    return sign | ((exponent + 127) << 23) | (rounded & 0x7fffff), flags


def finite_fma(a, b, c):
    va, vb, vc = map(finite_value, (a,b,c))
    value = va * vb + vc
    if not value and (not va or not vb) and not vc:
        return (a ^ b) & c & 0x80000000, 0
    return round_single(value)


def independent_native(pre=runner.PRE):
    values = []
    for phase in (0, 1):
        activation = (pre/('activation-native%d.bin' % phase)).read_bytes()
        require(len(activation) == 292, 'Q8_K row size differs')
        ad = struct.unpack_from('<I', activation)[0]
        qs = struct.unpack_from('<256b', activation, 4)
        sums = struct.unpack_from('<16h', activation, 260)
        require(all(sum(qs[16*i:16*i+16]) == sums[i] for i in range(16)),
                'Inconsistent individual Q8_K bsums')
        require(ad == (1, 3)[phase] and all(q == 1 for q in qs),
                'Exact activation prerequisites differ')
        weight = (pre/('weight-native%d.bin' % phase)).read_bytes()
        require(len(weight) == 176, 'Q5_K native size differs')
        d, dmin = struct.unpack_from('<HH', weight)
        require(d == (0x3c00, 0x3800)[phase] and dmin == 0, 'Exact scale prerequisites differ')
        dot = correction = 0
        scales = weight[4:16]
        for g in range(8):
            sc = scales[g] & 63 if g < 4 else (scales[g+4] & 15) | ((scales[g-4] >> 6) << 4)
            mn = scales[g+4] & 63 if g < 4 else (scales[g+4] >> 4) | ((scales[g] >> 6) << 4)
            for i in range(32):
                quant = ((weight[48+(g//2)*32+i] >> (4*(g&1))) & 15) | (((weight[16+i] >> g) & 1) << 4)
                dot += sc * quant * qs[32*g+i]
                correction += mn * qs[32*g+i]
        require(dot == 256 and correction == 0, 'Exact dot / correction prerequisites differ')
        stage_bits = [integer_single(dot), integer_single(correction)]
        stage_flags = [0, 0]
        for a, b in ((half_to_single(d), ad), (half_to_single(dmin), ad)):
            bits, flags = finite_fma(a, b, 0x80000000)
            stage_bits.append(bits); stage_flags.append(flags)
        bits, flags = finite_fma(stage_bits[2], stage_bits[0], 0)
        stage_bits.append(bits); stage_flags.append(flags)
        bits, flags = finite_fma(stage_bits[3] ^ 0x80000000, stage_bits[1], stage_bits[4])
        stage_bits.append(bits); stage_flags.append(flags)
        generated = 0
        for flags in stage_flags:
            generated |= flags
        values.append(dict(weight=weight, activation=activation, result_bits=bits,
                           integer_dot=dot, integer_correction=correction, fflags=generated,
                           stage_bits=stage_bits, stage_flags=stage_flags))
    return values


def regions(phase, symbols, data, native):
    item=native[phase]
    weight,activation,result=item['weight'],item['activation'],item['result_bits']
    seed=seed_image(phase); actual=bytearray(seed)
    actual[1024:1152]=bytes(128)
    struct.pack_into('<I',actual,1024,result)
    before=b''.join(struct.pack('<I',0x13570000+i) for i in range(16))
    after=b''.join(struct.pack('<I',0x24680000+i) for i in range(16))
    w=bytes([0xa5])*64+weight+bytes([0xa5])*(800-64-176)
    a=bytes([0x5a])*64+activation+bytes([0x5a])*(2496-64-292)
    for name,expected in [('gap108_weights%d'%phase,w),('gap108_activation%d'%phase,a)]:
        address,size=symbols[name]
        require(size==len(expected) and data(address,size)==expected,'ELF fixture/model differs: '+name)
    descriptor=bytes([0xc3])*64+struct.pack('<QQ',2|(4<<4)|(1<<8)|(1<<12)|(1<<16),
                                          symbols['weights'][0]+64)+bytes([0xc3])*64
    csr=b''.join(struct.pack('<Q',v) for v in
        [0x1234567800000000+i for i in range(4)]+[1,16,0,2,8,5]+[1,16,0,2,8|item['fflags'],5]+
        [0x8765432100000000+i for i in range(4)])
    values=dict(initial=before+seed+after,actual=before+actual+after,weights=w,
                activation=a,descriptor_packet=descriptor,csr_packet=csr)
    require(all(symbols[n][1]==len(b) for n,b in values.items()),'Region ELF extents differ')
    return values


def activity_bytes(activity, expected, start, done, custom=False):
    support.activity_bytes(activity,expected,start,done)
    if custom:
        require((activity.instruction,activity.vd,activity.vl)==(WORD,8,32),
                'M1 internal VL32 differs (software CSR VL1)')
        require(len(activity.writes)==16 and all(w.be==255 for w in activity.writes),
                'M1 full-register commit differs')
        require([sum(w.lane==lane for w in activity.writes) for lane in range(4)]==[4]*4,
                'M1 lane write population differs')

readback = reviewed.readback
phase_readback = reviewed.phase_readback
bind_custom = reviewed.bind_custom
scalar_access = reviewed.scalar_access

def software(log):
    text = log.read_text(); lines = text.splitlines()
    expected = ['GAP108 command=0 checks=17 errors=0','GAP108 command=1 checks=17 errors=0',
        'GAP108 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
        'PASSED: qbs_gap108_subnormal checks=41 errors=0']
    require(all(lines.count(line)==1 for line in expected),'Missing/duplicate full software selfcheck')
    require(not support.check_contract_log(log) and text.count('Core Test *** SUCCESS ***')==1 and
            not re.search(r'FAIL|Error:|Fatal:',text),'TB terminal/contract error')
    summary = [support.parse_contract_summary(l) for l in lines if '[ARA_CONTRACT]' in l]
    require(len(summary)==1 and summary[0] is not None and summary[0]['exceptions']==0,
            'Unexpected exception/contract')
    return summary[0]


def runtime(run, symbols, data, sites, native):
    contract = software(run/'run.vcs.log')
    trace = support.validate_trace(run/'commit_trace.csv')
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
    arch,retired_vector,trapped = support._parse_architecture_mapping(run/'commit_trace.csv')
    mapping = support._map_architecture_retires(arch,retired_vector,trapped)
    lanes,vlen,activities = support._parse_vector_trace(run/'vector_trace.csv')
    require((lanes,vlen)==(4,1024),'Wrong vector configuration')
    wanted = []
    for phase in (0,1):
        wanted += [s['pc'] for s in sites[phase][:4]]+[symbols['gap108_qbexec_site%d'%phase][0]]
        wanted += [s['pc'] for s in sites[phase][4:]]
    selected = sorted(activities,key=lambda s:starts[s][2])
    require(len(selected)==18 and [mapping[s].pc for s in selected]==wanted,
            'Unexpected/missing seed/custom/snapshot activities')
    seed_sequences = {s for p in (0,1) for s in selected[p*9:p*9+4]}
    retire_cycles = {}
    for seq in selected:
        matched = [r for r in retires if int(r['pc'],16)==mapping[seq].pc and
                   int(r['insn'],16)==mapping[seq].instruction]
        require(len(matched)==1,'Ambiguous site retirement')
        retire_cycles[seq] = int(matched[0]['cycle'])
    owners = {}; done = set(); windows = {}
    with (run/'vector_trace.csv').open() as stream: vector_rows = list(csv.DictReader(stream))
    for row in vector_rows:
        if row['event']=='config': continue
        require(row['event'] in ('alloc','write','done'),'Unexpected vector event/reset')
        seq,vid,cycle = int(row['arch_seq']),int(row['vid']),int(row['cycle'])
        require(seq in activities,'Unbound vector activity')
        if row['event']=='alloc':
            require(seq not in owners and seq not in done,'Duplicate vector allocation')
            require(starts[seq][2]<=cycle,'Allocation precedes architecture start')
            owners[seq] = (vid,cycle)
        else:
            require(seq in owners and owners[seq][0]==vid and owners[seq][1]<=cycle,
                    'Vector event outside lifecycle')
            if row['event']=='done':
                if seq not in seed_sequences:
                    require(cycle<=retire_cycles[seq],'Custom/store completion after retirement')
                windows[seq] = (owners[seq][1],cycle)
                owners.pop(seq); done.add(seq)
    require(not owners and done==set(selected),'Incomplete vector lifecycle')
    commit_uops = [(r['event'],int(r['order']),int(r['port']),int(r['cycle'])) for r in rows
                  if r['event'] in ('uop_alloc','uop_done')]
    vector_uops = [('uop_'+r['event'],int(r['arch_seq']),int(r['vid']),int(r['cycle']))
                   for r in vector_rows if r['event'] in ('alloc','done')]
    require(sorted(commit_uops)==sorted(vector_uops),'Commit/vector lifecycle probes differ')
    bindings = []; claimed_custom_responses = set()
    for phase in (0,1):
        group = selected[phase*9:(phase+1)*9]; custom_seq = group[4]
        custom_alloc = windows[custom_seq][0]
        require(all(windows[s][1]<custom_alloc for s in group[:4]),
                'Seed completion crosses custom consumer allocation')
        for i,seq in enumerate(group):
            a = activities[seq]; word,key,start = starts[seq]; retired = mapping[seq]
            require(a.instruction==word==retired.instruction,'Opcode/activity/retirement differs')
            match = [(begin,end) for begin,end in responses.get((word,key),[])
                     if start<=begin<=end<=retire_cycles[seq]]
            require(len(match)==1,'Ambiguous/missing activity response')
            begin,end = match[0]; alloc,completion = windows[seq]
            if i<4:
                reg = i*8; seed = seed_image(phase)
                require(a.vd==reg and a.vl==256,'Complete seed load configuration differs')
                expected = {(r,b):seed[r*128+b] for r in range(reg,reg+8) for b in range(128)}
                activity_bytes(a,expected,alloc,completion)
            elif i==4:
                blob=struct.pack('<I',native[phase]['result_bits'])+bytes(124)
                expected={(8,b):value for b,value in enumerate(blob)}
                require(completion<=end,'Custom completion after terminal response')
                activity_bytes(a,expected,alloc,completion,custom=True)
                custom_binding = bind_custom(seq,retired.pc,key,start,retire_cycles[seq],
                                             match,claimed_custom_responses)
            else:
                require(completion<=end,'Store completion after terminal response')
                require(not a.writes and a.allocations==a.completions==1,'Snapshot store wrote VRF/incomplete')
        require(all(retire_cycles[s]<=starts[custom_seq][2] for s in group[:4]) and
                all(retire_cycles[custom_seq]<=starts[s][2] for s in group[5:]),
                'Seed/custom/snapshot ordering differs')
        if phase:
            require(retire_cycles[selected[8]]<starts[group[0]][2],'Commands overlap')
        start = retire_cycles[custom_seq]
        end = starts[selected[9]][2] if phase==0 else max(int(r['cycle']) for r in rows)+1
        # All dependent scalar readbacks must occur after the seed data is complete.
        require(all(windows[s][1]<=start for s in group[:4]),'Seed completion crosses readback window')
        evidence = phase_readback(rows,start,end,symbols,regions(phase,symbols,data,native))
        bindings.append(dict(phase=phase,arch_seq=custom_seq,pc=mapping[custom_seq].pc,
            backend_vl=32,software_vl=1,native_active_write_bytes=4,native_total_write_bytes=128,zero_tail_bytes=124,readback_bytes=evidence,
            custom_binding=custom_binding,
            seed_windows=[dict(arch_seq=s,alloc=windows[s][0],done=windows[s][1],
                               retire=retire_cycles[s]) for s in group[:4]],custom_alloc=custom_alloc))
    require(sum(a.instruction==WORD for a in activities.values())==2,'Custom population differs')
    return dict(status='GAP108_COMPLETE_SOFTWARE_NATIVE_PASS_NOT_FULL_SCALAR_ISA',
        contract=contract,trace=trace,bindings=bindings,
        numeric_oracles=[{k:v[k] for k in ('result_bits','integer_dot','integer_correction','fflags','stage_bits','stage_flags')} for v in native],custom_write_bytes=256,custom_active_bytes=8,custom_zero_tail_bytes=248,full_vrf_bytes=8192,
        initial_vrf_bytes=8192,csr_values=24,source_guard_bytes=6880,checks=41,
        full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False)


def prepare(run, reviewed_seal):
    run=Path(run).absolute()
    require(run==RUN and run.resolve()==run and reviewed_seal==RUN_SEAL,
            'Only reviewed original GAP108 run allowed')
    record=run.with_name(run.name+'.prepared.json')
    config=life.read_bound(record,reviewed_seal)
    pre=life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL)
    runner.validate(pre)
    require(config['preflight']==pre and config['timeout_s']==600 and
            config['old_image_files_checked']==66 and config['expected_commands']==2 and
            config['command']==runner.command(run) and config['coverage_admitted'] is False,
            'Reviewed runtime contract differs')
    pins=life.merge_pins(config['pins'],{str(record):reviewed_seal})
    require(pins.get(str(BUILD))==BUILD_SHA,'Missing/conflicting historical build pin')
    build=life.read_bound(BUILD,BUILD_SHA)
    dispatcher=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    require(build[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]==DISPATCHER_SHA and
            pins.get(str(dispatcher))==DISPATCHER_SHA,'Old dispatcher identity differs')
    for rel in ('hardware/src/vlsu/qbs/qbs_commit.sv','hardware/tb/ara_commit_monitor.sv'):
        path=life.ROOT/rel
        pins=life.merge_pins(pins,{str(path):build[str(path)]})
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image'])==66 and plan['simv']==str(life.IMAGE) and
            plan['image'][str(life.IMAGE)]==runner.IMAGE_SEAL,'Exact old image differs')
    pins=life.merge_pins(pins,plan['image'])
    # Reused reviewed decoders and trace functions are checked against formal729
    # expected pins, not silently blessed by hashing current replacements.
    book_path=pre['baseline']+'/evidence-pins.json'
    book=life.read_bound(Path(book_path),pre['input_pins'][book_path])
    for module in list(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if not name:continue
        path=Path(name).resolve()
        if path.suffix=='.py' and (path.parent==Path(__file__).parent or
                str(path).startswith(str(life.ROOT/'verification/ara_verify')+'/')):
            expected=book.get(str(path),config['pins'].get(str(path)))
            if path not in (Path(__file__).resolve(),Path(runner.__file__).resolve()):
                require(expected is not None,'Unbound reused helper: '+str(path))
            pins=life.merge_pins(pins,{str(path):expected if expected else life.digest(path)})
    test=Path(__file__).with_name('test_qualify_gap108_native.py')
    pins=life.merge_pins(pins,{str(test):life.digest(test)})
    life.check(pins)
    require("ara_req.vl = vlen_t'(qbs_m * (VLEN / 32));" in dispatcher.read_text(),
            'Internal VL formula differs')
    commit=(life.ROOT/'hardware/src/vlsu/qbs/qbs_commit.sv').read_text()
    require("? {{4{high_active}}, {4{low_active}}} : 8'hff;" in commit and
            "? accumulator_bank_data_i[element] : 32'b0;" in commit,
            'M1 full-register zero-tail commit differs')
    symbols,data,sites=elf_view();native=independent_native()
    require([[v['result_bits']] for v in native]==pre['expected_bits_per_command'],
            'Independent Python/C native oracle differs')
    require([v['fflags'] for v in native] == pre['expected_fflags'] and
            [8 | v['fflags'] for v in native] == pre['expected_csr_fflags'],
            'Independent generated/architectural flags differ')
    for phase in (0,1):
        oracle = life.read_bound(runner.PRE/('oracle-command%d.json' % phase),
                                 pins[str(runner.PRE/('oracle-command%d.json' % phase))])
        require(oracle == runner.oracle_expected(phase) and
                native[phase]['stage_bits'] == oracle['stage_bits'] and
                native[phase]['stage_flags'] == oracle['stage_flags'],
                'Independent staged Python/C numeric oracle differs')
        regions(phase,symbols,data,native)
    life.check(pins)
    return dict(status='GAP108_NATIVE_PREPARED_NOT_COLLECTED',run=str(run),
        run_prepared_seal=reviewed_seal,pins=pins,software_checks=41,
        native_expected_bits=[v['result_bits'] for v in native],custom_commands=2,
        native_total_bytes_per_command=128,active_bytes_per_command=4,zero_tail_bytes_per_command=124,
        scope='Complete bounded software/native; NOT full scalar ISA',
        full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False)


def terminal(run):
    path=run/'simulation-status.json'
    require(path.is_file(),'Terminal simulation status required before collect')
    seal=life.digest(path);record=life.read_bound(path,seal)
    require(record.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and
            type(record.get('returncode')) is int and
            record.get('returncode')==0 and record.get('coverage_admitted') is False,
            'Not a clean terminal run')
    return path,seal


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','collect'))
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--prepared-seal',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config-seal')
    args=parser.parse_args(argv)
    require((args.mode=='collect')==bool(args.config_seal),'Collect alone requires reviewed qualifier seal')
    output=args.output.absolute()
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(),
            'Fresh independent output required')
    config=prepare(args.run,args.prepared_seal)
    path=output.with_name(output.name+'.prepared.json')
    if args.mode=='prepare':
        life.save(path,config)
        print(json.dumps(dict(config=str(path),seal=life.digest(path),pins=len(config['pins']))));return
    require(life.read_bound(path,args.config_seal)==config,'Reviewed qualifier config differs')
    run=Path(config['run']);status_path,status_seal=terminal(run)
    pins=life.merge_pins(config['pins'],{str(path):args.config_seal,str(status_path):status_seal})
    required=[run/n for n in ('manifest.json','started.json','console.log','run.vcs.log',
                             'commit_trace.csv','vector_trace.csv')]
    required += [p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    require(any(p.name=='cond.verilog.data.xml' for p in required),'Missing raw condition evidence')
    for p in required:pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    reviewed_run=life.read_bound(run.with_name(run.name+'.prepared.json'),args.prepared_seal)
    require(life.read_bound(run/'manifest.json',pins[str(run/'manifest.json')])==reviewed_run,
            'Runtime manifest differs')
    started=life.read_bound(run/'started.json',pins[str(run/'started.json')])
    require(started['command']==runner.command(run) and started['budget_s']==600 and
            started['input_elf']==str(runner.ELF) and started['elf_sha256']==runner.ELF_SEAL and
            started['image']==str(life.IMAGE) and started['image_sha256']==runner.IMAGE_SEAL and
            isinstance(started['pid'],int) and started['pid']>0,'Launch identity contract differs')
    output.mkdir();life.save(output/'evidence-pins.json',pins)
    try:
        symbols,data,sites=elf_view();audit=runtime(run,symbols,data,sites,independent_native())
        life.check(pins)
        life.save(output/'runtime-audit.json',audit)
        life.save(output/'qualification.json',dict(status='GAP108_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',
            audit_sha256=life.digest(output/'runtime-audit.json'),
            pins_sha256=life.digest(output/'evidence-pins.json'),
            full_scalar_isa_verified=False,spike_custom_isa_pass=False,
            coverage_admitted=False,coverage_increment_measured=False,
            gain_requires_latest_formal_baseline=True,simulation_rerun=False,rtl_changed=False))
    except Exception as error:
        life.save(output/'qualification.json',dict(status='GAP108_NATIVE_REJECTED',
            reason=type(error).__name__+': '+str(error),coverage_admitted=False))
        raise
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'qualification.json'))))


if __name__=='__main__':main()
