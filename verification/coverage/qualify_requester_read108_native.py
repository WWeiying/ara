"""One local typed108 read-payload qualification; all746 objects per lane audited."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
from types import FunctionType
import xml.etree.ElementTree as ET
import qualify_csr_pmp0_native765 as primitive
import review_requester_read_payload767 as source

runner=primitive.runner
life,tools,require=runner.life,runner.tools,runner.require
HERE=Path(__file__).resolve().parent
REVIEW=life.OUT/'requester-read-payload-constant767-agent-20261007-01.json'
REVIEW_SHA='4844e6f932404aa47a24b42de345ed77ea5e497cebfef5f8118eb07e0ac914fd'
ANNOTATION='Frozen nine read payloads wdata/be/wen zero after valid reset and settled evaluation; no initial-X waiver'
STAGES=runner.STAGES
bounds,aliases=primitive.bounds,primitive.aliases


def strict_percent(value):
    """Rooted CSV format check only; not used to infer native qualification."""
    if value == 'NA':
        return None
    require(isinstance(value,str) and re.fullmatch(r'(?:0|[1-9][0-9]?|100)(?:\.[0-9]+)?%',value,re.ASCII) is not None,
            'Exact single-percent encoding')
    number=float(value[:-1])
    require(0<=number<=100,'Percentage range')
    return number


def instances():
    r=life.read_bound(REVIEW,REVIEW_SHA)
    require(r['exact_objects']==108 and r['all_target_bits']==2628 and not r['exclusions_applied'],'Exact source candidate')
    rank=life.read_bound(source.RANK,source.RANK_SHA)
    byname={Path(p).name:Path(p) for p in rank['pins'] if p.endswith(('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml'))}
    scopes=sorted(r['protected_by_scope'])
    _,defs=source.shared.toggle.definitions(*(source.shared.toggle.xml(byname[n]) for n in
                         ('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml')),scopes)
    result=[]
    for scope in scopes:
        targets=[t for t in r['targets'] if t['scope']==scope]
        protected=[dict(kind='arrays',**ET.fromstring(n['definition']).attrib) if n['kind']=='arrays' else n
                   for n in r['protected_by_scope'][scope]]
        require(len(targets)==27 and len(protected)==719 and len({n['name'] for n in targets+protected})==746,'Full target/complement inventory')
        result.append(dict(scope=scope,targets=targets,protected=protected,toggle_checksum=targets[0]['checksum'],
                           design_module_checksum=defs[scope]['module']['chksum']))
    require(len(result)==4,'Only four requester scopes')
    return result


def contract(c):
    require(c['instances']==instances() and c['timeout_seconds']==900 and not c['automatic_retry'] and
            c['population_application'] is False and c['source_review_seal']==REVIEW_SHA,'Only exact reviewed108 contract')


def inventory(out,c,stage,index):
    require(stage in STAGES and 0<=index<4,'Stage/scope')
    with (out/('native_%s_%d.tsv'%(stage,index))).open(newline='') as f:rows=list(csv.reader(f,delimiter='\t'))
    require(rows and rows[0]==['handle','path','meta','name','excluded'] and
            all(len(r)==5 and all(r) for r in rows[1:]),'Strict full native schema')
    rows=rows[1:];i=c['instances'][index];allnodes=i['targets']+i['protected']
    require(len(rows)==746 and len({r[0] for r in rows})==len({r[1] for r in rows})==746,'All native rows unique and exact746')
    byname=defaultdict(list)
    for r in rows:byname[r[3]].append(r)
    used=set();bound=[];targetnames={n['name'] for n in i['targets']}
    for n in allnodes:
        matches=[r for name in aliases(n) for r in byname[name]]
        require(len(matches)==1 and matches[0][0] not in used,'Missing/ambiguous complete field: '+n['name'])
        r=matches[0];used.add(r[0]);dims=bounds(n)
        require(r[1]==r[3] and r[2] in (r[3],'logic '+n['name']+dims,'logic '+dims+n['name']), 'Exact path/meta/type')
        wanted='1' if stage in ('selected','reloaded') and n['name'] in targetnames else '0'
        require(r[4]==wanted,'Target/complement excluded flag: '+n['name'])
        bound.append((n['name'],r[1],r[2],r[3]))
    require(len(used)==len(rows),'No silent extra native object')
    return sorted(bound)


def parse_el(text,c):
    wanted={(i['scope'],n['name']):(i,n) for i in c['instances'] for n in i['targets']}
    scope=check=annotation=None;found=defaultdict(list);blocks=set()
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('ANNOTATION:'):
            require(line=='ANNOTATION: "'+ANNOTATION+'"','Exact intended annotation');annotation=ANNOTATION
        elif line.startswith('CHECKSUM:'):
            m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line);require(m is not None,'Checksum syntax');check=m.groups();scope=None
        elif line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip();require(scope not in blocks,'Duplicate scope block');blocks.add(scope)
            i=next((i for i in c['instances'] if i['scope']==scope),None)
            require(i and check==(i['design_module_checksum'],i['toggle_checksum']),'Scope/checksum')
        else:
            m=re.fullmatch(r'Toggle (?:(0to1|1to0) )?([^\s"]+) "logic ([^"\r\n]+)"',line)
            require(m is not None and annotation==ANNOTATION,'Only exact typed Toggle records')
            direction,name,decl=m.groups();key=scope,name;require(key in wanted,'Protected/extra/whole object')
            _,n=wanted[key];dims=bounds(n)
            require(decl in (name+dims,dims+name),'Full ordered field dimensions/type')
            found[key].append(direction)
    require(set(found)==set(wanted) and len(blocks)==4,'Exact complete108 four scopes')
    for key,dirs in found.items():
        require(dirs==[None] or len(dirs)==2 and set(dirs)=={'0to1','1to0'},'Duplicate/incomplete direction')
    return sorted((scope,name,bounds(wanted[scope,name][1]),ANNOTATION,('0to1','1to0')) for scope,name in found)


def check_file(out,c,name):
    require(name in ('initial-empty.el','reset-empty.el','final-empty.el','first.el','second.el'),'Exact EL filename')
    if name.endswith('empty.el'):require((out/name).read_bytes()==b'','Global empty EL');return 0
    return len(parse_el((out/name).read_text(),c))


def inspect(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and terminal['timeout'] is False and len(terminal['actual_dve'])==1,'Actual executable/terminal')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('REQUESTER_READ108_NATIVE_DONE')==1 and
            'REQUESTER_READ108_NATIVE_FAILED' not in gui and not (out/'error.txt').exists(),'Five stages incomplete')
    for index in range(4):
        before=inventory(out,c,'before',index)
        for stage in STAGES[1:]:require(inventory(out,c,stage,index)==before,'Full identity/protection drift')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','first.el','second.el'):check_file(out,c,name)
    require(parse_el((out/'first.el').read_text(),c)==parse_el((out/'second.el').read_text(),c),'Exact semantic multiset reload')
    pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and
                                  p.name not in ('worker.log','capture-result.json')})
    life.save(out/'capture-result.json',dict(status='REQUESTER_READ_FIELDS108_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED',
        config_seal=seal,source_review_seal=REVIEW_SHA,objects=108,logical_bits=2628,protected_objects=2876,
        complete_native_rows_per_scope=746,all_five_stage_excluded_flags_checked=True,
        exact_EL_both_directions=True,exact_annotations=True,all_other_metrics_and_scopes_globally_protected=True,
        initial_reset_final_global_EL_empty=True,population_application=False,source_population=767,
        native_context='Single fully qualified stride testcase, formally admitted in768; no population report',
        initial_X_excluded=False,official_percentage=None,pins=pins))
    print('NATIVE108_QUALIFIED',life.digest(out/'capture-result.json'),flush=True)


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh native directory')
    r=life.read_bound(REVIEW,REVIEW_SHA);life.check(r['pins'])
    source.source_contract(source.REQUESTER.read_text(),source.PACKAGE.read_text())
    origin=runner.inherited.PRODUCT/'config.json';old=json.loads(origin.read_bytes());tools.revalidate(old['identity'])
    vdb=source.shared.OUT/'stride-metadata-full64-old-image767-agent-20261007-01/code.vdb'
    m=source.shared.life.read_bound(source.shared.OUT/'stride-metadata-full64-offline-admitted-768-agent-20261007-01/admission-manifest.json',
        '1add5889916fd9cfe2bb6e95368a2a86d43f1d0ac27ac4cf89786639cb6f4198')
    life.check(m['output_pins']);dirs=list((vdb/'snps/coverage/db/testdata').iterdir());require(len(dirs)==1,'One admitted native test')
    paths=[origin,REVIEW,Path(__file__).resolve(),HERE/'qualify_requester_read108_native.tcl',HERE/'test_qualify_requester_read108_native.py',
        HERE/'queue_fp_temporaries_native.tcl',HERE/'fma_datapath_native.tcl',Path(primitive.__file__),Path(runner.__file__),
        Path(runner.inherited.__file__),Path(source.__file__),Path(life.__file__),Path(tools.__file__),
        source.shared.OUT/'stride-metadata-full64-offline-admitted-768-agent-20261007-01/admission-manifest.json',*vdb.rglob('*')]
    pins=life.merge_pins(r['pins'],{str(p):life.digest(p) for p in paths if p.is_file()})
    c=dict(instances=instances(),identity=old['identity'],pins=pins,timeout_seconds=900,population_application=False,
           automatic_retry=False,source_review_seal=REVIEW_SHA,output=str(out));contract(c);life.check(pins);out.mkdir()
    values=dict(fma_design=str(life.IMAGE)+'.vdb',fma_vdb=str(vdb),fma_test=str(vdb.with_suffix('')/dirs[0].name),
        fma_python=str(life.ROOT/'verification/tools/soc-venv/bin/python'),fma_helper=str(Path(__file__).resolve()),
        qfp_primitives=str(HERE/'fma_datapath_native.tcl'))
    require(all(not any(ch in v for ch in '{}\\\r\n') for v in values.values()),'Safe literal Tcl paths')
    lines=['set %s {%s}\n'%pair for pair in values.items()]+['set fma_instances {}\n']
    for index,i in enumerate(c['instances']):
        lines.append('lappend fma_instances [list {%s} {%s} {%s} %d]\n'%(i['scope'],
            ' '.join(n['name']+bounds(n) for n in i['targets']),' '.join(n['name']+bounds(n) for n in i['protected']),index))
    with (out/'selection.tcl').open('x') as f:f.write(''.join(lines))
    pins[str(out/'selection.tcl')]=life.digest(out/'selection.tcl');life.save(out/'config.json',c)
    print('PREPARED',str(out),life.digest(out/'config.json'),len(pins),flush=True)


class Route:
    def __truediv__(self,name):
        require(name=='capture_cast168_native.tcl','Only established lifecycle entry');return HERE/'qualify_requester_read108_native.tcl'


def run(out,seal):
    FunctionType(runner.run.__code__,dict(vars(runner),contract=contract,inspect=inspect,HERE=Route()))(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run','inventory','el','inspect'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--stage');p.add_argument('--index',type=int);p.add_argument('--file')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('inventory','el'):
        c=json.loads((out/'config.json').read_bytes())
        print(len(inventory(out,c,a.stage,a.index)) if a.mode=='inventory' else check_file(out,c,a.file))
    else:
        require(a.seal,'Exact seal')
        if a.mode=='verify':c=life.read_bound(out/'config.json',a.seal);contract(c);life.check(c['pins']);print('VERIFY_PASS')
        else:(run if a.mode=='run' else inspect)(out,a.seal)
