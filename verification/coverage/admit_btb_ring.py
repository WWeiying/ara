"""Append qualified BTB32 to an explicit latest formal777-prefix; offline only."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import xml.etree.ElementTree as ET
import collect_btb_target_ring_v3 as case
from admit_stride_metadata768 import dedup

life,require=case.life,case.require
core=case.original
bitmap,toggle=core.bitmap,core.pre.toggle
QUAL=life.OUT/'btb-target-ring-qualified777-agent-20261008-01'
Q_SHA='cd6e476360ff6c0c5b3753e6b0b305a09ba7617c65c897f0ac02a8f610c06dab'
RUN=life.OUT/'btb-target-ring-old-image777-agent-20261007-01'
PREPARED_SHA='2826b154102c5479b4e8a225378302891c336fdc2cb38537a6b78cd503ca9329'
ELF_SHA='52e103c2efeff51b497978c5e1b2a23c384f0f1805193b875117599522301781'
COUNTS=dict(line=1892,cond=2023,branch=2155,fsm=92)


def prefix(before,ledger,original_ledger,population):
    count=len(before['tests'])
    require(type(population) is int and count>=777 and population==count+1 and
        len(ledger)==len(set(ledger))==count+1 and ledger[1:]==before['tests'] and
        ledger[:778]==original_ledger and str(RUN/'code.vdb') not in ledger,
        'Exact777 prefix/latest unique member/population required')


def full_union(before,single):
    require(single['tests']==[str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'], 'One unique BTB candidate')
    after=bitmap.combine(before,single)
    require(before['design']==single['design']==after['design'] and
        after['tests']==before['tests']+single['tests'] and
        set(before['metrics'])==set(single['metrics'])==set(after['metrics'])==set(COUNTS),'Exact design/metric families/prefix')
    for metric,count in COUNTS.items():
        old,add,final=[x['metrics'][metric] for x in (before,single,after)]
        require(len(old)==count and set(old)==set(add)==set(final),'Exact6162 instance universe')
        for scope,r in old.items():
            n,a=add[scope],final[scope]
            require((r['width'],r['checksum'])==(n['width'],n['checksum'])==(a['width'],a['checksum']), 'Exact compiled width/checksum')
            vals=[int(x['bits'],16) for x in (r,n,a)]
            require(min(vals)>=0 and max(vals).bit_length()<=r['width'] and vals[2]==vals[0]|vals[1], 'Independent6162 OR/bounds')
    return after


def rebase(old,suffix,single,count):
    require(count>=777 and len(suffix)==count-777,'Exact latest suffix length')
    before={core.BTB:old}
    for sample in suffix:before=toggle.union(before,sample)
    after=toggle.union(before,single);gained=toggle.gains(before,after)[core.BTB]
    require(before[core.BTB]['width']==8992 and before[core.BTB]['checksum']=='1574888635', 'Exact BTB native shape')
    require(gained,'No fresh BTB gain against latest formal base')
    return dict(baseline=count,scope=core.BTB,before=before[core.BTB],single=single[core.BTB],after=after[core.BTB],
        new_positions=len(gained),new_serialized_positions=gained,direction_labels_verified=False,
        official_percentage=False,historical777_gain_not_recounted=True)


def native_identity(sim,args,command,design):
    tests=sim.findall('srctest')
    require(sim.tag=='test' and len(tests)==1,'One native test')
    t=tests[0]
    require(shlex.split(t.get('cmdline',''))==command and t.get('workdir')==str(RUN) and
        t.get('seed')=='1' and t.get('teststatus')=='unknown' and
        t.get('starttime')=='1791442247260002' and t.get('finishtime')=='1791442440022013',
        'Exact native command/workdir/seed/time; XML unknown is not PASS')
    require(args.tag=='vcm_args' and args.get('compvdbpath')==design and
        sorted(x.get('vcm_opt') for x in args.findall('vcm_arg_data') if x.get('vcm_opt'))==
        ['-cm branch','-cm cond','-cm fsm','-cm line','-cm tgl'],'Compatible five-metric compiled VDB')
    return dict(seed=1,command=command,workdir=str(RUN),compvdb=design,XML_teststatus='unknown',
                functional_authority='independent sealed full architecture/update/AXI qualification')


def evaluate(base_dir,bsha,population):
    base=life.read_bound(base_dir/'admission-manifest.json',bsha)
    require(base['coverage_admitted'] is True and base['output']==str(base_dir),'Explicit formal admitted base')
    q=life.read_bound(QUAL/'qualification.json',Q_SHA)
    require(q['status']=='BTB32_ARCHITECTURE_AXI_ACTUAL_UPDATES_QUALIFIED_NOT_ADMITTED' and q['baseline']==777 and
        q['slots']==32 and q['updates']==96 and q['checks']==2690 and q['full_scalar_ISA'] is True and
        q['coverage_admitted'] is False,'Exact independent BTB qualification')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(authority,q['input_pins']);pins=life.merge_pins(pins,q['output_pins'])
    life.check(pins)
    def bdoc(name):
        p=base_dir/name;return life.read_bound(p,base['output_pins'][str(p)])
    def qdoc(name):
        p=QUAL/name;return life.read_bound(p,q['output_pins'][str(p)])
    before=bdoc('combined-bits.json');status=bdoc('status.json')
    require(status['coverage_admitted'] is True and status['aggregate_passed']==len(before['tests']), 'Formal status population')
    ledger_path=base_dir/'combined-inputs.txt'
    require(life.digest(ledger_path)==base['output_pins'][str(ledger_path)],'Latest ledger seal')
    ledger=ledger_path.read_text().splitlines()
    oldbase=life.read_bound(core.pre.BASE/'admission-manifest.json',core.pre.BASE_SHA)
    oldledger=core.pre.BASE/'combined-inputs.txt';oldsha=oldbase['output_pins'][str(oldledger)]
    require(life.digest(oldledger)==oldsha,'Authoritative original777 ledger')
    prefix(before,ledger,oldledger.read_text().splitlines(),population)
    pins=life.merge_pins(pins,{str(core.pre.BASE/'admission-manifest.json'):core.pre.BASE_SHA,str(oldledger):oldsha})
    prepared=RUN.with_name(RUN.name+'.prepared.json');record=life.read_bound(prepared,PREPARED_SHA)
    core.runner.validate_record(record)
    require(json.loads((RUN/'manifest.json').read_bytes())==dict(record,pins=life.merge_pins(record['pins'],{str(prepared):PREPARED_SHA})),
        'Executed/prepared manifest identity')
    qpath=Path(record['preflight']);pre=life.read_bound(qpath,record['preflight_seal'])
    require(pre['input_pins'][str(qpath.parent/'input.elf')]==ELF_SHA and life.digest(qpath.parent/'input.elf')==ELF_SHA,
        'Exact qualified ELF')
    case.prior.scalar_exact(qdoc('scalar-comparison.json'),dict(pre['counts'],ara_trap_events=1))
    gold=qdoc('native-gold.json');require(gold['checks']==2690 and gold['failed']==0 and gold['full_VRF_bytes']==4096 and
        gold['restored_machine_CSRs']==9 and gold['source_executions']==96,'Complete native readback oracle')
    reference=core.pre.interval(core.pre.build.parse_spike_commits(qpath.parent/'spike.trace'))
    core.vector_gate(qdoc('vector-comparison.json'),reference)
    lifecycle=qdoc('lifecycle.json')
    require(lifecycle['requests']==lifecycle['responses']==44 and lifecycle['all_requests_retired'] is True and
        lifecycle['all_vector_uops_complete'] is True and len(lifecycle['exact_retire_bindings'])==44,
        'Complete independent accepted/retired/backend lifecycle')
    updates=qdoc('slot-updates.json')
    expected=[(hex(pre['symbols']['btb_bank%d'%b]+4*r),hex(t),r,b) for b in (0,1) for r in range(16) for t in core.pre.TARGETS]
    require(updates['status']=='EXACT32_SLOT_A_B_A_PREEDGE_UPDATE_PASS' and updates['slots']==32 and updates['updates']==96 and
        [(x['pc'],x['target'],x['row'],x['slot']) for x in updates['records']]==expected and
        all(x['JumpR'] is True and x['mispredict'] is True and x['preedge_update'] is True for x in updates['records']),
        'All32 actual A-B-A update identities')
    require(qdoc('axi-audit.json')['status']=='FULL_SCALAR_AXI_PREEDGE_DRAIN_PASS','Independent complete AXI drain')
    inputs=QUAL/'single-inputs.txt'
    require(inputs.read_text().splitlines()==[ledger[0],str(RUN/'code.vdb')],'Qualified singleton design/test identity')
    single=bitmap.collect(inputs)
    require(single==qdoc('single-bits.json') and all(q['input_pins'].get(p)==h for p,h in single['input_hashes'].items()),
        'Fresh four-metric singleton exact sealed equality')
    for rel,h in single['design'].items():require(pins.get(str(Path(ledger[0])/'snps/coverage/db'/rel))==h,'Bound compiled design')
    after=full_union(before,single);delta=bitmap.delta(before,after)
    folder=RUN/'code.vdb/snps/coverage/db/testdata'/core.runner.CASE
    require(list(folder.parent.iterdir())==[folder],'One exact native testcase')
    def xml(p):
        raw=p.read_bytes();require(pins.get(str(p))==life.digest(p),'Bound native XML identity')
        return ET.fromstring(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
    identity=native_identity(xml(folder/'siminfo.xml'),xml(folder/'vcmArguments.xml'),record['command'],ledger[0])
    measured=qdoc('toggle-gain.json');require(measured['baseline']==777 and measured['scope']==core.BTB,'Original777 Toggle ownership')
    def sample(db,evidence):
        files=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique admitted member Toggle file')
        rows,h=toggle.rows(files[0],[core.BTB]);require(evidence.get(str(files[0]))==h,'Bound native Toggle member')
        return rows
    suffix=[sample(db,authority) for db in before['tests'][777:]]
    added=sample(str(RUN/'code.vdb'),q['input_pins'])
    require(added[core.BTB]==measured['single'],'Qualified Toggle singleton')
    gain=rebase(measured['before'],suffix,added,len(before['tests']))
    # Historical ownership uses ONLY the admitted baseline, never candidate qualification pins.
    elf=dedup(ledger,ELF_SHA,authority)
    require(not elf['duplicate'] and elf['ledger_members']==len(before['tests']) and
        [x['vdb'] for x in elf['members']]==before['tests'] and
        all(authority.get(p)==h for p,h in elf['pins'].items()), 'Historical-only ELF/command dedup ownership')
    pins=life.merge_pins(pins,elf['pins'])
    fixed={str(base_dir/'admission-manifest.json'):bsha,str(QUAL/'qualification.json'):Q_SHA,str(prepared):PREPARED_SHA}
    for module in (case,case.prior,core,core.runner,core.pre,bitmap,toggle,toggle.base,life):
        p=Path(module.__file__).resolve();require(pins.get(str(p))==life.digest(p),'Bound reused helper closure')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_btb_ring.py').resolve(),Path(dedup.__code__.co_filename).resolve()):
        fixed[str(p)]=life.digest(p)
    pins=life.merge_pins(pins,fixed);life.check(pins)
    retained={}
    for name,h in base['output_pins'].items():
        p=Path(name)
        if p.parent==base_dir and p.suffix=='.json' and ('toggle-gain' in p.name or p.name.startswith('retained-')):
            retained[p.name]=life.read_bound(p,h)
    require('btb-toggle-gain.json' not in retained,'Candidate already admitted')
    products=dict(retained,**{'combined-bits.json':after,'single-bits.json':single,'raw-delta.json':delta,
        'btb-toggle-gain.json':gain,'elf-ledger-dedup.json':elf,'native-vdb-identity.json':identity,'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=population,
            coverage_admitted=True,baseline=len(before['tests']),exact_previous_prefix=True,exact777_prefix=True,
            full_OR_metric_instances=6162,unique_new_vdb=True,duplicate_ELF=False,
            new_toggle_raw_slots=gain['new_positions'],raw_delta=delta['metrics'],actual_slots=32,actual_updates=96,
            full_scalar_ISA=True,full_VRF_CSR_guards=True,complete_AXI=True,prior_gain_records_retained_not_recounted=True,
            official_percentage_claimed=False,new_simulation=False,RTL_changed=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify','admit'))
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--baseline-seal',required=True)
    p.add_argument('--population',type=int,default=779);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true');a=p.parse_args()
    require(a.parent_authorized==(a.mode=='admit') and bool(a.seal)==(a.mode!='prepare'),'Explicit parent authorization/seal')
    out=a.output.resolve();base=a.baseline.resolve();require(out.parent==life.OUT and not out.exists(),'Fresh output only')
    products,text=evaluate(base,a.baseline_seal,a.population)
    hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in products.items()}
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):hashes[str(out/n)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(output=str(out),baseline=str(base),baseline_seal=a.baseline_seal,qualification=str(QUAL/'qualification.json'),
        qualification_seal=Q_SHA,input_pins=products['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':life.save(record,proposal);print('PREPARED_NOT_ADMITTED',life.digest(record),flush=True);return
    require(life.read_bound(record,a.seal)==proposal,'Prepared proposal drift')
    if a.mode=='verify':print('VERIFY_PASS_NO_ADMISSION',flush=True);return
    out.mkdir()
    for n,v in products.items():life.save(out/n,v)
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/n).open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(record),prepared_seal=a.seal,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED',life.digest(out/'admission-manifest.json'),flush=True)


if __name__=='__main__':main()
