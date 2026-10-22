"""Offline diagnosis and minimal protected-singleton binder; no EDA launch API."""
import argparse
from collections import Counter
import copy
import csv
import json
from pathlib import Path

import rvh0_exception60_native772_v2 as frozen

FAILED = frozen.life.OUT / 'rvh0-exception60-native772-v2-parent-prepared-20261007-01'
CONFIG_SHA = '9fbcd99d5519a4a89178615fdaf9915de4e34f825ceb11393bccb44d9857fae7'
HELPER_SHA = 'edda229e8ecbf04b9f71523bdc65766aa7f088fe35219ca7ca572602cba481c6'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
NAME = 'instr.rvftype.repl'


def adjusted(config):
    """Only a source-bound protected [14:14] may use this observed bare name."""
    c = copy.deepcopy(config)
    instances = [i for i in c['instances'] if i['scope'] == SCOPE]
    frozen.need(len(instances) == 1, 'Exact singleton scope')
    nodes = [b for b in instances[0]['bindings'] if b['name'] == NAME]
    frozen.need(len(nodes) == 1, 'Exact singleton object')
    b = nodes[0]
    a = b['attributes']
    frozen.need(b['kind'] == 'vectornode' and b['role'] == 'protected' and b['width'] == 1
                and b['label'] == NAME + '[14:14]'
                and a == dict(name=NAME, file='402', line_num='180', type='1',
                              portnode='0', excluded='0', left='14', right='14',
                              aux_file='547', aux_line_num='516')
                and b['allowed_labels'] == [NAME + '[14:14]'],
                'Protected source-bound singleton only; no target/type/range relaxation')
    b['allowed_labels'] = sorted([NAME, NAME + '[14:14]'])
    for i in c['instances']:
        aliases = [label for n in i['bindings'] for label in n['allowed_labels']]
        frozen.need(len(aliases) == len(set(aliases)), 'Exact alias collision rejection')
    return c


def inventory(out, config, stage, index):
    # All schema, flags, completeness, duplicate and stage-drift checks stay frozen.
    return frozen.inventory(out, adjusted(config), stage, index)


def collect():
    c = frozen.life.read_bound(FAILED / 'config.json', CONFIG_SHA)
    frozen.need(frozen.life.digest(frozen.__file__) == HELPER_SHA, 'Frozen predecessor helper')
    frozen.contract(c)
    frozen.life.check(c['pins'])
    after = inventory(FAILED, c, 'before', 0)
    before_path = FAILED / 'native_before_0.tsv'
    with before_path.open(newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    i = c['instances'][0]
    aliases = {label: b for b in i['bindings'] for label in b['allowed_labels']}
    counts = Counter(aliases[r['name']]['name'] for r in rows if r['name'] in aliases)
    unknown = [r for r in rows if r['name'] not in aliases]
    terminal = json.loads((FAILED / 'terminal.json').read_bytes())
    sourceinfo = next(Path(p) for p in c['pins'] if p.endswith('verilog.sourceinfo.xml'))
    source = next(Path(n.get('name')) for n in frozen.xmltools.xml(sourceinfo).iter('fileinfo')
                  if n.get('id') == '402')
    frozen.need(str(source) in c['pins'], 'Actual declaration file pinned')
    frozen.need(source.read_text().splitlines()[179].strip() == 'logic [14:14] repl;',
                'Actual source declaration exact singleton')
    captures = sorted(p.name for p in FAILED.glob('native_*.tsv'))
    frozen.need(captures == ['native_before_0.tsv'], 'Unexpected additional captures: review anew')
    evidence = [FAILED / 'config.json', before_path, FAILED / 'error.txt',
                FAILED / 'terminal.json', FAILED / 'qualification-reject.json',
                FAILED / 'initial-empty.el', FAILED / 'cleanup-empty.el',
                FAILED / 'DVEfiles/dve_gui.log', sourceinfo, source,
                Path(frozen.__file__), Path(__file__).resolve(),
                Path(__file__).with_name('test_rvh0_exception60_alias_successor.py')]
    return dict(status='OFFLINE_FIRST_SCOPE_ALIAS_RESOLVED_NOT_NATIVE_QUALIFIED',
                failed_output=str(FAILED), config_seal=CONFIG_SHA,
                actual_dve_terminal=terminal, wrapper_status='FAILED_QUALIFICATION',
                unknown=unknown, duplicate_canonical_names={k: v for k, v in counts.items() if v > 1},
                missing_original_names=[b['name'] for b in i['bindings'] if b['name'] not in counts],
                actual_first_scope_rows=len(rows), resolved_first_scope_objects=len(after['bindings']),
                protected_arrays=[b for b in after['bindings'] if b['kind'] == 'arrays'],
                arrays_flattened=False, source_declaration=dict(path=str(source), line=180,
                    text='logic [14:14] repl;', compiled_file='402', compiled_aux_file='547',
                    compiled_aux_line=516),
                correction=dict(scope=SCOPE, name=NAME, original=NAME+'[14:14]', observed=NAME,
                                role='protected', excluded='0'),
                captures=captures, complete_five_stages=False, coverage_admitted=False,
                scopes_not_captured=[s['scope'] for s in c['instances'][1:]],
                total_compiled_objects=2854, targets=60, protected=2794,
                successor='Inventory adapter only; fresh config/entry/runner closure and parent authorization required before any capture. No later-stage evidence fabricated.',
                pins={str(p): frozen.life.digest(p) for p in evidence})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    result = collect()
    if args.verify:
        frozen.need(json.loads(args.verify.read_bytes()) == result, 'Exact offline replay')
        print('RVH0_ALIAS_OFFLINE_REPLAY_PASS_NOT_NATIVE_QUALIFIED')
    else:
        frozen.need(args.output and args.output.absolute().parent == frozen.life.OUT
                    and not args.output.exists(), 'Fresh independent review JSON only')
        frozen.life.save(args.output, result)
        print(json.dumps(dict(output=str(args.output), seal=frozen.life.digest(args.output),
                              status=result['status'])))
