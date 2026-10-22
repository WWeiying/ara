"""Checksum-bound FSM candidates; diagnostic raw coordinates, not native EL."""
import argparse
import hashlib
import json
from pathlib import Path
from closure_point_inventory import read_xml
from inventory_operand_debug import ROOT
from test_dispatcher_store_fsm_scope import StoreFSMScopeTests


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.base.absolute(), args.output.absolute()
    if base.parent != ROOT / 'verification/out' or out.parent != base.parent or out.exists():
        raise ValueError('Fresh direct output required')
    StoreFSMScopeTests.setUpClass()
    review = StoreFSMScopeTests()
    review.test_decode_blocked_has_only_default_and_guarded_assignment()
    review.test_arch_decode_allows_exactly_four_states()
    review.test_only_store_response_entry_requires_blocked_decode()
    source = ROOT.parent / 'ara_dsa/hardware/src/ara_dispatcher.sv'
    bitmap_path, status_path = base / 'combined-bits.json', base / 'status.json'
    status, bitmap = [json.loads(p.read_bytes()) for p in (status_path, bitmap_path)]
    count = status['aggregate_passed']
    if status['status'] != 'PASS_RAW_UNION_HISTORICAL_ONLY' or len(bitmap['tests']) != len(set(bitmap['tests'])) or len(bitmap['tests']) != count:
        raise ValueError('Not an admitted population')
    design = ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
    shape = design / 'snps/coverage/db/shape/fsm.verilog.shape.xml'
    if sha(shape) != bitmap['design']['shape/fsm.verilog.shape.xml']:
        raise ValueError('FSM shape differs')
    paths = [source, bitmap_path, status_path, shape, Path(__file__).resolve(),
             ROOT / 'verification/coverage/test_dispatcher_store_fsm_scope.py']
    pins = {str(path): sha(path) for path in paths}
    scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
    record = bitmap['metrics']['fsm'][scope]
    nodes = [n for n in read_xml(shape).iter('fsmdef') if n.get('chksum') == record['checksum'] and n.get('name') == 'ara_dispatcher']
    if len(nodes) != 1:
        raise ValueError('Ambiguous FSM definition')
    allowed = {'NORMAL_OPERATION', 'OVERLAP_ISSUE_ORIGINAL', 'WAIT_IDLE', 'WAIT_IDLE_FLUSH'}
    rows, offset = [], 0
    bits = int(record['bits'], 16)
    for fsm in nodes[0].iter('fsmfsm'):
        states, edges = fsm.findall('state'), fsm.findall('transition')
        names = {s.get('id'): s.get('name') for s in states}
        for index, node in enumerate([*states, *edges]):
            raw = offset + index
            if raw >= record['width']:
                raise ValueError('Invalid raw coordinate')
            edge = index >= len(states)
            frm, to = (names[node.get('fromid')], names[node.get('toid')]) if edge else (None, node.get('name'))
            target = edge and fsm.get('name') == 'state_q' and to == 'WAIT_STORE_RESPONSE' and frm not in allowed
            hit = bool(bits & (1 << (record['width'] - raw - 1)))
            if target and hit:
                raise ValueError('Hit contradicts structural invariant')
            rows.append(dict(machine=dict(fsm.attrib), raw_index=raw, kind='edge' if edge else 'state',
                             attributes=dict(node.attrib), source_state=frm, destination_state=to,
                             hit=hit, candidate=target))
        offset += len(states) + len(edges)
    if offset != record['width'] or sum(r['candidate'] for r in rows) != 11:
        raise ValueError('FSM population differs')
    if any(sha(Path(path)) != value for path, value in pins.items()):
        raise ValueError('Evidence drift')
    result = dict(status='STRUCTURAL_FSM_CANDIDATES_NOT_NATIVE_QUALIFIED', tests=count,
        scope=scope, checksum=record['checksum'], width=offset, targets=11, protected=offset-11,
        native_binding_verified=False, exclusions_applied=False, rows=rows, pins=pins)
    with out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'tests', 'targets', 'protected')}))


if __name__ == '__main__':
    main()
