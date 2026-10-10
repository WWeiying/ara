"""One finite VSMUL saturation/rounding/recovery matrix; software preflight only."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import preflight_vfirst_long_mask as shared
import targeted_toggle_evidence_v2 as toggle
from inventory_operand_debug import Design
from rank_cva6_scalar_data767 import typed_nodes
from report_global777_compact import semantic

life, require, build = shared.life, shared.require, shared.build
ROOT, OUT = life.ROOT, life.OUT
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vsmul_saturation796.c'
BASE = OUT/'akv-canonical-alias-offline-admitted796-parent-20261008-01'
BASE_SHA = '1aa18b04d4b1f3a4a2d8182c0457e240f43e0538bbeabe1b0385724e5a56400d'
REPORT = OUT/'current-population795-pmp816-agent-20261008-01'
REPORT_SHA = '43b1c922c2561daa5d5e8cb51e30e471bb8d0eaa137d90ad10c63b55cf5257a5'
GUARD, CHECKS = shared.GUARD, 1272
NAMES = ('tohost','num_failed','g75_result','sm_checks','trap_fail','sm_source',
         'sm_snapshot','sm_csr','sm_load_a','sm_load_b','sm_seed','sm_target',
         'sm_store_a','sm_store_b','sm_store_d')
DEFAULT_OUT = OUT/'vsmul-saturation796-preflight-agent-20261008-03'


def rounded_multiply(a, b, width):
    require(width in (8,16,32,64), 'Legal EEW')
    lower = -(1 << (width-1)); upper = -lower-1
    require(lower <= a <= upper and lower <= b <= upper, 'Signed operand range')
    if a == b == lower:
        return upper, 1
    product = a*b
    return (product + (1 << (width-2))) >> (width-1), 0


def case(index):
    require(0 <= index < 12, 'Exact finite case index')
    width = (8,16,32,64)[index//3]; phase = index%3
    low = -(1 << (width-1))
    a,b = ((low,low),(low+1,low//2+1),(0,0))[phase]
    mask = (1 << width)-1
    pack = lambda v: (v & mask).to_bytes(width//8,'little')
    result,sat = rounded_multiply(a,b,width)
    # All128 bytes of both input registers are defined, including reshuffle transports.
    sources = [pack(v)*(128//(width//8)) for v in (a,b)]
    destination = pack(result)*(32//(width//8)) + bytes([0x5a])*96
    return dict(width=width, phase=phase, vl=256//width, sources=sources,
                destination=destination, csr=[256//width,256//width,(index//3)<<3,0,sat,0])


def image(data):
    return GUARD.to_bytes(8,'little')*2 + data + GUARD.to_bytes(8,'little')*2


def words(data):
    require(len(data)%8 == 0, 'Whole words')
    return [int.from_bytes(data[i:i+8],'little') for i in range(0,len(data),8)]


def header():
    array = lambda values: '{'+','.join(hex(v)+'ULL' for v in values)+'}'
    src = [[words(image(data)) for data in case(c)['sources']] for c in range(12)]
    snap = [src[c]+[words(image(case(c)['destination']))] for c in range(12)]
    cube = lambda rows: '{'+','.join('{'+','.join(array(v) for v in row)+'}' for row in rows)+'}'
    return ('#include <stdint.h>\n#define SM_GUARD UINT64_C('+hex(GUARD)+')\n'
      'volatile uint64_t sm_source[12][2][20] __attribute__((aligned(128))) = '+cube(src)+';\n'
      'static const uint64_t sm_source_gold[12][2][20] = '+cube(src)+';\n'
      'static const uint64_t sm_snapshot_gold[12][3][20] = '+cube(snap)+';\n'
      'static const uint64_t sm_csr_gold[12][6] = {'+','.join(array(case(c)['csr']) for c in range(12))+'};\n')


def source_evidence():
    pins = {}
    def bound(path, expected):
        require(life.digest(path) == expected, 'Bound source/baseline drift: '+str(path))
        pins[str(path)] = expected
        return path.read_bytes()
    manifest = json.loads(bound(BASE/'admission-manifest.json',BASE_SHA))
    authority = dict(manifest['input_pins'], **manifest['output_pins'])
    ledger = bound(BASE/'combined-inputs.txt',authority[str(BASE/'combined-inputs.txt')]).decode().splitlines()
    require(len(ledger) == len(set(ledger)) == 797 and manifest['coverage_admitted'], 'Formal796 ledger')
    rows = json.loads(bound(BASE/'combined-toggle-bits.json',authority[str(BASE/'combined-toggle-bits.json')]))
    bookpath = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = json.loads(bound(bookpath,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'))
    for rel in ('hardware/src/lane/simd_mul.sv','hardware/src/lane/vmfpu.sv',
                'hardware/src/lane/lane_sequencer.sv','hardware/src/ara_sequencer.sv',
                'hardware/include/ara_pkg.sv'):
        snapshot = OUT/'old-image-source-evidence-20261006-01'/Path(rel).name
        bound(snapshot if snapshot.exists() else ROOT/rel,book[str(ROOT/rel)])
    code = (ROOT/'hardware/src/lane/simd_mul.sv').read_text()
    require(re.search(r'assign\s+input_sat\[l\]\s*=\s*FixPtSupport\s*==\s*FixedPointEnable\s*&&\s*op_i\s*==\s*VSMUL\s*&&\s*a\s*==\s*MinSigned\s*&&\s*b\s*==\s*MinSigned\s*;',code), 'Exact min/min saturation predicate')
    require('VSMUL' in (ROOT/'hardware/include/ara_pkg.sv').read_text() and
            '[VMUL:VFWREDOSUM]    : vfu = VFU_MFpu;' in (ROOT/'hardware/src/ara_sequencer.sv').read_text(), 'MFPU opcode route')
    q = json.loads(bound(REPORT/'qualification.json',REPORT_SHA))
    text = bound(REPORT/'applied.el',q['output_pins'][str(REPORT/'applied.el')]).decode()
    opaque,masks = semantic(text)
    shape_path = Path(ledger[0])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    bound(shape_path,authority[str(shape_path)])
    definitions = {}
    for node in toggle.xml(shape_path).findall('tgldef'):
        definitions.setdefault(node.get('chksum'),[]).append(node)
    db = Path(ledger[0])/'snps/coverage/db'
    for rel in ('design/verilog.design.xml','auxiliary/verilog.sourceinfo.xml',
                'shape/tgl.verilog.info.xml'):
        path = db/rel
        bound(path,authority[str(path)])
    design = Design(Path(ledger[0])); targets = []
    for lane in range(4):
        for width in (8,16,32,64):
            scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.i_simd_mul_ew%d' % (lane,width)
            row = rows[scope]; matches = definitions[row['checksum']]
            require(len(matches) == 1, 'Unique exact Toggle definition')
            definition = matches[0]
            require(design.source(scope)['resolved_path']==str(ROOT/'hardware/src/lane/simd_mul.sv') and
                    design.definition(scope,'tgl').get('chksum')==row['checksum'], 'Exact compiled SIMD source/caller')
            require('FixPtSupport=1,' in definition.get('name') and
                    'ElementWidth=%d,' % ((8,16,32,64).index(width)) in definition.get('name'), 'Enabled compiled fixed-point/EEW')
            nodes,arrays = typed_nodes(ET.tostring(definition,encoding='unicode'),row)
            node = next(n for n in nodes if n['name']=='input_sat')
            require(node['logical_width']==64//width and not any(k[0]==scope and
                    (k[2]=='input_sat' or 'input_sat'.startswith(k[2]+'.')) for k in masks), 'Exact binary target width/no existing field EL')
            require(not any(k[-1]=='WHOLE_SCOPE' and (scope==k[0] or scope.startswith(k[0]+'.')) for k in opaque), 'No whole-scope ownership')
            if node['missing_slots']:
                targets.append(dict(scope=scope,lane=lane,EEW=width,checksum=row['checksum'],
                    module_checksum=design.hierarchy[scope].get('chksum'),name='input_sat',
                    compiled_attributes=node,raw_coordinates=node['missing_coordinates']))
    require(len(targets)==15 and sum(len(t['raw_coordinates']) for t in targets)==114, 'Actual796 target zeros changed; re-review required')
    packet = OUT/'alua-group5-domain795-source-review-agent-20261008-03.json'
    prior = json.loads(bound(packet,'b2d4cd3deafca08aa8990d50f41a100d4f531e8c95c65b589ee12bb36eca6b1d'))
    branch = json.loads(bound(BASE/'combined-bits.json',authority[str(BASE/'combined-bits.json')]))
    missing = []
    for item in prior['protected_group5_vectors']:
        row = branch['metrics']['branch'][item['scope']];point = item['point']
        if not(int(row['bits'],16) >> (row['width']-1-point['raw_index']) & 1):
            missing.append(dict(scope=item['scope'],raw_index=point['raw_index'],vector=point['vector']))
    require(len(missing)==8 and {r['raw_index'] for r in missing}=={61,73}, 'Actual796 protected group5 residual')
    historical = next(Path(p).parents[3] for p in ledger if '/c0264-extra-rvv-vsmul-' in p)
    historical_source = ROOT/'apps/riscv-tests/isa/rv64uv/vsmul.c'
    pins[str(historical_source)] = life.digest(historical_source)
    return dict(population=796,manifest_sha256=BASE_SHA,targets=targets,zero_slots=114,pins=pins,
        protected_group5_missing_HOLD=missing,
        route='VSMUL enum in VMUL..VFWREDOSUM -> VFU_MFpu -> EW-specific simd_mul; FixPtSupport=1. Each VL=256/EEW fills one64-bit packet on all4 lanes.',
        hypothesis='All min/min operands set every input_sat bit; subsequent non-saturating and zero operands clear them. Predicted raw coordinates only, not native direction IDs or guaranteed gain.',
        history=str(historical),history_note='Existing vsmul.c uses only EW8/VL3/RTZ with no min/min. Actual796 target zeros independently prevent claiming covered stimulus as new gain.',
        no_data_gain_claim='AluA data and simd_alu numerical fields are already covered; remaining default-EEW Branch leaves are HOLD, not advertised as reachable.',
        native_direction_order_inferred=False,EDA_started=False,waivers_changed=False)


def linked(text):
    names = re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{8}|[0-9a-f]{4}|(?:[0-9a-f]{2}\s+){1,3}[0-9a-f]{2})\s+([\w.]+)',text,re.M)
    vector = [n for n in names if n.startswith('v')]
    require(sorted(vector)==sorted(['vsetvli','vle8.v','vle8.v','vmv.v.x','vsetvl','vsmul.vv','vs1r.v','vs1r.v','vs1r.v']), 'Only nine explicit static RVV instructions')
    return vector


def validate(trace,symbols):
    commits = build.parse_spike_commits(trace)
    require('exception ' not in trace.read_text() and not any(c.pc==symbols['trap_fail'] for c in commits), 'Unexpected Spike trap')
    memory = {}; snapshots = {}; reads = {}; events = {n:[] for n in NAMES if n.startswith(('sm_load','sm_seed','sm_target','sm_store'))}
    source = b''.join(image(d) for i in range(12) for d in case(i)['sources'])
    for c in commits:
        for name in events:
            if c.pc==symbols[name]: events[name].append(c)
        for address,value in c.memory_accesses:
            if value is not None:
                decode = shared.old.rvc.decode(c.instruction)
                if decode:
                    require(decode['kind']=='write','Read opcode carrying write'); width=decode['size']
                elif c.instruction&127==35:
                    require(c.instruction>>12&7<=3,'Scalar store width');width=1<<(c.instruction>>12&7)
                else:
                    require(c.instruction&127==39,'Known scalar/vector memory writer');width=1
                require(not symbols['sm_source']<=address<symbols['sm_source']+len(source),'Immutable source modified')
                for k in range(width): memory[address+k]=value>>(8*k)&255
                if c.pc in [symbols[n] for n in ('sm_store_a','sm_store_b','sm_store_d')]:
                    require(address not in snapshots and width==1,'Unique whole-register byte');snapshots[address]=value
            elif symbols['sm_source']<=address<symbols['sm_source']+len(source) and c.pc not in (symbols['sm_load_a'],symbols['sm_load_b']):
                require(len(c.gpr_writes)==1 and address%8==0,'Immutable whole-word source read')
                reads[address]=next(iter(c.gpr_writes.values()))
    require(all(len(v)==12 for v in events.values()),'Exactly twelve executions of each explicit RVV site')
    writers = [c for c in commits if c.vector_writes]
    require(len(writers)==48 and all(c.pc in [symbols[n] for n in ('sm_load_a','sm_load_b','sm_seed','sm_target')] for c in writers), 'No implicit/additional vector writer')
    def observed(address,size):
        require(all(address+i in memory for i in range(size)),'Missing exact terminal witness')
        return int.from_bytes(bytes(memory[address+i] for i in range(size)),'little')
    for index in range(12):
        expected = case(index)
        for name,reg,data in (('sm_load_a',8,expected['sources'][0]),('sm_load_b',16,expected['sources'][1]),
                              ('sm_seed',24,bytes([0x5a])*128),('sm_target',24,expected['destination'])):
            c=events[name][index]
            require(c.vector_writes=={reg:int.from_bytes(data,'little')},'Every defined full128-byte vector writer')
            require(c.vector_vstart==0 and c.vector_vl==(expected['vl'] if name=='sm_target' else 128) and
                    c.vector_sew==(expected['width'] if name=='sm_target' else 8),'Every exact active context')
            if name=='sm_target':
                require(c.instruction&127==87 and c.instruction>>26==0x27 and c.instruction>>25&1==1 and
                        c.instruction>>12&7==0 and c.instruction>>7&31==24 and
                        c.instruction>>15&31==16 and c.instruction>>20&31==8,'Exact unmasked VSMUL tuple')
        for reg,data in enumerate(expected['sources']+[expected['destination']]):
            start=symbols['sm_snapshot']+(index*3+reg)*160
            require(all(observed(start+8*k,8)==v for k,v in enumerate(words(image(data)))),'Complete snapshot/source/guard image')
            require(all(snapshots.get(start+16+k)==v for k,v in enumerate(data)),'Complete128-byte unique whole snapshot')
        require([observed(symbols['sm_csr']+(index*6+k)*8,8) for k in range(6)]==expected['csr'],'Every VL/vtype/vstart/vcsr/fcsr')
    require(len(snapshots)==4608 and len(reads)==480 and
            all(reads.get(symbols['sm_source']+i)==v for i,v in zip(range(0,len(source),8),words(source))), 'Full immutable source+guards and all4608 snapshot bytes')
    require([observed(symbols['g75_result'],4),observed(symbols['g75_result']+4,4),
             observed(symbols['sm_checks'],4),observed(symbols['num_failed'],4),observed(symbols['tohost'],8)]==[CHECKS,0,CHECKS,0,1],'Strict1272-check terminal')
    return dict(checks=CHECKS,target_operations=12,vector_writers=48,full_defined_snapshot_bytes=4608,
                source_guard_bytes=len(source),exact_CSRs=72,retirements=len(commits))


def prepare(out):
    require(out.parent==OUT and not out.exists(),'Fresh software-only preflight output')
    evidence=source_evidence(); pins=dict(evidence['pins'])
    template=shared.template
    command=json.loads(template.TEMPLATE.read_bytes())
    command=[str(APP) if a.endswith('/vgap99_csr_satp_mprv.c') else str(out/'input.elf') if a.endswith('/input.elf') else a for a in command]
    command+=['-I'+str(out),'-fno-unroll-loops','-mno-implicit-float']
    for path in (APP,Path(__file__).resolve(),Path(__file__).with_name('test_preflight_vsmul_saturation796.py'),
                 template.TEMPLATE,template.START,ROOT/'verification/tests/gap75.ld',Path(command[0]),
                 build.SPIKE,build.LLVM/'llvm-objdump',build.LLVM/'llvm-readelf',Path(shared.__file__),
                 Path(template.__file__),Path(build.__file__)):
        pins[str(path.resolve())]=life.digest(path)
    for function in (typed_nodes,semantic,toggle.xml,shared.old.rvc.decode,life.digest,Design):
        path=Path(sys.modules[function.__module__].__file__).resolve()
        pins[str(path)]=life.digest(path)
    life.check(pins);out.mkdir();life.save(out/'source-targets.json',evidence)
    (out/'vsmul_saturation796_gold.h').write_text(header());life.save(out/'compile-command.json',command)
    try:
        with (out/'build.log').open('x') as stream:
            subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=120,check=True)
        from elftools.elf.elffile import ELFFile
        with (out/'input.elf').open('rb') as stream:
            segments=[(p['p_paddr'],p['p_paddr']+p['p_memsz']) for p in ELFFile(stream).iter_segments() if p['p_type']=='PT_LOAD']
        require(segments and all(0x80000000<=a<b<=0x8003f000 for a,b in segments),'Frozen RAM/stack fit')
        symbols={n:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',n) for n in NAMES}
        require(symbols['tohost']==0x80001000,'Frozen tohost ABI')
        manifest=json.loads((BASE/'admission-manifest.json').read_bytes())
        elfs={p:h for p,h in manifest['input_pins'].items() if p.endswith('.elf')}
        require(len(elfs)>=797 and life.digest(out/'input.elf') not in elfs.values(),'Exact historical ELF dedup; no duplicate candidate')
        life.save(out/'elf-dedup.json',dict(ELF_sha=life.digest(out/'input.elf'),
            authority_manifest_sha=BASE_SHA,known_pinned_ELFs=len(elfs),same_ELF_already_admitted=False))
        dis=subprocess.check_output([str(build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],text=True,timeout=30)
        (out/'disassembly.txt').write_text(dis);mnemonics=linked(dis)
        spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
               '-m0x80000000:0x200000','-l','--log-commits',str(out/'input.elf')]
        life.save(out/'spike-command.json',spike)
        with (out/'spike.trace').open('x') as stream:
            subprocess.run(spike,stdout=stream,stderr=subprocess.STDOUT,timeout=120,check=True)
        counts=validate(out/'spike.trace',symbols)
        counts['runtime']=template.runtime(build.parse_spike_commits(out/'spike.trace'),symbols,segments)
        life.check(pins)
        pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
        result=dict(status='VSMUL_SATURATION796_HOST_SPIKE_PASS_NOT_DUT',input_pins=pins,symbols=symbols,
            ELF=str(out/'input.elf'),reference=str(out/'spike.trace'),counts=counts,actual_static_RVV=mnemonics,
            baseline=796,target_raw_zero_slots=114,measured_gain=None,coverage_admitted=False,VCS_started=False)
        life.save(out/'preflight.json',result)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight.json'),ELF_sha=life.digest(out/'input.elf'),counts=counts,VCS_started=False)),flush=True)
    except Exception as error:
        life.save(out/'failure.json',dict(error=str(error),VCS_started=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.resolve())
