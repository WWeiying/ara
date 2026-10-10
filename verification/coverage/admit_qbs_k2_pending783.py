"""782+one positive QBS: exact native qualification,214 Toggle directions,parent-only publish."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shlex

import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as toggle
import analyze_qbs_k2_pending782 as analysis
import seal_qbs_k2_echo_receipt782 as receipt

life,require=analysis.life,analysis.require
runner=analysis.case.runner
BASE,BASE_SHA=runner.BASE,runner.BASE_SHA
RUN=life.OUT/'qbs-k2-row-pending-old-image782-agent-20261008-01'
QUAL=receipt.CORE.parent
Q_SHA=receipt.CORE_SHA
SIDE=life.OUT/'qbs-k2-echo-core-receipt782-agent-20261008-01.json'
C_SHA='14b6139515b2def5482bb89cc009cdbbba9a8d61a3202bcbf29b2a39005ed0c8'
DIAG=life.OUT/'qbs-k2-row-pending-cycle782-agent-20261008-01'
CYCLE_SHA='2d2445778c4989e1a2ba49f8120800b503fd233dbdeaa9d3aca3a45483a6b21d'
GAIN_SHA='d6ef72f28f975e8bc6805d7c5b4f53396188eaf443d11ab363a8cfc09c2a44ed'
RUN_SHA='9ec4782319fbac9cb42e82464cef2a7c410ea3017cf8f73f471470005b047932'
ANALYSIS_SHA='cd8b4a69ffeac072f0919ad99c93d4a99beda24dd464da15cc57b8b63665f6ac'
PUBLISHER=Path(__file__).with_name('admit_akv_entropy777.py')
PUBLISHER_SHA='6c6e972d44665aaec8b4227f129c6240a5c368286ab6bc6c0c2468775451a84d'
DEDUP=Path(__file__).with_name('admit_stride_metadata768.py')
DEDUP_SHA='8bedad4daece0ff20ade7ccb9fb3b440cb23c6607456e9e3d626cadfd890bc53'
COUNTS=dict(line=1892,cond=2023,branch=2155,fsm=92)


def inherited(path,sha,names):
    require(life.digest(path)==sha,'Frozen inherited source')
    tree=ast.parse(path.read_text());functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    require({n.name for n in functions}==set(names),'Exact inherited functions')
    ns=dict(globals(),OUT=life.OUT)
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(path),'exec'),ns)
    return ns


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==782 and single['tests']==[str(RUN/'code.vdb')]
        and single['tests'][0] not in before['tests'],'Exact782 prefix and unique candidate')
    require(set(before['metrics'])==set(single['metrics'])==set(COUNTS),'Four metrics')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    after=bitmap.combine(before,single)
    require(after['tests']==before['tests']+single['tests'],'Ordered783 append')
    for metric,count in COUNTS.items():
        old,add,final=(x['metrics'][metric] for x in (before,single,after))
        require(len(old)==count and set(old)==set(add)==set(final),'Full6162 metric universe')
        for scope,row in old.items():
            rows=(row,add[scope],final[scope]);values=[int(r['bits'],16) for r in rows]
            require(all(type(r['width']) is int and r['width']>=0 for r in rows) and
                len({(r['width'],r['checksum']) for r in rows})==1 and
                min(values)>=0 and max(values).bit_length()<=row['width'] and
                values[2]==values[0]|values[1],'Every native shape/bounds/OR')
    return after


def native_identity(sim,args,record,design):
    tests=sim.findall('srctest')
    require(sim.tag=='test' and len(tests)==1,'Unique native run')
    t=tests[0]
    require(shlex.split(t.get('cmdline',''))==record['command'] and t.get('workdir')==str(RUN) and
        t.get('seed')=='1' and t.get('starttime','').isdigit() and t.get('finishtime','').isdigit() and
        int(t.get('finishtime'))>int(t.get('starttime')),'Actual command/cwd/seed/completed time')
    require(args.tag=='vcm_args' and args.get('compvdbpath')==design and
        sorted(n.get('vcm_opt') for n in args.findall('vcm_arg_data') if n.get('vcm_opt'))==
        ['-cm branch','-cm cond','-cm fsm','-cm line','-cm tgl'],'Same compiled five metrics')
    return dict(command=record['command'],workdir=str(RUN),design=design,seed=1,
        starttime=t.get('starttime'),finishtime=t.get('finishtime'),XML_teststatus=t.get('teststatus'),
        XML_teststatus_is_not_PASS_authority=True)


def historical(ledger,base,authority):
    path=BASE/'elf-ledger-dedup.json';audit=life.read_bound(path,base['output_pins'][str(path)])
    require(audit['ledger_members']==781 and len(audit['members'])==781 and
        [m['vdb'] for m in audit['members']]==ledger[1:782] and
        all(authority.get(p)==h for p,h in audit['pins'].items()),'Historical781 sealed ownership')
    for member in audit['members']:
        require(member['ELF_candidates'] and runner.ELF_SHA not in member['ELF_candidates'].values(),'Duplicate historical ELF')
    ns=inherited(DEDUP,DEDUP_SHA,('elf_references','dedup'))
    suffix=ns['dedup']([ledger[0],ledger[-1]],runner.ELF_SHA,authority)
    require(suffix['ledger_members']==1 and suffix['duplicate'] is False and
        all(authority.get(p)==h for p,h in suffix['pins'].items()),'782 suffix uses historical authority only')
    pins=life.merge_pins(audit['pins'],suffix['pins'])
    pins=life.merge_pins(pins,{str(path):base['output_pins'][str(path)]})
    return pins,dict(baseline=782,ledger_members=782,members=audit['members']+suffix['members'],pins=pins,
        duplicate=False,candidate_qualification_not_used_as_historical_owner=True)


def evaluate():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal782 authority')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    core=life.read_bound(QUAL/'qualification.json',Q_SHA)
    side=life.read_bound(SIDE,C_SHA)
    require(side==receipt.record(),'Exact core/echo receipt revalidation')
    require(core['baseline']==782 and core['coverage_admitted'] is False and
        core['primary_target_sample']=={'21532':True,'21533':False},'Sealed functional core')
    require(life.digest(Path(analysis.__file__))==ANALYSIS_SHA,'Frozen cycle/gain analyzer')
    cycle_path,gain_path=DIAG/'cycle-proof.json',DIAG/'payload-gain.json'
    cycle=life.read_bound(cycle_path,CYCLE_SHA);gain=life.read_bound(gain_path,GAIN_SHA)
    require(analysis.cycles(DIAG/'pending.vcd')=={k:v for k,v in cycle.items() if k!='input_pins'},'Actual preedge/FIFO/source same-b replay')
    require(analysis.gain(RUN)==gain and gain['new_directions']==214 and
        sorted(map(len,gain['new_coordinates'].values()))==[28,186] and gain['primary_new']==[21532],
        'Exact measured782 payload OR, not predicted222')
    require(cycle['missing_direct_wave_objects'] and cycle['pending_remains_same_b'] is True,
        'Source inference boundary must remain explicit')
    pins=life.merge_pins(authority,life.merge_pins(core['input_pins'],core['output_pins']))
    for extra in (side['input_pins'],cycle['input_pins'],gain['input_pins']):pins=life.merge_pins(pins,extra)
    def previous(name):return life.read_bound(BASE/name,base['output_pins'][str(BASE/name)])
    before=previous('combined-bits.json');ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    status=previous('status.json')
    require(ledger==[str(life.IMAGE)+'.vdb',*before['tests']] and len(ledger)==len(set(ledger))==783 and
        status['aggregate_passed']==782 and status['coverage_admitted'] is True,'Exact782 ordered ledger/status')
    record_path=RUN.with_name(RUN.name+'.prepared.json');record=life.read_bound(record_path,RUN_SHA)
    require(life.read_bound(RUN/'manifest.json',RUN_SHA)==record and record['command']==runner.command(RUN) and
        record['baseline_seal']==BASE_SHA and record['pins'][str(runner.ELF)]==runner.ELF_SHA,'Prepared/executed same image/ELF')
    analysis.case.native.terminal(RUN)
    folder=RUN/'code.vdb/snps/coverage/db/testdata'/runner.NAME
    require(list(folder.parent.iterdir())==[folder],'Singleton native testcase')
    members=[p for p in (RUN/'code.vdb').rglob('*') if p.is_file()]
    require(not any(p.is_symlink() for p in (RUN/'code.vdb').rglob('*')) and
        {str(p) for p in members}=={p for p in core['input_pins'] if p.startswith(str(RUN/'code.vdb')+'/')},'Complete VDB pin inventory')
    identity=native_identity(toggle.xml(folder/'siminfo.xml'),toggle.xml(folder/'vcmArguments.xml'),record,ledger[0])
    design=Path(ledger[0])/'snps/coverage/db'
    for rel,h in before['design'].items():
        require(pins.get(str(design/rel))==h==life.digest(design/rel),'Frozen design fingerprint')
    single=dict(design=before['design'],tests=[str(RUN/'code.vdb')],input_hashes={},metrics={})
    for metric in bitmap.METRICS:
        path=folder/(metric+'.verilog.data.xml');require(pins[str(path)]==life.digest(path),'Metric pin')
        single['metrics'][metric]=bitmap.read_metric(path);single['input_hashes'][str(path)]=pins[str(path)]
    after=full_union(before,single);delta=bitmap.delta(before,after)
    scopes=sorted(gain['single_rows'])
    checks,_=toggle.definitions(*(toggle.xml(design/rel) for rel in
        ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')),scopes)
    require(all(checks[s]=='3657545390' for s in scopes),'Compiled payload Toggle identity')
    sample,_=toggle.rows(folder/'tgl.verilog.data.xml',scopes)
    require(sample==gain['single_rows'],'Actual native Toggle single')
    hp,dedup=historical(ledger,base,authority);pins=life.merge_pins(pins,hp)
    fixed={str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):Q_SHA,str(SIDE):C_SHA,
        str(cycle_path):CYCLE_SHA,str(gain_path):GAIN_SHA,str(record_path):RUN_SHA,
        str(PUBLISHER.resolve()):PUBLISHER_SHA,str(DEDUP.resolve()):DEDUP_SHA}
    for module in (bitmap,toggle,analysis,receipt):
        p=Path(module.__file__).resolve();fixed[str(p)]=life.digest(p)
    for p in (Path(__file__),Path(__file__).with_name('test_admit_qbs_k2_pending783.py')):
        fixed[str(p.resolve())]=life.digest(p)
    pins=life.merge_pins(pins,fixed);life.check(pins)
    products={Path(p).name:previous(Path(p).name) for p in base['output_pins'] if
        Path(p).parent==BASE and Path(p).suffix=='.json' and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'qbs-k2-payload-toggle-gain782.json':gain,'qbs-k2-cycle-proof.json':cycle,
        'qbs-k2-core-receipt.json':side,'elf-ledger-dedup.json':dedup,'native-vdb-identity.json':identity,
        'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=783,
            baseline=782,new_passed=1,coverage_admitted=True,exact782_prefix=True,full_OR_metric_instances=6162,
            unique_new_vdb=True,duplicate_ELF=False,scoped_payload_toggle_new_serialized_positions=214,
            primary_new=[21532],primary_not_new=[21533],raw_delta=delta['metrics'],
            cycle_profile='Actual preedge pending values; source1 reconstructed FIFO; write_req source-inferred, not directly captured',
            native_Spike_comparison=False,full_scalar_ISA_verified=False,official_percentage_claimed=False,
            prior_gain_records_retained_not_recounted=True,new_simulation=False,RTL_changed=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    # Reuse only the sealed publisher function; do not import its unrelated AKV adapters.
    def display(*args,**kwargs):
        labels={'PREPARED777_NOT_ADMITTED':'PREPARED783_NOT_ADMITTED','ADMITTED777':'ADMITTED783'}
        print(*(labels.get(x,x) if isinstance(x,str) else x for x in args),**kwargs)
    ns=inherited(PUBLISHER,PUBLISHER_SHA,('main',));ns['print']=display
    ns['main']()


if __name__=='__main__':main()
