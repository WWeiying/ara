"""Read-only source/compiled inventory and existing conversion execution review."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
from elftools.elf.elffile import ELFFile
import targeted_toggle_evidence_v2 as native
import run_gap95_simulation as life

sys.path.insert(0, str(life.ROOT/'verification/tests'))
import generate_rvv_gap29 as reference

BASE = life.OUT/'gap115-offline-admitted-745-agent-20261007-01'
BUILD = life.OUT/'repaired-aligned-build-20260930-01'
DB = BUILD/'sim/simv.vdb/snps/coverage/db'
SOURCE = life.ROOT/'hardware/deps/fpnew/src/fpnew_cast_multi.sv'
NAMES = frozenset(('operands_q', 'inp_pipe_operands_q', 'encoded_mant', 'fmt_exponent',
    'fmt_mantissa', 'fmt_shift_compensation', 'ifmt_input_val', 'int_value', 'int_mantissa',
    'src_bias', 'src_exp', 'src_offset', 'fp_input_exp', 'int_input_exp', 'renorm_shamt',
    'renorm_shamt_sgn', 'input_mant', 'input_exp', 'destination_exp', 'input_exp_q',
    'input_mant_q', 'destination_exp_q', 'mid_pipe_input_exp_q', 'mid_pipe_input_mant_q',
    'mid_pipe_dest_exp_q'))


def selected(node):
    return (node.get('portnode') == '0' and node.get('name') in NAMES
            and int(node.get('line_num', '9999')) <= 423)


def dimensions(node):
    if node.tag == 'node': return []
    if node.tag == 'vectornode': return [[int(node.get('left')), int(node.get('right'))]]
    native.require(node.tag == 'arrays', 'Unexpected compiled object')
    out = []
    for kind in ('packedrange', 'unpackedrange'):
        v = list(map(int, node.get(kind, '').split()))
        native.require(len(v) % 2 == 0, 'Bad bounds')
        out += [v[i:i+2] for i in range(0, len(v), 2)]
    native.require(out, 'Missing array bounds')
    return out


def object_record(node):
    bounds = dimensions(node); bits = 1
    for a, b in bounds: bits *= abs(a-b)+1
    return dict(node.attrib, shape_kind=node.tag, dimensions=bounds, logical_bits=bits,
                native_name=node.get('name')+''.join('[%d:%d]'%(a,b) for a,b in bounds))


def actual_case(case, test, pins):
    src = life.ROOT/'apps/riscv-tests/isa/rv64uv'/(case[0]+'.c')
    native.require(src.read_text() == reference.render(case), 'Independent reference/source differs')
    inputs = json.loads((test/'inputs.json').read_bytes())
    native.require(life.digest(test/'input.elf') == inputs['binary']['sha256'], 'ELF drift')
    life.check(inputs['simv']['image_sha256']); pins.update(inputs['simv']['image_sha256'])
    command = json.loads((test/'command.json').read_bytes())['command']
    native.require(command[0] == inputs['simv']['path'] and
                   '+PRELOAD='+str(test/'input.elf') in command, 'Original image/ELF command differs')
    with (test/'input.elf').open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        segments = [(s['p_vaddr'], s.data()) for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
    values = reference.fp_inputs(); rm = case[4]
    converted = [reference.narrow_half(x, rm) for x in values]
    for name, data, width in (('input', values, 4), ('golden', [x[0] for x in converted], 2),
                              ('golden_flags', [x[1] for x in converted], 1)):
        packed = b''.join(x.to_bytes(width, 'little') for x in data); address = symbols[name]
        native.require([b[address-a:address-a+len(packed)] for a,b in segments
                        if a<=address and address+len(packed)<=a+len(b)] == [packed], 'ELF gold differs')
    rows = [r for r in csv.DictReader((test/'commit_trace.csv').open()) if r['event']=='retire']
    reads = {k: [] for k in ('output', 'output_wide')}; flags=[]; operations=[]
    for r in rows:
        pc, word = int(r['pc'],16), int(r['insn'],16); size=4 if word&3==3 else 2
        native.require([int.from_bytes(b[pc-a:pc-a+size], 'little') for a,b in segments
                        if a<=pc and pc+size<=a+len(b)] == [word], 'Retirement not bound to ELF')
        native.require(r['trap']=='0', 'Unexpected trap')
        if word&127==115 and word>>20==1 and word>>12&7==2 and word>>15&31==0:
            flags.append(int(r['rd_wdata'],16))
        if word&127==87 and word>>12&7==1:
            operations.append(word)
        if word&127==3:
            for name,width in (('output',2),('output_wide',4)):
                addr=int(r['mem_addr'],16); start=symbols[name]
                if start<=addr<start+65*width:
                    native.require(word>>12&7 in ((5,) if width==2 else (2,6)), 'Wrong result read width')
                    native.require(int(r['mem_rmask'],16)==((1<<width)-1)<<(addr%8), 'Partial readback')
                    value=int(r['rd_wdata'],16); mask=(1<<(8*width))-1
                    expected_upper = ((1<<64)-1)^mask if word>>12&7==2 and value&(1<<31) else 0
                    native.require(value&~mask == expected_upper, 'Wrong scalar read sign extension')
                    reads[name].append((addr-start,value&mask))
    narrow = 0x488a1857 if rm!=6 else 0x488a9857
    native.require(operations == [narrow,0x49061c57]*6, 'Actual conversion sites/shape differ')
    expected_flags=[]
    for phase, active in enumerate((65,64,65,65,1,0)):
        selected_elements = [i<active and (phase!=3) and (phase!=2 or i%2==0) for i in range(65)]
        acc=0
        for i, take in enumerate(selected_elements):
            if take: acc |= converted[i][1]
        expected_flags += [acc,0]
        for name,width in (('output',2),('output_wide',4)):
            gold=[(converted[i][0] if width==2 else reference.widen_half(converted[i][0]))
                  if selected_elements[i] else (0x3555 if width==2 else 0x3eaaa000) for i in range(65)]
            native.require(reads[name][phase*65:(phase+1)*65] == [(i*width,g)for i,g in enumerate(gold)],
                           'Actual complete bitexact conversion readback differs')
    native.require(flags==expected_flags and all(len(v)==390 for v in reads.values()), 'Flags/missing/extra readback')
    summary=json.loads((test.parent.parent/'summary.json').read_bytes())
    native.require(len(summary)==1 and summary[0]['status']=='PASS' and summary[0]['returncode']==0,
                   'Historical terminal not PASS')
    for p in (src,test/'input.elf',test/'inputs.json',test/'command.json',test/'commit_trace.csv',
              test.parent.parent/'summary.json'): pins[str(p)]=life.digest(p)
    return dict(name=case[0], rounding=rm, vdb=str(test/'work/code.vdb'),
                ELF_sha256=inputs['binary']['sha256'], retired_ELF_checks=len(rows), phases=6,
                readback_bytes=2340, flags_reads=flags, conversions=12,
                comparison='INTEGER_REFERENCE_VS_ACTUAL_COMPLETE_SCALAR_READBACK_AND_FFLAGS',
                full_ISA=False, native_vector_trace=False, exhaustive_IEEE=False)


def review(output):
    native.require(not output.exists(), 'Fresh artifact only')
    pins={}; read=lambda p: json.loads(p.read_bytes())
    book=read(BASE/'admission-manifest.json')
    before=life.read_bound(BASE/'combined-bits.json',book['output_pins'][str(BASE/'combined-bits.json')])
    native.require(len(before['tests'])==len(set(before['tests']))==745,'Exact745 required')
    frozen=read(BUILD/'build-source-pins.json'); native.require(life.digest(SOURCE)==frozen[str(SOURCE)],'Frozen source drift')
    upstream=subprocess.check_output(['git','show','HEAD:src/fpnew_cast_multi.sv'],cwd=SOURCE.parents[1])
    native.require(SOURCE.read_bytes().splitlines()[:423]==upstream.splitlines()[:423], 'Upstream numeric prefix drift')
    upstream_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE.parents[1],text=True).strip()
    info=native.xml(DB/'shape/tgl.verilog.info.xml'); shape=native.xml(DB/'shape/tgl.verilog.shape.xml')
    formats={x.get('chksum'):x for x in shape.findall('tgldef') if x.get('name','').startswith('fpnew_cast_multi (')}
    instances=[]
    for row in info.iter('instance_data'):
        scope=row.get('name','')
        if '.i_ara.gen_lanes[' not in scope or not scope.endswith('.i_fpnew_cast_multi'):continue
        definition=formats[row.get('chksum')]; targets=[]; protected=[]
        for node in definition.find('tglshape'):
            item=object_record(node)
            if selected(node):
                native.require(node.get('file')=='353' and node.get('excluded')=='0','Foreign/excluded data object')
                targets.append(item)
            else: protected.append(item)
        instances.append(dict(scope=scope,toggle_checksum=row.get('chksum'),compiled_definition=definition.get('name'),
                              targets=targets,protected=protected,all_children_protected=True))
    native.require(len(instances)==16 and all(x['targets'] for x in instances), 'Exact sixteen vector casts')
    evidence=[]
    for case in reference.cases():
        matches=[x for x in before['tests'] if '/rvv_'+case[0]+'/work/code.vdb' in x]
        native.require(len(matches)==1,'Missing/duplicate conversion member')
        evidence.append(actual_case(case,Path(matches[0]).parents[1],pins))
    for p in (SOURCE,BASE/'admission-manifest.json',BASE/'combined-bits.json',BUILD/'build-source-pins.json',
              DB/'design/verilog.design.xml',DB/'shape/tgl.verilog.info.xml',DB/'shape/tgl.verilog.shape.xml',
              life.ROOT/'apps/riscv-tests/isa/rv64uv/vrvv_gap29_body.h',Path(reference.__file__),Path(__file__).resolve()):
        pins[str(p)]=life.digest(p)
    life.check(pins)
    result=dict(status='UNCHANGED_PREFIX_NUMERIC_CANDIDATE_EXECUTION_REVIEW_PASS_NATIVE_HOLD',baseline=745,
        source_sha256=frozen[str(SOURCE)],module_modified=True,upstream_commit=upstream_commit,
        upstream_sha256=__import__('hashlib').sha256(upstream).hexdigest(),unchanged_source_prefix_lines=[1,423],
        protection='All ports/control/sign predicates/rounding/flags/specials/reset/valid/ready/mask/tail metadata; all fields from modified region and postround outputs; every child; scalar/QBS instances and all other metrics retained.',
        modified_region_protected=[426,752],instances=instances,evidence=evidence,
        target_objects=sum(len(x['targets'])for x in instances),logical_bits=sum(t['logical_bits']for x in instances for t in x['targets']),
        protected_objects=sum(len(x['protected'])for x in instances),selection_independent_of_hits=True,
        evidence_limit='Actual six FP32->FP16 narrow and FP16->FP32 widen policy cases; no integer-conversion/FP64/fullIEEE certification.',
        FMA_C910_disjoint=all('.gen_operation_groups[3].'in x['scope'] for x in instances),
        native_qualified=False,EDA_launched=False,applied=False,pins=pins)
    output.parent.mkdir(exist_ok=True);life.save(output,result)
    print(json.dumps(dict(output=str(output),seal=life.digest(output),objects=result['target_objects'],logical_bits=result['logical_bits'],pins=len(pins))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    review(p.parse_args().output.resolve())
