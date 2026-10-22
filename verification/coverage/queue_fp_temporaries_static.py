"""Inventory source-constant FP temporaries in non-FPU queues; no exclusions applied."""
import argparse
import json
from pathlib import Path
import re
from inventory_operand_debug import Design
import prove_mask_store_snapshot_zero as lexical
import targeted_toggle_evidence as evidence

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
BUILD = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
DESIGN = BUILD.parent/'sim/simv.vdb'
require, digest = evidence.require, evidence.digest
KINDS = ('alu_a','alu_b','st_mask_a','slide_addrgen_a','mask_b','mask_m')


def source_contract(text):
    text = lexical.clean(text)
    compact = re.sub(r'\s+', '', text)
    require("for(inti=0;i<4;i++)fp8[i]='0;" in compact and
            "for(inti=0;i<2;i++)fp16[i]='0;" in compact and "fp32='0;" in compact,
            'Default whole-object zero assignment differs')
    require(re.findall(r"\bfp8\s*\[[^]]+\]\s*=\s*([^;]+);", text)==["'0"],
            'Additional global fp8 writer')
    require(re.findall(r"\bfp16\s*\[[^]]+\]\s*=\s*([^;]+);", text)==
            ["'0", 'ibuf_operand[8*select + 32*e +: 16]'], 'Global fp16 writer differs')
    require(re.findall(r"\bfp32\s*=\s*([^;]+);", text)==
            ["'0", 'ibuf_operand[8*select +: 32]'], 'Global fp32 writer differs')
    block = compact.split('OpQueueConversionWideFP2:begin',1)[1].split('OpQueueAdjustFPCvt:begin',1)[0]
    require(block.startswith('if(FPUSupport!=FPUSupportNone)begin') and
            'fp16[e]=ibuf_operand[8*select+32*e+:16];' in block and
            'fp32=ibuf_operand[8*select+:32];' in block, 'Only nonzero writers not FPU-gated')
    return dict(default_zero=True, nonzero_writers_gated_by_FPU=True,
                initial_X_not_excluded=True, reset_and_control_not_excluded=True)


def fields():
    return {'fp8[%d].%s'%(i,f) for i in range(4) for f in ('s','e','m')} | {
        'fp16[%d].%s'%(i,f) for i in range(2) for f in ('s','e','m')} | {
        'fp32.'+f for f in ('s','e','m')}


def collect(output):
    require(not output.exists(), 'Fresh static inventory required')
    book = json.loads(BUILD.read_bytes())
    pins = {str(BUILD):digest(BUILD), str(Path(__file__).resolve()):digest(Path(__file__))}
    for rel in ('hardware/src/lane/operand_queue.sv','hardware/src/lane/operand_queues_stage.sv',
                'hardware/include/ara_pkg.sv'):
        p = ROOT/rel
        require(digest(p)==book[str(p)], 'Frozen source mismatch: '+rel)
        pins[str(p)] = book[str(p)]
    proof = source_contract((ROOT/'hardware/src/lane/operand_queue.sv').read_text())
    stage = (ROOT/'hardware/src/lane/operand_queues_stage.sv').read_text()
    blocks = {m.group(2):m.group(1) for m in re.finditer(
        r'operand_queue\s*#\((.*?)\)\s+(i_operand_queue_\w+)\s*\(', stage, re.S)}
    d = Design(DESIGN)
    instances = []
    for lane in range(4):
        for kind in KINDS:
            name = 'i_operand_queue_'+kind
            require(re.search(r'\.FPUSupport\s*\(\s*FPUSupportNone\s*\)', blocks[name]),
                    'Source instance is not explicitly FPU-disabled')
            scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_queues.%s'%(lane,name)
            node = d.definition(scope,'tgl')
            support = re.findall(r'FPUSupport=([^, ]+)', node.get('name',''))
            require(support and set(support)<= {'0','56'} and '0' in support,
                    'Unknown/missing compiled FPU specialization')
            compiled_disabled = set(support)=={'0'}
            selected = [dict(n.attrib, kind=n.tag) for n in node.iter()
                        if n.tag in ('node','vectornode') and n.get('name') in fields()]
            require(len(selected)==21 and {n['name'] for n in selected}==fields() and
                    all(n.get('portnode')=='0' and n.get('excluded')=='0' for n in selected),
                    'Missing/port/already-excluded compiled temporary')
            bits = sum(abs(int(n.get('left','0'))-int(n.get('right','0')))+1 for n in selected)
            require(bits==96, 'Wrong complete-object widths')
            protected = [dict(n.attrib,kind=n.tag) for n in node.iter()
                         if n.tag in ('node','vectornode') and n.get('name') not in fields()]
            instances.append(dict(scope=scope, checksum=node.get('chksum'),
                                  compiled_parameters=node.get('name'), targets=selected,
                                  all_other_objects_protected=protected, logical_bits=bits,
                                  compiled_all_variants_FPU_disabled=compiled_disabled,
                                  decision='STATIC_DISABLED_CANDIDATE_NATIVE_PENDING' if compiled_disabled else
                                  'HOLD_MERGED_FPU_VARIANTS_REQUIRE_INSTANCE_PARAMETER_BINDING'))
    for rel in ('design/verilog.design.xml','shape/tgl.verilog.shape.xml','shape/tgl.verilog.info.xml'):
        p = DESIGN/'snps/coverage/db'/rel
        pins[str(p)] = digest(p)
    for p,h in pins.items(): require(digest(p)==h, 'Inventory input drift')
    record = dict(status='SOURCE_COMPILED_DISABLED_FP_TEMPORARIES_STATIC_NOT_NATIVE_QUALIFIED',
                  instances=instances, source_proof=proof, input_pins=pins,
                  scopes=24, objects=504, logical_bits=2304, nominal_direction_slots=4608,
                  official_DVE_denominator=False, exclusions_applied=False, RTL_modified=False)
    record['unambiguous_compiled_scopes'] = sum(i['compiled_all_variants_FPU_disabled'] for i in instances)
    record['held_merged_scopes'] = 24-record['unambiguous_compiled_scopes']
    with output.open('x') as stream: json.dump(record,stream,indent=2)
    print({k:v for k,v in record.items() if k not in ('instances','input_pins','source_proof')})


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    collect(p.parse_args().output.resolve())
