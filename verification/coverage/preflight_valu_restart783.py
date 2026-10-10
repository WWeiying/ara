"""Finite standard RVV restart matrix; independent full VRF/CSR/guard oracle."""
import argparse
import json
from pathlib import Path
import subprocess

from elftools.elf.elffile import ELFFile
import prepare_mfpu_restart_word_boundary as reused
import targeted_toggle_evidence_v2 as toggle
from rank_cva6_scalar_data767 import typed_nodes
import scoped_rv64c_memory as rv64c

life, require = reused.life, reused.require
shared = reused.reused.reused.old.shared.shared
ROOT, HERE = life.ROOT, Path(__file__).resolve().parent
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vgap_valu_restart783.c'
OUT = life.OUT/'valu-restart783-preflight-agent-20261008-01'
BASE = life.OUT/'qbs-k2-pending-offline-admitted783-agent-20261008-01'
BASE_SHA = '8d0d58bf873e0b0f4c601d1e9fb88fca74babb572f822a0580967eef9e5d23f0'
REVIEW = life.OUT/'valu-restart782-source-candidate-agent-20261008-01.json'
REVIEW_SHA = '3eb9573e1485780661f00005b7057e3e2d456137afce223129339f8ca9a82ef0'
STARTS = (1020,)*4+(0,)*4+(1020,)*4
OPCODE = 0x030c0457
CHECKS, GUARD, SNAP_BYTES = 13144, 0x5a3c719de4b208f6, 4224
EVENTS = ('vr_start_read','vr_target_vadd','vr_read_vl','vr_read_vtype',
          'vr_read_vstart','vr_read_vcsr','vr_read_fcsr')
NAMES = (*EVENTS,'vr_snap','vr_source','vr_expected','vr_source_gold','vr_csr',
         'vr_requested','g75_result','num_failed','tohost','trap_fail')


def source_groups():
    return [bytes((a*i+b)&255 for i in range(1024)) for a,b in ((37,19),(73,101),(149,0x5a))]


def words(data):
    require(len(data)%8==0,'Whole word packing')
    return [int.from_bytes(data[i:i+8],'little') for i in range(0,len(data),8)]


def vector_state(destination):
    a,b,_ = source_groups()
    return [0x0101010101010101*(0x40+reg) for reg in range(8) for _ in range(16)]+words(destination+a+b)


def gold():
    a,b,seed = source_groups(); result = []
    for index,start in enumerate(STARTS):
        if index%4==0: destination = seed
        before = vector_state(destination)
        destination = destination[:start]+bytes((a[i]+b[i])&255 for i in range(start,1024))
        result.append([before,vector_state(destination)])
    return result


def source_bytes():
    return GUARD.to_bytes(8,'little')*8+b''.join(source_groups())+GUARD.to_bytes(8,'little')*8


def header():
    array = lambda values:'{'+','.join(hex(v)+'ULL' for v in values)+'}'
    groups = [words(g) for g in source_groups()]
    return ('#include <stdint.h>\n#define VR_GUARD UINT64_C('+hex(GUARD)+')\n'
      'static const volatile struct { uint64_t before[8],a[128],b[128],d[128],after[8]; } '
      'vr_source __attribute__((aligned(128))) = {'+array([GUARD]*8)+','+
      ','.join(array(g) for g in groups)+','+array([GUARD]*8)+'};\n'
      'static const uint64_t vr_source_gold[3][128] = {'+','.join(array(g) for g in groups)+'};\n'
      'static const uint64_t vr_expected[12][2][512] = {'+
      ','.join('{'+','.join(array(s) for s in pair)+'}' for pair in gold())+'};\n')


def oracle(value):
    require([value('g75_result',0,4),value('g75_result',4,4),value('num_failed',0,4),value('tohost')]
            ==[CHECKS,0,0,1],'Exact terminal and software check count')
    for index,pair in enumerate(gold()):
        for side,state in enumerate(pair):
            base = (index*2+side)*SNAP_BYTES
            for k,expected in enumerate([GUARD]*8+state+[GUARD]*8):
                require(value('vr_snap',base+k*8)==expected,'Full before/after VRF or guard mismatch')
        require(value('vr_requested',index*8)==STARTS[index],'Requested vstart order')
        for k,expected in enumerate((1024,3,0,0,0)):
            require(value('vr_csr',(index*5+k)*8)==expected,'Exact architectural CSR')


def memory_bytes(commits,symbols):
    memory = {symbols['vr_source']+i:b for i,b in enumerate(source_bytes())}
    registers = [0]*32; snapshots = set()
    counts = dict(scalar_loads=0,scalar_stores=0,compressed_memory=0,uncompressed_memory=0,
                  vector_loads=0,whole_register_stores=0,whole_register_store_bytes=0)
    states = gold()
    for commit in commits:
        word = commit.instruction
        require(not commit.fpr_writes,'Pure integer fixture has no floating register writes')
        if word&127 in (7,39) and commit.vector_sew is not None:
            base = registers[word>>15&31];reg = word>>7&31
            mask = ~((31<<7)|(31<<15))
            if word&127==7:
                require(word&mask==0x02000007 and reg in (8,16,24),'Only exact fixture vle8 groups')
                offset = {16:64,24:1088,8:2112}[reg]
                require(base==symbols['vr_source']+offset and commit.vector_vstart==0 and
                        commit.memory_accesses==tuple((base+i,None) for i in range(1024)),
                        'Complete exact initialized source load addresses')
                counts['vector_loads'] += 1
            else:
                require(word&mask==0x02800027 and commit.vector_vstart==0,'Only exact whole-register snapshot store')
                owner,offset = divmod(base-symbols['vr_snap'],SNAP_BYTES)
                require(0<=owner<24 and offset==64+reg*128 and (owner,reg) not in snapshots,
                        'Exact unique snapshot/register owner; no out-of-bounds write')
                expected = b''.join(v.to_bytes(8,'little') for v in states[owner//2][owner%2][reg*16:(reg+1)*16])
                require(commit.memory_accesses==tuple((base+i,b) for i,b in enumerate(expected)),
                        'Exact128 byte stores per snapshot register; no missing/duplicate/extra byte')
                memory.update({base+i:b for i,b in enumerate(expected)})
                snapshots.add((owner,reg))
                counts['whole_register_stores'] += 1
                counts['whole_register_store_bytes'] += 128
        else:
            compressed = word&3!=3
            access = rv64c.decode(word) if compressed else None
            if not compressed:
                decoded = shared.spike_trace._scalar_memory_access(word)
                if decoded:
                    kind,size = decoded
                    require(kind in ('read','write') and word&127 in (3,35),'No AMO/FP scalar memory')
                    immediate = word>>20 if kind=='read' else (word>>25<<5)|(word>>7&31)
                    immediate = immediate-4096 if immediate&2048 else immediate
                    access = dict(kind=kind,size=size,base=word>>15&31,offset=immediate,
                                  register=word>>7&31 if kind=='read' else word>>20&31)
            if access is None:
                require(not commit.memory_accesses,'No unexplained memory effects')
            else:
                kind,size = access['kind'],access['size']
                address = (registers[access['base']]+access['offset'])&((1<<64)-1)
                require(address%size==0,'Aligned scalar effective address')
                if kind=='write':
                    value = registers[access['register']]&((1<<(8*size))-1)
                    require(commit.memory_accesses==((address,value),),'Full scalar/RVC store address and prior-GPR data')
                    require(not symbols['vr_source']<=address<symbols['vr_source']+3200,'Immutable source/guards modified')
                    memory.update({address+i:b for i,b in enumerate(value.to_bytes(size,'little'))})
                    counts['scalar_stores'] += 1
                else:
                    require(commit.memory_accesses==((address,None),),'Full scalar/RVC load address')
                    counts['scalar_loads'] += 1
                counts['compressed_memory' if compressed else 'uncompressed_memory'] += 1
        for reg,value in commit.gpr_writes.items():registers[reg] = value
        registers[0] = 0
    require(snapshots=={(i,r) for i in range(24) for r in range(32)} and
            counts['vector_loads']==5 and counts['whole_register_store_bytes']==98304,
            'All24 full snapshots and five initialized source loads')
    return memory,dict(counts,scalar_memory_skipped=0,vector_memory_skipped=0,
                       snapshot_owner_bytes_exact=True,byte_reconstruction_not_word_assumption=True)


def validate_commits(commits,symbols,instruction=OPCODE):
    require(instruction==OPCODE,'Exact assembled source/destination opcode')
    registers = {}; event = 0; expected = gold()
    sites = {symbols[name]:i for i,name in enumerate(EVENTS)}
    require(len(sites)==7,'Distinct exact instruction/CSR sites')
    for commit in commits:
        require(commit.pc!=symbols['trap_fail'],'Unexpected trap')
        require(commit.pc==symbols['vr_target_vadd'] or commit.instruction!=OPCODE,'Foreign target opcode')
        if commit.pc in sites:
            index,kind = divmod(event,7)
            require(index<12 and sites[commit.pc]==kind,'Exact twelve ordered CSR/instruction events')
            if kind==1:
                require(commit.instruction==OPCODE and set(registers)==set(range(32)),'Exact target/full initialized VRF')
                state = [registers[r]>>(64*k)&((1<<64)-1) for r in range(32) for k in range(16)]
                require(state==expected[index][0],'Independent exact target before-state')
                require(commit.vector_writes and set(commit.vector_writes)<=set(range(8,16)),
                        'Only destination-group architectural writers')
                require((commit.vector_sew,commit.vector_lmul,commit.vector_vl,commit.vector_vstart,
                         commit.vector_vtype)==(8,'m8',1024,STARTS[index],3),'Exact target vector configuration')
            else:
                csr = (0x008,None,0xc20,0xc21,0x008,0x00f,0x003)[kind]
                require(commit.instruction&0x7f==0x73 and commit.instruction>>20==csr,
                        'Exact CSR instruction binding')
                values = list(commit.gpr_writes.values())
                require(values==[(STARTS[index],None,1024,3,0,0,0)[kind]],'Independent per-site CSR value')
            event += 1
        registers.update(commit.vector_writes)
        if commit.pc==symbols['vr_target_vadd']:
            state = [registers[r]>>(64*k)&((1<<64)-1) for r in range(32) for k in range(16)]
            require(state==expected[(event-1)//7][1],'Independent full VRF after-state')
    require(event==84,'All exact twelve ordered target/CSR groups')
    memory,audit = memory_bytes(commits,symbols)
    def value(name,offset=0,size=8):
        address = symbols[name]+offset
        require(all(address+i in memory for i in range(size)),'Missing defined readback bytes')
        return int.from_bytes(bytes(memory[address+i] for i in range(size)),'little')
    oracle(value)
    return dict(target_instructions=12,per_instruction_CSR_events=72,full_VRF_before_after_bytes=98304,
                memory_VRF_before_after_bytes=98304,output_guard_bytes=3072,immutable_source_guard_bytes=3200,
                software_checks=CHECKS,unknown_defined_bytes_skipped=0,memory_audit=audit)


def binding783():
    review = life.read_bound(REVIEW,REVIEW_SHA)
    manifest = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    pins = {str(REVIEW):REVIEW_SHA,str(BASE/'admission-manifest.json'):BASE_SHA}
    require(manifest['coverage_admitted'] is True,'Formal783 admitted')
    inventory_path = Path(review['inventory'])
    inventory = life.read_bound(inventory_path,review['inventory_sha256'])
    pins = life.merge_pins(pins,inventory['pins']);pins[str(inventory_path)] = review['inventory_sha256']
    old_base = Path(review['baseline_manifest']).parent
    old = life.read_bound(old_base/'admission-manifest.json',review['baseline_manifest_sha256'])
    old_ledger = old_base/'combined-inputs.txt'; new_ledger = BASE/'combined-inputs.txt'
    pins[str(old_ledger)] = old['output_pins'][str(old_ledger)]
    pins[str(new_ledger)] = manifest['output_pins'][str(new_ledger)]
    ledger = new_ledger.read_text().splitlines()
    require(len(ledger)==len(set(ledger))==784 and ledger[:-1]==old_ledger.read_text().splitlines() and
            manifest['baseline']==str(old_base) and manifest['baseline_seal']==review['baseline_manifest_sha256'],
            'Exact783 one append and782 full prefix genealogy')
    files = list((Path(ledger[-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1,'Exact783 native Toggle append')
    scopes = [s['scope'] for s in inventory['scopes'] if s['scope'].endswith('.i_valu')]
    rows,h = toggle.rows(files[0],scopes)
    require(h==manifest['input_pins'][str(files[0])],'Bound actual783 suffix')
    pins[str(files[0])] = h
    before = {s['scope']:s['row'] for s in inventory['scopes'] if s['scope'] in scopes}
    after = toggle.union(before,rows)
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/rel for rel in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')]
    for p in paths:
        require(toggle.digest(p)==manifest['input_pins'][str(p)],'Actual compiled pin')
        pins[str(p)] = toggle.digest(p)
    checks,defs = toggle.definitions(*(toggle.xml(p) for p in paths),scopes)
    objects = {}
    for scope in scopes:
        require(checks[scope]==after[scope]['checksum']=='994898616','Exact VALU compiled checksum')
        objects[scope] = {n['name']:n for n in typed_nodes(defs[scope]['shape'],after[scope])[0]}
    targets = []
    for target in review['targets']:
        node = objects[target['scope']][target['name']]
        require(node['left']=='10' and node['right']=='0' and node['serialized_offset']==
                target['compiled_attributes']['serialized_offset'],'Exact unchanged typed object')
        missing = sorted(set(target['missing_coordinates'])&set(node['missing_coordinates']))
        targets.append(dict(target,missing_coordinates=missing))
    for b in review['frozen_source_bindings']: pins[b['evidence']] = b['sha256']
    for key in ('source_book','shared_compiled_domain_prior_proof'):
        pins[review[key]] = review[key+'_sha256']
    require(len(targets)==45,'Exact reviewed45 objects; no scope expansion')
    life.check(pins)
    return dict(population=783,manifest=str(BASE/'admission-manifest.json'),manifest_sha256=BASE_SHA,
      exact782_prefix=True,appended_vdb=ledger[-1],reviewed_objects=45,targets=targets,
      remaining_candidate_positions=sum(len(t['missing_coordinates']) for t in targets),
      target_positions_unchanged_from782=all(a['missing_coordinates']==b['missing_coordinates']
                                            for a,b in zip(targets,review['targets'])),
      direction_labels_inferred=False,predicted_gain_upper_bound_only=True),pins


def build(existing=False):
    require(not (OUT/'preflight.json').exists() and (OUT.is_dir() if existing else not OUT.exists()),
            'Fresh qualification; existing execution only by explicit offline inspection')
    binding,pins = binding783()
    formal = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    prior = life.read_bound(reused.OUT/'preflight.json',formal['input_pins'][str(reused.OUT/'preflight.json')])
    template = reused.OUT/'compile-command.json'
    require(life.digest(template)==prior['pins'][str(template)],'Frozen mature compiler template')
    command = json.loads(template.read_text())
    changes = {str(reused.APP):str(APP),str(reused.OUT/'input.elf'):str(OUT/'input.elf'),
               '-I'+str(reused.OUT):'-I'+str(OUT)}
    command = [changes.get(a,a) for a in command]
    require(all(flag in command for flag in ('-O2','-fno-vectorize','-fno-slp-vectorize','-DVLEN=1024','-DNR_LANES=4'))
            and str(APP) in command and str(OUT/'input.elf') in command,'Exact compiler substitutions')
    compiler = Path(command[0]).resolve();spike = reused.reused.SPIKE
    require(life.digest(compiler)==prior['pins'][str(compiler)] and
            life.digest(spike)==prior['pins'][str(spike)],'Frozen compiler and Spike identities')
    if existing:
        rejection = json.loads((OUT/'initial-parser-rejection.json').read_text())
        life.check(rejection['input_pins'])
        require(json.loads((OUT/'compile-command.json').read_text())==command and
                (OUT/'valu_restart_gold.h').read_text()==header(),'Exact original build inputs; no recompile')
    else:
        OUT.mkdir()
        (OUT/'valu_restart_gold.h').write_text(header())
        life.save(OUT/'compile-command.json',command)
        with (OUT/'build.log').open('x') as log:
            subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=120,check=True)
    with (OUT/'input.elf').open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name in NAMES}
        segments = [(s['p_vaddr'],s.data()) for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
    require(set(symbols)==set(NAMES),'Full ELF symbols')
    def elfbytes(address,size):
        matches = [data[address-base:address-base+size] for base,data in segments if base<=address and address+size<=base+len(data)]
        require(len(matches)==1,'Exact file-backed ELF bytes')
        return matches[0]
    require(elfbytes(symbols['vr_source'],3200)==source_bytes(),'Exact initialized source/guards in ELF')
    require(elfbytes(symbols['vr_expected'],98304)==b''.join(v.to_bytes(8,'little') for pair in gold() for state in pair for v in state),
            'Exact independent before/after expected ELF')
    require(elfbytes(symbols['vr_source_gold'],3072)==b''.join(source_groups()),'Independent source comparison ELF')
    require(int.from_bytes(elfbytes(symbols['vr_target_vadd'],4),'little')==OPCODE,'Exact assembled vadd operands')
    command = [str(spike),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(OUT/'input.elf')]
    if existing:
        require(json.loads((OUT/'spike-command.json').read_text())==command,'Exact original Spike execution')
    else:
        life.save(OUT/'spike-command.json',command)
        with (OUT/'spike.trace').open('x') as log:
            subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
    require('exception ' not in (OUT/'spike.trace').read_text(),'No unexpected Spike exception')
    commits = shared.spike_trace.parse_spike_commits(OUT/'spike.trace')
    checks = validate_commits(commits,symbols)
    counts = shared.reference_counts(commits,symbols)
    for p in (APP,Path(__file__),HERE/'test_preflight_valu_restart783.py',compiler,spike,template,
              reused.OUT/'preflight.json',Path(reused.__file__),Path(shared.__file__),Path(shared.spike_trace.__file__),Path(rv64c.__file__),
              ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',*OUT.iterdir()):
        if p.is_file():pins[str(p.resolve())] = life.digest(p)
    life.check(pins)
    record = dict(status='VALU_RESTART783_SPIKE_FULL_BEFORE_AFTER_VRF_CSR_GUARDS_PASS_NOT_DUT',
      pins=pins,symbols=symbols,counts=counts,checks=checks,baseline=binding,instruction=OPCODE,
      starts=list(STARTS),software_checks=CHECKS,CSR_expected=[1024,3,0,0,0],
      full_scalar_reference_required=True,full_defined_vector_bytes_required=True,all_memory_reference_required=True,
      unknown_defined_bytes_skipped=0,native_DUT_execution_performed=False,ordinary_ISA_Spike_reference=True,
      Spike_only_not_DUT_qualification=True,
      original_Spike_execution_reused_offline=existing,
      intended_future_DUT_budget_seconds=600,EDA_launched=False,VCS_launched=False,RTL_changed=False,coverage_admitted=False,
      stimulus_constraints=dict(vlen=1024,lanes=4,sew=8,lmul=8,vl=1024,groups=[8,16,24],
       vstart_rewritten_before_each_target=True,destination_reinitialized_each_phase=True,
       active_elements_at_high_start=4,prefix_elements_at_high_start=1020,queue_depth=4,
       inactive_lane_carry_bit8_not_targeted=True),
      future_native_obligations=['Frozen simv/source and exact sealed ELF','Full scalar/GPR/RVC memory and defined vector comparison',
        'Independent full before/after VRF, source guards, target CSR sequence','Actual accepted queue slots and write byte enables',
        'AXI conservation/last drain and relative latest admitted raw union; capacity is not gain'])
    life.save(OUT/'preflight.json',record)
    print(json.dumps(dict(output=str(OUT),seal=life.digest(OUT/'preflight.json'),counts=counts,checks=checks,
                         baseline_candidates=binding['remaining_candidate_positions'])))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--build',action='store_true')
    mode.add_argument('--inspect-existing',action='store_true')
    args = parser.parse_args();build(existing=args.inspect_existing)
