"""Frozen PMP0 q/next constant proof and typed inventory; no EDA/exclusion generation."""
import json
from pathlib import Path
import re
import targeted_toggle_evidence_v2 as native

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'verification/out'
CONFIG=OUT/'native-batch-full765-agent-20261007-02/config.json'
CONFIG_SHA='7788edc2ea227e403c9fecc03abbc3085712e2a35a967028a317f6ee33b78c72'
SCOPE='ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i'
STEMS=('pmpcfg_q','pmpcfg_next','pmpcfg_o','pmpaddr_q','pmpaddr_next','pmpaddr_o')
REL=('hardware/src/ara_soc.sv','hardware/deps/cva6/core/include/build_config_pkg.sv',
     'hardware/deps/cva6/core/csr_regfile.sv','hardware/deps/cva6/core/include/riscv_pkg.sv')
require=native.require


def compact(text):
    return re.sub(r'\s+','',re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S))


def source_proof(soc,config,csr):
    soc,config,csr=map(compact,(soc,config,csr))
    require(soc.count('cfg.NrPMPEntries=')==soc.count('cfg.NrPMPEntries=0;')==1,'Unique SoC PMP0 override')
    for token in ('CVA6AraConfig_user=gen_usr_cva6_config(cva6_config_pkg::cva6_cfg);',
                  'CVA6AraConfig=build_config_pkg::build_config(CVA6AraConfig_user);','.CVA6Cfg(CVA6AraConfig)'):
        require(token in soc,'Config propagation differs')
    require(config.count('cfg.NrPMPEntries=CVA6Cfg.NrPMPEntries;')==1,'Build config PMP preservation differs')
    for stem in ('pmpcfg','pmpaddr'):
        writes=re.findall(stem+r'_q(?:\[[^\]]+\])?(?:\.[\w.]+)?<=([^;]+);',csr)
        expected=["riscv::pmpcfg_t'(CVA6Cfg.PMPCfgRstVal[i])","'0",'pmpcfg_next'] if stem=='pmpcfg' else [
            "CVA6Cfg.PMPAddrRstVal[i][CVA6Cfg.PLEN-3:0]","'0",'pmpaddr_next']
        require(writes==expected,'All q reset/capture writers differ: '+stem)
    reset="""for(inti=0;i<64;i++)beginif(i<CVA6Cfg.NrPMPEntries)begin
        pmpcfg_q[i]<=riscv::pmpcfg_t'(CVA6Cfg.PMPCfgRstVal[i]);
        pmpaddr_q[i]<=CVA6Cfg.PMPAddrRstVal[i][CVA6Cfg.PLEN-3:0];
        endelsebeginpmpcfg_q[i]<='0;pmpaddr_q[i]<='0;endend"""
    require(compact(reset) in csr,'Reset zero-branch structure differs')
    start=csr.index('always_combbegin:write');end=csr.index('//',start) if '//' in csr[start:] else len(csr)
    body=csr[start:end]
    require(body.startswith('always_combbegin:writefor(inti=0;i<64;i++)beginif(i<CVA6Cfg.NrPMPEntries)begin') and
        "endelsebeginpmpcfg_next[i]='0;pmpaddr_next[i]='0;endendend" in body,'Next zero-branch structure differs')
    for stem,count in [('pmpcfg_next',5),('pmpaddr_next',3)]:
        require(len(re.findall(stem+r'(?:\[[^\]]+\])?(?:\.[\w.]+)?=(?!=)',csr))==count,
                'All next-state writers differ: '+stem)
    for stem in ('pmpcfg','pmpaddr'):
        token='assign'+stem+'_o='+stem+'_q[(CVA6Cfg.NrPMPEntries>0?CVA6Cfg.NrPMPEntries-1:0):0];'
        require(token in csr,'Output q alias differs')
    require('if(!pmpcfg_q[index*4+i].locked)pmpcfg_d[index*4+i]=csr_wdata[i*8+:8];' in csr and
            'pmpaddr_d[index]=csr_wdata[CVA6Cfg.PLEN-3:0];' in csr,'Protected temporary CSR write paths differ')
    return dict(pmp_entries=0,indices=64,reset_q_zero=True,settled_next_zero=True,
                all_q_writers=3,output_alias_index=0,d_protected=True,
                boundary='After valid reset/settled combinational evaluation, ordinary legal operation; '
                         'no initialization X, delta transient, arbitrary force/fault or nonzero-PMP configuration claim.')


def pending_model(entries,d,readonly=False):
    require(type(entries) is int and 0<=entries<=64 and len(d)==64,'Model configuration')
    return [value if i<entries and not readonly else 0 for i,value in enumerate(d)]


def bits(node):
    if node.tag=='node':return 1
    if node.tag=='vectornode':return abs(int(node.get('left'))-int(node.get('right')))+1
    require(node.tag=='arrays','Unknown typed object')
    require(node.get('unpackedrange','').strip()=='','Unexpected unpacked PMP dimension')
    dims=list(map(int,node.get('packedrange','').split()));require(len(dims)==4,'Exact packed PMP array rank2')
    total=1
    for i in (0,2):total*=abs(dims[i]-dims[i+1])+1
    return total


def build():
    require(native.digest(CONFIG)==CONFIG_SHA,'Prepared765 config seal differs')
    c=json.loads(CONFIG.read_bytes());book_path=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    require(native.digest(book_path)==c['pins'][str(book_path)],'Frozen build source ledger differs')
    book=json.loads(book_path.read_bytes())
    pins={str(CONFIG):CONFIG_SHA,str(book_path):native.digest(book_path)};texts=[]
    for rel in REL:
        p=ROOT/rel;require(native.digest(p)==book[str(p)],'Frozen build source pin differs')
        if str(p) in c['pins']:
            require(book[str(p)]==c['pins'][str(p)],'Direct765 source pin differs')
        else:
            require(rel==REL[3],'Required direct765 behavior source pin missing')
        pins[str(p)]=book[str(p)];texts.append(p.read_text())
    proof=source_proof(*texts[:3])
    proof['struct_package_binding']='riscv_pkg.sv bound through frozen build-source-pins.json, itself pinned by765; other three behavior sources also directly pinned by765.'
    cases=0
    for value in range(256):
        for readonly in (False,True):
            require(pending_model(0,[value]*64,readonly)==[0]*64,'PMP0 known Boolean induction counterexample');cases+=1
    proof['exhaustive_cfg_d_byte_models']=cases
    proof['address_proof']='All54bit d values are ignored by constant i<0 false branch; no sampled-address generalization.'
    db=Path(c['input_ledger'][0])/'snps/coverage/db';paths=[db/'design/verilog.design.xml',
        db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    for p in paths:require(native.digest(p)==c['pins'][str(p)],'Compiled identity pin differs');pins[str(p)]=c['pins'][str(p)]
    checks,defs=native.definitions(*(native.xml(p) for p in paths),[SCOPE])
    require(checks[SCOPE]=='1176918775','Exact frozen CSR Toggle checksum')
    root=native.base.ET.fromstring(defs[SCOPE]['shape'])
    rows=[n for n in root.iter() if n.tag in ('node','vectornode','arrays')]
    target=[n for n in rows if any(n.get('name','')==s or n.get('name','').startswith(s+'[') for s in STEMS)]
    complement=[n for n in rows if n not in target]
    require(len(target)==777 and sum(map(bits,target))==7998,'Exact typed target/bit capacity differs')
    require(sum(n.get('name','').startswith('pmpcfg_d[') for n in complement)==384 and
            len([n for n in complement if n.get('name')=='pmpaddr_d'])==1,'Every dynamic d object must remain protected')
    require(not any(g['scope']==SCOPE and any('pmp' in name.lower() for name in g['targets'])
                    for g in c['toggle_groups']),'PMP intersects existing approved Toggle groups')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_review_csr_pmp0_toggle765.py')):pins[str(p)]=native.digest(p)
    return dict(status='PMP0_SOURCE_TYPED_CANDIDATE_NATIVE_HOLD',population=765,scope=SCOPE,checksum=checks[SCOPE],
        proof=proof,targets=[dict(kind=n.tag,**n.attrib) for n in target],protected=[dict(kind=n.tag,**n.attrib) for n in complement],
        objects=777,internal_objects=770,constant_port_aliases=7,logical_bits=7998,nominal_directions=15996,
        official_denominator_reduction=None,existing_toggle_overlap=0,pins=pins,
        native_binding='Use actual unique GUI path/name/type/meta; bracket-safe exact comparison. '
                       'Two internal full arrays logic[63:0][53:0], dummy output logic[0:0][53:0]. '
                       'Never bind by XML ordering or silently coerce away the outer dimension.',
        native_required=['Complete before/selected/reset/reloaded/final typed inventory and local complement',
            'Exact EL semantic multiset/checksum/ranges and no alias expansion into d',
            'Global empty EL initially/reset/final; every other CSR/scope/metric protected',
            'Port aliases independently approved before inclusion; typed capability is not current PMP evidence'],
        DVE_launched=False,exclusions_generated=False,RTL_modified=False)


if __name__=='__main__':
    path=OUT/'csr-pmp0-toggle-source-review765-agent-20261007-01.json'
    require(not path.exists(),'Fresh artifact only');value=build()
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print('SOURCE_READY_NATIVE_HOLD',native.digest(path),value['objects'],value['logical_bits'],len(value['protected']))
