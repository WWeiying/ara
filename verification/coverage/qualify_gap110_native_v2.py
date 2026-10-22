"""GAP110 v2 exact ABI-aligned descriptor; preserved v1 reject, no full ISA/admission."""
import argparse
import csv
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
import run_gap110_simulation as runner
import qualify_gap105_native as support
import qualify_gap105_native_v5 as reviewed
import rv64_compressed_memory as compressed

life, require = runner.life, support.require
WORD = 0x08b5045b
RUN = life.OUT/'gap110-q3-r4-old-image-parent-20261006-01'
RUN_SEAL = '6803bc87380efafecb2d53b3e0688c14dfec175cf573a5d04b0a3d11b8b46387'
RUN_PID = 3280044
BUILD = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BUILD_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
DISPATCHER_SHA = '9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'
seed_image = support.seed_image
ORIGINAL_SHA='340fdbe6ebd9eb79f5dbf5815b7f93a79e06b5ac08ec7d3c15556d70db84c688'
ORIGINAL_TEST_SHA='0d12e54548d2e1259df69e5032e6fedc82afb3f0e65081a451a478a37691cb25'
ABI=life.ROOT/'apps/common/qbs_abi.h'
ABI_DEP=life.ROOT/'apps/qbs_gap110_q3_r4_tail/../common/qbs_abi.h'

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
        address,size = symbols['gap110_exec%d'%phase]
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
        pc = symbols['gap110_qbexec_site%d'%phase][0]
        require(int.from_bytes(data(pc,4),'little')==WORD,'Actual custom ELF word differs')
    return symbols,data,sites


def integer_single(value):
    require(type(value) is int and abs(value)<2**23,'Bounded exact integer conversion')
    if not value: return 0
    top=abs(value).bit_length()-1
    return (0x80000000 if value<0 else 0)|((top+127)<<23)|((abs(value)-(1<<top))<<(23-top))


def independent_native(pre=runner.PRE):
    """Unpack native bitplanes/scales and every bsum; unit scales make all stages exact."""
    values=[]
    for phase,n in enumerate((7,5)):
        weight=(pre/('weight-native%d.bin'%phase)).read_bytes()
        activation=(pre/('activation-native%d.bin'%phase)).read_bytes()
        require(len(weight)==880 and len(activation)==2336,'Exact Q3_K R4/Q8_K M8 storage')
        contexts=[]
        for ctx in range(8):
            require(struct.unpack_from('<I',activation,4*ctx)[0]==0x3f800000,
                    'Bounded unit activation scale')
            qs=[struct.unpack('b',activation[32+8*i+ctx:33+8*i+ctx])[0] for i in range(256)]
            require(all(v==ctx+1 for v in qs),'Exact context activation quants')
            for group in range(16):
                require(struct.unpack_from('<h',activation,2080+16*group+2*ctx)[0]
                        ==sum(qs[16*group:16*group+16]),'Individual Q8_K bsum mismatch')
            contexts.append(qs)
        dots=[]
        for row in range(8):
            block=weight[110*row:110*(row+1)]
            require(struct.unpack_from('<H',block,108)[0]==0x3c00,'Bounded unit weight scale')
            quants=[]
            for i in range(256):
                group=i//16;section,slot=divmod(group,4)
                scale=((block[96+(section%2)*4+slot]>>(4*(section//2)))&15)
                scale|=((block[104+slot]>>(2*section))&3)<<4
                scale-=32
                packet,lane=divmod(i,32)
                quant=(block[32+32*(packet//4)+lane]>>(2*(packet%4)))&3
                if not (block[lane]>>packet)&1: quant-=4
                require(scale==1 and quant==1,'Exact Q3_K scale/quant prerequisites')
                quants.append(scale*quant)
            dots.append([sum(q*act for q,act in zip(quants,c)) for c in contexts])
        bits=[integer_single(dots[row][ctx]) for ctx in range(5) for row in range(n)]
        values.append(dict(weight=weight,activation=activation,result_bits=bits,
                           integer_dots=[dots[row][ctx] for ctx in range(5) for row in range(n)],
                           fflags=0,n=n))
    return values


def abi_pins():
    pre=life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL)
    require(str(ABI_DEP) in pre['input_pins'],'Missing frozen ABI compiler-dependency pin')
    require(ABI_DEP.resolve()==ABI and ABI.resolve()==ABI and not ABI.is_symlink(),
            'Frozen ABI dependency resolution differs')
    require(ABI.is_file() and all(p.is_dir() and not p.is_symlink()
            for p in (*ABI_DEP.parents,*ABI.parents)),
            'Symlink/non-directory ABI ancestor')
    expected=pre['input_pins'][str(ABI_DEP)]
    pins=life.merge_pins({str(ABI_DEP):expected},{str(ABI):expected})
    if str(ABI) in pre['input_pins']:
        pins=life.merge_pins(pins,{str(ABI):pre['input_pins'][str(ABI)]})
    life.check(pins)
    return pins


def abi_descriptor_header(n):
    require(type(n) is int and n in (7,5),'Exact two descriptor shapes')
    abi_pins()
    text=ABI.read_text()
    for typename,symbol,value in (
        ('qbs_weight_layout_t','QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR',2),
        ('qbs_activation_layout_t','QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED',3),
        ('qbs_weight_profile_t','QBS_WEIGHT_PROFILE_Q3_K',5),
        ('qbs_activation_profile_t','QBS_ACTIVATION_PROFILE_Q8_K',1),
        ('qbs_activation_access_t','QBS_ACTIVATION_ACCESS_DIRECT',0)):
        blocks=re.findall(r'typedef enum\s*\{([^{}]+)\}\s*'+typename+r'\s*;',text)
        require(len(blocks)==1 and re.findall(r'\b'+symbol+r'\s*=\s*([0-9]+)\s*[,}]',blocks[0]+ '}')
                ==[str(value)],'Exact frozen ABI enum differs: '+symbol)
    require(re.findall(r'^#define QBS_DESCRIPTOR_VERSION ([0-9]+)u$',text,re.M)==['2'],
            'Exact descriptor version differs')
    functions=re.findall(r'static inline uint64_t qbs_pack_descriptor_header\s*\([^{}]+\)\s*\{([^{}]+)\}',text)
    expected="""return ((uint64_t)(fields->descriptor_version & 0x0fu) << 0) |
         ((uint64_t)(fields->weight_profile & 0x0fu) << 4) |
         ((uint64_t)(fields->activation_profile & 0x0fu) << 8) |
         ((uint64_t)(fields->weight_layout & 0x0fu) << 12) |
         ((uint64_t)(fields->activation_layout & 0x0fu) << 16) |
         ((uint64_t)((fields->n - 1u) & 0x1fu) << 20) |
         ((uint64_t)((fields->k_blocks - 1u) & 0xffu) << 25) |
         ((uint64_t)(fields->activation_access & 0x03u) << 33) |
         ((uint64_t)(fields->context_id & 0x0fu) << 35) |
         ((uint64_t)fields->context_generation << 39);"""
    require(len(functions)==1 and re.sub(r'\s+','',functions[0])==re.sub(r'\s+','',expected),
            'Exact frozen descriptor field packing differs')
    return 2|(5<<4)|(1<<8)|(2<<12)|(3<<16)|((n-1)<<20)


def regions(phase, symbols, data, native):
    item=native[phase];n=item['n'];skew=(0,12)[phase]
    seed=seed_image(phase); actual=bytearray(seed)
    for ctx in range(5):
        for row in range(n):
            struct.pack_into('<I',actual,1024+ctx*128+row*4,item['result_bits'][ctx*n+row])
    before=b''.join(struct.pack('<I',0x13570000+i) for i in range(16))
    after=b''.join(struct.pack('<I',0x24680000+i) for i in range(16))
    weight=item['weight'];activation=item['activation']
    w=bytes([0xa5])*(64+skew)+weight+bytes([0xa5])*(1024-64-skew-len(weight))
    a=bytes([0x5a])*68+activation+bytes([0x5a])*(2496-68-len(activation))
    for name,expected in [('gap110_weights%d'%phase,w),('gap110_activation%d'%phase,a)]:
        address,size=symbols[name]
        require(size==len(expected) and data(address,size)==expected,'ELF fixture/model differs: '+name)
    header=abi_descriptor_header(n)
    descriptor=bytes([0xc3])*64+struct.pack('<QQ',header,symbols['weights'][0]+64+skew)+bytes([0xc3])*64
    csr=b''.join(struct.pack('<Q',v) for v in
        [0x1234567800000000+i for i in range(4)]+[n,16,0,2,8,5]*2+
        [0x8765432100000000+i for i in range(4)])
    values=dict(initial=before+seed+after,actual=before+actual+after,weights=w,
                activation=a,descriptor_packet=descriptor,csr_packet=csr)
    require(all(symbols[name][1]==len(blob) for name,blob in values.items()),'Region ELF extents differ')
    return values


def custom_expected(item):
    n=item['n']
    return {(8+ctx,4*row+b):(bits>>(8*b))&255
            for ctx in range(5) for row,bits in enumerate(item['result_bits'][ctx*n:(ctx+1)*n])
            for b in range(4)}


def activity_bytes(activity, expected, start, done, custom=False):
    support.activity_bytes(activity,expected,start,done)
    if custom:
        require((activity.instruction,activity.vd,activity.vl)==(WORD,8,160),
                'M5 internal VL160 differs (software CSR VL7/5)')
        n=len(expected)//20
        require(n in (5,7),'Only N7/N5 active output population')
        wanted={(lane,(8+ctx)*4):255 if lane<n-4 else 15
                for ctx in range(5) for lane in range(4)}
        observed={}
        for write in activity.writes:
            key=(write.lane,write.addr)
            require(key not in observed,'Duplicate lane/address commit')
            observed[key]=write.be
        require(observed==wanted,'M5 active-only lane masks/addresses differ')


readback = reviewed.readback
phase_readback = reviewed.phase_readback
bind_custom = reviewed.bind_custom
scalar_access = reviewed.scalar_access

def software(log):
    text = log.read_text(); lines = text.splitlines()
    expected = ['GAP110 command=0 checks=17 errors=0','GAP110 command=1 checks=17 errors=0',
        'GAP110 inspected vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24',
        'PASSED: qbs_gap110_q3_r4_tail checks=41 errors=0']
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
        wanted += [s['pc'] for s in sites[phase][:4]]+[symbols['gap110_qbexec_site%d'%phase][0]]
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
                expected=custom_expected(native[phase])
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
            backend_vl=160,software_vl=native[phase]['n'],native_active_write_bytes=20*native[phase]['n'],native_total_write_bytes=20*native[phase]['n'],preserved_vrf_bytes=4096-20*native[phase]['n'],readback_bytes=evidence,
            custom_binding=custom_binding,
            seed_windows=[dict(arch_seq=s,alloc=windows[s][0],done=windows[s][1],
                               retire=retire_cycles[s]) for s in group[:4]],custom_alloc=custom_alloc))
    require(sum(a.instruction==WORD for a in activities.values())==2,'Custom population differs')
    return dict(status='GAP110_COMPLETE_SOFTWARE_NATIVE_PASS_NOT_FULL_SCALAR_ISA',
        contract=contract,trace=trace,bindings=bindings,
        numeric_oracles=[{k:v[k] for k in ('result_bits','integer_dots','fflags','n')} for v in native],custom_write_bytes=240,custom_active_bytes=240,custom_preserved_vrf_bytes=7952,full_vrf_bytes=8192,
        initial_vrf_bytes=8192,csr_values=24,source_guard_bytes=7328,checks=41,
        full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False)


def prepare(run, reviewed_seal):
    run=Path(run).absolute()
    require(run==RUN and run.resolve()==run and reviewed_seal==RUN_SEAL,
            'Only reviewed original GAP110 run allowed')
    record=run.with_name(run.name+'.prepared.json')
    config=life.read_bound(record,reviewed_seal)
    pre=life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL)
    runner.validate(pre)
    runner.exact(config,dict(case=runner.NAME,timeout_s=600,old_image_files_checked=66,
        preflight_files_checked=298,expected_commands=2,expected_dut_checks=41,
        expected_checks_per_command=17,expected_external_request_count=None,
        expected_backend_vl=[160,160],expected_software_vl=[7,5],
        expected_active_output_bytes=[140,100],expected_csr_fflags=[8,8],
        coverage_delta_requires_latest_formal_baseline=True,coverage_admitted=False,
        command=runner.command(run),preflight=pre),'Reviewed runtime')
    pins=life.merge_pins(config['pins'],{str(record):reviewed_seal})
    pins=life.merge_pins(pins,{
        str(Path(__file__).with_name('qualify_gap110_native.py')):ORIGINAL_SHA,
        str(Path(__file__).with_name('test_qualify_gap110_native.py')):ORIGINAL_TEST_SHA})
    pins=life.merge_pins(pins,abi_pins())
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
    # The sealed732 ancestor book binds all reused decoders; new code is pinned separately.
    book_path=pre['baseline']+'/evidence-pins.json'
    book_seal=pre['input_pins'][book_path]
    book=life.read_bound(Path(book_path),book_seal)
    pins=life.merge_pins(pins,{book_path:book_seal})
    prior_book=life.OUT/'gap108-offline-admitted-730-parent-20261006-01/evidence-pins.json'
    require(str(prior_book) in book,'Missing sealed ancestor helper book')
    prior_seal=book[str(prior_book)]
    pins=life.merge_pins(pins,{str(prior_book):prior_seal})
    book=life.merge_pins(life.read_bound(prior_book,prior_seal),book)
    test=Path(__file__).with_name('test_qualify_gap110_native_v2.py').resolve()
    for module in list(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if not name:continue
        path=Path(name).resolve()
        if path.suffix=='.py' and (path.parent==Path(__file__).parent or
                str(path).startswith(str(life.ROOT/'verification/ara_verify')+'/')):
            expected=book.get(str(path),config['pins'].get(str(path)))
            if path not in (Path(__file__).resolve(),Path(runner.__file__).resolve(),test):
                require(expected is not None,'Unbound reused helper: '+str(path))
            pins=life.merge_pins(pins,{str(path):expected if expected else life.digest(path)})
    pins=life.merge_pins(pins,{str(test):life.digest(test)})
    life.check(pins)
    require("ara_req.vl = vlen_t'(qbs_m * (VLEN / 32));" in dispatcher.read_text(),
            'Internal VL formula differs')
    commit=(life.ROOT/'hardware/src/vlsu/qbs/qbs_commit.sv').read_text()
    require("wide_command = unsigned'(m_q) >= QbsWideMMin;" in commit and
            "ldu_result_be_o[lane] = wide_command" in commit and
            "? {{4{high_active}}, {4{low_active}}} : 8'hff;" in commit,
            'M5 active-only preservation commit differs')
    symbols,data,sites=elf_view();native=independent_native()
    require([v['result_bits'] for v in native]==pre['expected_bits_per_command'] and
            [v['fflags'] for v in native]==pre['expected_fflags'],
            'Independent Python/C native oracle differs')
    for phase in (0,1):
        oracle=life.read_bound(runner.PRE/('oracle-command%d.json'%phase),
                              pins[str(runner.PRE/('oracle-command%d.json'%phase))])
        require(oracle==dict(phase=phase,flags=native[phase]['fflags'],
                            bits=native[phase]['result_bits']),'Native oracle artifact differs')
        regions(phase,symbols,data,native)
    life.check(pins)
    return dict(status='GAP110_NATIVE_PREPARED_NOT_COLLECTED',run=str(run),
        run_prepared_seal=reviewed_seal,run_pid=RUN_PID,pins=pins,software_checks=41,
        expected_backend_vl=[160,160],expected_software_vl=[7,5],
        expected_external_request_count=None,native_expected_bits=[v['result_bits'] for v in native],
        custom_commands=2,native_bytes_per_command=[140,100],preserved_vrf_bytes_per_command=[3956,3996],
        gain_requires_latest_formal_baseline=True,gain_baseline_required=733,
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
            type(started['pid']) is int and started['pid']==RUN_PID,'Launch identity contract differs')
    output.mkdir();life.save(output/'evidence-pins.json',pins)
    try:
        symbols,data,sites=elf_view();audit=runtime(run,symbols,data,sites,independent_native())
        life.check(pins)
        life.save(output/'runtime-audit.json',audit)
        life.save(output/'qualification.json',dict(status='GAP110_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',
            audit_sha256=life.digest(output/'runtime-audit.json'),
            pins_sha256=life.digest(output/'evidence-pins.json'),
            full_scalar_isa_verified=False,spike_custom_isa_pass=False,
            coverage_admitted=False,coverage_increment_measured=False,
            gain_requires_latest_formal_baseline=True,simulation_rerun=False,rtl_changed=False))
    except Exception as error:
        life.save(output/'qualification.json',dict(status='GAP110_NATIVE_REJECTED',
            reason=type(error).__name__+': '+str(error),coverage_admitted=False))
        raise
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'qualification.json'))))


if __name__=='__main__':main()
