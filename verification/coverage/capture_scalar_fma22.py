"""Approved scalar F/D 22 complete arithmetic objects; one native qualification."""
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path
import re
import shutil
import sys
import types
import xml.etree.ElementTree as ET
import capture_scalar_fma8 as eight
import review_fma_arithmetic_scope as shape_tools

life, require, tools = eight.life, eight.require, eight.tools
HERE = Path(__file__).resolve().parent
PRIOR = life.OUT/'scalar-fma8-native-agent-20261007-01'
PRIOR_SHA = 'ef5db2372ad86e6b3d5a3887fda51f7df51895e1b7941d50e187dcc5de74043b'
NAME = r'[A-Za-z_][\w.]*'
DIMS = r'(?:\[\d+:\d+\])+'


def records(text, c):
    expected={i['scope']:i for i in c['instances']}
    require(len(expected)==2,'Not two scalar instances')
    found=defaultdict(list);blocks=set();scope=None;checksum=None
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('ANNOTATION:'):
            require(line=='ANNOTATION: "Approved unchanged local FMA datapath integration scope; all other signals retained"','Unknown annotation')
        elif line.startswith('CHECKSUM:'):
            require(scope is not None or checksum is None,'Unbound consecutive checksum')
            m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            require(m is not None,'Malformed checksum');checksum=m.groups();scope=None
        elif line.startswith('INSTANCE:'):
            scope=line[len('INSTANCE:'):].strip()
            require(scope in expected and scope not in blocks and checksum==
                (expected[scope]['design_module_checksum'],expected[scope]['toggle_checksum']),
                'Scope/checksum/duplicate block differs')
            blocks.add(scope)
        else:
            m=re.fullmatch(r'Toggle (?:(0to1|1to0) )?('+NAME+r') "logic ([^"\r\n]+)"',line)
            require(scope is not None and m is not None,'Unexpected directive/type')
            direction,name,decl=m.groups()
            target=next((s for s in expected[scope]['signals'] if s['name']==name),None)
            require(target is not None,'Unapproved object')
            suffix=re.fullmatch('('+NAME+')('+DIMS+')',decl)
            prefix=re.fullmatch('('+DIMS+')('+NAME+')',decl)
            require(suffix is not None or prefix is not None,'Malformed full typed declaration')
            declared,dims=suffix.groups() if suffix else tuple(reversed(prefix.groups()))
            require(declared==name and declared+dims==target['native_name'],'Full bounds/member identity differs')
            found[(scope,name)+checksum+(dims,)].append(direction)
    wanted={(i['scope'],s['name']) for i in c['instances'] for s in i['signals']}
    require(len(wanted)==len(found)==22 and {(k[0],k[1]) for k in found}==wanted and
        blocks==set(expected) and scope is not None,'Not exact complete22 union')
    for key,directions in found.items():
        require(directions==[None] or (len(directions)==2 and set(directions)=={'0to1','1to0'}),
                'Duplicate/incomplete/mixed direction selection: '+key[1])
    return sorted(found)


def source_binding(target,lines):
    declaration=lines[int(target['line_num'])-1].strip()
    require(re.match(r'logic\b',declaration) and re.search(r'\b'+re.escape(target['name'].split('.')[-1])+r'\b',declaration),
        'Source declaration identity differs')
    auxiliary=None
    if '.' in target['name']:
        require(target['name'].startswith(('operand_a.','operand_b.','operand_c.')) and
            target['aux_file']==target['file']=='381','Foreign struct')
        auxiliary=lines[int(target['aux_line_num'])-1].strip()
        require(re.match(r'fp_t\b',auxiliary) and target['name'].split('.')[0] in auxiliary,'Struct declaration differs')
    return dict(declaration=declaration,auxiliary_declaration=auxiliary,
        source_signed=bool(re.match(r'logic\s+signed\b',declaration)),native_type='logic',native_qualifiers=[])


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh output required')
    r=life.read_bound(eight.REVIEW,eight.REVIEW_SHA)
    p=life.read_bound(PRIOR/'capture-qualification.json',PRIOR_SHA)
    require(p['status']=='EXACT_SCALAR_FMA8_NATIVE_ROUNDTRIP_QUALIFIED' and p['objects']==8 and
        p['global_empty_resets'] and p['full_typed_complements_protected'],'Prior native8 not qualified')
    pins=life.merge_pins(life.merge_pins(r['pins'],p['pins']),{str(eight.REVIEW):eight.REVIEW_SHA,
        str(PRIOR/'capture-qualification.json'):PRIOR_SHA})
    life.check(pins)
    pins,rebuilt=eight.fixture.compiled(pins)
    require([{k:i[k] for k in ('scope','checksum','compiled_parameters','targets')} for i in rebuilt]==
        [{k:i[k] for k in ('scope','checksum','compiled_parameters','targets')} for i in r['instances']],
        'Actual compiled scalar identity differs')
    source=life.ROOT/'hardware/deps/fpnew/src/fpnew_fma.sv'
    require(pins[str(source)]=='f46700037a6f9efe9b74855d3d21ebaeaf42f5dd522b9e812bbc56ad7193ec71',
        'Frozen unchanged source differs')
    lines=source.read_text().splitlines()
    shape=eight.fixture.old.BUILD/'sim/simv.vdb/snps/coverage/db/shape/tgl.verilog.shape.xml'
    root=ET.fromstring(gzip.decompress(shape.read_bytes()));instances=[]
    for n,i in enumerate(r['instances']):
        definitions=[d for d in root.findall('tgldef') if d.get('chksum')==i['checksum'] and d.get('name')==i['compiled_parameters']]
        require(len(definitions)==1,'Compiled parameter/checksum ambiguity')
        nodes=list(definitions[0].find('tglshape'));partition=i['field_partition']
        selected=partition['initial_four']+partition['extension_seven_source_candidates']
        require(len(selected)==11 and len(partition['protected_from_family51'])==40,'Approved11/protected40 differs')
        signals=[]
        for t in selected:
            matches=[node for node in nodes if node.get('name')==t['name']]
            require(len(matches)==1,'Compiled target ambiguity')
            node=matches[0]
            require(node.attrib=={k:v for k,v in t.items() if k not in ('kind','native_name','logical_bits')} and
                node.tag==t['kind'] and shape_tools.native_name(node)==t['native_name'] and
                shape_tools.width(node)==t['logical_bits'],'Full compiled field differs')
            require(node.get('file')=='381' and node.get('portnode')=='0' and node.get('excluded')=='0','Port/foreign/preexcluded target')
            signals.append(dict(t,left=int(t['left']),right=int(t['right']),source_binding=source_binding(t,lines)))
        require('sum_raw' not in {t['name'] for t in signals},'Carry boundary excluded')
        selected_names={t['name'] for t in signals}
        complement=[dict(node.attrib,kind=node.tag,native_name=shape_tools.native_name(node))
            for node in nodes if node.get('name') not in selected_names]
        instances.append(dict(scope=i['scope'],design_module_checksum='2431620414',toggle_checksum=i['checksum'],
            compiled_parameters=i['compiled_parameters'],signals=signals,protected_typed_complement=complement,
            protected_family40=partition['protected_from_family51'],all_descendants_protected=True,
            native_identity_source=str(PRIOR/('native_before_%d.tsv'%n))))
    require(sum(s['logical_bits'] for i in instances for s in i['signals'])==1566,'Exact1566 bits differs')
    entry=HERE/'fma_datapath_native.tcl';tcl=entry.read_text()
    require(tcl.count('[llength $fma_rows] == 9')==1,'Primitive cardinality changed')
    tcl=tcl.replace('[llength $fma_rows] == 9','[llength $fma_rows] == 11').replace('Not nine unique','Not eleven unique').replace('FMA108NativeOnly','ScalarFMA22NativeOnly')
    identity=tools.prepare(shutil.which('dve'),'/usr/bin/xvfb-run')
    for file in (Path(__file__).resolve(),HERE/'test_capture_scalar_fma22.py',entry,Path(eight.__file__).resolve(),
        Path(shape_tools.__file__).resolve(),Path(tools.__file__).resolve()):
        pins=life.merge_pins(pins,{str(file):life.digest(file)})
    pins=life.merge_pins(pins,{v['path']:v['sha256'] for v in identity['files']});life.check(pins)
    vdb=eight.fixture.RUN/'code.vdb'
    tests=list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(tests)==1 and tests[0].name=='scalar_fpu_finite','Not sole qualified scalar test')
    values=dict(fma_design=str(eight.fixture.old.BUILD/'sim/simv.vdb'),fma_vdb=str(vdb),
        fma_test=str(vdb.with_suffix('')/tests[0].name),fma_python=sys.executable,fma_helper=str(Path(__file__).resolve()))
    require(all(not any(ch in v for ch in '{}\\\n\r') for v in values.values()),'Unsafe Tcl scalar')
    selection=['set '+k+' {'+v+'}\n' for k,v in values.items()]+['set fma_instances {}\n']
    for n,i in enumerate(instances):
        selection.append('lappend fma_instances [list {'+i['scope']+'} {'+' '.join(s['native_name'] for s in i['signals'])+'} {} '+str(n)+']\n')
    candidate=eight.primitive.candidate_text(instances);records(candidate,dict(instances=instances))
    out.mkdir()
    for name,text in (('selection.tcl',''.join(selection)),('capture.tcl',tcl),('candidate.el',candidate)):
        eight.primitive.one.common.save(out/name,text);pins[str(out/name)]=life.digest(out/name)
    c=dict(output=str(out),pins=pins,identity=identity,instances=instances,logical_bits=1566,
        timeout_seconds=600,input_VDB_count=1,selected_test=values['fma_test'],population_application=False,
        source_basis='Unchanged reused arithmetic integration scope; not unreachability',automatic_retry=False)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),objects=22,pins=len(pins))),flush=True)


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);tools.revalidate(c['identity'])
    t=json.loads((out/'terminal.json').read_bytes())
    require(t['returncode']==0 and not t['timeout'] and len(t['actual_dve'])==1,'Terminal identity failed')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('FMA_DATAPATH_NATIVE_CAPTURE_DONE')==1 and
        'FMA_DATAPATH_NATIVE_CAPTURE_FAILED' not in gui and 'FMA_CLEANUP_FAILED' not in gui,'Session failed')
    actual=records((out/'first.el').read_text(),c)
    require(actual==records((out/'second.el').read_text(),c),'Full identity/direction reload differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes()==b'','Not global empty')
    for n,i in enumerate(c['instances']):
        def rows(path):
            lines=path.read_text().splitlines()
            require(lines[0]=='handle\tpath\tmeta\tname','Native inventory header differs')
            result=[tuple(line.split('\t')[1:]) for line in lines[1:]]
            require(result and all(len(row)==3 and all(row) for row in result) and len(result)==len(set(result)),
                'Missing/ambiguous native inventory')
            require(len({row[0] for row in result})==len(result) and len({row[2] for row in result})==len(result),
                'Duplicate native identity')
            return result
        before=rows(out/('native_before_%d.tsv'%n))
        require(before==rows(Path(i['native_identity_source'])),'Original full typed complement changed')
        names={row[2] for row in before}
        require({s['native_name'] for s in i['signals']} <= names,'Native target not present')
        for stage in ('selected','reset','reloaded','final'):
            require(rows(out/('native_%s_%d.tsv'%(stage,n)))==before,'Full target/protected native inventory changed')
    result=dict(status='EXACT_SCALAR_FMA22_NATIVE_ROUNDTRIP_QUALIFIED',objects=22,logical_bits=1566,
        config_seal=seal,semantic_reload=True,whole_objects_or_complete_direction_pairs=True,
        global_empty_resets=True,full_typed_complements_protected=True,protected_family_objects_per_instance=40,
        all_other_scopes_protected=True,population_application=False,official_denominator=False,
        pins={**c['pins'],**{str(p):life.digest(p) for p in out.rglob('*') if p.is_file()}})
    life.check(result['pins']);life.save(out/'capture-result.json',result)
    print('QUALIFIED '+life.digest(out/'capture-result.json'),flush=True)


def run(out,seal):
    # Private namespace, unchanged sealed launch/timeout/live-executable mechanism.
    launch=types.FunctionType(eight.run.__code__,dict(eight.run.__globals__,verify=verify),eight.run.__name__)
    launch(out,seal)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','run','verify','el'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal');parser.add_argument('--file',choices=('first.el','second.el'))
    a=parser.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode=='el':
        require(a.file is not None,'EL filename required');c=json.loads((out/'config.json').read_bytes())
        print(json.dumps(dict(objects=len(records((out/a.file).read_text(),c)))))
    else:
        require(a.seal,'Config seal required');(run if a.mode=='run' else verify)(out,a.seal)
