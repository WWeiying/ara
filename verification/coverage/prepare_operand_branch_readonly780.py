"""Prepare two exact native Branch detail exports; no EDA launch API."""
import argparse
import json
from pathlib import Path
import tkinter

import audit_operand_conversion_domains780 as domains
from closure_point_inventory import points

P = domains.P
TCL = Path(__file__).with_name('export_operand_branch_readonly780.tcl').resolve()


def prepare(output):
    P.need(output.parent == P.OUT and not output.exists(), 'Fresh independent output')
    config_path = P.REPORT / 'config.json'
    config = P.life.read_bound(config_path, '1d0c7ddf9b7752f79192ca90f8915e1be3da8d1180f8057ec2b3ad18c481ed00')
    q = P.life.read_bound(P.REPORT / 'qualification.json', P.Q_SHA)
    P.need(config['population'] == q['population'] == 780, 'Exact qualified population780')
    pins = P.life.read_bound(P.OUT / 'operand-conversion-domains780-mapping-gated-agent-20261008-01.json',
        'ff2f57662a7376a5154b2dc215ff73f663412b97a648fbe215eaf0c8c57c4e27')['input_pins'].copy()
    bitmap = P.life.read_bound(P.BASE / 'combined-bits.json', pins[str(P.BASE / 'combined-bits.json')])
    design = P.inventory.s.Design(P.inventory.old.BUILD / 'sim/simv.vdb')
    scopes = [P.SCOPE.replace('i_operand_queue_mask_b', 'i_operand_queue_alu_a'), P.SCOPE]
    evidence = []
    for scope in scopes:
        row = bitmap['metrics']['branch'][scope]
        definition = design.definition(scope, 'branch')
        specs = {g.get('id'): g for g in definition.iter('branch_spec')}
        records = []
        for p in points('branch', definition, 101):
            ones = {str(i+1) for i, b in enumerate(p['native_vector']['vector'][::-1]) if b == '1'}
            names = [e.get('name', e.get('exprstr', '')).strip()
                for e in specs[p['native_id']].iter() if e.get('index') in ones]
            queue = 'alu_a' if scope == scopes[0] else 'mask_b'
            reason = domains.classify(queue, p['native_id'], names)
            hit = bool(int(row['bits'], 16) >> (100-p['raw_index']) & 1)
            records.append(dict(raw_index=p['raw_index'], group=p['native_id'],
                vector=p['vector'], group_checksum=p['attributes']['chksum'],
                xml_vector=p['native_vector']['vector'], source_items=names, before_hit=hit,
                domain_contradiction=reason if hit else None,
                candidate_reason=reason if not hit else None,
                native_label=None, native_mapping_status='HOLD_UNMEASURED'))
        evidence.append(dict(scope=scope, data_checksum=row['checksum'],
            definition_checksum=definition.get('chksum'), points=records))
    pins[str(config_path)] = P.life.digest(config_path)
    for p in (TCL, Path(__file__).resolve(), Path(__file__).with_name('test_operand_branch_readonly780.py')):
        pins[str(p.resolve())] = P.life.digest(p)
    P.life.check(pins)
    interp = tkinter.Tcl()
    def line(name, values):
        return interp.call('format', '%s', interp.call('list', 'set', name, tuple(values))) + '\n'
    selection = line('obr_design', [config['input_ledger'][0]])
    # Scalar design must be a path, not a one-element list containing a path.
    selection = interp.call('format', '%s', interp.call('list', 'set', 'obr_design', config['input_ledger'][0])) + '\n'
    selection += line('obr_testdirs', config['input_ledger'][1:])
    selection += line('obr_tests', config['expected_selected'])
    selection += line('obr_scopes', scopes)
    interp.eval(selection)
    P.need(int(interp.call('llength', interp.getvar('obr_tests'))) == 780 and
           int(interp.call('llength', interp.getvar('obr_scopes'))) == 2, 'Generated Tcl list identity')
    output.mkdir()
    (output / 'selection.tcl').write_text(selection)
    P.life.save(output / 'xml-knownhit-and-hold.json', evidence)
    pins.update({str(p): P.life.digest(p) for p in output.iterdir() if p.is_file()})
    P.life.save(output / 'plan.json', dict(schema='OPERAND_TWO_BRANCH_READONLY780_PLAN_V1',
        input_pins=pins, output=str(output), entry=str(TCL), population=780, scopes=scopes,
        env=dict(OPERAND_BRANCH_READONLY_SELECTION=str(output/'selection.tcl'),
                 OPERAND_BRANCH_READONLY_OUTPUT=str(output)),
        native_columns='Read actual gui_list_get_property column labels; do not assume names',
        native_unique_bindings=0, all_132_candidates_status='HOLD_PENDING_NATIVE_EXPRESSION_VECTOR_CALIBRATION',
        timeout_seconds=300, no_exclusions=True, EDA_started=False,
        parent_review_required=True))
    print(json.dumps(dict(output=str(output), seal=P.life.digest(output/'plan.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    prepare(parser.parse_args().output.resolve())
