"""Disjoint formal762 successor: append only four qualified Dispatcher arcs."""
import argparse
import copy
import inspect
import json
from pathlib import Path
from types import FunctionType

import report_native_population_union_v2 as previous
import capture_dispatcher_four762 as dispatcher

life, require = previous.life, previous.require
HERE = Path(__file__).resolve().parent
CAPTURE = life.OUT / 'dispatcher-four-native762-agent-20261007-01'
CAPTURE_SHA = 'a069195b8977e94f63d775083ef605b5424322185663f7f6963bd43ff8507c85'
REPLAY = life.OUT / 'native-population-union-full761-readonly-replay-agent-20261007-01.json'
REPLAY_SHA = '1ecb319763f0f5db643819934cd96d24f30233c75b0e425ea11af948e7479b23'
BASE = dispatcher.BASE
BASE_SHA = '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5'
FMA = life.OUT / 'fma_expanded_native_612-agent-20261007-04'
FMA_SHA = 'b07201c920d2a952f08d263758cd54c4d5093e5eeac81a419d4512f2e8f7b492'


def qualify():
    replay = life.read_bound(REPLAY, REPLAY_SHA)
    require(replay['status'] == 'STRICT_SUBSTANTIVE_REPLAY_PASS_EXACT_STDOUT_APPEND_ONLY' and
            replay['full_original_substantive_verifier_completed'] and replay['population'] == 761,
            'Qualified761 substantive replay required')
    life.check(replay['current_evidence_pins'])
    q = life.read_bound(CAPTURE / 'capture-result.json', CAPTURE_SHA)
    require(q['status'] == 'EXACT_DISPATCHER4_NATIVE_ROUNDTRIP_NOT_APPLICATION_APPROVAL' and
            q['targets'] == 4 and q['protected'] == 88 and q['baseline'] == 762 and
            q['five_stages'] and q['semantic_reload'] and q['finalreset'] and q['remaining13_protected'] and
            not q['population_application'], 'Four-transition native qualification differs')
    life.check(q['input_pins']); life.check(q['output_pins'])
    c = life.read_bound(CAPTURE / 'config.json', q['config_seal'])
    require(dispatcher.native.native_records((CAPTURE / 'first.el').read_text()) ==
            [tuple(r) for r in q['native_records']] ==
            dispatcher.native.native_records((CAPTURE / 'second.el').read_text()), 'Four native reload differs')
    return c, q, previous.predecessor.merge(q['input_pins'], q['output_pins'],
        replay['current_evidence_pins'], {str(CAPTURE / 'capture-result.json'): CAPTURE_SHA, str(REPLAY): REPLAY_SHA})


def merge_plan(plan, addition):
    result = copy.deepcopy(plan)
    touched = set()
    for new_group in addition['groups']:
        matching = [(index, g) for index, g in enumerate(result['groups'])
                    if (g['scope'], g['checksum'], g['machine'], g['mode']) ==
                       (new_group['scope'], new_group['checksum'], new_group['machine'], new_group['mode'])]
        require(len(matching) == 1, 'Dispatcher full group identity differs')
        index, group = matching[0]
        require([dict(r, target=False) for r in group['rows']] ==
                [dict(r, target=False) for r in new_group['rows']], 'Compiled92 row/signature complement differs')
        for row, candidate in zip(group['rows'], new_group['rows']):
            if candidate['target']:
                require(not row['target'] and group['mode'] == 'Transition' and
                        row['raw_index'] in dispatcher.TARGETS, 'Duplicate/nontransition target')
                row['target'] = True
                touched.add((index, row['raw_index']))
    require({pos for _, pos in touched} == dispatcher.TARGETS and len(touched) == 4, 'Not exact four additions')
    result['targets'] = plan['targets'] + 4
    result['protected'] = plan['protected'] - 4
    return result, sorted({index for index, _ in touched})


def append_four(config, combined, selection):
    require(config['population'] == 762, 'Only formal762 for this successor')
    c, q, pins = qualify()
    plan, indices = merge_plan(config['plan'], c['plan'])
    before = copy.deepcopy(config['expected_union'])
    config['plan'] = plan
    combined += (CAPTURE / 'first.el').read_text()
    expected = previous.predecessor.records(combined, config)
    oldfsm = before['retained']['prior']['original']['prior'][0]
    newfsm = expected['retained']['prior']['original']['prior'][0]
    oldset, newset = {tuple(r) for r in oldfsm}, {tuple(r) for r in newfsm}
    require(newset - oldset == {tuple(r) for r in q['native_records']} and oldset <= newset,
            'Not exact disjoint four-record canonical union')
    copy_expected = copy.deepcopy(expected)
    copy_expected['retained']['prior']['original']['prior'][0] = oldfsm
    require(copy_expected == before, 'Other approved policy records changed')
    config.update(expected_union=expected, dispatcher4_capture_seal=CAPTURE_SHA,
                  dispatcher4_input_pins=pins, dispatcher_remaining13_protected=True)
    atom = previous.predecessor.frozen.prior.old.base.capture.tcl_atom
    for index in indices:
        targets = [r['name'] for r in plan['groups'][index]['rows'] if r['target']]
        # Keep actual source/scope/machine/native labels from the existing group.
        selection += 'set union_group [lindex $fx_groups %d]\n' % index
        selection += 'set union_group [lreplace $union_group 5 5 [list %s]]\n' % ' '.join(map(atom, targets))
        selection += 'set fx_groups [lreplace $fx_groups %d %d $union_group]\n' % (index, index)
    return combined, selection


def snapshot_stdout(data, out):
    path, snapshot = out / 'service.log', out / 'service-before-qualification.log'
    require(str(path) in data['output_pins'], 'Foreground lifecycle stdout missing')
    current = path.read_bytes()
    if snapshot.exists():
        prefix = snapshot.read_bytes()
        qualification = out / 'qualification.json'
        require(qualification.exists(), 'Snapshot without sealed qualification')
        saved = json.loads(qualification.read_bytes())
        tail = (json.dumps(dict(status=saved['status'], seal=life.digest(qualification),
                               system=saved['system'])) + '\n').encode('ascii')
        require(current == prefix + tail, 'Not exact post-qualification lifecycle append')
    else:
        require(data['output_pins'][str(path)] == life.digest(path), 'Stdout changed during final save')
        with snapshot.open('xb') as stream:
            stream.write(current)
    del data['output_pins'][str(path)]
    data['output_pins'][str(snapshot)] = life.digest(snapshot)
    data.update(fsm_prior=128, qualified_fsm_union=159, dispatcher4_capture_seal=CAPTURE_SHA,
                lifecycle_stdout=dict(path=str(path), immutable_snapshot=str(snapshot),
                    immutable_prefix_sha256=life.digest(snapshot), postseal_record='EXACT_VERIFIER_JSON_ONLY'))


def namespace():
    ns = previous.namespace()
    ns.update(__file__=__file__, append_four=append_four)
    body = inspect.getsource(previous.predecessor.prepare)
    root = "root = dict(scope=i['scope'], name=i['scope'].split('.')[-1])"
    require(body.count(root) == 1, 'Root-name adapter anchor differs')
    body = body.replace(root, "root = dict(scope=i['scope'], name=root_name(i['scope']))")
    anchor = '    dependencies = ['
    require(body.count(anchor) == 1, 'Four-union adapter anchor differs')
    body = body.replace(anchor, '    combined, selection = append_four(config, combined, selection)\n' + anchor)
    anchor = '    pins = merge(pins, c[\'pins\']'
    require(body.count(anchor) == 1, 'Exact pin adapter anchor differs')
    body = body.replace(anchor, "    dependencies.extend([HERE / 'report_native_population_union.py',\n"
        "        HERE / 'report_native_population_union_v2.py', HERE / 'test_report_dispatcher_four_union762.py'])\n"
        "    pins = merge(pins, config['dispatcher4_input_pins'])\n" + anchor)
    exec(compile(body, __file__, 'exec'), ns)
    for name in ('check', 'verify', 'run'):
        ns[name] = FunctionType(getattr(previous.predecessor, name).__code__, ns)
    body = inspect.getsource(previous.predecessor.verify)
    anchor = '        if path.exists():'
    require(body.count(anchor) == 1, 'Exact immutable-save snapshot anchor differs')
    body = body.replace(anchor, '        snapshot_stdout(data, out)\n' + anchor)
    ns['snapshot_stdout'] = snapshot_stdout
    exec(compile(body, __file__, 'exec'), ns)
    return ns


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'verify', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--runtime-ready', action='store_true')
    a = p.parse_args(); out = a.output.resolve(); ns = namespace()
    if a.mode == 'prepare':
        ns['prepare'](out, BASE / 'admission-manifest.json', BASE_SHA, FMA, FMA_SHA, a.runtime_ready)
    else:
        require(a.seal, 'Exact successor config seal required')
        ns[a.mode](out, a.seal)
