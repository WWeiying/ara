"""Add exact raw724 replay branch coordinates to sealed software preflight."""
import argparse
import json
from pathlib import Path

import build_operand_index_snapshot_preflight as p
from closure_point_inventory import points

PRE = p.OUT/'operand-index-snapshot-preflight-724-20261006-02'
SEAL = '97922fb66b63b47a82c8da544dda28e9a270ff3de22b51dee7028f4dfb278448'


def bind(row, definition):
    p.require(row['width'] == 752 and row['checksum'] == definition.get('chksum') == '1229254119',
              'Compiled branch shape differs')
    point = next(v for v in points('branch',definition,row['width']) if v['raw_index'] == 526)
    p.require((point['native_id'],point['vector'],point['attributes']['chksum']) ==
              ('104','7','3186254472'), 'Replay branch coordinate differs')
    leaves = [e for e in point['expressions'] if e['id'] == '518' and
              e['exprstr'] == 'requester_metadata_q[6].source_snapshot_replay']
    p.require(len(leaves) == 1 and point['native_vector']['vector'][-int(leaves[0]['index'])] == '1',
              'Not the source replay true arm')
    p.require(not int(row['bits'],16)&(1 << (row['width']-1-526)), 'Branch already hit724')
    return point


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output = parser.parse_args().output.absolute()
    p.require(output.parent == p.OUT and output.resolve() == output and not output.exists(), 'Fresh output required')
    manifest_path = PRE/'preflight-manifest.json'
    p.require(p.s.sha(manifest_path) == SEAL, 'Software preflight seal differs')
    manifest = json.loads(manifest_path.read_bytes())
    p.s.check(manifest['pins'])
    p.s.check(manifest['output_pins'])
    p.require(manifest['status'] == 'OPERAND_INDEX_SNAPSHOT_SPIKE_PREFLIGHT_PASS_NOT_DUT' and
              manifest['baseline_tests'] == 724, 'Software qualification differs')
    evidence = json.loads((PRE/'target-before.json').read_bytes())
    bits = json.loads((p.BASE/'combined-bits.json').read_bytes())
    design = p.s.Design(p.old.BUILD/'sim/simv.vdb')
    targets = list(evidence['targets'])
    for lane in range(4):
        scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_requester' % lane
        row = bits['metrics']['branch'][scope]
        point = bind(row,design.definition(scope,'branch'))
        targets.append(dict(scope=scope,metric='branch',point=point,width=row['width'],
                            checksum=row['checksum'],hit_before=False))
    pins = p.s.merge_pins(p.s.merge_pins(manifest['pins'],manifest['output_pins']),
        {str(f):p.s.sha(f) for f in (manifest_path,Path(__file__).resolve(),
         Path(__file__).with_name('test_bind_operand_index_snapshot_branch_targets.py'))})
    p.s.check(pins)
    p.s.save(output,dict(status='RAW724_EXACT16_REACHABLE_TARGET_HYPOTHESIS_NOT_DUT',
        software_preflight=str(PRE),software_seal=SEAL,pins=pins,targets=targets,
        counts=dict(cond=12,branch=4),runtime_hit_required=True,expected_branch_line='518',
        native_GUI_ID_qualification=False,coverage_admitted=False,vcs_started=False,
        predicate_chain=evidence['predicate_chain'],budget_seconds=300))
    print(json.dumps(dict(output=str(output),seal=p.s.sha(output),targets=len(targets))))


if __name__ == '__main__':
    main()
