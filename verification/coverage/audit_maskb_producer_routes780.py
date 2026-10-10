"""Frozen-source/raw-shape diagnostic only; never runs EDA or applies EL."""
import argparse
import json
from pathlib import Path
import re

import preflight_mask_b_sext4 as prior
from closure_point_inventory import points


def audit():
    life, root, out = prior.life, prior.ROOT, prior.OUT
    book = out / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    pins = {str(book): '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'}
    sources = life.read_bound(book, pins[str(book)])
    paths = {}
    for name, original in (
            ('dispatcher', 'hardware/src/ara_dispatcher.sv'),
            ('lane', 'hardware/src/lane/lane_sequencer.sv'),
            ('sequencer', 'hardware/src/ara_sequencer.sv'),
            ('package', 'hardware/include/ara_pkg.sv'),
            ('queue', 'hardware/src/lane/operand_queue.sv'),
            ('stage', 'hardware/src/lane/operand_queues_stage.sv'),
            ('requester', 'hardware/src/lane/operand_requester.sv')):
        path = root / original
        if name in ('dispatcher', 'lane'):
            path = out / 'old-image-source-evidence-20261006-01' / path.name
        paths[name] = str(path)
        pins[str(path)] = sources[str(root / original)]
    life.check(pins)
    lane = Path(paths['lane']).read_text()
    prior.need([int(lane[:m.start()].count('\n')) + 1 for m in
                re.finditer(r'operand_request\[MaskB\] =', lane)] == [1066, 1143, 1227],
               'All three MaskB request writers must be reviewed')
    prior.need([int(lane[:m.start()].count('\n')) + 1 for m in
                re.finditer(r'operand_request\[AluA\] =', lane)] == [494, 946],
               'All two AluA request writers must be reviewed')
    manifest_path = prior.BASE / 'admission-manifest.json'
    manifest = life.read_bound(manifest_path, prior.BASE_SHA)
    bitmap_path = prior.BASE / 'combined-bits.json'
    pins[str(manifest_path)] = prior.BASE_SHA
    pins[str(bitmap_path)] = manifest['output_pins'][str(bitmap_path)]
    bitmap = life.read_bound(bitmap_path, pins[str(bitmap_path)])
    db = prior.inventory.old.BUILD / 'sim/simv.vdb/snps/coverage/db'
    pins.update({str(db / p): h for p, h in bitmap['design'].items()})
    design = prior.inventory.s.Design(prior.inventory.old.BUILD / 'sim/simv.vdb')
    mask, alu = [], []
    for lane_id in range(4):
        for queue, records in (('mask_b', mask), ('alu_a', alu)):
            scope = prior.SCOPE.replace('gen_lanes[0]', f'gen_lanes[{lane_id}]').replace(
                'i_operand_queue_mask_b', f'i_operand_queue_{queue}')
            row = bitmap['metrics']['branch'][scope]
            definition = design.definition(scope, 'branch')
            prior.need(row['width'] == 101 and definition.get('chksum') == '1417162425',
                       'Exact compiled queue shape')
            selected = points('branch', definition, row['width'])
            if queue == 'mask_b':
                selected = [p for p in selected if p['raw_index'] == 71]
                p = selected[0]
                prior.need((p['native_id'], p['vector'], p['attributes']['chksum']) ==
                           ('5', '5', '718333796'), 'Exact branch identity')
                prior.need([i + 1 for i, bit in enumerate(p['native_vector']['vector'][::-1])
                            if bit == '1'] == [8, 9, 10], 'SExt4/SupportIntExt4/EW8')
            else:
                selected = [p for p in selected if not
                            (int(row['bits'], 16) >> (100 - p['raw_index']) & 1)]
            records.append(dict(scope=scope, width=101, data_checksum=row['checksum'],
                definition_checksum=definition.get('chksum'), points=[dict(
                    raw_index=p['raw_index'], group=p['native_id'], vector=p['vector'],
                    group_checksum=p['attributes']['chksum'], xml_vector=p['native_vector']['vector'],
                    before_hit=bool(int(row['bits'], 16) >> (100 - p['raw_index']) & 1))
                    for p in selected]))
    prior.need(all(not r['points'][0]['before_hit'] for r in mask), 'Target must remain zero780')
    el = prior.REPORT / 'combined.el'
    q = life.read_bound(prior.REPORT / 'qualification.json', prior.Q_SHA)
    pins[str(prior.REPORT / 'qualification.json')] = prior.Q_SHA
    pins[str(el)] = q['source_design_native_pins'][str(el)]
    other, _ = prior.report.semantic(el.read_text())
    prior.need(not any(s in {r['scope'] for r in mask} and
                       re.match(r'^Branch\s+5(?:\D|$)', line) for s, h, machine, line in other),
               'MaskB group must not already be excluded')
    pins[str(Path(__file__).resolve())] = life.digest(Path(__file__).resolve())
    life.check(pins)
    return dict(schema='MASKB_PRODUCER_ROUTE780_READONLY_V1', baseline=780,
        source_paths=paths, input_pins=pins, mask_b_targets=mask, alu_a_missing=alu,
        rejected_hypothesis=dict(instructions=['VCPOP', 'VFIRST'],
            dispatcher='2637/2642 preserves source EEW; 2658 chooses SExt4 at SEW16',
            route='sequencer294 VFU_MaskUnit -> lane981 AluB conv=None -> lane1010 EEW64',
            mask_b='lane1066 conv=None, push1103 requires use_vd_op; scalar result has no vd',
            existing776='e8m8; changing SEW does not change downstream consumer route'),
        producer_partition=[
            dict(writer=1066, kind='MaskUnit old destination', conversion='None'),
            dict(writer=1143, kind='VFU_None scalar move', conversion='pe_req.conversion_vs2',
                 invariant='VMVXS SExt4 iff SEW16; default eew_vs2=SEW16; VFMVFS has no SExt4'),
            dict(writer=1227, kind='VRGATHER/VCOMPRESS ad-hoc override', conversion='zero/None')],
        scope_limit='Legal reset-initialized binary product requests; not malformed requests or X-state waiver',
        mask_b_status='SOURCE_STRUCTURAL_CANDIDATE_ONLY_NEEDS_NATIVE_SINGLETON_ROUNDTRIP',
        alu_a_status='NO_SOURCE_PROVEN_LEGAL_MISSING_BRANCH_FOUND',
        alu_a_reasons=['flush tied0', 'SupportReduct/IntExt2/4/8 fixed1, SupportNtrVal fixed0',
            'AluA target_fu always ALU_SLDU, never MFPU_ADDRGEN',
            'Legal VS1 conversions None/SExt2/ZExt2/ReductionZExt; factor4/8 and FP conversion have no AluA producer',
            'ReductionZExt raw49..52 require lane_id0 and are hit in lane0; other lanes cannot take them'],
        native_GUI_qualified=False, application_approved=False, EDA_started=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    prior.need(output.parent == prior.OUT and not output.exists(), 'Fresh independent evidence')
    prior.life.save(output, audit())
    print(json.dumps(dict(output=str(output), sha256=prior.life.digest(output))))
