"""Actual68-row protection-schema successor; no retry or application implied."""
import argparse
from functools import lru_cache
import gzip
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import xml.etree.ElementTree as ET
import queue_fp_temporaries_native as old

life, require, tools = old.life, old.require, old.tools
HERE = Path(__file__).resolve().parent
ORIGIN = life.OUT/'queue-disabled-fp-temporaries-native-agent-20261007-01'
ORIGIN_SHA = 'b067bf7c2fcf98411c2d9c50caedff4ce7943110287fa860b2abfdc0081f1686'
ROWS_SHA = 'bb30d353dfc95375ce185beebdd0ea44403093e506b37004bc62f850dcdbcf13'
SCALARS = {'operand_queue_cmd_i.target_fu','cmd.target_fu','operand_ready_i','operand_target_fu_o'}
UNIONS = {'ntr.w8': [7,0,7,0], 'ntr.w16': [3,0,15,0],
          'ntr.w32': [1,0,31,0], 'ntr.w64': [0,0,63,0]}


def protection(node):
    name = node['name']
    if name in SCALARS:
        require(node['kind'] == 'vectornode' and node['left'] == node['right'] == '0',
                'Only explicit protected compiled [0:0] scalar aliases')
        return name
    if node['kind'] == 'arrays':
        require(name in UNIONS and not node.get('unpackedrange','').strip() and
                list(map(int,node['packedrange'].split())) == UNIONS[name], 'Exact protected union dimensions')
        dims = UNIONS[name]
        # Actual DVE renders the singleton first dimension only as [0].
        return name+''.join('[%d]' % a if a == b else '[%d:%d]' % (a,b)
                            for a,b in zip(dims[::2],dims[1::2]))
    return old.label(node)


@lru_cache(maxsize=1)
def compiled_arrays():
    review = life.read_bound(old.REVIEW,old.REVIEW_SHA)
    path = old.source.DESIGN/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    require(life.digest(path) == review['input_pins'][str(path)], 'Frozen compiled shape drift')
    root = ET.fromstring(gzip.decompress(path.read_bytes()))
    result = {}
    for checksum in ('4023802205','885747700'):
        matches = [n for n in root.findall('tgldef') if n.get('chksum') == checksum]
        require(len(matches) == 1, 'Unique FPU0 compiled definition')
        rows = [dict(n.attrib,kind=n.tag) for n in matches[0].iter('arrays')]
        require(len(rows) == 4 and {r['name'] for r in rows} == set(UNIONS), 'All four protected union arrays')
        for row in rows: protection(row)
        result[checksum] = rows
    return result


def instances(review):
    result = old.instances(review)
    arrays = compiled_arrays()
    for i in result:
        protected = i['protected_compiled']+arrays[i['toggle_checksum']]
        require({t['name'] for t in protected if t['name'] in SCALARS} == SCALARS, 'All four protected aliases retained')
        i['protected_compiled'] = protected
        i['protected'] = [protection(n) for n in protected]
        i['protection_bindings'] = [dict(compiled=n,native_name=protection(n)) for n in protected]
        require(len(i['protected']) == len(set(i['protected'])) == 47 and
                len(set(i['protected']+[t['native_name'] for t in i['targets']])) == 68,
                'Exact68 target/protection bijection')
    return result


def contract(c):
    require(c['instances'] == instances(life.read_bound(old.REVIEW,old.REVIEW_SHA)),
            'Full compiled/native protection mapping drift')
    require(c['population_application'] is False and c['timeout_seconds'] == 900, 'Local one-shot only')


def inventory(out,c,stage,index):
    require(stage in old.STAGES and 0 <= index < 16, 'Stage/scope selector')
    with (out/('native_%s_%d.tsv' % (stage,index))).open(newline='') as stream:
        table = list(old.csv.reader(stream,delimiter='\t'))
    require(table and table[0] == ['handle','path','meta','name'] and
            len(table) == 69 and all(len(r) == 4 and all(r) for r in table[1:]), 'Exactly68 full native rows')
    require(len({r[0] for r in table[1:]}) == 68, 'Unique real native handles')
    i = c['instances'][index]
    required = set(i['protected']+[t['native_name'] for t in i['targets']])
    rows = [tuple(r[1:]) for r in table[1:]]
    require(len(required) == len({r[2] for r in rows}) == len({r[0] for r in rows}) == 68 and
            {r[2] for r in rows} == required, 'Exact unique source/native full complement')
    # The actual01 API returns bare labels for both path and meta. This is
    # identity evidence only; declaration type comes separately from saved EL.
    require(all(path == meta == name for path,meta,name in rows), 'Observed bare native path/meta identity drift')
    return sorted(rows)


def check_file(out,c,name):
    if name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes() == b'', 'Global exclusion must be empty')
        return 0
    require(name in ('first.el','second.el'), 'EL filename')
    for index in range(16): inventory(out,c,'before',index)
    # Never feed bare GUI meta into the typed parser as a declaration.
    # The frozen parser proves exact logic type, full bounds, checksums and
    # complete direction pairs against every source/compiled target.
    return len(old.parse_el((out/name).read_text(),c))


def fixture():
    origin = life.read_bound(ORIGIN/'config.json',ORIGIN_SHA)
    life.check(origin['pins'])
    require(life.digest(ORIGIN/'native_before_0.tsv') == ROWS_SHA, 'Actual68-row fixture drift')
    c = dict(origin,instances=instances(life.read_bound(old.REVIEW,old.REVIEW_SHA)))
    rows = inventory(ORIGIN,c,'before',0)
    require((ORIGIN/'initial-empty.el').read_bytes() == (ORIGIN/'cleanup-empty.el').read_bytes() == b'',
            'Actual01 empty/cleanup drift')
    return c,rows


class Route:
    def __truediv__(self,name):
        return HERE/({'queue_fp_temporaries_native.tcl':'queue_fp_temporaries_native_alias.tcl',
                      'test_queue_fp_temporaries_native.py':'test_queue_fp_temporaries_native_alias.py'}.get(name,name))


def prepare(out):
    fixture()
    deps = [Path(old.__file__),HERE/'queue_fp_temporaries_native.tcl',
        HERE/'test_queue_fp_temporaries_native.py',Path(old.source.lexical.__file__),
        Path(old.source.evidence.__file__),Path(old.lifecycle.inherited.__file__),
        ORIGIN/'config.json',ORIGIN/'native_before_0.tsv',ORIGIN/'error.txt',
        ORIGIN/'DVEfiles/dve_gui.log',ORIGIN/'initial-empty.el',ORIGIN/'cleanup-empty.el',ORIGIN/'terminal.json']
    def save(path,data):
        if path == out/'config.json':
            data = dict(data,actual01_fixture=str(ORIGIN/'native_before_0.tsv'),
                        repair='EXACT_PROTECTED_SINGLETON_AND_FOUR_UNION_ARRAY_NATIVE_BINDINGS')
            data['pins'] = life.merge_pins(data['pins'],{str(p):life.digest(p) for p in deps})
            life.check(data['pins'])
        life.save(path,data)
    namespace = dict(vars(old),instances=instances,contract=contract,HERE=Route(),
        __file__=str(Path(__file__).resolve()),life=SimpleNamespace(**dict(vars(life),save=save)))
    FunctionType(old.prepare.__code__,namespace)(out)


def inspect(out,seal):
    def save(path,data):
        if path == out/'capture-result.json':
            data = dict(data,protected_local_objects=752,compiled_node_vector_protections=688,
                additional_union_array_protections=64,actual_bare_meta_not_type_evidence=True,
                exact_saved_EL_source_typed_binding=True,actual01_HOLD_preserved=True)
        life.save(path,data)
    namespace = dict(vars(old),contract=contract,inventory=inventory,check_file=check_file,
        life=SimpleNamespace(**dict(vars(life),save=save)))
    FunctionType(old.inspect.__code__,namespace)(out,seal)


class TclRoute:
    def __truediv__(self,name):
        require(name == 'capture_cast168_native.tcl', 'Only established lifecycle Tcl entry')
        return HERE/'queue_fp_temporaries_native_alias.tcl'


def run(out,seal):
    namespace = dict(vars(old.lifecycle),contract=contract,inspect=inspect,HERE=TclRoute())
    FunctionType(old.lifecycle.run.__code__,namespace)(out,seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('fixture','prepare','verify','run','inspect','inventory','el'))
    p.add_argument('--output',type=Path);p.add_argument('--seal');p.add_argument('--stage');p.add_argument('--index',type=int)
    p.add_argument('--file');a = p.parse_args()
    if a.mode == 'fixture': print('ACTUAL68_FIXTURE_PASS',len(fixture()[1]))
    else:
        require(a.output,'Output required');out = a.output.resolve()
        if a.mode == 'prepare': prepare(out)
        elif a.mode in ('inventory','el'):
            c = json.loads((out/'config.json').read_bytes())
            print(len(inventory(out,c,a.stage,a.index)) if a.mode == 'inventory' else check_file(out,c,a.file))
        else:
            require(a.seal,'Exact config seal')
            if a.mode == 'verify':
                c = life.read_bound(out/'config.json',a.seal);contract(c);life.check(c['pins']);print('VERIFY_PASS')
            else: (run if a.mode == 'run' else inspect)(out,a.seal)
