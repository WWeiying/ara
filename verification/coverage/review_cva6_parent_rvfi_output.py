"""Exact observation-only core output leaves; no core/module/functional waiver."""
import argparse
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import re
import review_srt_radix16_child_residual as frozen

ROOT,OUT,BUILD,DB=frozen.ROOT,frozen.OUT,frozen.BUILD,frozen.DB
SCOPE='ara_tb.dut.i_ara_soc.i_system.i_ariane'
CORE=ROOT/'hardware/deps/cva6/core/cva6.sv'
PRODUCER=ROOT/'hardware/deps/cva6/core/cva6_rvfi_probes.sv'
SYSTEM=ROOT/'hardware/src/ara_system.sv'
TYPES=ROOT/'hardware/deps/cva6/core/include/rvfi_types.svh'
RISCV=ROOT/'hardware/deps/cva6/core/include/riscv_pkg.sv'
SOURCE_SHA='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
CHECKSUM='1939539040'
DESIGN_CHECKSUM='376119937'
need=frozen.need


def clean(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"',
                  lambda m:''.join('\n' if x=='\n' else ' ' for x in m.group()),text,flags=re.S)


def count(text,name):return len(re.findall(r'\b'+re.escape(name)+r'\b',clean(text)))


def guards(text):
    stack=[];result=[]
    for line in clean(text).splitlines():
        match=re.match(r'\s*`(ifdef|ifndef|else|elsif|endif)\b\s*(\w*)',line)
        if match:
            directive,macro=match.groups()
            if directive in ('ifdef','ifndef'):stack.append((macro,directive=='ifdef'))
            elif directive=='else':
                need(stack,'Unmatched else');stack[-1]=(stack[-1][0],not stack[-1][1])
            elif directive=='elsif':
                need(stack,'Unmatched elsif');stack[-1]=(macro,True)
            else:need(stack,'Unmatched endif');stack.pop()
        result.append(list(stack))
    need(not stack,'Unbalanced conditional source')
    return result


def balanced(text,start):
    need(text[start]=='(','Expected opening parenthesis')
    depth=0
    for index in range(start,len(text)):
        if text[index]=='(':depth+=1
        elif text[index]==')':
            depth-=1
            if depth==0:return index
    raise ValueError('Unbalanced named connection')


def connections(text,instance):
    text=clean(text)
    matches=list(re.finditer(r'\)\s*'+re.escape(instance)+r'\s*\(',text))
    need(len(matches)==1,'Missing/duplicate exact instance: '+instance)
    start=matches[0].end()-1;end=balanced(text,start)
    body=text[start+1:end]
    need(not re.search(r'\.\s*\*',body),'Implicit wildcard fanout not qualified')
    result=[]
    for m in re.finditer(r'\.([A-Za-z_]\w*)\s*\(',body):
        begin=start+1+m.end()-1;finish=balanced(text,begin)
        result.append(dict(port=m.group(1),net=text[begin+1:finish].strip(),
            line=text.count('\n',0,begin)+1))
    return result


def source_contract(core,producer,system):
    c,p,s=map(clean,(core,producer,system))
    need(count(core,'rvfi_probes_o')==3 and count(producer,'rvfi_probes_o')==6 and
         count(system,'rvfi_probes_o')==2 and count(system,'rvfi_probes')==3,
         'Additional read/write/fanout of observation output')
    need(re.search(r'output\s+rvfi_probes_t\s+rvfi_probes_o\s*,',c),'Not output-only typed core port')
    links=connections(core,'i_cva6_rvfi_probes')
    need([x['net'] for x in links if x['port']=='rvfi_probes_o']==['rvfi_probes_o'],
         'Producer->core output connection differs')
    need(len(re.findall(r'\boutput\b',p))==1 and not re.search(r'\b(?:inout|ref)\b',p) and
         re.search(r'output\s+rvfi_probes_t\s+rvfi_probes_o\s*\)',p),
         'Producer has functional output/ref side effects')
    for fragment in (r"rvfi_probes_o\s*=\s*'0\s*;",
                     r'\$bits\(rvfi_probes_o\.instr\)\s*==\s*\$bits\(instr\)',
                     r'\$bits\(rvfi_probes_o\.csr\)\s*==\s*\$bits\(csr\)',
                     r'rvfi_probes_o\.instr\s*=\s*instr\s*;',
                     r'rvfi_probes_o\.csr\s*=\s*csr\s*;'):
        need(re.search(fragment,p),'Producer observation assignment changed')
    parent=connections(system,'i_ariane');consumer=connections(system,'i_cva6_rvfi')
    output=[x for x in parent if x['port']=='rvfi_probes_o']
    use=[x for x in consumer if x['port']=='rvfi_probes_i']
    need(len(output)==2 and [x['net'] for x in output]==['rvfi_probes',''] and
         len(use)==1 and use[0]['net']=='rvfi_probes','Wrong/non-observer consumer')
    contexts=guards(system)
    need(('FOR_VERIFY',True) in map(tuple,contexts[output[0]['line']-1]) and
         ('FOR_VERIFY',False) in map(tuple,contexts[output[1]['line']-1]) and
         ('FOR_VERIFY',True) in map(tuple,contexts[use[0]['line']-1]),
         'FOR_VERIFY producer/consumer guards differ')
    declarations=[i for i,line in enumerate(s.splitlines()) if re.search(r'\brvfi_probes_t\s+rvfi_probes\s*;',line)]
    need(len(declarations)==1 and ('FOR_VERIFY',True) in map(tuple,contexts[declarations[0]]),
         'Observer net type/declaration not guarded')
    for typ,macro in (('rvfi_probes_instr_t','RVFI_PROBES_INSTR_T'),('rvfi_probes_csr_t','RVFI_PROBES_CSR_T')):
        m=re.search(r'localparam\s+type\s+'+typ+r'\s*=\s*`'+macro+r'\(CVA6Cfg\)\s*;',s)
        need(m and ('FOR_VERIFY',True) in map(tuple,contexts[s.count('\n',0,m.start())]),
             'FOR_VERIFY expanded struct type not bound')
        need(len(re.findall(r'\.\s*'+typ+r'\s*\(\s*'+typ+r'\s*\)',s))==2,
             'Core/observer concrete type associations differ')
    for name,total in (('rvfi_instr',3),('rvfi_csr',2),('rvfi_to_iti',2)):
        need(count(system,name)==total,'Observer downstream functional fanout: '+name)
    need(any(x['port']=='rvfi_instr_o' and x['net']=='rvfi_instr' for x in consumer) and
         any(x['port']=='rvfi_instr_i' and x['net']=='rvfi_instr' for x in connections(system,'i_ara_commit_monitor')),
         'RVFI consumer no longer feeds pure commit monitor')
    return dict(producer='i_ariane.i_cva6_rvfi_probes.rvfi_probes_o',
        core_output=SCOPE+'.rvfi_probes_o',integration_net='i_system.rvfi_probes',
        only_consumer='i_system.i_cva6_rvfi.rvfi_probes_i',
        downstream='i_system.i_ara_commit_monitor.rvfi_instr_i; csr/to_iti outputs unused',
        core_output_runtime_reads=0,hardware_feedback=False,
        producer_core_instance_unconditionally_declared=True,
        FOR_VERIFY_guard_applies_to='Concrete packed types and system observer wiring; not entire CVA6 producer',
        non_FOR_VERIFY_core_output_connection='open',portnode3_exception='Exact observer-only output leaves, not generic functional outputs',
        monitor_assertions_trace_tohost_and_finish_unchanged=True)


def selected(name):return re.match(r'^rvfi_probes_o\.(?:instr|csr)\.',name) is not None


def scope_identity(scope,design_checksum,toggle_checksum):
    need((scope,design_checksum,toggle_checksum)==(SCOPE,DESIGN_CHECKSUM,CHECKSUM),
         'Only exact core-parent output scope is authorized')


def shape_identity(definition):
    return tuple((n.tag,json.dumps(n.attrib,sort_keys=True)) for n in definition.find('tglshape'))


@lru_cache(maxsize=1)
def frozen_shape_identity():
    path=DB/'shape/tgl.verilog.shape.xml'
    need(frozen.digest(path)=='243ae4d4d29b7ee2190ef35a39482f7287c78a260128315b666d500e90f18ae7',
         'Frozen target/complement shape pin mismatch')
    definitions=[n for n in frozen.xml(path).iter('tgldef') if n.get('name')=='cva6']
    need(len(definitions)==1,'Ambiguous frozen core shape')
    return shape_identity(definitions[0])


def partition(definition,width):
    need(definition.get('name')=='cva6' and definition.get('chksum')==CHECKSUM,'Wrong compiled core definition')
    need(shape_identity(definition)==frozen_shape_identity(),
         'Exact full target/complement name/type/source/port/bounds identity differs')
    targets=[];protected=[];offset=0
    names=set()
    for n in definition.find('tglshape'):
        need(n.get('name') not in names,'Duplicate compiled identity');names.add(n.get('name'))
        need(n.tag in ('node','vectornode','arrays'),'Unknown shape kind')
        size=None if n.tag=='arrays' else 1 if n.tag=='node' else abs(int(n.get('left'))-int(n.get('right')))+1
        record=dict(kind=n.tag,attributes=dict(n.attrib),width=size,raw_offset=None if size is None else offset)
        if selected(n.get('name')) and size is not None:
            need(n.get('aux_file')=='419' and n.get('aux_line_num')=='343' and
                 n.get('file') in ('595','402') and n.get('portnode')=='3' and
                 n.get('excluded')=='0' and n.get('type')=='1','Not exact observation output identity')
            if n.get('file')=='595':need(n.get('line_num') in ('108','109'),'Wrong packed macro type binding')
            record.update(compiled_name=n.get('name'),compiled_label=n.get('name')+
                ('[%s:%s]'%(n.get('left'),n.get('right')) if n.tag=='vectornode' else ''),
                native_label_and_type_require_actual_capture=True)
            targets.append(record)
        else:
            record['protection_reason']='ALL_ARRAY_INTERVAL_OBJECTS' if size is None else 'ALL_NON_OUTPUT_PROBE_CORE_OBJECTS'
            if n.tag=='arrays':record['complete_shape_xml']=__import__('xml.etree.ElementTree',fromlist=['tostring']).tostring(n,encoding='unicode')
            protected.append(record)
        if size is not None:offset+=2*size
    need(offset==width==38866 and len(targets)==457 and sum(n['width'] for n in targets)==2599 and
         len(protected)==1315 and sum(n['kind']=='arrays' for n in protected)==31,
         'Exact target/full complement/bitmap width differs')
    return targets,protected


def macro_fields(text,macro):
    match=re.search(r'`define\s+'+macro+r'\(Cfg\)\s+struct\s+packed\s*\{(.*?)\n\}',text,re.S)
    need(match,'Missing exact RVFI type macro')
    fields={}
    for offset,line in enumerate(match.group(1).splitlines()):
        m=re.fullmatch(r'\s*(.+?)\s+(\w+)\s*;\s*\\?\s*',line)
        if m:
            fields[m.group(2)]=dict(source_type_expression=m.group(1),declaration=line,
                line=text.count('\n',0,match.start(1))+offset+1)
    return fields


def bind_types(targets,files):
    text=TYPES.read_text();types={group:macro_fields(text,'RVFI_PROBES_'+group.upper()+'_T') for group in ('instr','csr')}
    result=[]
    for t in targets:
        a=t['attributes'];path=a['name'];m=re.fullmatch(r'rvfi_probes_o\.(instr|csr)\.(\w+)(.*)',path)
        need(m,'Invalid root member');group,member,suffix=m.groups()
        need(member in types[group],'Unknown RVFI type member')
        declaration=files[a['file']].read_text().splitlines()[int(a['line_num'])-1]
        if a['file']=='402':
            leaf=path.rsplit('.',1)[-1]
            need(re.search(r'\b'+re.escape(leaf)+r'\s*;',clean(declaration)),'Nested source leaf not bound')
        else:need('rvfi_probes_'+group+'_t' in declaration,'Macro source line differs')
        result.append(dict(t,source_binding=dict(root_port_file=str(CORE),root_port_line=343,
            root_port_declaration=CORE.read_text().splitlines()[342],
            macro_source=str(TYPES),macro='RVFI_PROBES_'+group.upper()+'_T',
            root_member=member,root_member_declaration=types[group][member],nested_path=suffix,
            compiled_leaf_file=str(files[a['file']]),compiled_leaf_source_line=int(a['line_num']),
            compiled_leaf_source_declaration=declaration,
            scalar_or_vector=t['kind'],compiled_type_code=a['type'],compiled_output_port_code=a['portnode'],
            complete_compiled_bounds=[int(a['left']),int(a['right'])] if t['kind']=='vectornode' else [],
            source_and_compiled_ranges_not_blindly_canonicalized=True,
            actual_native_qualifiers_pending=True)))
    return result


def collect():
    scope_identity(SCOPE,DESIGN_CHECKSUM,CHECKSUM)
    pins={}
    def pin(path,sha=None):
        value=frozen.digest(path);need(sha is None or value==sha,'Pin drift: '+str(path));pins[str(path)]=value
    bookpath=BUILD/'build-source-pins.json';book=frozen.load(bookpath,SOURCE_SHA);pin(bookpath)
    pin(BUILD/'sim/simv','2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3')
    recovered={'hardware/src/ara_dispatcher.sv':'ara_dispatcher.sv',
        'hardware/src/lane/lane_sequencer.sv':'lane_sequencer.sv','hardware/src/sldu/sldu.sv':'sldu.sv'}
    texts={};scan=[];references=[]
    for original,sha in book.items():
        path=Path(original)
        if path.suffix not in ('.v','.vh','.sv','.svh'):continue
        if frozen.digest(path)!=sha:
            rel=str(path.relative_to(ROOT));need(rel in recovered,'Unrecovered frozen HDL source')
            path=OUT/'old-image-source-evidence-20261006-01'/recovered[rel]
        pin(path,sha);text=path.read_text();texts[original]=text
        scan.append(dict(original=original,actual_frozen_source=str(path),sha256=sha))
        hits=count(text,'rvfi_probes_o')
        if hits:references.append(dict(file=original,count=hits))
    need({n['file']:n['count'] for n in references}=={str(CORE):3,str(PRODUCER):6,str(SYSTEM):2},
         'Cross-module output reference/fanout changed')
    contract=source_contract(texts[str(CORE)],texts[str(PRODUCER)],texts[str(SYSTEM)])
    for p,sha in ((DB/'design/verilog.design.xml','6ba9f4af477f14793ca1967e7d9aa3fc8274864d897dee88de267597cd3be3be'),
        (DB/'shape/tgl.verilog.info.xml','5603b64b35df34925586b68ba6bf429c7e92836b239c94e9c193c666e3d70b0a'),
        (DB/'shape/tgl.verilog.shape.xml','243ae4d4d29b7ee2190ef35a39482f7287c78a260128315b666d500e90f18ae7')):pin(p,sha)
    sourceinfo=DB/'auxiliary/verilog.sourceinfo.xml';pin(sourceinfo)
    files={n.get('id'):Path(n.get('name')) for n in frozen.xml(sourceinfo).iter('fileinfo')}
    need(files['419']==CORE and files['595']==SYSTEM and files['402']==RISCV,'Compiled source ID differs')
    design=frozen.xml(DB/'design/verilog.design.xml')
    nodes={n.get('id'):n for n in design.iter('srcinst')}
    owners={n.get('id'):d for d in design.iter('srcdef') for n in d.findall('srcinst')}
    def scope(n):
        parent=nodes.get(n.get('pid'));return (scope(parent)+'.' if parent is not None else '')+n.get('name')
    compiled={scope(n):n for n in nodes.values()}
    need(SCOPE in compiled and owners[compiled[SCOPE].get('id')].get('name')=='cva6' and
         owners[compiled[SCOPE].get('id')].get('chksum')==DESIGN_CHECKSUM,'Compiled core coordinate differs')
    chain={SCOPE+'.i_cva6_rvfi_probes':('cva6_rvfi_probes','1089031276'),
        SCOPE.rsplit('.',1)[0]+'.i_cva6_rvfi':('cva6_rvfi','3460467670'),
        SCOPE.rsplit('.',1)[0]+'.i_ara_commit_monitor':('ara_commit_monitor','182875116')}
    for s,(module,checksum) in chain.items():
        need(s in compiled and owners[compiled[s].get('id')].get('name')==module and
             owners[compiled[s].get('id')].get('chksum')==checksum,'Compiled observer chain differs')
    info=frozen.xml(DB/'shape/tgl.verilog.info.xml')
    need([n.get('chksum') for n in info.iter('instance_data') if n.get('name')==SCOPE]==[CHECKSUM],
         'Exact core Toggle identity differs')
    defs=[d for d in frozen.xml(DB/'shape/tgl.verilog.shape.xml').iter('tgldef') if d.get('name')=='cva6']
    need(len(defs)==1 and 'rvfi_probes_t=anonymous_type_24' in defs[0].get('param',''),
         'Not compiled FOR_VERIFY expanded probe struct')
    targets,protected=partition(defs[0],38866);targets=bind_types(targets,files)
    cache=frozen.load(frozen.CACHE,frozen.CACHE_SHA);pin(frozen.CACHE,frozen.CACHE_SHA)
    row=cache['instances'][SCOPE]
    need(row['width']==38866 and row['checksum']==CHECKSUM and cache['tests']==741,'Wrong raw741 native identity')
    value=int(row['bits'],16);raw741=value
    manifest=frozen.load(frozen.BASE/'admission-manifest.json',
        '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5');pin(frozen.BASE/'admission-manifest.json')
    inputpath=frozen.BASE/'combined-inputs.txt';pin(inputpath,manifest['output_pins'][str(inputpath)])
    inputs=inputpath.read_text().splitlines()
    oldpath=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'));pin(oldpath,cache['input_pins'][str(oldpath)])
    need(len(inputs)==len(set(inputs))==763 and inputs[:742]==oldpath.read_text().splitlines(),'741-prefix/762 ledger differs')
    def overlay(vdb,authority):
        paths=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(paths)==1 and str(paths[0]) in authority,'Unbound native suffix')
        pin(paths[0],authority[str(paths[0])]);hits=[n for n in frozen.xml(paths[0]).iter('instance_data') if n.get('name')==SCOPE]
        need(len(hits)==1 and hits[0].get('chksum')==CHECKSUM and len(hits[0].get('value'))==38866 and
             set(hits[0].get('value'))<={'0','1'},'Suffix exact compiled core shape differs')
        return int(hits[0].get('value'),2)
    for vdb in inputs[742:]:value|=overlay(vdb,manifest['input_pins'])
    raw762=value
    newer=OUT/'operand-mask-data-defined-policy-admitted763-agent-20261007-01'
    admitted=frozen.load(newer/'admission-manifest.json','962d7292ff80e5fffe4fd8e8e8de00938c32dca3a92d21e179b8cf59f915200c')
    pin(newer/'admission-manifest.json');newledger=newer/'combined-inputs.txt';pin(newledger,admitted['output_pins'][str(newledger)])
    successor=newledger.read_text().splitlines();need(successor[:-1]==inputs,'Not exact763 successor')
    value|=overlay(successor[-1],admitted['input_pins'])
    for t in targets:
        coordinate=dict(raw_offset=t['raw_offset'],width=t['width'])
        t['missing_raw741']=frozen.direction_missing(raw741,38866,coordinate)
        t['missing_formal762']=frozen.direction_missing(raw762,38866,coordinate)
        t['missing_admitted763']=frozen.direction_missing(value,38866,coordinate)
    # Supplemental build-filelist observation, corroborated by compiled concrete types.
    flist=BUILD/'build/vcs/bender_script_default';pin(flist)
    need('+define+FOR_VERIFY' in flist.read_text().splitlines(),'Current frozen build filelist lacks FOR_VERIFY')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_review_cva6_parent_rvfi_output.py'),Path(frozen.__file__)):
        pin(p)
    for path,sha in pins.items():need(frozen.digest(path)==sha,'Evidence changed during review')
    return dict(status='CVA6_PARENT_OUTPUT_RVFI457_SOURCE_BOUND_OBSERVATION_CANDIDATES_NOT_NATIVE_QUALIFIED',
        scope=SCOPE,module='cva6',design_checksum=DESIGN_CHECKSUM,toggle_checksum=CHECKSUM,
        compiled_instance=dict(compiled[SCOPE].attrib),compiled_parameters=defs[0].get('param'),
        source_contract=contract,frozen_HDL_scan_count=len(scan),source_scan=scan,exact_output_reference_files=references,
        compiled_observer_chain=[dict(scope=s,module=m,design_checksum=c) for s,(m,c) in chain.items()],
        source_candidate_objects=457,scalar_objects=276,vector_objects=181,logical_bits=2599,
        serialized_capacity=5198,raw741_parent_width=38866,raw741_parent_missing=38866-bin(raw741).count('1'),
        raw741_candidate_missing=sum(t['missing_raw741']['total'] for t in targets),
        formal762_candidate_missing=sum(t['missing_formal762']['total'] for t in targets),
        admitted763_candidate_missing=sum(t['missing_admitted763']['total'] for t in targets),
        protected_local_objects=1315,protected_scalar_vector_objects=1284,protected_arrays=31,
        protected_output_probe_arrays=13,targets=targets,protected_full_complement=protected,
        raw_coverage_population=763,raw_coverage_or=hex(value),official_percentage=False,
        serialized_pair_slot_direction_order_not_claimed=True,
        protects=['Every non-rvfi_probes_o core object','CVXIF/AXI ports and handshake/control',
            'Functional CSR/PMP/fflags state and control','All31 arrays including13 probe-output arrays',
            'Every child scope including i_cva6_rvfi_probes','system-parent RVFI788 owner scope'],
        independent_scope='Only core parent output leaves; disjoint scope from system RVFI788 and descendant observers',
        functional_integration_not_unreachable_proof=True,whole_core_waiver=False,
        filelist_observation_not_sole_compile_authority=True,
        native_label_type_alias_qualifiers_unproven=True,native_qualified=False,
        explicit_compiled_0to0_fields=[t['compiled_name'] for t in targets
            if t['kind']=='vectornode' and t['attributes']['left']==t['attributes']['right']=='0'],
        EL_generated=False,EDA_launched=False,RTL_modified=False,pins=pins)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();need(args.output.parent.resolve()==OUT and not args.output.exists(),'Fresh independent output required')
    result=collect()
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],seal=frozen.digest(args.output),objects=457,
        logical_bits=2599,missing=result['admitted763_candidate_missing'],protected=1315)))
