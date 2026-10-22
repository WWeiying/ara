"""Exact initialized RVH0 TLB fields: local native qualification, no population application."""
import argparse
import csv
import json
from pathlib import Path
import re
from types import FunctionType

import capture_csr_reserved1193_v2 as csr
import audit_csr_reserved1193_percent as pct
import targeted_toggle_evidence_v2 as native

life, require, tools = csr.life, csr.require, csr.tools
HERE = Path(__file__).resolve().parent
HOOK = HERE/'capture_tlb_rvh0_726.tcl'
RANK = life.OUT/'cva6-toggle-capacity-source-review768-agent-20261007-01.json'
RANK_SHA = 'd964f780dd7ecfbfa928c72b77bb42e2fe0e41e90830dfad84ff377909862f08'
QUAL = life.OUT/'native-batch-full766-offline-closure-parent-review-01/qualification.json'
QUAL_SHA = '0ed4bbb08ea2dda3ad7b8472698d7ee7964c54db3c3dc0d150284ee40e20d5e8'
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.'
SCOPES = [PREFIX+'i_itlb', PREFIX+'i_dtlb']
CHECKSUM = '475068782 817233724'
BOUNDARY = 'RVH0 initialized internal guest PTE storage only; valid reset and settled operation; no startup-X or arbitrary force claim; all ordinary PTE and interfaces protected.'
STAGES = csr.STAGES
EL_FILES = csr.EL_FILES


def compact(text):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S))


def source_induction(text):
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    writers = re.findall(r'\b(content_[qn](?:\[[^\]]+\]|\.\w+)*)\s*(<=|=(?!=))\s*([^;]+);', clean)
    observed = [(a,b,compact(c)) for a,b,c in writers]
    require(observed == [('content_n','=','content_q'),
        ('content_n[i].pte','=','update_i.content'),
        ('content_n[i].gpte','=','update_i.g_content'),
        ('content_q','<=',"'{default:0}"),('content_q','<=','content_n')], 'All content writers differ')
    c = compact(text)
    require(c.count('if(CVA6Cfg.RVH)content_n[i].gpte=update_i.g_content;') == 1,
            'Sole guest modification must be RVH guarded')
    require("if(~rst_ni)begintags_q<='{default:0};content_q<='{default:0};plru_tree_q<='{default:0};endelsebegintags_q<=tags_n;content_q<=content_n;plru_tree_q<=plru_tree_n;end" in c,
            'Unconditional reset and matching capture/hold')
    guest = re.findall(r'\bg_content(?:\.\w+|\[[^\]]+\])*\s*(<=|=(?!=))\s*([^;]+);', clean)
    require([(op,compact(rhs)) for op,rhs in guest] == [('=',"'{default:0}")], 'Internal g_content additional writer')
    return dict(all_content_writers=observed, g_content_writers=guest,
        induction='RVH0 removes sole gpte modification; unconditional reset zero; combinational hold and sequential capture preserve zero. Internal g_content has only explicit zero assignment.',
        boundary=BOUNDARY)


def eligible(n):
    return n['kind'] in ('node','vectornode') and n.get('portnode') == '0' and (
        re.fullmatch(r'content_[qn]\[(?:[0-9]|1[0-5])\]\.gpte\.\w+', n['name']) is not None or
        re.fullmatch(r'g_content\.\w+', n['name']) is not None)


def no_overlap(text):
    require(not re.search(r'^(?:MODULE|FILE):', text, re.M), 'Unreviewed broad prior waiver')
    prior=None;directives=[]
    def check():
        if prior not in (None, '') and any(s==prior or s.startswith(prior+'.') for s in SCOPES):
            require(directives, 'Prior whole-scope waiver overlaps TLB ancestor')
            for line in directives:
                match=re.match(r'Toggle (?:(?:0to1|1to0) )?([^\s"]+)',line)
                require(match is not None,'Unreviewed ancestor directive')
                full=prior+'.'+match.group(1)
                require(all(not (full.startswith(s+'.') or s==prior) for s in SCOPES),
                        'Prior field waiver overlaps exact TLB')
    for raw in text.splitlines():
        line=raw.strip()
        if line.startswith(('CHECKSUM:','INSTANCE:')):
            check();directives=[]
            prior=line.split(':',1)[1].strip() if line.startswith('INSTANCE:') else None
        elif line and not line.startswith(('ANNOTATION:','//')):
            directives.append(line)
    check()


def proof():
    rank = life.read_bound(RANK, RANK_SHA); life.check(rank['pins'])
    config_review = life.read_bound(csr.original.REVIEW, csr.original.REVIEW_SHA)
    life.check(config_review['input_pins'])
    require(config_review['config']['RVH'] == 0 and config_review['config']['XLEN'] == 64,
            'Exact initialized RVH0 configuration')
    bp = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = life.read_bound(bp,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    pins = life.merge_pins(life.merge_pins(rank['pins'], config_review['input_pins']),
                          {str(RANK):RANK_SHA,str(csr.original.REVIEW):csr.original.REVIEW_SHA,str(QUAL):QUAL_SHA})
    rels = ['core/cva6_mmu/cva6_tlb.sv','core/cva6_mmu/cva6_mmu.sv',
            'core/load_store_unit.sv','core/include/build_config_pkg.sv',
            'core/include/cv64a6_imafdcv_sv39_config_pkg.sv']
    texts = {}
    for rel in rels:
        p = life.ROOT/'hardware/deps/cva6'/rel
        require(life.digest(p) == book[str(p)], 'Historical source drift')
        pins = life.merge_pins(pins,{str(p):book[str(p)]});texts[rel] = p.read_text()
    induction = source_induction(texts[rels[0]])
    cfg,lsu,mmu = (compact(texts[k]) for k in (rels[4],rels[2],rels[1]))
    require('localparamCVA6ConfigHExtEn=0;' in cfg and "RVH:bit'(CVA6ConfigHExtEn)" in cfg and
            "InstrTlbEntries:int'(16)" in cfg and "DataTlbEntries:int'(16)" in cfg,
            'Frozen RVH/entries propagation')
    require('localparamHYP_EXT=CVA6Cfg.RVH?1:0;' in lsu and
            '.CVA6Cfg(CVA6Cfg)' in lsu and '.HYP_EXT(HYP_EXT))i_cva6_mmu(' in lsu,
            'LSU MMU configuration forwarding')
    for entries,scope in [('InstrTlbEntries','i_itlb'),('DataTlbEntries','i_dtlb')]:
        require('.TLB_ENTRIES(CVA6Cfg.%s),.HYP_EXT(HYP_EXT))%s('%(entries,scope) in mmu,
                'TLB entries/HYP forwarding')
    paths = {Path(p).name:Path(p) for p in rank['pins'] if p.endswith(
        ('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml'))}
    checks,defs = native.definitions(*(native.xml(paths[n]) for n in
        ('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml')),SCOPES)
    instances = []
    for scope in SCOPES:
        require(checks[scope] == '817233724' and defs[scope]['module']['name'] == 'cva6_tlb' and
                defs[scope]['module']['chksum'] == '475068782', 'Exact compiled TLB identity')
        nodes = [dict(kind=n.tag,**n.attrib) for n in native.base.ET.fromstring(defs[scope]['shape']).find('tglshape')]
        targets = [n for n in nodes if eligible(n)]
        require(len(targets) == 363 and sum(width(n) for n in targets) == 2112,
                'Exact per-scope target set')
        require(all(n['excluded'] == '0' and n['file'] == '407' and n['aux_file'] == '405' for n in targets),
                'Compiled original/type source or exclusion differs')
        instances.append(dict(scope=scope,nodes=nodes,targets=targets))
    q = life.read_bound(QUAL,QUAL_SHA)
    require(q['population'] == 766, 'Reviewed prior population')
    old = life.OUT/'native-batch-full766-agent-20261007-01/applied.el'
    require(str(old) in q['output_pins'], 'Prior EL authority missing')
    text = old.read_text()
    require(life.digest(old) == q['output_pins'][str(old)], 'Prior native EL drift')
    no_overlap(text);pins = life.merge_pins(pins,{str(old):q['output_pins'][str(old)]})
    return instances,induction,pins


def width(n):
    return 1 if n['kind'] == 'node' else abs(int(n['left'])-int(n['right']))+1


def declaration(n):
    return csr.original.declaration(n)


def candidate(c):
    lines = []
    for instance in c['instances']:
        lines += ['CHECKSUM: "'+CHECKSUM+'"','INSTANCE: '+instance['scope'],'ANNOTATION: "'+BOUNDARY+'"']
        lines += ['Toggle '+n['name']+' "logic '+declaration(n)+'"' for n in instance['targets']]
    return '\n'.join(lines)+'\n'


def records(text,c):
    byscope = {i['scope']:{n['name']:n for n in i['targets']} for i in c['instances']}
    actual=set();seen=set();scope=None;checksum=False;pending=False
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('CHECKSUM:'):
            require(line=='CHECKSUM: "'+CHECKSUM+'"' and not pending,'Exact checksum block');checksum=True;pending=True;continue
        if line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip()
            require(checksum and scope in byscope and scope not in seen,'Exact unique native scope')
            seen.add(scope);pending=False;continue
        if line.startswith('ANNOTATION:'):
            require(line=='ANNOTATION: "'+BOUNDARY+'"','Exact settled-reset annotation');continue
        match=re.fullmatch(r'Toggle (?:(0to1|1to0) )?([^\s"]+)(?: \[(\d+)(?::(\d+))?\])? "logic ([^"\r\n]+)"',line)
        require(scope and not pending and match is not None,'Unknown/incomplete native directive')
        direction,name,left,right,meta=match.groups();require(name in byscope[scope],'Foreign/protected native field')
        n=byscope[scope][name];require(meta==declaration(n),'Complete typed declaration differs')
        full={0} if n['kind']=='node' else set(range(int(n['right']),int(n['left'])+1))
        bits=full if left is None else set(range(int(right or left),int(left)+1))
        require(bits and bits<=full,'Out-of-range native bit')
        for bit in bits:
            for d in (('0to1','1to0') if direction is None else (direction,)):
                key=(scope,name,bit,d);require(key not in actual,'Duplicate/cross-bit direction');actual.add(key)
    expected={(s,n['name'],b,d) for s,nodes in byscope.items() for n in nodes.values()
              for b in ({0} if n['kind']=='node' else range(int(n['right']),int(n['left'])+1)) for d in ('0to1','1to0')}
    require(not pending and seen==set(SCOPES) and actual==expected and len(actual)==8448,
            'Exact726 fields/4224 bits/both directions only')
    return sorted(actual)


def inventory(out,c,stage,index):
    i=c['instances'][index];aliases={a:n for n in i['nodes'] for a in csr.original.base.aliases(n)}
    targets={n['name'] for n in i['targets']};found={}
    with (out/('objects-%s-%d.tsv'%(stage,index))).open(newline='') as f:rows=list(csv.reader(f,delimiter='\t'))
    require(rows[0]==['path','meta','name','excluded'] and len(rows)==len(i['nodes'])+1,'Complete typed inventory')
    for path,meta,name,flag in rows[1:]:
        require(path==meta==name and name in aliases and flag in ('0','1'),'Native typed attributes')
        n=aliases[name];require(n['name'] not in found,'Duplicate native alias')
        if stage not in ('selected','reloaded') or n['name'] not in targets:
            require(flag=='0','Protected PTE/tag/valid/ASID/control/port/array excluded')
        found[n['name']]=(path,meta,name)
    require(set(found)=={n['name'] for n in i['nodes']},'Complete complement')
    return found


def metrics(out,stage):
    with (out/('rooted_'+stage+'.csv')).open(newline='') as f:rows=list(csv.DictReader(f))
    require(len(rows)==2,'Two actual rooted metrics rows');result={}
    for row in rows:
        scope=row['Scope'];require(scope in SCOPES and scope not in result and row['Stage']==stage and
            row['Token']==scope and row['GUIPath']==row['Name']==scope.rsplit('.',1)[1] and row['Handle'].isdecimal(),
            'Exact rooted scope token/identity')
        require(set(row)=={'Stage','Scope','Token','Handle','GUIPath','Name','Score','Line','Toggle','FSM','Condition','Branch'},'Rooted schema')
        values={m:row[m] for m in ('Score','Line','Toggle','FSM','Condition','Branch')}
        for m,v in values.items():
            if v=='NA':require(m not in ('Score','Toggle'),'Available Score/Toggle');continue
            pct.percent(v)
        result[scope]=values
    return result


def contract(c):
    instances,induction,pins=proof()
    require(c['instances']==instances and c['induction']==induction and c['timeout_seconds']==900 and
            c['population_application'] is False,'Exact frozen proof/range')
    life.merge_pins(c['pins'],pins)


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins']);tools.revalidate(c['identity'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Tool terminal0 required')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('TLB726_NATIVE_DONE')==1 and not (out/'error.txt').exists(),'Complete native five stages')
    baseline=[inventory(out,c,'before',index) for index in range(2)];values={}
    for stage in STAGES:
        for index in range(2):require(inventory(out,c,stage,index)==baseline[index],'Typed inventory identity drift')
        text=(out/EL_FILES[stage]).read_text()
        if stage in ('selected','reloaded'):records(text,c)
        else:require(text=='','Global EL empty reset')
        values[stage]=metrics(out,stage)
    require(records((out/'first.el').read_text(),c)==records((out/'second.el').read_text(),c),'Exact global native reload')
    for scope in SCOPES:pct.compare_metrics({stage:values[stage][scope] for stage in STAGES})
    p=out/'qualification.json';pins={str(x):life.digest(x) for x in out.rglob('*') if x.is_file() and x!=p}
    result=dict(status='TLB_RVH0_EXACT726_LOCAL_NATIVE_QUALIFIED',config_seal=seal,objects=726,bits=4224,
        directions=8448,complement_objects=sum(len(i['nodes'])-363 for i in c['instances']),
        all_ports_arrays_controls_protected=True,per_bit_GUI_flags_read=False,metrics=values,
        startup_X_claim=False,population_application=False,official_percentage=None,pins=life.merge_pins(c['pins'],pins))
    if p.exists():require(json.loads(p.read_bytes())==result,'Existing qualification differs')
    else:life.save(p,result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(p))),flush=True)


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh local capture')
    instances,induction,pins=proof()
    old=life.read_bound(csr.ORIGIN/'config.json',csr.ORIGIN_SHA)
    life.check(old['pins']);tools.revalidate(old['identity']);pins=life.merge_pins(life.merge_pins(pins,old['pins']),{str(csr.ORIGIN/'config.json'):csr.ORIGIN_SHA})
    for p in (Path(__file__).resolve(),HOOK,HERE/'test_capture_tlb_rvh0_726.py',Path(csr.__file__),
              Path(pct.__file__),Path(native.__file__),Path(native.base.__file__),csr.ROOTED):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    c=dict(instances=instances,induction=induction,pins=pins,identity=old['identity'],output=str(out),
           timeout_seconds=900,automatic_retry=False,population_application=False)
    text=candidate(c);records(text,c)
    oldselection=(csr.ORIGIN/'selection.tcl').read_text()
    selected=oldselection+'set ::tlb_helper {%s}\n'%Path(__file__).resolve()
    selected+='set ::tlb_scopes [list '+' '.join('{'+s+'}' for s in SCOPES)+']\nset ::p740_scopes $::tlb_scopes\n'
    for s in SCOPES:selected+='set ::p740_root_names(%s) {%s}\n'%(s,s.rsplit('.',1)[1])
    out.mkdir()
    for name,data in [('selection.tcl',selected),('candidate.el',text),('source-proof.json',json.dumps(induction,indent=2)+'\n')]:
        with (out/name).open('x') as f:f.write(data)
        pins[str(out/name)]=life.digest(out/name)
    life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins),objects=726,bits=4224)),flush=True)


class Route:
    def __truediv__(self,name):
        require(name=='capture_cast168_native.tcl','Exact new capture hook');return HOOK


def run(out,seal):
    FunctionType(csr.original.base.runner.run.__code__,dict(vars(csr.original.base.runner),contract=contract,inspect=verify,HERE=Route()))(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify','inventory','el'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--stage',choices=STAGES);p.add_argument('--index',type=int)
    a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('inventory','el'):
        c=json.loads((out/'config.json').read_bytes());life.check(c['pins'])
        require(a.stage in STAGES,'Five-stage name')
        if a.mode=='inventory':require(a.index in (0,1),'Two scopes');print(len(inventory(out,c,a.stage,a.index)))
        else:
            text=(out/EL_FILES[a.stage]).read_text()
            if a.stage in ('selected','reloaded'):print(len(records(text,c)))
            else:require(text=='','Empty global native EL');print(0)
    else:require(a.seal,'Config seal');(run if a.mode=='run' else verify)(out,a.seal)
