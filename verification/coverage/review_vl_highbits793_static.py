"""Read-only frozen VL/count high-bit inventory; unresolved writers stay HOLD."""
import argparse
import json
from pathlib import Path
import re

import targeted_toggle_evidence_v2 as t
import rank_cva6_scalar_data767 as typed
import report_population793_qbs3232 as policy

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
BASE = OUT/'scalar-slot-rotation-offline-admitted793-parent-20261008-01'
BASE_SHA = '757513188f805841491c898584b22722df80facd8f8c9fb424564a82502f17c3'
REPORT = OUT/'current-population793-qbs3232-parent-20261008-01'
REPORT_SHA = 'b38418835ab071fdd5918f51bc4b7e85e22e4851b4e6478c2c4a75b11d934549'
BOOK = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'


def collect():
    pins = {}
    def read(path,sha):
        t.require(t.digest(path) == sha,'Frozen input drift: '+str(path))
        pins[str(path)] = sha
        return path.read_bytes()
    book = json.loads(read(BOOK,BOOK_SHA))
    sources = {}
    for relative in ('hardware/src/ara.sv','hardware/src/ara_dispatcher.sv',
                     'hardware/src/lane/lane_sequencer.sv','hardware/src/lane/operand_requester.sv',
                     'hardware/src/lane/operand_queue.sv','hardware/src/vlsu/addrgen.sv'):
        original = ROOT/relative
        actual = original
        if t.digest(original) != book[str(original)]:
            actual = OUT/'old-image-source-evidence-20261006-01'/original.name
        read(actual,book[str(original)])
        sources[relative] = dict(path=str(actual),sha256=book[str(original)],original=str(original))
    log = OUT/'repaired-aligned-build-20260930-01/compile.log'
    text = read(log,t.digest(log)).decode()
    t.require('ARA Configuration: NR_LANES=4 VLEN=1024' in text,'Actual frozen compile configuration')
    admission = json.loads(read(BASE/'admission-manifest.json',BASE_SHA))
    t.require(admission['coverage_admitted'] is True,'Published793 required')
    authority = dict(admission['input_pins'],**admission['output_pins'])
    union = json.loads(read(BASE/'combined-toggle-bits.json',authority[str(BASE/'combined-toggle-bits.json')]))
    ledger = read(BASE/'combined-inputs.txt',authority[str(BASE/'combined-inputs.txt')]).decode().splitlines()
    t.require(len(ledger) == len(set(ledger)) == 794,'Exact formal793')
    config = json.loads(read(REPORT/'config.json',REPORT_SHA))
    t.require(config['input_ledger'] == ledger,'Current native report population binding')
    el = read(REPORT/'combined.el',config['pins'][str(REPORT/'combined.el')]).decode()
    semantics = policy.stable.semantic(el)
    t.require(policy.stable.semantic_seal(semantics) == config['expected_EL_semantic_sha256'],'Current EL authority')
    masks = policy.physical(semantics)
    scopes = [s for s in union if s.endswith('.i_ara.i_dispatcher') or
              re.search(r'\.i_operand_queues\.i_operand_queue_[^.]+$',s)]
    db = Path(ledger[0])/'snps/coverage/db'
    trees = []
    for relative in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        path = db/relative; read(path,authority[str(path)]); trees.append(t.xml(path))
    checks,defs,held = {},{},[]
    for scope in scopes:
        try:
            c,d = t.definitions(*trees,[scope]); checks.update(c); defs.update(d)
        except ValueError as error:
            held.append(dict(scope=scope,raw_scope_width=union[scope]['width'],reason=str(error),
                             typed_capacity_not_inferred=True,status='HOLD_COMPILED_DEFINITION'))
    fields = []
    wanted = {'csr_vl_q','csr_vl_d','csr_vstart_q','csr_vstart_d','elem_count_q','elem_count_d','cmd.elem_count'}
    for scope in scopes:
        if scope not in defs: continue
        t.require(union[scope]['checksum'] == checks[scope],'Exact compiled scope')
        nodes,_ = typed.typed_nodes(defs[scope]['shape'],union[scope])
        for n in nodes:
            if n['name'] not in wanted: continue
            t.require(n['logical_width'] == 11 and n['left'] == '10' and n['right'] == '0','Exact vlen_t width')
            owners = [dict(checksum=k[1],prefix=list(k[3]),direction=k[4],mask=hex(v))
                      for k,v in masks.items() if k[0] == scope and k[2] == n['name'] and v & (3 << 9)]
            opaque = [list(r) for r in semantics[0] if (r[0] == scope or scope.startswith(r[0]+'.')) and
                      (r[3] == 'WHOLE_SCOPE' or r[3].startswith('Toggle '))]
            fields.append(dict(scope=scope,name=n['name'],module=defs[scope]['module'],attributes=n,
                reviewed_source_bits=[9,10],full_field_raw_missing_serialized_positions=n['missing_coordinates'],
                source_highbit_raw_coordinates=None,source_highbit_raw_capacity=None,
                existing_EL_owners=owners,opaque_EL_owners=opaque,
                status='DYNAMIC_SCALAR_WRITE' if 'vstart' in n['name'] else
                       'DYNAMIC_VSET' if n['name'].startswith('csr_vl_') else 'HOLD_FULL_WRITER_DOMAIN',
                native_bit_and_direction_order_not_inferred=True,waiver_candidate=False))
    for path,sha in pins.items(): t.require(t.digest(Path(path)) == sha,'Read-end drift')
    return dict(status='STATIC_VL_HIGHBITS_HOLD_NO_EXCLUSION',population=793,VLEN=1024,NrLanes=4,vlen_width=11,
        input_pins=pins,source_binding=sources,fields=fields,
        reviewed_scopes=len(scopes),exact_bound_scopes=len(defs),compiled_definition_HOLD=held,reviewed_objects=len(fields),
        raw_missing_highbit_slots=None,
        full_field_raw_missing_slots=sum(len(f['full_field_raw_missing_serialized_positions']) for f in fields),
        supersedes_unqualified_diagnostic='vl-highbits793-static-agent-20261008-01.json: linear serialized position is not proven source bit order',
        permitted_exclusion_directions=0,official_denominator=None,EDA_started=False,EL_created=False,
        conclusions=[
            dict(field='csr_vstart_[dq]',status='DYNAMIC_KEEP',source='ara_dispatcher.sv:4649,4672,4710,4749,4773,4814',
                 reason='Scalar CSR write/set/clear truncates to11 bits, not VL. Values512/1024/2047 are hardware-representable.'),
            dict(field='csr_vl_[dq]',status='DYNAMIC_KEEP',source='ara_dispatcher.sv:1698..1737,4342',
                 reason='VL512 (e8m4) and1024 (e8m8) legally set bits9/10. Illegal vtype writes0. FOF exception_vstart bypasses the vset clamp, blocking a separate complete-domain induction.'),
            dict(field='FOF exception_vstart producer',status='HOLD_INDUCTION_REQUIRED',source='addrgen.sv:1084,1243',
                 reason='vl-(axi_addrgen.len>>vew) needs all-cycle remaining-length invariant; no unsigned underflow assumed away.'),
            dict(field='cmd.elem_count',status='HOLD_ALL_REQUEST_PRODUCERS',source='operand_requester.sv:402..416,452,473,568; lane_sequencer.sv:861..896',
                 reason='scale_vl changes EEW domain; slide adds residue before ceil lane division. Computed subtraction runs before request validity gating.'),
            dict(field='elem_count_[dq]',status='HOLD_NOT_CMD_EQUIVALENT',source='operand_queue.sv:507..544',
                 reason='Increment and same-cycle completion reset differ from command threshold; require complete command-domain/step/reset proof, not bench maximum.')])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    a = p.parse_args(); t.require(a.output.parent.resolve() == OUT and not a.output.exists(),'Fresh separate output')
    result = collect()
    with a.output.open('x') as stream: json.dump(result,stream,indent=2,sort_keys=True); stream.write('\n')
    print(json.dumps(dict(output=str(a.output),sha256=t.digest(a.output),objects=result['reviewed_objects'],
                         raw_missing_slots=result['raw_missing_highbit_slots'],permitted_exclusion_directions=0)))
