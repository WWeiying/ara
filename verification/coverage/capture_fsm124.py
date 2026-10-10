"""Exact124 FSM qualification on formal742; no observer or SIMD additions."""
import argparse
import copy
import csv
import json
from pathlib import Path
import re
import types

import report_fsm_observers742 as base

life, require, native = base.life, base.require, base.native
PRIOR = life.OUT / 'fsm72-four-observer-full742-20261007-01'
PRIOR_SEAL = '29a9513672657156858ad011369edec1f15e914dc8da06c5d40a1720736c5986'
PAIR = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_store_load_lookahead'
PORT0 = base.capture.PORT.replace('ports[2]', 'ports[0]')
PAIR_ARCS = {'Empty->Ready', 'Fill->Send', 'Pending->Ready', 'Ready->Send',
             'Replay->Ready', 'Replay->Send'}
PORT_ARCS = {'KILL_MISS->IDLE', 'KILL_MISS_ACK->IDLE', 'KILL_MISS_ACK->KILL_MISS',
             'MISS_REQ->KILL_MISS', 'MISS_REQ->KILL_MISS_ACK', 'MISS_WAIT->KILL_MISS'}


def addition(scope, source, dest):
    if scope == PAIR:
        return source + '->' + dest in PAIR_ARCS
    if scope == PORT0:
        return source + '->' + dest in PORT_ARCS
    if scope.endswith('.i_vmfpu'):
        lane = int(scope.split('gen_lanes[')[1].split(']')[0])
        return ((source in {'INTER_LANES_REDUCTION_RX', 'INTER_LANES_REDUCTION_TX'} and
                 dest in {'INTRA_LANE_REDUCTION', 'OSUM_REDUCTION'}) or
                (source == 'INTRA_LANE_REDUCTION' and dest == 'OSUM_REDUCTION') or
                (lane != 0 and source == 'LN0_REDUCTION_COMMIT' and
                 dest in {'INTRA_LANE_REDUCTION', 'OSUM_REDUCTION'}))
    if scope.endswith('.i_valu'):
        return source in {'INTER_LANES_REDUCTION_RX', 'INTER_LANES_REDUCTION_TX'} and dest == 'INTRA_LANE_REDUCTION'
    return False


def extra_groups(shape, bits, scope, source):
    metric = bits['metrics']['fsm'][scope]
    nodes = [n for n in shape.iter('fsmdef') if n.get('chksum') == metric['checksum'] and
             any(i.get('name') == scope for i in n.findall('fsminst'))]
    require(len(nodes) == 1, 'Ambiguous FSM instance')
    groups, offset = [], 0
    for machine in nodes[0].iter('fsmfsm'):
        states = machine.findall('state')
        ids = {s.get('id'): s.get('name') for s in states}
        for mode, items in [('State', states), ('Transition', machine.findall('transition'))]:
            rows = []
            for item in items:
                src = ids[item.get('fromid')] if mode == 'Transition' else None
                dst = ids[item.get('toid')] if mode == 'Transition' else item.get('name')
                rows.append(dict(name=src + '->' + dst if src else dst, raw_index=offset,
                                 target=bool(src and addition(scope, src, dst)), source=src,
                                 destination=dst, attributes=dict(item.attrib)))
                offset += 1
            groups.append(dict(scope=scope, source=source, checksum=metric['checksum'],
                               machine=dict(machine.attrib), mode=mode, rows=rows))
    require(offset == metric['width'], 'FSM width differs')
    return groups


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh output required')
    c = life.read_bound(PRIOR / 'config.json', PRIOR_SEAL)
    life.check(c['pins'])
    pins = life.merge_pins(c['pins'], {str(PRIOR / 'config.json'): PRIOR_SEAL})
    bits_path = base.BASE / 'combined-bits.json'
    bits = life.read_bound(bits_path, pins[str(bits_path)])
    design = Path(c['input_ledger'][0])
    shape = native.read_xml(design / 'snps/coverage/db/shape/fsm.verilog.shape.xml')
    groups = copy.deepcopy(c['plan']['groups'])
    for g in groups:
        for r in g['rows']:
            if g['mode'] == 'Transition' and addition(g['scope'], r['source'], r['destination']):
                require(not r['target'], 'Overlapping old/new candidate')
                r['target'] = True
    groups += extra_groups(shape, bits, PAIR, 'hardware/src/vlsu/store_load_lookahead_pair.sv')
    groups += extra_groups(shape, bits, PORT0, 'hardware/deps/cva6/core/cache_subsystem/wt_dcache_ctrl.sv')
    old = {tuple(r) for r in c['native_fsm']}
    targets = sum(r['target'] for g in groups for r in g['rows'])
    require(targets == 124, 'Exact124 required; enum names or candidate count differ')
    buildbook = base.capture.BUILD / 'build-source-pins.json'
    book = life.read_bound(buildbook, pins[str(buildbook)])
    for g in groups:
        p = life.ROOT / g['source']
        require(str(p) in book, 'Unbound source')
        # The approved dispatcher source lives at its sealed historical alias.
        if g['scope'] != base.capture.DISPATCH:
            pins = life.merge_pins(pins, {str(p): book[str(p)]})
        for r in g['rows']:
            if r['target']:
                v = bits['metrics']['fsm'][g['scope']]
                require(not (int(v['bits'], 16) & (1 << (v['width'] - 1 - r['raw_index']))), 'Target already hit')
    total = sum(len(g['rows']) for g in groups)
    plan = dict(groups=groups, targets=124, protected=total-124, no_other_waivers=True,
                strategy='direct-transition-only-66', point_query_authority='saved-native-identity')
    expected = native.expected_records(plan, native.Design(design))
    require(old <= set(expected) and len(set(expected)-old) == 52, 'Prior72 changed')
    new = set(expected)-old
    require(all(r[-3] == 'Transition' for r in expected), 'State directive forbidden')
    require(all('NO_REDUCTION' not in r[-2] for r in new if '.i_vmfpu' in r[2] or '.i_valu' in r[2]),
            'New reset-to-NO arc forbidden')
    require(all('simd_div' not in r[2] for r in new), 'SIMD candidates forbidden')
    for name in ('capture_fsm124.py', 'test_capture_fsm124.py'):
        p = base.HERE / name
        pins[str(p)] = life.digest(p)
    life.check(pins)
    out.mkdir()
    (out / 'inputs.txt').write_text('\n'.join(c['input_ledger']) + '\n')
    el = ''.join('CHECKSUM: "%s %s"\nINSTANCE: %s\nFsm %s "%s"\nANNOTATION: "%s"\n%s %s "%s"\n' % r for r in expected)
    require(base.combined_records(el) == (expected, {}), 'Native serialization differs')
    (out / 'combined.el').write_text(el)
    with (out / 'selection.tcl').open('x') as stream:
        stream.write('set fx_groups {}\n')
        for g in groups:
            source = life.ROOT / g['source'] if g['scope'] != base.capture.DISPATCH else life.ROOT.parent/'ara_dsa'/g['source']
            values = [g['scope'], str(source), g['machine']['name'], g['mode']]
            atom = base.capture.tcl_atom
            stream.write('lappend fx_groups [list ' + ' '.join(atom(v) for v in values) +
                         ' [list ' + ' '.join(atom(r['name']) for r in g['rows']) + '] [list ' +
                         ' '.join(atom(r['name']) for r in g['rows'] if r['target']) + ']]\n')
    approval = dict(status='SOURCE_REVIEWED_NATIVE_QUALIFICATION_PENDING', population=742,
                    composition=dict(prior=72, vmfpu=26, valu=8, pair=12, port0=6),
                    excluded_from_candidates=['VMFPU15 reset-to-NO', 'VALU12 reset-to-NO',
                                              'port0 REPLAY_REQ->IDLE reset', 'SIMD20 reset'],
                    native_records=[list(r) for r in expected], plan=plan)
    life.save(out/'approval.json', approval)
    for name in ('inputs.txt', 'combined.el', 'selection.tcl', 'approval.json'):
        pins[str(out/name)] = life.digest(out/name)
    c.update(schema='EXACT124_NATIVE_QUALIFICATION_FORMAL742', output=str(out), pins=pins,
             native_fsm=[list(r) for r in expected], observers={}, plan=plan)
    life.save(out/'config.json', c)
    print(json.dumps(dict(status='PREPARED_NO_DVE', output=str(out), seal=life.digest(out/'config.json'), targets=124)), flush=True)


def verify(out, seal):
    c = life.read_bound(out/'config.json', seal)
    life.check(c['pins'])
    require((out/'selected_tests.txt').read_text().splitlines() == c['expected_selected'] and
            (out/'inputs.txt').read_text().splitlines() == c['input_ledger'], 'Population differs')
    expected = ([tuple(r) for r in c['native_fsm']], {})
    for name in ('applied.el', 'reloaded.el'):
        require(base.combined_records((out/name).read_text()) == expected, 'Native identity differs')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        require((out/name).read_bytes() == b'', 'Reset not empty')
    native.audit_points(list(csv.reader((out/'exact-audit.tsv').open(), delimiter='\t')), c['plan'])
    reports = {}
    for stage in ('raw', 'applied', 'reset', 'reloaded', 'final'):
        rows = list(csv.DictReader((out/('rooted_'+stage+'.csv')).open()))
        require(len(rows)==1 and rows[0]['Scope']==rows[0]['Token']==base.observer.SYSTEM and
                rows[0]['Name']==rows[0]['GUIPath']=='i_system' and rows[0]['Stage']==stage, 'Root identity differs')
        reports[stage] = {m: rows[0][m] for m in native.METRICS}
    require(reports['raw']==reports['reset']==reports['final'] and reports['applied']==reports['reloaded'], 'Statistics differ')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('EXACT742_FSM_OBSERVERS_DONE')==1 and gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE')==1 and
            not re.search(r'EXPORT_FAILED|EXACT742_FAILED|Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136',gui), 'GUI failure')
    require(gui.splitlines().count('DVE_SELECTED_TESTS: '+' '.join(c['expected_selected']))==1, 'GUI population differs')
    life.check(c['pins'])
    life.save(out/'qualification.json',dict(status='EXACT124_NATIVE_SAVE_RELOAD_RESET_QUALIFIED',
              config_seal=seal, population=742, targets=124, observers_included=False, system=reports,
              input_pins=c['pins'], output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}))


def run(out, seal):
    # Private function namespace preserves the sealed launcher and hook unchanged.
    namespace=dict(base.run.__globals__, verify=verify)
    types.FunctionType(base.run.__code__, namespace)(out, seal)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','run','verify'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal')
    a=p.parse_args()
    if a.mode!='prepare': require(a.seal,'Seal required')
    if a.mode=='prepare': prepare(a.output.absolute())
    else: (run if a.mode=='run' else verify)(a.output.absolute(),a.seal)
