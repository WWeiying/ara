"""Fresh native successor: protected compiled singletons may display bare names.

Frozen v2 functions execute in a private namespace. Only proof-derived protected
inventory aliases change; target declarations and every native stage gate remain.
No automatic launch API.
"""
import argparse
import copy
import inspect as introspection
from pathlib import Path
from types import FunctionType

import rvh0_exception60_native772_v2 as predecessor

HERE = Path(__file__).resolve().parent
PREDECESSOR_SHA = 'edda229e8ecbf04b9f71523bdc65766aa7f088fe35219ca7ca572602cba481c6'


def singleton_aliases(instances):
    result = copy.deepcopy(instances)
    for instance in result:
        for b in instance['bindings']:
            a = b['attributes']
            if b['role'] != 'protected' or b['kind'] != 'vectornode':
                continue
            predecessor.need(a['name'] == b['name'] and a['type'] == '1'
                             and b['label'] == b['name'] + '[%s:%s]' % (a['left'], a['right']),
                             'Exact compiled protected type/name/range')
            if a['left'] == a['right']:
                predecessor.need(b['width'] == 1 and a['excluded'] == '0',
                                 'Only complete protected compiled singleton')
                b['allowed_labels'] = sorted(set(b['allowed_labels']) | {b['name']})
        aliases = [label for b in instance['bindings'] for label in b['allowed_labels']]
        predecessor.need(len(aliases) == len(set(aliases)), 'Compiled singleton alias collision')
    return result


def proof():
    predecessor.need(predecessor.life.digest(predecessor.__file__) == PREDECESSOR_SHA,
                     'Frozen v2 helper identity')
    review, instances = predecessor.proof()
    return review, singleton_aliases(instances)


# FunctionType rebinds globals without mutating the imported sealed module.
_namespace = dict(vars(predecessor), __file__=__file__, proof=proof,
                  ENTRY=HERE / 'rvh0_exception60_native772_v3.tcl')
for _name, _function in vars(predecessor).items():
    if isinstance(_function, FunctionType) and _function.__module__ == predecessor.__name__ and _name != 'proof':
        _namespace[_name] = FunctionType(_function.__code__, _namespace, _name,
                                         _function.__defaults__, _function.__closure__)

# The successor test must be frozen with its config; no other prepare logic changes.
_prepare_source = introspection.getsource(predecessor.prepare)
_anchor = "test_rvh0_exception60_native772_v2.py"
predecessor.need(_prepare_source.count(_anchor) == 1, 'Exact predecessor test-pin anchor')
exec(compile(_prepare_source.replace(_anchor, 'test_rvh0_exception60_native772_v3.py'),
             __file__ + ':private-prepare', 'exec'), _namespace)
for _name, _value in _namespace.items():
    if not _name.startswith('__') and _name != 'proof':
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
            print('RVH0_EXCEPTION60_V3_PREPARED_VERIFY_PASS_NOT_LAUNCHED')
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
