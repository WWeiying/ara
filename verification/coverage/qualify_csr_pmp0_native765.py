"""One bounded local PMP0 internal-only native roundtrip; no population application."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
from types import FunctionType
import capture_cast168_native as runner
import review_csr_pmp0_toggle765 as source

life, tools, require = runner.life, runner.tools, runner.require
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT/'csr-pmp0-toggle-source-review765-agent-20261007-01.json'
REVIEW_SHA = '514b2d595b744803251388832c15ad948b44ed9d20d1a5b169f2a89c3368e7ac'
STAGES = runner.STAGES


def bounds(n):
    if n['kind'] == 'node': return ''
    if n['kind'] == 'vectornode': return '[%s:%s]' % (n['left'],n['right'])
    require(n['kind'] == 'arrays' and not n.get('unpackedrange','').strip(), 'Packed array only')
    dims = list(map(int,n['packedrange'].split()))
    require(len(dims) % 2 == 0 and dims, 'Full ordered array dimensions')
    return ''.join('[%d:%d]' % (a,b) for a,b in zip(dims[::2],dims[1::2]))


def aliases(n):
    full = n['name']+bounds(n)
    result = {full}
    # Previously observed DVE singleton renderings, explicitly compiled only.
    if n['kind'] == 'vectornode' and n['left'] == n['right'] == '0': result.add(n['name'])
    if n['kind'] == 'arrays': result.add(full.replace('[0:0]','[0]'))
    return result


def instance():
    a = life.read_bound(REVIEW,REVIEW_SHA)
    targets = [n for n in a['targets'] if n['portnode'] == '0']
    protected = a['protected']+[n for n in a['targets'] if n['portnode'] != '0']
    require(len(targets) == 770 and len(protected) == 1307, 'Exact internal/complement counts')
    require(sum(source.bits(source.native.base.ET.Element(n['kind'],n)) for n in targets) == 7936,
            'Exact internal capacity')
    require(all(n['name'].startswith(('pmpcfg_q[','pmpcfg_next[')) or
                n['name'] in ('pmpaddr_q','pmpaddr_next') for n in targets), 'Only q/next internals')
    all_nodes = targets+protected
    require(len({n['name'] for n in all_nodes}) == 2077, 'Complete unique compiled inventory')
    paths = [Path(p) for p in a['pins'] if p.endswith(('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml'))]
    byname = {p.name:p for p in paths}
    _, defs = source.native.definitions(*(source.native.xml(byname[n]) for n in
        ('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml')),[source.SCOPE])
    return dict(scope=source.SCOPE,toggle_checksum=a['checksum'],
        design_module_checksum=defs[source.SCOPE]['module']['chksum'],targets=targets,protected=protected)


def contract(c):
    require(c['instances'] == [instance()] and c['timeout_seconds'] == 900 and
            c['population_application'] is False and c['automatic_retry'] is False, 'Exact frozen qualification contract')


def inventory(out,c,stage,index):
    require(stage in STAGES and index == 0, 'Only exact CSR scope/stage')
    with (out/('native_%s_0.tsv' % stage)).open(newline='') as stream:
        rows = list(csv.reader(stream,delimiter='\t'))
    require(rows and rows[0] == ['handle','path','meta','name'] and
            all(len(r) == 4 and all(r) for r in rows[1:]), 'Strict native schema/encoding')
    rows = rows[1:]
    require(len({r[0] for r in rows}) == len(rows) and len({r[1] for r in rows}) == len(rows),
            'Duplicate native handles/paths')
    bound = []
    used = set()
    byname = defaultdict(list)
    for row in rows:byname[row[3]].append(row)
    for n in c['instances'][0]['targets']+c['instances'][0]['protected']:
        matches = [r for name in aliases(n) for r in byname[name]]
        require(len(matches) == 1 and matches[0][0] not in used, 'Missing/ambiguous full object: '+n['name'])
        r = matches[0];used.add(r[0])
        require(r[1] == r[3] and r[2] in (r[3],'logic '+n['name']+bounds(n),'logic '+bounds(n)+n['name']),
                'Exact path/metadata differs: '+n['name'])
        bound.append((n['name'],r[1],r[2],r[3]))
    return sorted(bound)


def parse_el(text,c):
    i = c['instances'][0];expected = {n['name']:n for n in i['targets']}
    found = defaultdict(list);scope = check = None;blocks = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'): continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"',line), 'Annotation syntax')
        elif line.startswith('CHECKSUM:'):
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            require(m is not None,'Checksum syntax');check=m.groups();scope=None
        elif line.startswith('INSTANCE:'):
            scope = line.split(':',1)[1].strip();blocks+=1
            require(blocks == 1 and scope == i['scope'] and check ==
                    (i['design_module_checksum'],i['toggle_checksum']), 'Only exact scope/checksums')
        else:
            m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?([^\s"]+) "logic ([^"\r\n]+)"',line)
            require(scope == i['scope'] and m is not None, 'Only typed Toggle objects')
            direction,name,declaration = m.groups()
            require(name in expected, 'Protected/extra object')
            n = expected[name];dims=bounds(n)
            require(declaration in (name+dims,dims+name), 'Exact full ordered type/name/dimensions')
            found[name].append(direction)
    require(blocks == 1 and set(found) == set(expected) and len(found) == 770, 'Exact complete770')
    for name,ds in found.items():
        require(ds == [None] or len(ds) == 2 and set(ds) == {'0to1','1to0'}, 'Incomplete/duplicate direction '+name)
    return sorted((name,bounds(expected[name])) for name in found)


def check_file(out,c,name):
    require(name in ('initial-empty.el','reset-empty.el','final-empty.el','first.el','second.el'), 'EL name')
    if name.endswith('empty.el'):
        require((out/name).read_bytes() == b'', 'All-scope empty EL required');return 0
    return len(parse_el((out/name).read_text(),c))


def inspect(out,seal):
    c = life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1,
            'Actual executable/terminal')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('PMP0_NATIVE_DONE') == 1 and 'PMP0_NATIVE_FAILED' not in gui and
            not (out/'error.txt').exists(), 'Five stages incomplete')
    before=inventory(out,c,'before',0)
    for stage in STAGES[1:]: require(inventory(out,c,stage,0) == before,'Complete native identity/protection drift')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','first.el','second.el'):check_file(out,c,name)
    require(parse_el((out/'first.el').read_text(),c) == parse_el((out/'second.el').read_text(),c),'Exact semantic reload')
    pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and
        p.name not in ('worker.log','capture-result.json')})
    result=dict(status='PMP0_INTERNAL770_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,objects=770,
        logical_bits=7936,protected_objects=1307,output_aliases_protected=7,d_protected=True,
        valid_reset_settled_only=True,initial_X_excluded=False,population_application=False,
        official_denominator_reduction=None,pins=pins)
    life.save(out/'capture-result.json',result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(out/'capture-result.json'))),flush=True)


def prepare(out):
    require(out.parent == life.OUT and not out.exists(),'Fresh independent output')
    a=life.read_bound(REVIEW,REVIEW_SHA);life.check(a['pins'])
    inherited_path=runner.inherited.PRODUCT/'config.json';inherited=json.loads(inherited_path.read_bytes())
    tools.revalidate(inherited['identity'])
    test=Path(inherited['test']);vdb=test.parent.with_suffix('.vdb')
    require(vdb.is_dir() and (vdb/'snps/coverage/db/testdata'/test.name).is_dir(),'Exact existing native test')
    pins=life.merge_pins(a['pins'],{str(REVIEW):REVIEW_SHA})
    dependencies=[inherited_path,Path(__file__).resolve(),HERE/'test_qualify_csr_pmp0_native765.py',
        HERE/'qualify_csr_pmp0_native765.tcl',HERE/'queue_fp_temporaries_native.tcl',
        HERE/'fma_datapath_native.tcl',Path(runner.__file__),Path(runner.inherited.__file__),
        Path(life.__file__),Path(tools.__file__),*vdb.rglob('*')]
    for p in dependencies:
        if p.is_file():pins=life.merge_pins(pins,{str(p.resolve()):life.digest(p)})
    c=dict(output=str(out),instances=[instance()],pins=pins,identity=inherited['identity'],timeout_seconds=900,
        automatic_retry=False,population_application=False,source_review=str(REVIEW),source_review_seal=REVIEW_SHA)
    contract(c);life.check(pins);out.mkdir()
    values=dict(fma_design=str(life.IMAGE)+'.vdb',fma_vdb=str(vdb),fma_test=str(test),
        fma_python=str(life.ROOT/'verification/tools/soc-venv/bin/python'),fma_helper=str(Path(__file__).resolve()),
        qfp_primitives=str(HERE/'fma_datapath_native.tcl'))
    require(all(not any(x in v for x in '{}\\\r\n') for v in values.values()),'Safe Tcl paths')
    i=c['instances'][0]
    lines=['set %s {%s}\n' % item for item in values.items()]+['set fma_instances {}\n']
    lines.append('lappend fma_instances [list {%s} {%s} {%s} 0]\n' %
        (i['scope'],' '.join(n['name']+bounds(n) for n in i['targets']),
         ' '.join(n['name']+bounds(n) for n in i['protected'])))
    with (out/'selection.tcl').open('x') as stream:stream.write(''.join(lines))
    pins[str(out/'selection.tcl')]=life.digest(out/'selection.tcl')
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


class Route:
    def __truediv__(self,name):
        require(name == 'capture_cast168_native.tcl','Only established lifecycle entry')
        return HERE/'qualify_csr_pmp0_native765.tcl'


def run(out,seal):
    FunctionType(runner.run.__code__,dict(vars(runner),contract=contract,inspect=inspect,HERE=Route()))(out,seal)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify','run','inspect','inventory','el'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--stage');p.add_argument('--index',type=int);p.add_argument('--file')
    a=p.parse_args();out=a.output.resolve()
    if a.mode == 'prepare':prepare(out)
    elif a.mode in ('el','inventory'):
        c=json.loads((out/'config.json').read_bytes())
        print(check_file(out,c,a.file) if a.mode == 'el' else len(inventory(out,c,a.stage,a.index)))
    else:
        require(a.seal,'Exact config seal')
        if a.mode == 'verify':
            c=life.read_bound(out/'config.json',a.seal);contract(c);life.check(c['pins']);print('VERIFY_PASS')
        else:(run if a.mode == 'run' else inspect)(out,a.seal)
