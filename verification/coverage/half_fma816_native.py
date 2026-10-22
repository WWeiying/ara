"""Exact16 FP16 arithmetic scopes; parent-qualified finite evidence, local EL only."""
import argparse
from collections import defaultdict
from functools import lru_cache
import gzip
import json
from pathlib import Path
import re
from types import FunctionType
import xml.etree.ElementTree as ET
import fma_expanded_native as common
import run_half_fma_finite as fixture

life, require, tools, source = common.life, common.require, common.tools, common.source
HERE = Path(__file__).resolve().parent
QUAL = life.OUT/'half-fma-source-tail-qualified-agent-20261007-01/qualification.json'
QUAL_SHA = 'c80479bddc7569c3e6d36afc958121a52e50476b8f2bfdb5c79bbfc78821c568'
REVIEW = life.OUT/'fpnew-next-numeric-scope-static-review-agent-20261007-01.json'
REVIEW_SHA = 'e251f316272411703ad9f4c1b6221e872e0cdffb67ebdf2b6007e9dd5ab00b8f'
SOURCE = life.ROOT/'hardware/deps/fpnew/src/fpnew_fma.sv'
SOURCE_SHA = 'f46700037a6f9efe9b74855d3d21ebaeaf42f5dd522b9e812bbc56ad7193ec71'
DB = Path(str(life.IMAGE)+'.vdb')
SHAPE = DB/'snps/coverage/db/shape/tgl.verilog.shape.xml'
STAGES, EL_FILES = common.STAGES, common.EL_FILES
NAME = r'[A-Za-z_][\w.]*'
DIMS = r'(?:\[-?\d+:-?\d+\])+'


def review_pins(review):
    result = {}
    for name,sha in review['pins'].items():
        p = Path(name)
        require('..' not in p.parts, 'No review pin path traversal')
        p = (p if p.is_absolute() else life.ROOT/p).resolve()
        require(life.ROOT in p.parents, 'Static review pins must remain in project')
        result = life.merge_pins(result,{str(p):sha})
    require(len(result) == len(review['pins']) and result, 'Unique complete canonical review pins')
    return result


@lru_cache(maxsize=1)
def partition():
    static = life.read_bound(REVIEW,REVIEW_SHA);life.check(review_pins(static))
    require(life.digest(SOURCE) == SOURCE_SHA and static['primary']['source_sha256'] == SOURCE_SHA,
            'Unmodified frozen FMA source identity')
    require(static['primary']['target_objects'] == 816 and static['primary']['toggle_checksum'] == '2490155775',
            'Approved exact half arithmetic group')
    root = ET.fromstring(gzip.decompress(SHAPE.read_bytes()))
    modules = [n for n in root.findall('tgldef') if n.get('chksum') == '2490155775']
    require(len(modules) == 1 and 'FpFormat=2,' in modules[0].get('name','') and
            'WIDTH=16,' in modules[0].get('name',''), 'Exact compiled half specialization')
    targets,protected = [],[];lines = SOURCE.read_text().splitlines()
    for n in modules[0].find('tglshape'):
        require(n.tag in ('node','vectornode','arrays'), 'Unknown compiled declaration kind')
        t = dict(n.attrib,shape_kind=n.tag,dimensions=source.dimensions(n),
                 logical_bits=source.width(n),native_name=source.native_name(n))
        category = source.group(n)
        if category:
            require(t['portnode'] == t['excluded'] == '0' and t['file'] == '381', 'Foreign/excluded numeric field')
            decl = lines[int(t['line_num'])-1].strip()
            member = t['name'].rsplit('.',1)[-1]
            require(re.match(r'logic\b',decl) and re.search(r'\b'+re.escape(member)+r'\b',decl),
                    'Logic declaration bound to source')
            if '.' in t['name']:
                require(t['name'].split('.')[0] in ('operand_a','operand_b','operand_c') and
                        t['aux_file'] == '381' and re.match(r'fp_t\b',lines[int(t['aux_line_num'])-1].strip()) and
                        t['name'].split('.')[0] in lines[int(t['aux_line_num'])-1], 'Exact numeric struct source')
            t.update(source_group=category,source_declaration=decl,
                     source_signed=bool(re.match(r'logic\s+signed\b',decl)))
            targets.append(t)
        else: protected.append(t)
    require(len(targets) == 51 and len(protected) == 220 and
            sum(t['logical_bits'] for t in targets) == 779, 'Full271 source partition')
    return targets,protected


def instances():
    targets,protected = partition()
    return [dict(scope=s,design_module_checksum='2431620414',toggle_checksum='2490155775',
                 targets=targets,protected=protected) for s in fixture.scopes()]


def evidence():
    q = life.read_bound(QUAL,QUAL_SHA);life.check(q['pins'])
    require(q['status'] == 'FOUR_PHASE_HALF_FMA_FUNCTIONALLY_QUALIFIED_NOT_ADMITTED' and
            q['software_checks'] == 2900 and q['full_vrf_bytes'] == 16384 and q['csr_words'] == 20 and
            q['scalar_counts']['matched_instructions'] == 40429 and q['vector_bytes'] == 18814 and
            q['FMA_observations']['accepted'] == q['FMA_observations']['completed'] == 224 and
            set(q['FMA_observations']['per_scope']) == set(fixture.scopes()), 'Complete actual half functional evidence')
    return q


def contract(c):
    require(c['instances'] == instances() and c['functional_qualification_seal'] == QUAL_SHA and
            c['timeout_seconds'] == 1800 and c['population_application'] is False, 'Exact source/function/scope contract')


def parse_el(text,c):
    expected = {i['scope']:i for i in c['instances']};scope=checksum=None;blocks=set();found=defaultdict(list)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'): continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"',line), 'Annotation syntax')
        elif line.startswith('CHECKSUM:'):
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line);require(m is not None,'Checksum syntax')
            checksum=m.groups();scope=None
        elif line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            require(scope in expected and scope not in blocks and checksum ==
                    (expected[scope]['design_module_checksum'],expected[scope]['toggle_checksum']), 'Exact scope/checksum')
            blocks.add(scope)
        else:
            m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?('+NAME+r') "logic ([^"\r\n]+)"',line)
            require(scope is not None and m is not None,'Exact typed whole numerical object')
            direction,name,decl = m.groups()
            t = next((t for t in expected[scope]['targets'] if t['name'] == name),None)
            require(t is not None,'Protected/control/extra exclusion')
            dims = ''.join('[%d:%d]' % tuple(d) for d in t['dimensions'])
            require(decl in (name+dims,dims+name),'Full ordered dimensions/name only')
            found[scope,name,checksum,name+dims].append(direction)
    wanted = {(i['scope'],t['name']) for i in c['instances'] for t in i['targets']}
    require(blocks == set(expected) and len(found) == len(wanted) == 816 and
            {(k[0],k[1]) for k in found} == wanted, 'Exact full816 union')
    for ds in found.values():
        require(ds == [None] or (len(ds) == 2 and set(ds) == {'0to1','1to0'}),'Complete unique direction pair')
    return sorted(found)


def check_stage(out,stage,c):
    require(stage in STAGES,'Stage selector');text=(out/EL_FILES[stage]).read_text()
    if stage in ('apply','reload'): parse_el(text,c)
    else: require(text == '', 'Global exclusion not empty')
    for index,i in enumerate(c['instances']):
        rows = common.inventory(out/('native_%s_%d.tsv' % (stage,index)))
        names = {r['name'] for r in rows}
        required = {t['native_name'] for t in i['targets']+i['protected']}
        require(len(rows) == len(required) == 271 and names == required,'All271 exact native target/protection rows')
        if stage != 'initial':
            before = common.inventory(out/('native_initial_%d.tsv' % index))
            require(sorted(common.semantic_rows(rows)) == sorted(common.semantic_rows(before)), 'Full native identity drift')
    return dict(stage=stage,objects=816,protected_local_objects=3520,global_EL_exact=True)


def prepare(out):
    require(out.parent == life.OUT and not out.exists(),'Fresh native output')
    q=evidence();c=dict(instances=instances(),functional_qualification_seal=QUAL_SHA,
                      population_application=False,timeout_seconds=1800)
    contract(c)
    from inventory_operand_debug import Design
    d=Design(DB)
    require(all(d.hierarchy[i['scope']].get('chksum') == i['design_module_checksum'] for i in c['instances']),
            'Compiled design module identity')
    config=common.predecessor.PRODUCT/'config.json';identity=json.loads(config.read_bytes())['identity'];tools.revalidate(identity)
    vdb=fixture.OUT/'code.vdb';tests=list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(tests) == 1 and tests[0].name == fixture.NAME,'One qualified actual test VDB')
    static=life.read_bound(REVIEW,REVIEW_SHA)
    pins=life.merge_pins(q['pins'],review_pins(static));pins=life.merge_pins(pins,{str(QUAL):QUAL_SHA,str(REVIEW):REVIEW_SHA})
    for p in [Path(__file__),HERE/'test_half_fma816_native.py',HERE/'half_fma816_native.tcl',
              HERE/'fma_expanded_native_02.tcl',Path(common.__file__),Path(source.__file__),
              Path(life.__file__),Path(tools.__file__),config,*vdb.rglob('*')]:
        if p.is_file():pins=life.merge_pins(pins,{str(p.resolve()):life.digest(p)})
    life.check(pins);out.mkdir()
    values=dict(fma_design=str(DB),fma_vdb=str(vdb),fma_test=str(vdb.with_suffix('')/tests[0].name),
        fma_python=str(life.ROOT/'verification/tools/soc-venv/bin/python'),fma_helper=str(Path(__file__).resolve()))
    require(all(not any(ch in v for ch in '{}\\\r\n') for v in values.values()),'Safe Tcl paths')
    lines=['set %s {%s}\n' % p for p in values.items()]+['set fma_instances {}\n']
    for index,i in enumerate(c['instances']):
        lines.append('lappend fma_instances [list {%s} {%s} %d]\n' %
                     (i['scope'],' '.join(t['native_name'] for t in i['targets']),index))
    with (out/'selection.tcl').open('x') as f:f.write(''.join(lines))
    pins[str(out/'selection.tcl')]=life.digest(out/'selection.tcl')
    c.update(output=str(out),pins=pins,identity=identity,automatic_retry=False,objects=816,logical_bits=12464,
        source_review_sha256=REVIEW_SHA,entry_script=str(HERE/'half_fma816_native.tcl'),
        all_descendants_retained=True,exhaustive_functional_validation=False)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1,'Actual DVE terminal')
    log=(out/'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('FMA_EXPANDED_NATIVE_CAPTURE_DONE') == 1 and
            'FMA_EXPANDED_NATIVE_CAPTURE_FAILED' not in log,'Full five stages incomplete')
    stages=[check_stage(out,s,c) for s in STAGES]
    require(parse_el((out/'first.el').read_text(),c) == parse_el((out/'second.el').read_text(),c),'Semantic reload drift')
    pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file()
                                 and p.name not in ('worker.log','capture-result.json')})
    result=dict(status='EXACT_HALF_FMA816_NATIVE_FIVE_STAGE_QUALIFIED_NOT_APPLIED',scopes=16,objects=816,
        logical_bits=12464,protected_local_objects=3520,stages=stages,functional_qualification_seal=QUAL_SHA,
        both_directions=True,all_children_retained=True,population_application=False,
        no_exhaustive_IEEE_claim=True,global_final_reset_empty=True,pins=pins)
    life.save(out/'capture-result.json',result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(out/'capture-result.json'))),flush=True)


class Route:
    def __truediv__(self,name):
        require(name == 'fma_expanded_native.tcl','Only established lifecycle entry')
        return HERE/'half_fma816_native.tcl'


def run(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c)
    FunctionType(common.run.__code__,dict(vars(common),HERE=Route(),verify=verify))(out,seal)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','stage','run','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--stage',choices=STAGES)
    a=p.parse_args();out=a.output.resolve()
    if a.mode == 'prepare':prepare(out)
    else:
        require(a.seal,'Exact config seal')
        if a.mode in ('stage','check'):
            c=life.read_bound(out/'config.json',a.seal);contract(c);life.check(c['pins'])
            print(json.dumps(check_stage(out,a.stage,c)) if a.mode == 'stage' else 'CHECK_PASS')
        else:(run if a.mode == 'run' else verify)(out,a.seal)
