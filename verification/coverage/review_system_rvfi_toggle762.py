"""Parent-level observation-only RVFI Toggle candidates; no EL or EDA."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import review_scalar_dwc_write_fsm as frozen
from review_qbs_scale742 import scalar_shape

life,require,t=frozen.life,frozen.require,frozen.prior.t
SCOPE='ara_tb.dut.i_ara_soc.i_system'
ROOTS=('rvfi_probes','rvfi_instr','rvfi_csr','rvfi_to_iti')
RANK=life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
RANK_SHA='8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'
OBS=life.OUT/'observer-only-rooted-741-agent-20261007-04'
OBS_SHA='89f34505d6650340851c46c983e95b0672803b6fd4949d2ac7c6b2ac05207c9c'


def source_contract(text):
    text=frozen.prior.clean(text)
    counts={name:len(re.findall(r'\b'+name+r'\b',text)) for name in ROOTS}
    require(counts==dict(rvfi_probes=3,rvfi_instr=3,rvfi_csr=2,rvfi_to_iti=2),'Additional RVFI use/feedback')
    pairs=(('rvfi_probes_o','rvfi_probes'),('rvfi_probes_i','rvfi_probes'),
        ('rvfi_instr_o','rvfi_instr'),('rvfi_instr_i','rvfi_instr'),
        ('rvfi_csr_o','rvfi_csr'),('rvfi_to_iti_o','rvfi_to_iti'))
    for port,net in pairs:
        require(len(re.findall(r'\.'+port+r'\s*\(\s*'+net+r'\s*\)',text))==1,'Missing/extra observer connection')
    require(') i_cva6_rvfi (' in text and ') i_ara_commit_monitor (' in text and
        text.count('`ifdef FOR_VERIFY')>=3,'Observation guard/instance missing')
    return dict(producer='i_ariane.rvfi_probes_o',probe_consumer='i_cva6_rvfi.rvfi_probes_i',
        instruction_consumer='i_ara_commit_monitor.rvfi_instr_i',csr_consumers=[],iti_consumers=[],
        hardware_feedback=False,simulation_monitor_finish_fatal_and_logging_unchanged=True,
        classification='Observation-only integration scope, not unreachable hardware')


def selected(name):
    return any(re.match(r'^'+root+r'(?:\.|\[|$)',name) for root in ROOTS)


def partition(definition,width):
    require(definition.get('name')=='ara_system' and definition.get('chksum')=='3385959260','Wrong compiled definition')
    mapped={p['signal']:p for p in scalar_shape(definition,width)}
    targets=[];protected=[]
    for n in definition.find('tglshape'):
        candidate=selected(n.get('name','')) and n.tag in ('node','vectornode')
        if candidate:
            require(n.get('file') in ('595','402') and n.get('aux_file')=='595' and n.get('aux_line_num') in ('115','116','117','118')
                and n.get('portnode')=='0' and n.get('excluded')=='0' and n.get('type')=='1','Port/preexcluded/foreign source target')
            p=mapped[n.get('name')]
            targets.append(dict(p,native_name=n.get('name')+('[%s:%s]'%(n.get('left'),n.get('right')) if n.tag=='vectornode' else ''),
                compiled_kind=n.tag,native_type_requires_capture=True))
        else:protected.append(dict(kind=n.tag,attributes=dict(n.attrib),serialized=mapped.get(n.get('name'))))
    require(len(targets)==788 and sum(p['width'] for p in targets)==22126 and len(protected)==418,
        'Exact target/full typed complement differs')
    require(len({p['signal'] for p in targets})==788,'Duplicate target identity')
    return targets,protected


def collect():
    m=life.read_bound(frozen.BASE/'admission-manifest.json',frozen.BASE_SHA)
    rank=life.read_bound(RANK,RANK_SHA);obs=life.read_bound(OBS/'qualification.json',OBS_SHA)
    require(rank['tests']==741 and obs['status']=='QUALIFIED_EFFECTIVE_FOUR_OBSERVER_741_INTEGRATION_SCOPE', 'Wrong historical authorities')
    bpath=frozen.BASE/'combined-bits.json';bitmap=life.read_bound(bpath,m['output_pins'][str(bpath)])
    require(len(bitmap['tests'])==len(set(bitmap['tests']))==762,'Not exact formal762')
    ledgerpath=frozen.BASE/'combined-inputs.txt'
    ledger=ledgerpath.read_text().splitlines()
    require(life.digest(ledgerpath)==m['output_pins'][str(ledgerpath)] and len(ledger)==763,'Formal ledger drift')
    oldpaths=[Path(p) for p in rank['input_pins'] if p.endswith('/inputs.txt')]
    require(len(oldpaths)==1,'Ambiguous rank ledger')
    oldpath=oldpaths[0];require(life.digest(oldpath)==rank['input_pins'][str(oldpath)],'741 ledger drift')
    oldledger=oldpath.read_text().splitlines()
    require(len(oldledger)==742 and ledger[:742]==oldledger and ledger[1:]==bitmap['tests'],'Exact741 prefix/762 membership differs')
    bookpath=frozen.BUILD/'build-source-pins.json';book=life.read_bound(bookpath,frozen.support.old.SOURCE_SHA)
    pins={str(frozen.BASE/'admission-manifest.json'):frozen.BASE_SHA,str(bpath):m['output_pins'][str(bpath)],
        str(ledgerpath):m['output_pins'][str(ledgerpath)],str(RANK):RANK_SHA,str(oldpath):rank['input_pins'][str(oldpath)],
        str(OBS/'qualification.json'):OBS_SHA,str(bookpath):frozen.support.old.SOURCE_SHA}
    # Exhaustive exact-root identifier search in authenticated build-source HDL, including headers.
    names=re.compile(r'\b(?:'+'|'.join(ROOTS)+r')\b')
    files=[];texts={};scan_count=0
    recovered={'hardware/src/ara_dispatcher.sv':'ara_dispatcher.sv',
        'hardware/src/lane/lane_sequencer.sv':'lane_sequencer.sv','hardware/src/sldu/sldu.sv':'sldu.sv'}
    for original,sha in book.items():
        p=Path(original)
        if p.suffix not in ('.sv','.svh','.v','.vh'):continue
        if life.digest(p)!=sha:
            rel=str(p.relative_to(life.ROOT));require(rel in recovered,'Unrecovered historical HDL source')
            p=life.OUT/'old-image-source-evidence-20261006-01'/recovered[rel]
        require(life.digest(p)==sha,'Historical source byte mismatch')
        pins=life.merge_pins(pins,{str(p):sha});text=frozen.prior.clean(p.read_text());scan_count+=1
        if names.search(text):files.append(original)
        texts[original]=text
    system=life.ROOT/'hardware/src/ara_system.sv';core=life.ROOT/'hardware/deps/cva6/core/cva6.sv'
    require(set(files)=={str(system),str(core)},'Additional cross-module parent-net reference')
    contract=source_contract(texts[str(system)])
    for rel in ('hardware/deps/cva6/core/cva6_rvfi.sv','hardware/deps/cva6/core/cva6_rvfi_probes.sv','hardware/tb/ara_commit_monitor.sv'):
        require(str(life.ROOT/rel) in texts,'Missing observer source in build')
    require('.rvfi_probes_o(rvfi_probes_o)' in re.sub(r'\s+','',texts[str(core)]),'CVA6 output boundary differs')
    db=frozen.DB
    prior_review=life.read_bound(frozen.PRIOR,frozen.PRIOR_SHA)
    pins[str(frozen.PRIOR)]=frozen.PRIOR_SHA
    paths=[db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    for p in paths:
        require(str(p) in prior_review['input_pins'],'Missing historical compiled input')
        pins[str(p)]=prior_review['input_pins'][str(p)]
        require(life.digest(p)==pins[str(p)],'Compiled input drift')
    info=db/'auxiliary/verilog.sourceinfo.xml'
    pins[str(info)]=prior_review['input_pins'][str(info)]
    files_by_id={n.get('id'):n.get('name') for n in t.xml(info).iter('fileinfo')}
    require(life.digest(info)==pins[str(info)] and files_by_id['595']==str(system) and
        files_by_id['402']==str(life.ROOT/'hardware/deps/cva6/core/include/riscv_pkg.sv'),
        'Compiled parent/type-package source differs')
    checks,defs=t.definitions(*(t.xml(p) for p in paths),[SCOPE])
    require(checks[SCOPE]=='3385959260','Parent Toggle checksum differs')
    definition=ET.fromstring(defs[SCOPE]['shape']);merged={SCOPE:rank['instances'][SCOPE]}
    require(merged[SCOPE]['checksum']==checks[SCOPE],'Historical Toggle checksum differs')
    for vdb in ledger[742:]:
        data=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(data)==1 and str(data[0]) in m['input_pins'],'Unbound added Toggle member')
        sample,sha=t.rows(data[0],[SCOPE]);require(sha==m['input_pins'][str(data[0])],'Singleton drift')
        pins[str(data[0])]=sha;merged=t.union(merged,sample)
    row=merged[SCOPE];targets,protected=partition(definition,row['width'])
    bits=format(int(row['bits'],16),'0%db'%row['width'])
    for p in targets:
        value=bits[p['raw_offset']:p['raw_offset']+2*p['width']]
        p['serialized_value']=value;p['serialized_missing']=value.count('0')
    el=OBS/'observers.el';require(str(el) in obs['output_pins'],'Unbound observer EL')
    pins[str(el)]=obs['output_pins'][str(el)];require(life.digest(el)==pins[str(el)],'Observer EL drift')
    excluded=re.findall(r'^INSTANCE:\s*(\S+)$',el.read_text(),re.M)
    require(len(excluded)==len(set(excluded))==4 and all(s.startswith(SCOPE+'.') for s in excluded), 'Wrong observer ownership')
    require(all(not (SCOPE==s or SCOPE.startswith(s+'.')) for s in excluded),'Parent target already excluded by owner')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_review_system_rvfi_toggle762.py'),
              Path(frozen.__file__).resolve(),Path(t.__file__).resolve()):pins[str(p)]=life.digest(p)
    life.check(pins)
    return dict(status='PARENT_RVFI_OBSERVATION_ONLY_TOGGLE_CANDIDATES_NOT_NATIVE_APPROVED',baseline=762,
        scope=SCOPE,checksum=checks[SCOPE],compiled_module=defs[SCOPE]['module'],compiled_parameters=definition.get('param'),
        source_contract=contract,source_scan_count=scan_count,exact_root_reference_files=files,
        candidate_objects=788,candidate_bits=22126,candidate_serialized_positions=44252,
        candidate_serialized_missing=sum(p['serialized_missing'] for p in targets),
        protected_objects=418,all_arrays_protected=True,protected=protected,targets=targets,
        prior_observer_scopes=excluded,prior_scope_exclusions_cover_parent_nets=False,
        bit_direction_order_not_claimed=True,official_percentage=False,native_identity_qualified=False,
        EL_generated=False,exclusions_applied=False,EDA_launched=False,RTL_modified=False,pins=pins)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(a.output.absolute().parent==life.OUT and not a.output.exists(),'Fresh output required')
    r=collect();life.save(a.output,r)
    print(json.dumps(dict(output=str(a.output),seal=life.digest(a.output),objects=r['candidate_objects'],
        bits=r['candidate_bits'],serialized_missing=r['candidate_serialized_missing'])),flush=True)
