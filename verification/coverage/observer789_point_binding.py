"""Exact observed category/branch identities, not invented Line point rows."""
import csv
import functools
import gzip
import io
import re
import tkinter
import xml.etree.ElementTree as ET
from pathlib import Path
from report_population788_observers import *
import report_population788_observers as frozen

OBSERVATION = life.OUT/'cvxif-point789-readonly-v3-prepared-agent-20261008-01'
OBSERVATION_SHA = 'b8131b282e9346709bb16721ab07ab5b4985d42d57d86cd57025079a3740dd27'


def cells(value):
    try: return tuple(tkinter.Tcl().splitlist(value))
    except tkinter.TclError as error: raise ValueError('Invalid native Tcl cells') from error


@functools.lru_cache(maxsize=1)
def binding():
    receipt = life.read_bound(OBSERVATION/'observation.json', OBSERVATION_SHA)
    need(receipt['status'] == 'READONLY_NATIVE_LABELS_NOT_POINT_QUALIFICATION' and
         receipt['exclusion_attributes'] == 'UNOBSERVED' and
         receipt['point_binding_qualified'] is False, 'Observation scope differs')
    config = life.read_bound(OBSERVATION/'config.json', receipt['config_seal'])
    authority = life.read_bound(REPORT/'config.json', CONFIG_SHA)
    need(authority['input_ledger'][0] == config['design'], 'Observation/qualified design differs')
    result = dict(pins={str(OBSERVATION/'observation.json'): OBSERVATION_SHA,
                        str(OBSERVATION/'config.json'): receipt['config_seal'],
                        str(REPORT/'config.json'): CONFIG_SHA})
    design = Path(config['design'])/'snps/coverage/db/shape'
    definitions = {}
    for metric, tag, checksum in [('line','linedef','1382966637'), ('branch','branch_def','2887169998')]:
        path = design/(metric+'.verilog.shape.xml')
        sha = authority['pins'][str(path)]
        raw = path.read_bytes(); need(life.digest(path) == sha, 'Compiled shape drift')
        tree = ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
        matches = [node for node in tree.iter(tag) if node.get('id') == '-160' and node.get('chksum') == checksum]
        need(len(matches) == 1, 'Compiled metric binding ambiguous')
        definitions[metric] = matches[0]; result['pins'][str(path)] = sha
    line = definitions['line']
    bbs = [dict(node.attrib) for node in line.iter('linebb')]
    statements = [dict(node.attrib) for node in line.iter('linestmt')]
    need({row['id'] for row in bbs} == set(map(str, range(8))) and len(bbs) == 8 and
         {row['id'] for row in statements} == set(map(str, range(10))) and len(statements) == 10,
         'Exact aggregate Line schema')
    need(all(row['file_id'] == '610' for row in bbs+statements), 'Foreign source file')
    result['line_schema'] = dict(blocks=bbs, statements=statements,
                                nonignored_statements=sum(row['line_ignore'] == '0' for row in statements))
    groups = list(definitions['branch'].iter('branch_spec'))
    need([g.get('id') for g in groups] == ['0','1'] and
         all(len(g.findall('branch_vector')) == 2 for g in groups), 'Exact branch groups/vectors')
    result['branch_schema'] = {g.get('id'):dict(attributes=dict(g.attrib),
        expressions=[dict(e.attrib) for e in g.findall('branch_expr')],
        vectors=[dict(v.attrib) for v in g.findall('branch_vector')]) for g in groups}
    gold = {}
    for metric in ('Line','Branch'):
        path = OBSERVATION/('observed_'+metric+'_0.tsv')
        sha = receipt['output_pins'][str(path)]
        need(life.digest(path) == sha, 'Observed labels drift')
        rows = list(csv.DictReader(io.StringIO(path.read_bytes().decode()), delimiter='\t'))
        columns = OBSERVATION/('observed_'+metric+'_0.columns')
        column_sha = receipt['output_pins'][str(columns)]
        need(life.digest(columns) == column_sha, 'Observed column drift')
        expected = {('Block','Block','Block'), ('Statement','Statement','Statement')} if metric == 'Line' else {
            ('Item0','Item0','Item0'), ('Item0.Branch0.0','Branch0.0','Branch0.0'),
            ('Item0.MISSING_ELSE0.1','MISSING_ELSE0.1','MISSING_ELSE0.1'),
            ('Item1','Item1','Item1'), ('Item1.MISSING_ELSE1.0','MISSING_ELSE1.0','MISSING_ELSE1.0'),
            ('Item1.MISSING_ELSE1.1','MISSING_ELSE1.1','MISSING_ELSE1.1')}
        identities = {tuple(row[k] for k in ('path','meta','name')):cells(row['cells']) for row in rows}
        need(len(rows) == len(identities) and set(identities) == expected and
             all(row['excluded'] == 'UNOBSERVED' for row in rows), 'Actual observation identities differ')
        if metric == 'Branch':
            need([identities[key][2] for key in expected if key[0] == 'Item0'] == ['55'] and
                 identities[('Item1','Item1','Item1')][2] == '65', 'Branch group source lines')
            for key, value in identities.items():
                if '.' not in key[0]: continue
                match = re.fullmatch(r'Item([01])\.(?:Branch|MISSING_ELSE)([01])\.([01])', key[0])
                need(match is not None and match[1] == match[2], 'Native branch group identity')
                group = result['branch_schema'][match[1]]
                need(match[3] in {v['id'] for v in group['vectors']} and value[2] in
                     {e[k] for e in group['expressions'] for k in ('true_clause_line','false_clause_line')},
                     'Native branch leaf outside source/compiled group')
        gold[metric] = dict(identities=identities, columns=columns.read_bytes().decode())
        result['pins'].update({str(path):sha,str(columns):column_sha})
    result['gold'] = gold
    return result


def snapshot_gate(metric, text, columns):
    data = binding()['gold'][metric]
    rows = observer.rows(text)
    need(set(rows) == set(data['identities']) and columns == data['columns'], 'Native compiled category/point identities differ')
    for key, (_, value) in rows.items():
        actual, expected = cells(value), data['identities'][key]
        # Coverage is dynamic; names/source lines/condition columns are identities.
        need(len(actual) == len(expected) and actual[0] == expected[0] and
             actual[2:] == expected[2:], 'Native point metadata differs')


def observer_audit(out, c):
    for metric in ('Line','Branch'):
        for stage in observer.STAGES:
            snapshot_gate(metric, (out/('%s_%s_0.tsv' % (stage,metric))).read_text(),
                          (out/('%s_%s_0.columns' % (stage,metric))).read_text())
    frozen.observer_audit(out, c)


def native_gate(text, inherited, ob):
    records = frozen.native_gate(text, inherited, ob)
    source = binding()
    for scope, checks, directive in records:
        kind, _, tail = directive.partition(' ')
        if kind not in ('Block','Line','Branch'): continue
        need(scope == SCOPES[0], 'Code directive in compiled-zero scope')
        if not tail: continue  # Exact whole-category metric primitive, never scope wildcard.
        if kind == 'Branch':
            match = re.fullmatch(r'(\d+) "(\d+)" "([^"]*)" \((\d+)\) "([^"]*)"', tail)
            need(match is not None and match[1] in source['branch_schema'], 'Unknown/foreign native Branch point')
            group = source['branch_schema'][match[1]]
            need(match[2] == group['attributes']['chksum'] and match[4] in
                 {v['id'] for v in group['vectors']} and match[3] ==
                 ' ; '.join(e['exprstr'] for e in group['expressions']), 'Native Branch attributes differ')
            # Partial signatures have not been observed: keep fail-closed until exact grammar exists.
            raise ValueError('Partial native Branch signature requires measured source-bound serialization')
        raise ValueError('Partial native Line/Block syntax not yet observed')
    return records
