"""Indexed typed binding, equivalent to the sealed offline binder; no EDA."""
import argparse
import inspect
import json
from pathlib import Path

import verify_mfpu272_native_binding_offline as previous

life, require = previous.life, previous.require


class Resolver:
    def __init__(self, instance):
        objects = instance['typed_objects']
        self.names = {n['name']: n for n in objects}
        require(len(self.names) == len(objects), 'Duplicate compiled names')
        self.exact = {}
        self.cache = {}
        for n in objects:
            dims = previous.frozen.dimensions(n)
            label = n['name'] + ''.join('[%d:%d]' % pair for pair in dims)
            self.exact.setdefault(previous.frozen.normalize_name(label), []).append(n)

    def matches(self, label, row_type):
        key = (label, row_type)
        if key not in self.cache:
            candidates = {n['name']: n for n in
                          self.exact.get(previous.frozen.normalize_name(label), [])}
            # Generated instance indices are part of the name. Try every
            # bracket boundary, not a lossy split at the first index.
            for name in [label, *(label[:i] for i, char in enumerate(label) if char == '[')]:
                if name in self.names:
                    candidates[name] = self.names[name]
            values = [(n, previous.match_label(n, label, row_type))
                      for n in candidates.values()]
            self.cache[key] = [(n, match) for n, match in values if match is not None]
        return self.cache[key]


def bind_with_aliases(instance, text):
    resolver = Resolver(instance)
    require(life.digest(previous.frozen.__file__) == previous.FROZEN_SHA, 'Frozen binder source drift')
    body = inspect.getsource(previous.frozen.bind_inventory)
    role = "row['type'] and (n['portnode'] in ('2','3'))==(row['type']=='port')"
    require(body.count(role) == 1, 'Exact sealed role anchor differs')
    body = body.replace(role, 'native_role(n,row)')
    anchor = "matches=[(n,match_label(n,label,row['type'])) for n in objects]"
    require(body.count(anchor) == 1, 'Exact sealed lookup anchor differs')
    environment = dict(vars(previous.frozen), match_label=previous.match_label,
                       native_role=previous.native_role, resolver=resolver)
    exec(compile(body.replace(anchor, "matches=resolver.matches(label,row['type'])"),
                 __file__, 'exec'), environment)
    bound = environment['bind_inventory'](instance, text)
    changes = []
    target_names = {t['name'] for t in instance['targets']}
    for label, row in bound['native_rows'].items():
        matches = resolver.matches(label, row['type'])
        require(len(matches) == 1, 'Alias proof identity ambiguous: ' + label)
        n = matches[0][0]
        collapsed = previous.frozen.match_label(n, label, row['type']) is None
        mda = n['kind'] == 'arrays' and row['type'] == 'MDA'
        if collapsed or mda:
            require(n['name'] not in target_names, 'Aliases must never promote target scope')
            changes.append(dict(scope=instance['scope'], name=n['name'], native_label=label,
                native_row=row, compiled_attributes=n,
                reason='EXACT_INTERNAL_VECTOR0_0_BARE_SIGNAL' if collapsed else 'EXACT_ORDERED_ARRAY_MDA_DISPLAY',
                source_role_authority='Pinned compiled portnode; MDA display has no direction column',
                protected=True))
    return bound, changes


def replay(binding, binding_seal, closure_seal, output):
    require(output.parent == life.OUT and not output.exists(), 'Fresh evidence output only')
    q = life.read_bound(binding, binding_seal)
    closure = life.read_bound(binding.parent / 'closure.json', closure_seal)
    require(closure['status'] == 'MFPU272_READONLY_CAPTURE_TYPED_ALIAS_OFFLINE_CLOSURE_PASS' and
            closure['binding_sha256'] == binding_seal and closure['EDA_launched'] is False and
            closure['local_qualified'] is False, 'Completed readonly closure required')
    require(q['status'] == 'MFPU272_COMPLETE_FRESH_BEFORE_OFFLINE_TYPED_BOUND_NOT_EXCLUSION_QUALIFICATION'
            and q['original_run'] == str(previous.RUN) and q['config_seal'] == previous.SEAL,
            'Exact sealed binding origin required')
    life.check(q['pins']); life.check(q['offline_adapter_pins']); life.check(closure['original_pins'])
    c = json.loads((previous.RUN / 'config.json').read_bytes())
    require(len(c['instances']) == len(q['instances']) == 788, 'Complete 788 scopes required')
    aliases = []
    for index, (instance, expected) in enumerate(zip(c['instances'], q['instances'])):
        bound, changes = bind_with_aliases(instance,
            (previous.RUN / ('native_before_%d.tsv' % index)).read_text())
        require(bound == expected, 'Indexed binding differs: ' + instance['scope'])
        aliases.extend(changes)
    require(aliases == q['typed_aliases'] and len(aliases) == 1652, 'Exact alias proof differs')
    pins = life.merge_pins(q['offline_adapter_pins'], {
        str(binding): binding_seal, str(binding.parent / 'closure.json'): closure_seal,
        str(Path(__file__).resolve()): life.digest(__file__),
        str(Path(__file__).with_name('test_mfpu272_indexed_binding.py')):
            life.digest(Path(__file__).with_name('test_mfpu272_indexed_binding.py'))})
    life.check(pins)
    result = dict(status='INDEXED_BINDING_ALL788_EXACT_EQUIVALENCE_PASS', scopes=788,
        aliases=1652, targets=272, binding_seal=binding_seal, closure_seal=closure_seal,
        pins=pins, EDA_launched=False, local_qualified=False)
    life.save(output, result)
    print(json.dumps(dict(output=str(output), seal=life.digest(output), **{k: result[k]
        for k in ('status', 'scopes', 'aliases', 'targets', 'EDA_launched')})), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--binding-seal', required=True)
    parser.add_argument('--closure-seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    replay(args.binding.resolve(), args.binding_seal, args.closure_seal, args.output.resolve())
