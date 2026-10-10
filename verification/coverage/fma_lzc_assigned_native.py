"""Explicit multidimensional assigned-row candidate; only real DVE readback qualifies."""
import argparse
import itertools
import json
from pathlib import Path
import re
from types import FunctionType
import cva6_fixed_fields_native768 as native
import prove_fma_lzc_binary_tree as proof

life, require, tools = native.life, native.require, native.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT/'fma-lzc-binary-tree-independent-review-agent-20261007-01.json'
REVIEW_SHA = '8152618a2107ce5f153bb578de69bd4077c83030a9bd9a950c63fb91eb1313c6'
TEMPLATE = life.OUT/'cva6-fixed120-native768-agent-20261007-01'
TEMPLATE_SHA = '1a34f949b9d89a1a7403c067a1d3c56228df3d72d9d4527b36d6c33c2604858c'


def coordinates(dimensions):
    require(all(left >= right >= 0 for left,right in dimensions),'Descending exact ranges only')
    return set(itertools.product(*(range(right,left+1) for left,right in dimensions)))


def wanted(config):
    return {(i['scope'],s['name'],coord,direction) for i in config['instances'] for s in i['signals']
            for coord in coordinates(s['selected_dimensions']) for direction in ('0to1','1to0')}


def declaration(s):
    return s['name']+''.join('['+str(left)+':'+str(right)+']' for left,right in s['dimensions'])


def candidate(config):
    lines=[]
    for i in config['instances']:
        lines += ['CHECKSUM: "'+i['design_module_checksum']+' '+i['toggle_checksum']+'"','INSTANCE: '+i['scope'],
                  'ANNOTATION: "Reviewed assigned binary LZC library internals only; undriven spare and all ports retained"']
        for s in i['signals']:
            selects=''.join('['+str(left)+':'+str(right)+']' for left,right in s['selected_dimensions'])
            # This is a candidate request, not an assertion that DVE accepts MDA selects.
            # needsReview and exact exported physical-coordinate set are mandatory.
            lines.append('Toggle '+s['name']+' '+selects+' "logic '+declaration(s)+'"')
    return '\n'.join(lines)+'\n'


def parse_el(text,config):
    instances={i['scope']:i for i in config['instances']};found=set();scope=None;checks=None
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('//'):continue
        if re.fullmatch(r'ANNOTATION: "[^"\n]*"',line):continue
        m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
        if m:checks=list(m.groups());scope=None;continue
        if line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            require(scope in instances and checks==[instances[scope]['design_module_checksum'],instances[scope]['toggle_checksum']], 'Scope/checksum differs')
            continue
        m=re.fullmatch(r'Toggle(?: (0to1|1to0))? (gen_lzc\.(?:index_lut|index_nodes|sel_nodes|in_tmp))((?:\s*\[\d+(?::\d+)?\])*) "([^"\n]+)"',line)
        require(scope is not None and m is not None,'Unknown EL directive or protected port')
        direction,name,ranges,signature=m.groups()
        s=next(x for x in instances[scope]['signals'] if x['name']==name)
        prefix=''.join('['+str(l)+':'+str(r)+']' for l,r in s['dimensions'])
        require(signature in ('logic '+declaration(s),'logic '+prefix+name),'Full declaration signature/bounds differ')
        dimensions=[(int(a),int(b or a)) for a,b in re.findall(r'\[(\d+)(?::(\d+))?\]',ranges)]
        if not dimensions:dimensions=s['dimensions']
        require(len(dimensions)==len(s['dimensions']),'No flattened/omitted dimension permitted')
        selected=coordinates(dimensions)
        require(selected <= coordinates(s['selected_dimensions']),'Undriven spare or out-of-bounds selected')
        for coord in selected:
            for d in (direction,) if direction else ('0to1','1to0'):
                key=(scope,name,coord,d);require(key not in found,'Duplicate direction');found.add(key)
    require(found==wanted(config),'Missing/extra assigned-coordinate directions')
    return sorted(found)


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh qualification directory only')
    review=life.read_bound(REVIEW,REVIEW_SHA);life.check(review['pins'])
    replay=proof.evidence()
    require(replay['candidate_assigned_internal_bits']==23132 and replay['retained_undriven_spare_bits']==212,'Source proof boundary')
    static=life.read_bound(proof.STATIC,proof.STATIC_SHA);life.check(static['pins'])
    template=life.read_bound(TEMPLATE/'config.json',TEMPLATE_SHA)
    # Consume source/shape/identity, not any old qualification status or historical full prepare.
    pins=life.merge_pins(review['pins'],static['pins'])
    pins[str(REVIEW)]=REVIEW_SHA;pins[str(proof.STATIC)]=proof.STATIC_SHA;pins[str(TEMPLATE/'config.json')]=TEMPLATE_SHA
    instances=[]
    for item in static['instances']:
        width=item['parameters']['WIDTH'];levels=(width-1).bit_length();size=1<<levels
        require(item['parameters']==dict(WIDTH=width,MODE=1,CNT_WIDTH=levels,**{'gen_lzc.NumLevels':levels}),'Actual elaborated parameters')
        signals=[]
        for field in item['internal_candidates']:
            dims=field['dimensions'];name=field['name']
            expected={'gen_lzc.index_lut':[[width-1,0],[levels-1,0]],'gen_lzc.in_tmp':[[width-1,0]],
                      'gen_lzc.sel_nodes':[[size-1,0]],'gen_lzc.index_nodes':[[size-1,0],[levels-1,0]]}[name]
            require(dims==expected,'Compiled multidimensional shape')
            selected=[list(d) for d in dims]
            if name in ('gen_lzc.sel_nodes','gen_lzc.index_nodes'):selected[0]=[size-2,0]
            signals.append(dict(name=name,dimensions=dims,selected_dimensions=selected,shape=field['attributes'],
                                native_label=field['typed_native_label_candidate']))
        protected=item['protected_full_complement']
        require(len(protected)==3 and {p['name'] for p in protected}=={'in_i','cnt_o','empty_o'},'Full port protection')
        instances.append(dict(scope=item['scope'],design_module_checksum=item['module_checksum'],toggle_checksum=item['toggle_checksum'],
            signals=signals,protected=protected,all_typed_labels=[x['typed_native_label_candidate'] for x in item['internal_candidates']+protected],
            retained_sel_node=size-1,retained_index_row=size-1,parameters=item['parameters']))
    config=dict(template,output=str(out),pins=pins,instances=instances,source_review_sha256=REVIEW_SHA,
        timeout_seconds=900,population_application=False,launch_authorized=True,
        qualification_scope='Only32 matched LZC assigned internals; independent library scope, not unreachable/X equivalence',
        candidate_MDA_select_grammar_native_unproven=True)
    require(len(instances)==32 and len(wanted(config))==46264,'Exact23132 assigned bits')
    identity=template['identity'];tools.revalidate(identity)
    db=Path(config['design'])/'snps/coverage/db'
    for relative in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        path=db/relative
        expected=static['pins'].get(str(path),template['pins'].get(str(path)))
        require(expected is not None and life.digest(path)==expected,'Reviewed compiled database identity')
        pins[str(path)]=expected
    shape=native.primitive.toggle.xml(db/'shape/tgl.verilog.shape.xml')
    info=native.primitive.toggle.xml(db/'shape/tgl.verilog.info.xml')
    checks={node.get('name'):node.get('chksum') for node in info.iter('instance_data')}
    design=native.Design(Path(config['design']))
    for i in instances:
        require(checks.get(i['scope'])==i['toggle_checksum'] and
                design.hierarchy[i['scope']].get('chksum')==i['design_module_checksum'],'Actual native instance/checksum')
        definitions=[d for d in shape.findall('tgldef') if d.get('chksum')==i['toggle_checksum']]
        require(len(definitions)==1,'Unique compiled LZC shape')
        nodes={node.get('name'):dict(node.attrib) for node in definitions[0].find('tglshape')}
        require(nodes=={s['name']:s['shape'] for s in i['signals']}|{p['name']:p['attributes'] for p in i['protected']},
                'Complete actual compiled target and protected declarations')
    for path,sha in template['pins'].items():
        if path.startswith(config['vdb']+'/'):pins[path]=sha
    for module in (native,native.primitive,native.primitive.common,life,tools,proof,proof.calibration):
        path=Path(module.__file__).resolve();pins[str(path)]=life.digest(path)
    for name in ('fma_lzc_assigned_native.py','test_fma_lzc_assigned_native.py','cva6_fixed_fields_native768.tcl'):
        path=HERE/name;pins[str(path)]=life.digest(path)
    text=candidate(config);parse_el(text,config);life.check(pins)
    out.mkdir();native.primitive.common.common.save(out/'candidate.el',text)
    native.primitive.common.common.save(out/'queue_constant_native.tcl',(HERE/'cva6_fixed_fields_native768.tcl').read_text())
    selection=''.join('set qc_'+k+' {'+config[k]+'}\n' for k in ('design','vdb','test'))
    selection+='set qc_python {'+__import__('shutil').which('python3')+'}\nset qc_helper {'+str(Path(__file__).resolve())+'}\nset qc_instances {}\n'
    for i in instances:selection+='lappend qc_instances [list {'+i['scope']+'} [list '+' '.join('{'+s['native_label']+'}' for s in i['signals'])+']]\n'
    native.primitive.common.common.save(out/'selection.tcl',selection)
    for name in ('candidate.el','selection.tcl','queue_constant_native.tcl'):pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',config)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),assigned_bits=23132,spare_bits_retained=212,ports_retained=96)))


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);tools.revalidate(c['identity'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Native execution identity')
    for name in ('launcher.log','DVEfiles/dve_gui.log'):
        text=(out/name).read_text();require(not re.search(r'(?:Warning-|Error-|Fatal-|\b(?:Error|Fatal):|QUEUE_CONSTANT_NATIVE_FAILED)',text),'Native diagnostic')
    require((out/'DVEfiles/dve_gui.log').read_text().splitlines().count('QUEUE_CONSTANT_NATIVE_DONE')==1,'Five-stage incomplete')
    first=parse_el((out/'first.el').read_text(),c);require(first==parse_el((out/'second.el').read_text(),c),'Exact physical-coordinate reload mismatch')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):require((out/name).read_bytes()==b'','Global reset not empty')
    for k,i in enumerate(c['instances']):
        stages={s:native.native_rows((out/('native_'+s+'_'+str(k)+'.tsv')).read_text()) for s in ('before','selected','reset','reloaded','final')}
        require(set(stages['before'])==set(i['all_typed_labels']),'Exact complete typed instance')
        ports={p['typed_native_label_candidate'] for p in i['protected']}
        for stage,rows in stages.items():
            require(set(rows)==set(stages['before']),'Native object set changed')
            for name,row in rows.items():
                before=stages['before'][name]
                require(all(row[key]==before[key] for key in ('path','meta','type')),'Native identity drift')
                if name in ports or stage in ('reset','final'):require(row==before,'Port/reset percentage/display drift')
        require(stages['selected']==stages['reloaded'],'Reload percentages differ')
    result=dict(status='LZC_ASSIGNED23132_NATIVE_PARTIAL_ARRAY_ROUNDTRIP_NOT_APPLIED',config_seal=seal,
        assigned_bits=23132,exact_physical_directions=46264,retained_spare_bits=212,protected_port_objects=96,
        exact_global_EL=True,semantic_reload=True,finalreset=True,initial_X_excluded=False,
        official_denominator_verified=False,population_application=False,
        pins={**c['pins'],**{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='capture-result.json'}})
    life.save(out/'capture-result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','run','verify','el'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal');parser.add_argument('--file')
    args=parser.parse_args();out=args.output.resolve()
    if args.mode=='prepare':prepare(out)
    elif args.mode=='run':FunctionType(native.run.__code__,dict(vars(native),verify=verify))(out,args.seal)
    elif args.mode=='verify':verify(out,args.seal)
    else:print(len(parse_el((out/args.file).read_text(),json.loads((out/'config.json').read_bytes()))))
