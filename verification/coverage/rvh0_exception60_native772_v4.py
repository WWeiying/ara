"""Prepare-only successor for the exact observed RVH0 native EL grammar."""
import argparse
import inspect as introspection
import json
from pathlib import Path
import re
from types import FunctionType

import rvh0_exception60_native772_v3 as inherited

predecessor = inherited.predecessor
life, need = inherited.life, inherited.need
HERE = Path(__file__).resolve().parent
FIXTURE = life.OUT / 'rvh0-exception60-native772-v3-agent-prepared-20261007-01'
V3_SHA = 'dc3103db0407eb8cb7de879bd724eba9249291f9821b0d3ca2f9a1ad33f498f8'
FIXTURE_SEAL = 'de6fdcb02be2cfd736a95d4a0c29c1d36c572684f5d56b5378b69de1060a830a'


def proof():
    need(life.digest(inherited.__file__) == V3_SHA, 'Frozen v3 alias producer identity')
    return inherited.proof()


def records(text, config):
    expected = {i['scope']: i for i in config['instances']}
    wanted = {(i['scope'], b['name']): b for i in config['instances']
              for b in i['bindings'] if b['role'] == 'target'}
    found = set()
    scopes = set()
    checksum = None
    scope = None
    annotation = False
    pair = None
    scalars = vectors = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if match:
            need(checksum is None and not annotation and pair is None, 'Orphan checksum/annotation/pair')
            checksum = match.groups()
            scope = None
            continue
        match = re.fullmatch(r'INSTANCE:\s*(\S+)', line)
        if match:
            scope = match[1]
            need(checksum is not None and scope in expected and scope not in scopes,
                 'Foreign/duplicate/whole scope')
            i = expected[scope]
            need(checksum == (i['design_checksum'], i['toggle_checksum']), 'Exact scope checksum')
            checksum = None
            scopes.add(scope)
            continue
        match = re.fullmatch(r'ANNOTATION: "([^"\r\n]*)"', line)
        if match:
            need(scope is not None and checksum is None and not annotation and pair is None
                 and match[1] == inherited.ANNOTATION, 'Foreign/duplicate/orphan annotation')
            annotation = True
            continue
        match = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) "logic ([^"\r\n]+)"', line)
        need(match is not None and scope is not None and checksum is None,
             'Only exact whole typed Toggle; no other metrics or partial ranges')
        direction, name, declaration = match.groups()
        key = (scope, name)
        b = wanted.get(key)
        need(b is not None and key not in found, 'Protected/foreign/duplicate target')
        need(declaration in b['allowed_labels'], 'Exact source-bound type/name/bounds')
        if direction is None:
            need(b['kind'] == 'vectornode' and b['width'] > 1 and annotation and pair is None,
                 'Whole vector requires exact preceding annotation')
            annotation = False
            found.add(key)
            vectors += 1
        else:
            need(b['kind'] == 'node' and b['width'] == 1 and not annotation,
                 'Only unannotated source-bound scalar directions')
            if pair is None:
                need(direction == '0to1', 'Scalar pair must start 0to1')
                pair = (key, declaration)
            else:
                need(direction == '1to0' and pair == (key, declaration),
                     'Exact adjacent scalar 0to1+1to0 pair')
                pair = None
                found.add(key)
                scalars += 1
    need(checksum is None and not annotation and pair is None, 'Orphan checksum/annotation/scalar direction')
    need(scopes == set(expected) and found == set(wanted) and len(found) == 60
         and scalars == 19 and vectors == 41, 'Exact60 / 38 scalar directions / 41 whole vectors')
    return sorted(found)


def candidate(config):
    lines = []
    for i in config['instances']:
        lines += ['CHECKSUM: "%s %s"' % (i['design_checksum'], i['toggle_checksum']),
                  'INSTANCE: ' + i['scope']]
        for b in i['bindings']:
            if b['role'] != 'target':
                continue
            if b['kind'] == 'node':
                lines += ['Toggle %s %s "logic %s"' % (direction, b['name'], b['label'])
                          for direction in ('0to1', '1to0')]
            else:
                lines += ['ANNOTATION: "' + inherited.ANNOTATION + '"',
                          'Toggle %s "logic %s"' % (b['name'], b['label'])]
    return '\n'.join(lines) + '\n'


def grammar_evidence_pins():
    c = life.read_bound(FIXTURE / 'config.json', FIXTURE_SEAL)
    need(c['instances'] == proof()[1], 'Actual before bindings unchanged')
    actual = json.loads((FIXTURE / 'actual-binding.json').read_bytes())
    need(actual['config_seal'] == FIXTURE_SEAL, 'Actual before binding config identity')
    for index in range(5):
        path = FIXTURE / ('native_before_%d.tsv' % index)
        need(actual['before_pins'][str(path)] == life.digest(path), 'Actual before inventory pin')
        need(inherited.inventory(FIXTURE, c, 'before', index) == actual['scopes'][index],
             'All 2854 actual native-before bindings unchanged')
    need(records((FIXTURE / 'first.el').read_text(), c) == records(candidate(c), c),
         'Complete real EL exact source target union')
    names = ['config.json', 'actual-binding.json', 'actual-selection.tcl', 'first.el',
             'error.txt', 'terminal.json', 'qualification-reject.json',
             'initial-empty.el', 'cleanup-empty.el', 'DVEfiles/dve_gui.log']
    names += ['native_before_%d.tsv' % index for index in range(5)]
    return {str(FIXTURE / name): life.digest(FIXTURE / name) for name in names}


# Rebind frozen functions privately; no mutation of either predecessor module.
_namespace = dict(inherited._namespace, __file__=__file__, proof=proof, records=records,
                  candidate=candidate, grammar_evidence_pins=grammar_evidence_pins,
                  ENTRY=HERE / 'rvh0_exception60_native772_v4.tcl')
for _name, _function in inherited._namespace.items():
    if isinstance(_function, FunctionType) and _name not in ('proof', 'records', 'candidate', 'prepare'):
        _namespace[_name] = FunctionType(_function.__code__, _namespace, _name,
                                         _function.__defaults__, _function.__closure__)
_prepare_source = introspection.getsource(predecessor.prepare)
_anchor = 'test_rvh0_exception60_native772_v2.py'
_gate = 'contract(c); records(candidate(c),c); life.check(pins); out.mkdir()'
need(_prepare_source.count(_anchor) == _prepare_source.count(_gate) == 1, 'Exact private prepare anchors')
_prepare_source = _prepare_source.replace(_anchor, 'test_rvh0_exception60_native772_v4.py')
_prepare_source = _prepare_source.replace(_gate, 'pins.update(grammar_evidence_pins())\n    ' + _gate)
exec(compile(_prepare_source, __file__ + ':private-prepare', 'exec'), _namespace)
for _name, _value in _namespace.items():
    if not _name.startswith('_') and _name not in ('proof', 'records', 'candidate'):
        globals()[_name] = _value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify-config', 'bind', 'inventory', 'el', 'selection', 'inspect'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--stage', choices=STAGES)
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    out = args.output.absolute()
    if args.mode == 'prepare':
        prepare(out)
    else:
        need(args.seal, 'Exact successor config seal')
        config = life.read_bound(out / 'config.json', args.seal)
        if args.mode == 'verify-config':
            verify_config(out, args.seal)
            print('RVH0_EXCEPTION60_V4_PREPARED_VERIFY_PASS_NOT_LAUNCHED')
        elif args.mode == 'inspect':
            inspect(out, args.seal)
        elif args.mode == 'bind':
            bind(out, config)
            print('ACTUAL_FULL2854_BINDING60_TARGETS2794_PROTECTED')
        elif args.mode == 'inventory':
            inventory(out, config, args.stage, args.index)
            print('EXACT_SCOPE_INVENTORY_PASS')
        elif args.mode == 'el':
            check_el(out, config, args.stage)
            print('EXACT_ALL_SCOPE_EL_PASS')
        else:
            binding = json.loads((out / 'actual-binding.json').read_bytes())
            need(binding['config_seal'] == args.seal and binding['actual_selection_sha256'] ==
                 life.digest(out / 'actual-selection.tcl'), 'Actual binding selection pin')
            print('ACTUAL_SELECTION_PIN_PASS')
