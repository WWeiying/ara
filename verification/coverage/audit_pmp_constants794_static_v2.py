"""Complete reflection writer closure supplement; static only, no EL or EDA."""
import argparse
import json
from pathlib import Path
import re

import audit_pmp_constants794_static as old


def clean(text):return re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)


def writers(text,root):
    pattern=r'(?<![\w.])('+re.escape(root)+r'(?:\[[^\]]+\]|\.[A-Za-z_]\w*)*)\s*(?:<=|=(?!=))\s*([^;]+);'
    return [(re.sub(r'\s+','',lhs),re.sub(r'\s+','',rhs)) for lhs,rhs in re.findall(pattern,clean(text))]


def writer_guard(texts):
    old.proof(texts)
    expected={
        'pmpcfg_q':[('pmpcfg_q[i]',"riscv::pmpcfg_t'(CVA6Cfg.PMPCfgRstVal[i])"),('pmpcfg_q[i]',"'0"),('pmpcfg_q','pmpcfg_next')],
        'pmpaddr_q':[('pmpaddr_q[i]','CVA6Cfg.PMPAddrRstVal[i][CVA6Cfg.PLEN-3:0]'),('pmpaddr_q[i]',"'0"),('pmpaddr_q','pmpaddr_next')],
        'pmpcfg_next':[('pmpcfg_next[i]','pmpcfg_d[i]'),('pmpcfg_next[i].addr_mode','pmpcfg_q[i].addr_mode'),
                       ('pmpcfg_next[i].access_type','pmpcfg_q[i].access_type'),('pmpcfg_next[i]','pmpcfg_q[i]'),('pmpcfg_next[i]',"'0")],
        'pmpaddr_next':[('pmpaddr_next[i]','pmpaddr_d[i]'),('pmpaddr_next[i]','pmpaddr_q[i]'),('pmpaddr_next[i]',"'0")]}
    for root in ('pmpcfg','pmpaddr'):
        expected[root+'_o']=[(root+'_o',root+'_q[(CVA6Cfg.NrPMPEntries>0?CVA6Cfg.NrPMPEntries-1:0):0]')]
    state_writers={r:writers(texts['csr_regfile.sv'],r) for r in expected}
    old.base.t.require(state_writers==expected,'Every blocking/nonblocking q/next/output writer')
    csr=[w for w in writers(texts['csr_regfile.sv'],'rvfi_csr_o')
         if w[0]=='rvfi_csr_o' or w[0].startswith(('rvfi_csr_o.pmpcfg_q','rvfi_csr_o.pmpaddr_q'))]
    old.base.t.require(csr==[('rvfi_csr_o.pmpcfg_q','pmpcfg_q'),('rvfi_csr_o.pmpaddr_q','pmpaddr_q')],
                       'Complete CSR PMP reflection writer closure')
    probe=writers(texts['cva6_rvfi_probes.sv'],'csr')
    old.base.t.require(len(probe)==3 and probe[:2]==[('csr',"'0"),('csr','csr_i')]
                       and probe[2][0]=='csr.mip_q','Complete probe local CSR writers')
    reflected=[w for w in writers(texts['cva6_rvfi_probes.sv'],'rvfi_probes_o')
               if w[0]=='rvfi_probes_o' or w[0].startswith('rvfi_probes_o.csr')]
    old.base.t.require(reflected==[('rvfi_probes_o',"'0"),('rvfi_probes_o.csr','csr')],
                       'Complete probe output CSR writers')
    core=clean(texts['cva6.sv'])
    refs={}
    for root,count in (('pmpcfg',4),('pmpaddr',4),('rvfi_csr',3)):
        old.base.t.require(not writers(core,root),'No alternate parent constant alias driver')
        refs[root]=len(re.findall(r'\b'+root+r'\b',core))
        old.base.t.require(refs[root]==count,'Closed parent alias reference/connection census: '+root)
    consumer_refs={}
    for file,counts in (('ex_stage.sv',(2,2)),('load_store_unit.sv',(4,4)),('cva6_mmu.sv',(3,3)),
                        ('cva6_ptw.sv',(2,2)),('acc_dispatcher.sv',(2,1)),('pmp_data_if.sv',(7,3))):
        actual=[]
        for root in ('pmpcfg_i','pmpaddr_i'):
            old.base.t.require(not writers(texts[file],root),'No consumer input override: '+file)
            actual.append(len(re.findall(r'\b'+root+r'\b',clean(texts[file]))))
        old.base.t.require(tuple(actual)==counts,'Closed consumer input reference census: '+file)
        consumer_refs[file]=actual
    return dict(state_and_output_writers=state_writers,csr_reflection_writers=csr,probe_local_writers=probe,probe_output_writers=reflected,
                consumer_reference_counts=consumer_refs,
                parent_alias_reference_counts=refs,all_consumer_input_overrides=0,
                proof='Every reflected PMP whole object/subfield/slice writer and parent alias reference enumerated; '
                      'no input override or second module driver accepted.')


def build():
    value=old.build()
    texts={}
    for rel in old.FILES:
        p=old.ROOT/rel
        old.base.t.require(old.base.t.digest(p)==value['input_pins'][str(p)],'Source writer closure pin')
        texts[p.name]=p.read_text()
    value['complete_reflection_writer_closure']=writer_guard(texts)
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_audit_pmp_constants794_static_v2.py')):
        value['input_pins'][str(p)]=old.base.t.digest(p)
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=build()
    for path,sha in value['input_pins'].items():old.base.t.require(old.base.t.digest(path)==sha,'Read-end pin')
    with a.output.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(output=str(a.output),seal=old.base.t.digest(a.output),fields=value['fresh_fields'],
                         bits=value['fresh_logical_bits'],missing=value['fresh_raw_missing'],
                         already_owned=len(value['already_owned']),HOLD=len(value['HOLD']))))
