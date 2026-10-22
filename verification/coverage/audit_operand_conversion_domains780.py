"""Conservative source-domain branch candidates, not native qualification."""
import argparse
import json
from pathlib import Path

import audit_maskb_producer_routes780 as routes
from closure_point_inventory import points

P = routes.prior
EW = ['EW8', 'EW16', 'EW32', 'EW64']
DOMAINS = {
    'alu_a': {'OpQueueConversionNone': EW, 'OpQueueConversionSExt2': EW[:3],
              'OpQueueConversionZExt2': EW[:3], 'OpQueueReductionZExt': EW},
    'mask_b': {'OpQueueConversionNone': EW, 'OpQueueConversionSExt8': ['EW8'],
               'OpQueueConversionSExt4': ['EW16'], 'OpQueueConversionSExt2': ['EW32']},
}


def classify(queue, group, selected_names):
    P.need(queue in DOMAINS, 'Only reviewed exact queue domains')
    names = set(selected_names)
    if group == '4':
        if queue == 'mask_b' and 'cmd.is_reduct' in names:
            return 'MaskB all command writers is_reduct=0'
        if queue == 'alu_a' and 'MFPU_ADDRGEN' in names:
            return 'AluA all command writers target_fu=ALU_SLDU'
    if group == '5':
        conversions = names & {f'OpQueueConversion{x}' for x in
            ('None', 'SExt2', 'SExt4', 'SExt8', 'ZExt2', 'ZExt4', 'ZExt8', 'WideFP2')}
        conversions |= names & {'OpQueueReductionZExt', 'OpQueueAdjustFPCvt'}
        P.need(len(conversions) <= 1, 'Ambiguous conversion vector')
        if conversions:
            conversion = next(iter(conversions))
            if conversion not in DOMAINS[queue]:
                return f'No {queue} producer for {conversion}'
            eews = names & set(EW)
            P.need(len(eews) <= 1, 'Ambiguous EEW vector')
            if eews and not eews <= set(DOMAINS[queue][conversion]):
                return f'Producer relation forbids {conversion}/{next(iter(eews))}'
    return None


def audit():
    previous = routes.audit()
    pins = previous['input_pins'].copy()
    bitmap_path = P.BASE / 'combined-bits.json'
    bitmap = P.life.read_bound(bitmap_path, pins[str(bitmap_path)])
    design = P.inventory.s.Design(P.inventory.old.BUILD / 'sim/simv.vdb')
    candidates, retained = [], []
    for lane in range(4):
        for queue in DOMAINS:
            scope = P.SCOPE.replace('gen_lanes[0]', f'gen_lanes[{lane}]').replace(
                'i_operand_queue_mask_b', f'i_operand_queue_{queue}')
            row = bitmap['metrics']['branch'][scope]
            definition = design.definition(scope, 'branch')
            P.need(row['width'] == 101 and definition.get('chksum') == '1417162425',
                   'Exact frozen compiled layout')
            specs = {g.get('id'): g for g in definition.iter('branch_spec')}
            for point in points('branch', definition, 101):
                if int(row['bits'], 16) >> (100 - point['raw_index']) & 1:
                    continue
                ones = {str(i + 1) for i, b in enumerate(
                    point['native_vector']['vector'][::-1]) if b == '1'}
                names = [e.get('name', e.get('exprstr', '')).strip()
                         for e in specs[point['native_id']].iter() if e.get('index') in ones]
                reason = classify(queue, point['native_id'], names)
                record = dict(scope=scope, raw_index=point['raw_index'], width=101,
                    data_checksum=row['checksum'], definition_checksum='1417162425',
                    group=point['native_id'], vector=point['vector'],
                    group_checksum=point['attributes']['chksum'],
                    xml_vector=point['native_vector']['vector'], selected_source_items=names,
                    before_hit=False, reason=reason)
                (candidates if reason else retained).append(record)
    pins[str(Path(__file__).resolve())] = P.life.digest(Path(__file__).resolve())
    pins[str(Path(__file__).with_name('test_audit_operand_conversion_domains780.py').resolve())] = P.life.digest(
        Path(__file__).with_name('test_audit_operand_conversion_domains780.py'))
    P.life.check(pins)
    return dict(schema='OPERAND_CONVERSION_DOMAINS780_STATIC_V1', baseline=780,
        input_pins=pins, legal_domain_overapproximation=DOMAINS,
        proof_routes=previous['producer_partition'],
        source_contract=dict(alu_a_writers=[494, 946], mask_b_writers=[1066, 1143, 1227],
            requester='450..456 copies eew/conv/target_fu/is_reduct; only elem_count adjusted',
            command_fifo='operand_queue.sv70..75 stores entire command unchanged',
            alu_a='VFU_Alu VS1 integer conversion; VFU_MaskUnit conv=None; no FP VS1 routing'),
        branch_candidates=candidates, retained_unhit=retained,
        counts=dict(candidates=len(candidates), retained_unhit=len(retained), scopes=8),
        other_queue_status='AluB/MFPU/StA/SlideAddrGenA/MaskM not approved by this audit; producer domains HOLD',
        toggle_domain_candidates=[
            dict(scopes=[r['scope'] for r in previous['alu_a_missing']],
                 fields=['cmd.target_fu', 'cmd.conv'],
                 contract='Valid commands: target_fu=ALU_SLDU; conv restricted to documented domain'),
            dict(scopes=[r['scope'] for r in previous['mask_b_targets']],
                 fields=['cmd.target_fu', 'cmd.is_reduct', 'cmd.conv'],
                 contract='Valid commands: target_fu=ALU_SLDU or zero default; is_reduct=0; conv restricted')],
        toggle_status='HOLD: require FIFO/reset/empty-output identity and typed bit mapping plus existing EL difference',
        protected_dynamic_fields=['usage_q', 'usage_d', 'select_q', 'select_d', 'elem_count_q',
                                  'elem_count_d', 'operand_i', 'operand_o', 'hazard', 'ready', 'valid'],
        scope_limit='Legal reset-initialized binary requests; no X-state or malformed-request waiver',
        native_GUI_qualified=False, application_approved=False, EDA_started=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    path = parser.parse_args().output.resolve()
    P.need(path.parent == P.OUT and not path.exists(), 'Fresh independent artifact')
    result = audit()
    P.life.save(path, result)
    print(json.dumps(dict(output=str(path), sha256=P.life.digest(path), counts=result['counts'])))
