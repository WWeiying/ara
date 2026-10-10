"""Frozen-source SLDU transition review, not native exclusion approval."""
import argparse
import itertools
import json
from pathlib import Path

import capture_dispatcher_four762 as prior

life, require, native = prior.life, prior.require, prior.native
BASE = life.OUT / 'operand-mask-data-defined-policy-admitted763-agent-20261007-01'
BASE_SHA = '962d7292ff80e5fffe4fd8e8e8de00938c32dca3a92d21e179b8cf59f915200c'
SOURCE = life.OUT / 'old-image-source-evidence-20261006-01/sldu.sv'
SOURCE_SHA = 'e23f11037461a2648e1b783d01ecba32f2f1569ac3e0f2258248a95b0149d687'
BOOK = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu'
TARGETS = {
    20: ('SLIDE_NP2_COMMIT', 'SLIDE_RUN', '801'),
    32: ('SLIDE_RUN_VSLIDE1UP_FIRST_WORD', 'SLIDE_EMIT_VSLIDE1DOWN_SCALAR', '912'),
}


def common_next(state, op, scalar, enabled, input_done, output_done, finished, flush):
    """Overapproximate progress gates; preserve ordered state assignments."""
    result = state
    if enabled:
        if state != 'SLIDE_NP2_COMMIT':
            result = 'SLIDE_RUN'
        if input_done and state == 'SLIDE_NP2_COMMIT':
            result = 'SLIDE_NP2_SETUP'
        if output_done and state == 'SLIDE_NP2_COMMIT':
            result = 'SLIDE_NP2_WAIT'
        if finished:
            result = ('SLIDE_EMIT_VSLIDE1DOWN_SCALAR'
                      if op == 'VSLIDEDOWN' and scalar else 'SLIDE_IDLE')
    return 'SLIDE_IDLE' if flush else result


def rows(shape, bits):
    metric = bits['metrics']['fsm'][SCOPE]
    require(metric['width'] == 36 and metric['checksum'] == '3728352571',
            'Wrong compiled SLDU FSM')
    definitions = [d for d in shape.iter('fsmdef')
                   if d.get('chksum') == metric['checksum']
                   and any(i.get('name') == SCOPE for i in d.findall('fsminst'))]
    require(len(definitions) == 1, 'Ambiguous SLDU definition')
    groups, position, selected = [], 0, set()
    for machine in definitions[0].iter('fsmfsm'):
        ids = {s.get('id'): s.get('name') for s in machine.findall('state')}
        for mode, nodes in (('State', machine.findall('state')),
                            ('Transition', machine.findall('transition'))):
            entries = []
            for item in nodes:
                source = ids[item.get('fromid')] if mode == 'Transition' else None
                destination = ids[item.get('toid')] if source else item.get('name')
                target = position in TARGETS
                if target:
                    require(mode == 'Transition' and machine.get('name') == 'state_q'
                            and (source, destination, item.get('line')) == TARGETS[position]
                            and not (int(metric['bits'], 16) >> (35-position)) & 1,
                            'Wrong or observed target')
                    selected.add(position)
                entries.append(dict(name=source+'->'+destination if source else destination,
                                    source=source, destination=destination, raw_index=position,
                                    target=target, attributes=dict(item.attrib)))
                position += 1
            groups.append(dict(scope=SCOPE, checksum=metric['checksum'],
                               machine=dict(machine.attrib), mode=mode, rows=entries))
    require(position == 36 and selected == set(TARGETS), 'Incomplete 36-point identity')
    return groups


def collect(output):
    require(output.parent == life.OUT and not output.exists(), 'Fresh evidence required')
    admission = life.read_bound(BASE/'admission-manifest.json', BASE_SHA)
    bits_path, ledger_path = BASE/'combined-bits.json', BASE/'combined-inputs.txt'
    bits = life.read_bound(bits_path, admission['output_pins'][str(bits_path)])
    require(life.digest(ledger_path) == admission['output_pins'][str(ledger_path)], 'Ledger drift')
    ledger = ledger_path.read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 764 and ledger[1:] == bits['tests'],
            'Not exact admitted763')
    book = json.loads(BOOK.read_bytes())
    original = life.ROOT/'hardware/src/sldu/sldu.sv'
    require(book[str(original)] == SOURCE_SHA and life.digest(SOURCE) == SOURCE_SHA,
            'Frozen SLDU alias differs')
    source = SOURCE.read_text()
    anchors = [
        "`FF(vinsn_issue_q, vinsn_queue_d.vinsn[vinsn_queue_d.issue_pnt], '0)",
        'SLIDE_RUN, SLIDE_RUN_VSLIDE1UP_FIRST_WORD, SLIDE_NP2_COMMIT: begin',
        'if (state_q != SLIDE_NP2_COMMIT)\n            state_d = SLIDE_RUN;',
        'if (state_q == SLIDE_NP2_COMMIT) state_d = SLIDE_NP2_WAIT;',
        'if (vinsn_issue_q.op == VSLIDEDOWN && vinsn_issue_q.use_scalar_op) begin',
        'if (vinsn_issue_q.use_scalar_op)\n                state_d = SLIDE_RUN_VSLIDE1UP_FIRST_WORD;',
    ]
    require(all(a in source for a in anchors), 'Reviewed SLDU control anchor differs')
    design = native.Design(Path(ledger[0]))
    require(design.source(SCOPE)['resolved_path'] == str(original), 'Foreign source instance')
    shape = Path(ledger[0])/'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(life.digest(shape) == bits['design']['shape/fsm.verilog.shape.xml'], 'Shape drift')
    groups = rows(native.read_xml(shape), bits)
    checked = 0
    for controls in itertools.product((False, True), repeat=5):
        for op, scalar in itertools.product(('VSLIDEUP', 'VSLIDEDOWN', 'OTHER'), (False, True)):
            require(common_next('SLIDE_NP2_COMMIT', op, scalar, *controls) != 'SLIDE_RUN',
                    'NP2 guard counterexample')
            checked += 1
        require(common_next('SLIDE_RUN_VSLIDE1UP_FIRST_WORD', 'VSLIDEUP', True,
                            *controls) != 'SLIDE_EMIT_VSLIDE1DOWN_SCALAR',
                'First-word opcode counterexample')
        checked += 1
    require(common_next('SLIDE_RUN_VSLIDE1UP_FIRST_WORD', 'VSLIDEDOWN', True,
                        True, False, False, True, False) == 'SLIDE_EMIT_VSLIDE1DOWN_SCALAR',
            'Corrupt-opcode negative calibration failed')
    paths = [SOURCE, BOOK, BASE/'admission-manifest.json', bits_path, ledger_path,
             shape, Path(__file__).resolve(), Path(__file__).with_name('test_review_sldu_two_boundaries763.py')]
    pins = {str(p): life.digest(p) for p in paths}
    life.check(pins)
    result = dict(status='SLDU_TWO_BOUNDARIES_SOURCE_REVIEW_REQUIRES_NATIVE_QUALIFICATION',
                  population=763, groups=groups, pins=pins, targets=2, protected=34,
                  progress_combinations_checked=checked, native_qualified=False,
                  exclusions_applied=False,
                  proof=[
                      'Within the common run branch, every SLIDE_RUN assignment is guarded by '
                      'state_q != SLIDE_NP2_COMMIT. NP2 overrides select SETUP, WAIT, IDLE or '
                      'scalar emit; cancellation selects IDLE, never RUN.',
                      'FIRST_WORD is entered only in the VSLIDEUP scalar branch. The '
                      'registered issue descriptor remains owned until issue completion; '
                      'a completed operation leaves the first-word state in that same edge. '
                      'The scalar emit assignment instead requires VSLIDEDOWN.'],
                  limits='Known reset-established legal queue state only; no arbitrary descriptor '
                  'corruption or forced opcode. NP2_COMMIT->scalar emit and all flush/cancel '
                  'transitions remain protected, not claimed impossible.')
    life.save(output, result)
    print(json.dumps(dict(path=str(output), seal=life.digest(output), targets=2, protected=34)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args().output.absolute())
