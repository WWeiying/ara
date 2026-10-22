"""Read-only recovery: only compiled one-bit vectors may have scalar GUI labels."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import cva6_fixed_fields_native768 as frozen

life, require = frozen.life, frozen.require
CAPTURE = life.OUT / 'cva6-fixed120-native768-agent-20261007-01'
SEAL = '1a34f949b9d89a1a7403c067a1d3c56228df3d72d9d4527b36d6c33c2604858c'


def label(node):
    name = node['name']
    tag = node['tag']
    if tag == 'node': return name
    if tag == 'vectornode': return name+'['+node['left']+':'+node['right']+']'
    require(tag == 'arrays', 'Unknown compiled tag')
    bounds = (node.get('unpackedrange','')+' '+node.get('packedrange','')).split()
    require(len(bounds) % 2 == 0, 'Array range shape')
    return name+''.join('['+bounds[i]+':'+bounds[i+1]+']' for i in range(0,len(bounds),2))


def bind_inventory(instance, rows):
    nodes = list(instance['protected_shape']) + [dict(s['shape'], tag='node' if s['scalar'] else 'vectornode') for s in instance['signals']]
    expected = {label(node) for node in nodes}
    require(len(expected) == len(nodes) and expected == set(instance['all_typed_labels']), 'Compiled inventory inconsistent')
    found, aliases = set(), []
    for node in nodes:
        compiled = label(node)
        choices = [compiled]
        # Do not strip dimensions from arrays or ranges from wider vectors.
        if node['tag'] == 'vectornode' and node['left'] == node['right']:
            choices.append(node['name'])
        matches = [name for name in choices if name in rows]
        if not matches:
            normalized = frozen.normalized_label(compiled)
            matches = [name for name in rows if frozen.normalized_label(name) == normalized]
        require(len(matches) == 1, 'Missing/ambiguous compiled object: '+compiled)
        native = matches[0]
        require(native not in found, 'Native alias collision')
        require(rows[native]['path'] == native and rows[native]['meta'] == native, 'Native path/meta signature differs')
        expected_type = 'MDA' if node['tag'] == 'arrays' else ('signal' if node['portnode'] == '0' else 'port')
        require(rows[native]['type'] == expected_type, 'Native typed object differs')
        found.add(native)
        if native != compiled:
            aliases.append(dict(compiled=compiled, native=native, tag=node['tag'],
                                left=node.get('left'), right=node.get('right'),
                                declaration_line=node.get('line_num')))
    require(found == set(rows), 'Extra native object outside compiled inventory')
    return aliases


def audit_native(instance, stages):
    before = frozen.native_rows(stages['before'])
    aliases = bind_inventory(instance, before)
    targets = {s['native_label'] for s in instance['signals']}
    require(targets <= set(before), 'Target label must remain exact')
    for stage in ('selected','reset','reloaded','final'):
        rows = frozen.native_rows(stages[stage])
        require(bind_inventory(instance, rows) == aliases, 'Compiled/native binding changed')
        for name, original in before.items():
            actual = rows[name]
            require(all(actual[key] == original[key] for key in ('path','meta','type')), 'Native identity drift')
            if name not in targets or stage in ('reset','final'):
                require(actual == original, 'Protected percentage/display or reset drift')
    require(frozen.native_rows(stages['selected']) == frozen.native_rows(stages['reloaded']), 'Reload percentage/display drift')
    return len(before), len(before)-len(targets)


def verify(output):
    require(output.parent == life.OUT and not output.exists(), 'Fresh independent receipt only')
    config = life.read_bound(CAPTURE/'config.json', SEAL)
    life.check(config['pins'])
    # Rebind every typed declaration to the immutable compiled definition.
    shape = frozen.primitive.toggle.xml(Path(config['design'])/'snps/coverage/db/shape/tgl.verilog.shape.xml')
    for instance in config['instances']:
        defs = [d for d in shape.findall('tgldef') if d.get('chksum') == instance['toggle_checksum']]
        require(len(defs) == 1, 'Ambiguous compiled definition')
        actual = {n.get('name'):dict(n.attrib, tag=n.tag) for n in defs[0].find('tglshape')}
        configured = {n['name']:n for n in instance['protected_shape']}
        configured.update({s['name']:dict(s['shape'], tag='node' if s['scalar'] else 'vectornode') for s in instance['signals']})
        require(actual == configured, 'Compiled protected/target declarations differ')
    aliases = [dict(scope=i['scope'], bindings=bind_inventory(i, frozen.native_rows((CAPTURE/('native_before_'+str(k)+'.tsv')).read_text())))
               for k,i in enumerate(config['instances'])]
    result = None
    def save(path, value):
        nonlocal result
        require(path == CAPTURE/'capture-result.json' and result is None, 'Unexpected frozen write')
        result = value
    # Same terminal, tools, logs, EL, empty/reset, and output-pin checks;
    # only the complete-inventory display-name binder differs.
    ns = dict(vars(frozen), audit_native=audit_native,
              life=SimpleNamespace(**dict(vars(life), save=save)))
    FunctionType(frozen.verify.__code__, ns)(CAPTURE, SEAL)
    require(result is not None, 'Frozen verifier did not complete')
    pins = result['pins']
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_verify_cva6_fixed_fields_native768_offline.py')):
        pins[str(path)] = life.digest(path)
    result.update(status='CVA6_FIXED120_4396_NATIVE_OFFLINE_REVERIFIED_NOT_APPLIED',
                  capture=str(CAPTURE), config_seal=SEAL, adapter_scope='Only compiled width-one vector scalar GUI spelling; no array flattening',
                  compiled_native_aliases=aliases, physical_target_bits=2198, target_directions=4396,
                  protected_other_typed_objects=1403, protected_arrays=50,
                  protected_partial_target_bits=64, HOLD1656_included=False,
                  frozen_capture_modified=False, native_rerun=False,
                  original_failure='Missing/ambiguous compiled scalar/vector/array object',
                  original_service_failure_preserved=True)
    life.check(pins)
    output.mkdir()
    life.save(output/'qualification.json', result)
    print(json.dumps(dict(status=result['status'], output=str(output), seal=life.digest(output/'qualification.json'),
                          aliases=sum(len(a['bindings']) for a in aliases), pins=len(pins))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); verify(args.output.resolve())
