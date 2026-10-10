"""Reject domain/bitmap contradictions and unbound inherited layouts."""
import argparse
import json
from pathlib import Path

import audit_operand_conversion_domains780 as a
from closure_point_inventory import points


def audit():
    result = a.audit()
    bpath = a.P.BASE / 'combined-bits.json'
    bitmap = a.P.life.read_bound(bpath, result['input_pins'][str(bpath)])
    design = a.P.inventory.s.Design(a.P.inventory.old.BUILD / 'sim/simv.vdb')
    contradictions = []
    for lane in range(4):
        for queue in a.DOMAINS:
            scope = a.P.SCOPE.replace('gen_lanes[0]', f'gen_lanes[{lane}]').replace(
                'i_operand_queue_mask_b', f'i_operand_queue_{queue}')
            row = bitmap['metrics']['branch'][scope]
            definition = design.definition(scope, 'branch')
            specs = {g.get('id'): g for g in definition.iter('branch_spec')}
            for p in points('branch', definition, 101):
                if not (int(row['bits'], 16) >> (100-p['raw_index']) & 1):
                    continue
                ones = {str(i+1) for i, c in enumerate(p['native_vector']['vector'][::-1]) if c == '1'}
                names = [e.get('name', e.get('exprstr', '')).strip()
                         for e in specs[p['native_id']].iter() if e.get('index') in ones]
                reason = a.classify(queue, p['native_id'], names)
                if reason:
                    contradictions.append(dict(scope=scope, raw_index=p['raw_index'],
                        group=p['native_id'], vector=p['vector'],
                        selected_items=names, contradicted_reason=reason,
                        data_checksum=row['checksum']))
    blocked_scopes = {c['scope'] for c in contradictions}
    eligible, hold = [], []
    for r in result['branch_candidates']:
        if r['data_checksum'] is None or r['scope'] in blocked_scopes:
            r['status'] = 'HOLD_UNBOUND_OR_CONTRADICTED_MAPPING'
            hold.append(r)
        else:
            r['status'] = 'SOURCE_BOUND_STATIC_CANDIDATE_NEEDS_NATIVE_QUALIFICATION'
            eligible.append(r)
    result['schema'] = 'OPERAND_CONVERSION_DOMAINS780_MAPPING_GATE_V1'
    result['branch_candidates'] = eligible
    result['mapping_hold'] = hold
    result['hit_domain_contradictions'] = contradictions
    result['counts'] = dict(source_bound_candidates=len(eligible), mapping_hold=len(hold),
        retained_unhit=len(result['retained_unhit']), hit_contradictions=len(contradictions))
    result['input_pins'][str(Path(__file__).resolve())] = a.P.life.digest(Path(__file__).resolve())
    a.P.life.check(result['input_pins'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    p = parser.parse_args().output.resolve()
    a.P.need(p.parent == a.P.OUT and not p.exists(), 'Fresh independent evidence')
    result = audit()
    a.P.life.save(p, result)
    print(json.dumps(dict(output=str(p), sha256=a.P.life.digest(p), counts=result['counts'])))
