"""Exact partial CSR bits, local native qualification only; never a population waiver."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
from types import FunctionType

import qualify_csr_pmp0_native765 as base

life, require, tools = base.life, base.require, base.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT/'csr-reserved-config-static-audit765-agent-20261007-01.json'
REVIEW_SHA = '4ba7d4526039dc97ee4456c614ae74c9de95ed9ad8fc5fe044375f660734415a'
STAGES = base.STAGES
HOOK = HERE/'capture_csr_reserved1193.tcl'
BOUNDARY = 'Valid reset and settled legal operation only; no startup-X, delta transient, arbitrary force or fault waiver.'


def source_check(texts, pins):
    # Full source seals cover EVERY assignment, including later overrides and generate guards.
    for path, text in texts.items():
        require(hashlib.sha256(text.encode()).hexdigest() == pins[path], 'Frozen writer/mask/config differs: '+path)
    csr = next(v for p,v in texts.items() if p.endswith('/csr_regfile.sv'))
    stems = r'(?:dcache|icache|acc_cons|medeleg|mideleg|mie|mip|mintstatus|mintthresh|mtvt|fcsr|mstatus)_[qd]'
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', csr, flags=re.S)
    writers = re.findall(r'\b('+stems+r'(?:\.[\w]+|\[[^\]]+\])*)\s*(<=|=(?!=))\s*([^;]+);', clean)
    require(writers, 'Complete writer corpus missing')
    return [list(w) for w in writers]


def expected_bits():
    result = {}
    def both(stem, bits):
        for suffix in ('q','d'): result[stem+'_'+suffix] = set(bits)
    for stem in ('dcache','icache','acc_cons'): both(stem, range(1,64))
    for stem, retained in [('medeleg',{0,1,2,3,4,5,6,7,8,12,13,15}),
                           ('mideleg',{1,5,9}),('mie',{1,3,5,7,9,11}),('mip',{1,3,5,7,9,11})]:
        both(stem, set(range(64))-retained)
    both('mtvt', range(64))
    for suffix in ('q','d'):
        for field in ('uil','sil','vsil','mil'): result['mintstatus_'+suffix+'.'+field] = set(range(8))
        result['mintthresh_'+suffix+'.th'] = set(range(8))
        result['fcsr_'+suffix+'.reserved'] = set(range(15,32))
        for field,bits in [('wpri0',{0}),('wpri1',{0}),('wpri2',{0}),('ube',{0}),
                           ('xs',{0,1}),('wpri3',set(range(9))),('uxl',{0}),('sxl',{0})]:
            result['mstatus_'+suffix+'.'+field] = bits
    result['mstatus_extended'] = {0,2,4,6,15,16,32,34}|set(range(23,32))
    result['vsstatus_extended'] = set(range(64))
    return result


def semantic_evidence(csr):
    clean=re.sub(r'/\*.*?\*/|//[^\n]*','',csr,flags=re.S)
    compact=re.sub(r'\s+','',clean)
    guards=[]
    for feature,field,source in [('RVXHCLIC','vsil','ex_i.cause'),('RVSCLIC','sil','ex_i.cause'),
                                 ('RVSCLIC','mil','ex_i.cause'),('RVSCLIC','mil','mcause_q'),
                                 ('RVSCLIC','sil','scause_q'),('RVXHCLIC','vsil','vscause_q')]:
        condition='CVA6Cfg.%s&&clic_mode_o&&%s[CVA6Cfg.XLEN-1]'%(feature,source)
        token='if('+condition+')'+('begin' if source=='ex_i.cause' else '')+'mintstatus_d.%s=%s[23:16];'%(field,source)
        require(compact.count(token)==1,'Exact trap/return CLIC guard differs')
        guards.append(dict(lhs='mintstatus_d.'+field,rhs=source+'[23:16]',condition=condition,enabled=False))
    for case,lhs,rhs in [('MTVT','mtvt_d',"{csr_wdata[CVA6Cfg.XLEN-1:8],8'b0}"),
                         ('MINTTHRESH','mintthresh_d.th','csr_wdata[7:0]')]:
        token='riscv::CSR_%s:beginif(CVA6Cfg.RVSCLIC)beginif(clic_mode_o)begin%s=%s;'%(case,lhs,rhs)
        require(token in compact,'Exact CSR CLIC guard differs')
        guards.append(dict(lhs=lhs,rhs=rhs,condition='RVSCLIC && clic_mode_o',enabled=False))
    clic_writers=re.findall(r'\b((?:mintstatus|mintthresh|mtvt)_[qd](?:\.\w+)?)\s*(<=|=(?!=))\s*([^;]+);',clean)
    require(len(clic_writers)==17,'Complete CLIC default/reset/capture/eight modification writers')
    require("assignclic_mode_o=1'b0;" in compact,'Configured-off CLIC mode')
    for enum,rhs in [('IRQ_M_EXT','irq_i[0]'),('IRQ_M_SOFT','CVA6Cfg.SoftwareInterruptEn&&ipi_i'),
                     ('IRQ_M_TIMER','time_irq_i')]:
        require('mip_d[riscv::%s]=%s;'%(enum,rhs) in compact,'External interrupt override missing')
    require('mstatus_d.sxl=riscv::XLEN_64;' in compact and 'mstatus_d.uxl=riscv::XLEN_64;' in compact,
            'XLEN64 forced size fields')
    explanations={
        'single_enable_upper63':'q resets zero; d holds q except one-bit CSR writes with zero extension; q captures d. Bit0 remains writable and protected.',
        'interrupt_delegation_reserved':'Zero reset, default hold and masked CSR write induction. MEDELEG retains 0..8/12/13/15; MIDELEG 1/5/9; MIE and MIP retain 1/3/5/7/9/11. MIP software writes 1/5/9 and external overrides 3/7/11 are all protected; supervisor masked writes remain within these sets; hypervisor alternative writers disabled by RVH0.',
        'clic_disabled_initialized':'All three q objects reset unconditionally zero and capture d. Three d defaults hold q; every one of eight non-hold writers is guarded as enumerated. No uil writer exists. RVSCLIC/RVXHCLIC0 and generated clic_mode_o0 make each modification inactive; reset/capture still active.',
        'fcsr_reserved':'q reset0/default hold/capture; FFLAGS writes and exception/accelerator updates touch 4:0, FRM 7:5, FCSR only7:0, FPREC14:8. Reserved31:15 never modified; fprec/frm/fflags all protected.',
        'mstatus_cleared_reserved':'q reset0/default hold/capture; full MSTATUS write clears XS/WPRI0/1/2/3/UBE after bulk assignment; SSTATUS masked merge omits these bits. All trap/return/dirty writers target other fields. XLEN64 assigns SXL/UXL=10 each settled evaluation: only bit0 excluded, bit1 protected including its reset transition. WPRI4 writable and protected.',
        'mstatus_read_alias':'RV64 direct alias mstatus_extended=mstatus_q; mapping is architectural bit numbers, not struct-local offsets. Only proven WPRI0/1/2/3,UBE,XS and low SXL/UXL bits selected.',
        'rvh_disabled_constant_mux':'Explicit RVH false generate assigns vsstatus_extended zero. Not a claim that uninitialized vsstatus_q/d are constants; both HOLD and retained.'}
    # Entire relevant source spans include masks, generate/config gating, all later overrides and reset/capture.
    spans=[(236,369),(1050,1112),(1240,1500),(1550,1750),(1848,1867),(1960,2035),
           (2078,2158),(2348,2420),(2800,3005)]
    lines=csr.splitlines()
    return dict(boundary=BOUNDARY,induction=explanations,all_CLIC_modification_guards=guards,
                CLIC_writer_count=17,MIP_external_overrides_protected=[3,7,11],
                MIP_all_retained_bits=[1,3,5,7,9,11],
                source_excerpts=[dict(first=a,last=b,text='\n'.join(lines[a-1:b])) for a,b in spans],
                proof_kind='Source induction and exact compiled/config binding; SHA locks reviewed semantics, not an independent semantic argument.')


def proof():
    a = life.read_bound(REVIEW, REVIEW_SHA); life.check(a['input_pins'])
    require(a['config'] == dict(XLEN=64,RVH=0,RVZCMT=0,RVSCLIC=0,RVXHCLIC=0,
                               DebugEn=1,RVS=1,RVU=1,RVV=1,FpPresent=1), 'Frozen feature configuration')
    targets = [t for group in a['source_groups'].values() for t in group]
    require({t['signal']:set(t['source_bits']) for t in targets} == expected_bits(), 'Exact reviewed bits; no HOLD expansion')
    require(len(targets)==46 and sum(len(t['source_bits']) for t in targets)==1193, 'Exact capacity')
    book_path = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    require(a['input_pins'][str(book_path)] == '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b', 'Build authority')
    book = life.read_bound(book_path,a['input_pins'][str(book_path)])
    texts = {}
    for p,sha in a['input_pins'].items():
        if p.endswith('.sv'):
            require(book[p]==sha, 'Frozen build/source agreement')
            texts[p] = Path(p).read_text()
    writers = source_check(texts,a['input_pins'])
    semantic_evidence(next(v for p,v in texts.items() if p.endswith('/csr_regfile.sv')))
    paths = {Path(p).name:Path(p) for p in a['input_pins'] if p.endswith(('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml'))}
    _,defs = base.source.native.definitions(*(base.source.native.xml(paths[n]) for n in
        ('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml')),[a['scope']])
    definition = defs[a['scope']]
    require(definition['module']==a['compiled_module'], 'Compiled module identity')
    root = base.source.native.base.ET.fromstring(definition['shape'])
    nodes = [dict(kind=n.tag,**n.attrib) for n in root.iter() if n.tag in ('node','vectornode','arrays')]
    require(len(nodes)==2077 and len({n['name'] for n in nodes})==2077, 'Complete typed CSR inventory')
    byname = {n['name']:n for n in nodes}
    for t in targets:
        n=byname[t['signal']]
        require({k:v for k,v in n.items() if k!='kind'}==t['compiled_attributes'] and n['portnode']=='0' and
                n['kind'] in ('node','vectornode'), 'Exact internal source-bound typed target')
        full = {0} if n['kind']=='node' else set(range(int(n['right']),int(n['left'])+1))
        require(set(t['source_bits'])|set(t['retained_source_bits'])==full and
                not set(t['source_bits'])&set(t['retained_source_bits']), 'Exact retained bit complement')
    return a,targets,nodes,writers


def declaration(n):
    return n['name']+base.bounds(n)


def candidate(c):
    lines=['CHECKSUM: "1371260681 1176918775"','INSTANCE: '+c['scope'],'ANNOTATION: "'+BOUNDARY+'"']
    nodes={n['name']:n for n in c['nodes']}
    for t in c['targets']:
        n=nodes[t['signal']]
        for bit in t['source_bits']:
            selector='' if n['kind']=='node' else ' [%d]'%bit
            lines.append('Toggle '+n['name']+selector+' "logic '+declaration(n)+'"')
    return '\n'.join(lines)+'\n'


def records(text,c):
    nodes={n['name']:n for n in c['nodes']}; found=set(); scope=check=None; blocks=0
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('ANNOTATION:'):
            require(line=='ANNOTATION: "'+BOUNDARY+'"','Exact boundary annotation');continue
        if line.startswith('CHECKSUM:'):
            require(line=='CHECKSUM: "1371260681 1176918775"','Exact checksum');check=True;scope=None;continue
        if line.startswith('INSTANCE:'):
            require(check and line=='INSTANCE: '+c['scope'] and blocks==0,'Exact sole scope')
            scope=c['scope'];blocks+=1;continue
        m=re.fullmatch(r'Toggle (?:(0to1|1to0) )?([^\s"]+)(?: \[(\d+)(?::(\d+))?\])? "logic ([^"\r\n]+)"',line)
        require(scope and m is not None,'Only exact typed partial Toggle directives: '+line)
        direction,name,left,right,meta=m.groups(); require(name in nodes,'Foreign object')
        n=nodes[name]; require(meta==declaration(n),'Exact full declaration')
        full={0} if n['kind']=='node' else set(range(int(n['right']),int(n['left'])+1)) if n['kind']=='vectornode' else set()
        bits=full if left is None else set(range(int(right or left),int(left)+1))
        require(bits and bits<=full,'Nonempty in-range bits')
        for bit in bits:
            for d in (('0to1','1to0') if direction is None else (direction,)):
                key=(name,bit,d);require(key not in found,'Duplicate/mixed direction or bit');found.add(key)
    wanted={(t['signal'],b,d) for t in c['targets'] for b in t['source_bits'] for d in ('0to1','1to0')}
    require(blocks==1 and found==wanted and len(found)==2386,'Exact1193 both directions; protected bits preserved')
    return sorted(found)


def contract(c):
    a,targets,nodes,writers=proof()
    require(c['scope']==a['scope'] and c['targets']==targets and c['nodes']==nodes and c['writers']==writers and
            c['timeout_seconds']==900 and c['population_application'] is False,'Frozen exact source/compiled contract')


def check_inventory(out,c,stage):
    nodes={alias:n for n in c['nodes'] for alias in base.aliases(n)}
    with (out/('objects-'+stage+'.tsv')).open(newline='') as f: rows=list(csv.reader(f,delimiter='\t'))
    require(rows[0]==['path','meta','name','excluded'] and len(rows[1:])==2077,'Full object schema/count')
    require(len({r[0] for r in rows[1:]})==2077,'Unique full paths')
    targetnames={t['signal'] for t in c['targets']}
    bound=set()
    for path,meta,name,excluded in rows[1:]:
        require(name in nodes and path==name and meta==name and excluded in ('0','1'),'Exact object attributes')
        require(nodes[name]['name'] not in bound,'Duplicate compiled object alias')
        bound.add(nodes[name]['name'])
        if stage not in ('selected','reloaded') or nodes[name]['name'] not in targetnames:
            require(excluded=='0','Non-target object excluded')
    require(bound=={n['name'] for n in c['nodes']},'Complete compiled object complement')
    with (out/('bits-'+stage+'.tsv')).open(newline='') as f: rows=list(csv.reader(f,delimiter='\t'))
    require(rows[0]==['signal','bit','path','meta','name','0to1','1to0'],'Bit attribute schema')
    found={}; bysignal={t['signal']:t for t in c['targets']}
    for signal,b,path,meta,name,rise,fall in rows[1:]:
        require(signal in bysignal and b.isdecimal(),'Reviewed bit identity')
        bit=int(b);n=next(n for n in c['nodes'] if n['name']==signal)
        expected=signal if n['kind']=='node' else signal+'[%d]'%bit
        require(path==name==meta==expected and rise in ('0','1') and fall in ('0','1'),'Native bit attributes')
        require((signal,bit) not in found,'Duplicate bit')
        want=str(int(stage in ('selected','reloaded') and bit in bysignal[signal]['source_bits']))
        require(rise==fall==want,'Target/non-target direction attribute differs')
        found[signal,bit]=True
    wanted={(t['signal'],b) for t in c['targets'] for b in t['source_bits']+t['retained_source_bits']}
    require(set(found)==wanted,'Full target objects bit complement missing')
    return len(found)


def inspect(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Live tool/terminal')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('CSR1193_NATIVE_DONE')==1 and not (out/'error.txt').exists(),'Complete five-stage session')
    for stage in STAGES:check_inventory(out,c,stage)
    require(records((out/'first.el').read_text(),c)==records((out/'second.el').read_text(),c),'Exact semantic roundtrip')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes()==b'','Global empty exclusions')
    pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='capture-result.json'})
    result=dict(status='CSR46_PARTIAL1193_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED',objects=46,source_bits=1193,
                directions=2386,all_other_CSR_objects_arrays_ports_retained=True,
                target_bit_complements_verified=True,boundary=BOUNDARY,config_seal=seal,pins=pins,
                population_application=False,official_percentage=None)
    dest=out/'capture-result.json'
    if dest.exists():require(json.loads(dest.read_bytes())==result,'Existing result differs')
    else:life.save(dest,result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(dest))),flush=True)


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh isolated output')
    a,targets,nodes,writers=proof()
    origin=life.OUT/'csr-pmp0-internal770-native765-agent-20261007-01/config.json'
    inherited=json.loads(origin.read_bytes());life.check(inherited['pins']);tools.revalidate(inherited['identity'])
    selection=(origin.parent/'selection.tcl').read_text()
    values={m[0]:m[1] for m in re.findall(r'^set (fma_design|fma_vdb|fma_test) \{([^{}\n]+)\}$',selection,re.M)}
    require(len(values)==3 and values['fma_design']==str(life.IMAGE)+'.vdb','Existing one-test native binding')
    pins=life.merge_pins(life.merge_pins(a['input_pins'],inherited['pins']),
                         {str(REVIEW):REVIEW_SHA,str(origin):life.digest(origin)})
    for p in (Path(__file__).resolve(),HOOK,HERE/'test_capture_csr_reserved1193.py',Path(base.__file__),Path(base.runner.__file__),
              Path(base.source.__file__),Path(base.source.native.__file__),Path(base.source.native.base.__file__)):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    c=dict(scope=a['scope'],targets=targets,nodes=nodes,writers=writers,identity=inherited['identity'],pins=pins,
           timeout_seconds=900,population_application=False,automatic_retry=False,output=str(out),boundary=BOUNDARY)
    contract(c);out.mkdir()
    csr_path=next(p for p in a['input_pins'] if p.endswith('/csr_regfile.sv'))
    life.save(out/'writer-proof.json',dict(writers=writers,config=a['config'],boundary=BOUNDARY,source_review_sha=REVIEW_SHA,
        semantic_evidence=semantic_evidence(Path(csr_path).read_text()),source_pins={p:sha for p,sha in a['input_pins'].items() if p.endswith('.sv')}))
    text=['set ::%s {%s}\n'%pair for pair in values.items()]
    text+=['set ::csr_scope {%s}\n'%c['scope'], 'set ::csr_targets {}\n']
    byname={n['name']:n for n in nodes}
    for t in targets:
        n=byname[t['signal']];text.append('lappend ::csr_targets [list {%s} {%s} {%s}]\n'%(t['signal'],declaration(n),n['kind']))
    text+=['set ::csr_python {%s}\n'%str(life.ROOT/'verification/tools/soc-venv/bin/python'),
           'set ::csr_helper {%s}\n'%str(Path(__file__).resolve())]
    for name,body in [('selection.tcl',''.join(text)),('candidate.el',candidate(c))]:
        # Exclusive creation; the generated EL has been strictly checked before DVE.
        if name=='candidate.el':records(body,c)
        with (out/name).open('x') as f:f.write(body)
        pins[str(out/name)]=life.digest(out/name)
    pins[str(out/'writer-proof.json')]=life.digest(out/'writer-proof.json')
    life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


class Route:
    def __truediv__(self,name):
        require(name=='capture_cast168_native.tcl','Fixed session entry');return HOOK


def run(out,seal):
    FunctionType(base.runner.run.__code__,dict(vars(base.runner),contract=contract,inspect=inspect,HERE=Route()))(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','inspect','el','inventory'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file');p.add_argument('--stage',choices=STAGES)
    args=p.parse_args();out=args.output.absolute()
    if args.mode=='prepare':prepare(out)
    elif args.mode in ('el','inventory'):
        c=json.loads((out/'config.json').read_bytes());life.check(c['pins'])
        print(len(records((out/args.file).read_text(),c)) if args.mode=='el' else check_inventory(out,c,args.stage))
    else:
        require(args.seal,'Config seal');(run if args.mode=='run' else inspect)(out,args.seal)
