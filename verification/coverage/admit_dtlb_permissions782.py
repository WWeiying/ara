"""Offline formal781+qualified scalar permissions: prepare/verify, parent-only admit."""
import json
from pathlib import Path
from types import FunctionType

import admit_akv_entropy777 as publish
import admit_dtlb_ppn_swap780 as prior
import collect_dtlb_permissions780_scalar as case
from rank_cva6_scalar_data767 import typed_nodes

life,require=case.life,case.require
BASE=life.OUT/'akv-tile-range-admitted781-parent-20261008-01'
BASE_SHA='720511a144576a95fee244a675635c96104b249c0f99ab3d6b8e0249de77f900'
QUAL=life.OUT/'dtlb-permissions-qualified780-scalar-agent-20261008-01'
Q_SHA='603ee851e1f9e505805a7f113263ebe9827bb8cf1c74ebcb4e0e879e687ee38d'
RUN=life.OUT/'dtlb-permissions780-agent-20261008-01'
PREPARED_SHA='13484ec02db18086914486561dc69693de57f8ef42216870ebe605f220a8fe12'
COUNTS=dict(line=1892,cond=2023,branch=2155,fsm=92)
native_identity=FunctionType(prior.native_identity.__code__,dict(prior.native_identity.__globals__,RUN=RUN))


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==781 and
            single['tests']==[str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'],
            'Exact781 prefix and distinct candidate')
    require(set(before['metrics'])==set(single['metrics'])==set(COUNTS),'All four metrics')
    require(all(len(before['metrics'][m])==n for m,n in COUNTS.items()),'All6162 metric instances')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    after=prior.bitmap.combine(before,single)
    publish.case.independent_or(before,single,after)
    for rows in after['metrics'].values():
        for row in rows.values():
            require(type(row['width']) is int and row['width']>=0 and
                    0<=int(row['bits'],16)<(1<<row['width']),'Exact binary bounds')
    return after


def architecture(q,scalar,memory,vector,wave,preflight):
    require(q['status']=='DTLB_PERMISSIONS780_SCALAR_FAULT_QUALIFIED_NOT_ADMITTED' and
            q['baseline']==780 and q['prepared_seal']==PREPARED_SHA and q['coverage_admitted'] is False and
            q['VCS_rerun'] is False and type(q['scalar_faults_proven']) is int and q['scalar_faults_proven']==5 and
            q['scalar_trap_rows_observable'] is False,'Exact sealed scalar-fault qualification')
    expected={k:preflight['counts'][k] for k in ('matched_instructions','matched_scalar_writes',
              'matched_floating_writes','matched_scalar_memory_accesses')}
    case.runner.software.p.shared.architecture.scalar_exact(scalar,expected)
    require(scalar['matched_instructions']==193080 and scalar['matched_scalar_writes']==112155 and
            scalar['matched_scalar_memory_accesses']==2716 and scalar['ara_trap_events']==0,
            'Complete source-bound scalar ISA and nonobservable trap rows')
    for key,value in dict(status='ALL_INTEGER_RVC_AND_UNCOMPRESSED_MEMORY_EXACT',retired=193080,
        compressed=17141,uncompressed=2716,loads=9245,stores=10612,total=19857,skipped=0,
        native_trap_rows=0,trap_rows_observable=False).items():
        require(type(memory[key]) is type(value) and memory[key]==value,'Exact full scalar/RVC obligation '+key)
    case.zero_schema.vector_zero(vector)
    require(preflight['counts']['software_checks']==8378 and
            preflight['counts']['complete_physical_guard_bytes']==65536 and
            preflight['counts']['full_pte_slots']==1536,'Full gold, PTE and guards')
    require(len(wave['replacements'])==56 and wave['global_asid_fence_cycles']>=1 and
            len(wave['fault_samples'])==len(memory['handler_faults'])==5,'Actual native slots/global/fault population')
    for phase in range(3):
        require({r['slot'] for r in wave['replacements'][phase*16:(phase+1)*16]}==set(range(16)),
                'All actual16 slots per contrast phase')
    require(case.link_fault_cycles(wave,memory)==wave['handler_cycle_linkage'],'Exact five MMU-to-handler owners')
    for sample,gold in zip(wave['fault_samples'],[r for r in case.runner.software.audit.cases() if r['mcause']]):
        require((sample['cause'],sample['tval'],sample['effective_privilege'],sample['SUM'],sample['MXR'])==
                (gold['mcause'],gold['mtval'],int(gold['effective_privilege']=='S'),int(gold['SUM']),int(gold['MXR'])),
                'Exact source-bound native fault phase')


def evaluate():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE) and
            base['baseline']==str(case.runner.BASE) and base['baseline_seal']==case.runner.BASE_SHA,
            'Exact formal781 genealogy from frozen780')
    q=life.read_bound(QUAL/'qualification.json',Q_SHA)
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(authority,life.merge_pins(q['input_pins'],q['output_pins']))
    def previous(name):return life.read_bound(BASE/name,base['output_pins'][str(BASE/name)])
    def product(name):return life.read_bound(QUAL/name,q['output_pins'][str(QUAL/name)])
    before=previous('combined-bits.json');status=previous('status.json')
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(life.IMAGE)+'.vdb',*before['tests']] and len(ledger)==len(set(ledger))==782 and
            status['aggregate_passed']==781 and status['coverage_admitted'] is True,'Exact formal781 ledger/status')
    old=life.read_bound(case.runner.BASE/'admission-manifest.json',case.runner.BASE_SHA)
    old_ledger=case.runner.BASE/'combined-inputs.txt'
    require(life.digest(old_ledger)==old['output_pins'][str(old_ledger)] and
            ledger[:-1]==old_ledger.read_text().splitlines(),'Every780 prefix byte preserved')
    prepared=RUN.with_name(RUN.name+'.prepared.json');record=case.runner.check(prepared,PREPARED_SHA)
    require(life.read_bound(RUN/'manifest.json',pins[str(RUN/'manifest.json')])==
            dict(record,pins=life.merge_pins(record['pins'],{str(prepared):PREPARED_SHA})),
            'Exact actual run manifest from approved prepared')
    case.terminal_gate(life.read_bound(RUN/'simulation-status.json',pins[str(RUN/'simulation-status.json')]))
    case.identity_gate(life.read_bound(RUN/'live-simv-identity.json',pins[str(RUN/'live-simv-identity.json')]),record)
    preflight=life.read_bound(case.runner.PRE,case.runner.PRE_SHA)
    architecture(q,product('scalar-comparison.json'),product('memory-audit.json'),
                 product('vector-comparison.json'),product('actual-replacements.json'),preflight)
    case.logs((RUN/'console.log').read_text(),(RUN/'run.vcs.log').read_text(),preflight['symbols'])
    db=RUN/'code.vdb';members=sorted(p for p in db.rglob('*') if p.is_file())
    require(not any(p.is_symlink() for p in db.rglob('*')) and
            {str(p) for p in members}=={p for p in q['input_pins'] if p.startswith(str(db)+'/')},
            'Complete immutable terminal VDB membership')
    folder=db/'snps/coverage/db/testdata'/case.runner.CASE
    require(list(folder.parent.iterdir())==[folder],'One exact native test owner')
    identity=native_identity(prior.toggle.xml(folder/'siminfo.xml'),prior.toggle.xml(folder/'vcmArguments.xml'),record,ledger[0])
    design_db=Path(ledger[0])/'snps/coverage/db'
    require(all(life.digest(design_db/rel)==h==pins[str(design_db/rel)] for rel,h in before['design'].items()),
            'Full frozen design fingerprint')
    single=dict(design=before['design'],tests=[str(db)],input_hashes={},metrics={})
    for metric in prior.bitmap.METRICS:
        path=folder/(metric+'.verilog.data.xml')
        require(pins[str(path)]==life.digest(path),'Native metric pin')
        single['metrics'][metric]=prior.bitmap.read_metric(path);single['input_hashes'][str(path)]=pins[str(path)]
    after=full_union(before,single);delta=prior.bitmap.delta(before,after)
    # Existing780 DTLB gain is kept intact; extend its sealed after by only the781 suffix.
    retained=previous('dtlb-toggle-gain.json')
    require(retained['baseline']==779 and retained==life.read_bound(case.runner.BASE/'dtlb-toggle-gain.json',
            old['output_pins'][str(case.runner.BASE/'dtlb-toggle-gain.json')]),'Original DTLB780 record unchanged')
    scope=case.SCOPE
    def sample(vdb,evidence):
        files=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'One Toggle sample')
        rows,h=prior.toggle.rows(files[0],[scope]);require(evidence.get(str(files[0]))==h,'Sealed Toggle source')
        return rows
    t_before=prior.toggle.union({scope:retained['after']},sample(ledger[-1],authority))
    t_single=sample(str(db),q['input_pins']);t_after=prior.toggle.union(t_before,t_single)
    positions=prior.toggle.gains(t_before,t_after)[scope]
    require(t_before[scope]['width']==11852 and t_before[scope]['checksum']=='817233724' and positions,
            'Exact DTLB native identity and positive rebased gain')
    checks,defs=prior.toggle.definitions(*(prior.toggle.xml(design_db/rel) for rel in
        ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')),[scope])
    require(checks[scope]=='817233724','Exact compiled DTLB checksum')
    nodes,arrays=typed_nodes(defs[scope]['shape'],t_before[scope])
    fresh=set(positions)
    targets=[dict(n,new_coordinates=sorted(fresh.intersection(n['missing_coordinates']))) for n in nodes
             if n['name'].startswith(('content_q[','content_n[')) and '.pte.' in n['name'] and
             n['name'].rsplit('.',1)[1] in ('x','u','g','r','w','d')]
    gain=dict(baseline=781,scope=scope,before=t_before[scope],single=t_single[scope],after=t_after[scope],
        new_positions=len(positions),new_serialized_positions=positions,typed_attribute_targets=targets,
        attribute_new_positions=sum(len(n['new_coordinates']) for n in targets),
        arrays_not_flattened=len(arrays),official_percentage=False,direction_labels_verified=False,
        retained_780_gain_not_recounted=True)
    elf=case.runner.PRE.parent/'input.elf'
    elf_audit=prior.dedup(ledger,pins[str(elf)],authority)
    require(elf_audit['ledger_members']==781 and elf_audit['duplicate'] is False and
            [r['vdb'] for r in elf_audit['members']]==ledger[1:] and
            all(authority.get(p)==h for p,h in elf_audit['pins'].items()),'Historical-only781 ELF dedup/pins')
    elf_audit=dict(elf_audit,baseline=781,candidate_qualification_not_used_as_historical_owner=True)
    pins=life.merge_pins(pins,elf_audit['pins'])
    fixed={str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):Q_SHA,
           str(prepared):PREPARED_SHA,str(old_ledger):old['output_pins'][str(old_ledger)]}
    for module in (prior,publish,publish.case,prior.bitmap,prior.toggle,case):
        path=Path(module.__file__).resolve();fixed[str(path)]=life.digest(path)
    for path in (Path(__file__),Path(__file__).with_name('test_admit_dtlb_permissions782.py'),
                 Path(prior.dedup.__code__.co_filename)):
        fixed[str(path.resolve())]=life.digest(path)
    pins=life.merge_pins(pins,fixed);life.check(pins)
    products={Path(p).name:previous(Path(p).name) for p in base['output_pins']
              if Path(p).parent==BASE and Path(p).suffix=='.json' and
              ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'dtlb-permissions-toggle-gain781.json':gain,'native-vdb-identity.json':identity,
        'elf-ledger-dedup.json':elf_audit,'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=781,aggregate_passed=782,
            new_passed=1,coverage_admitted=True,exact781_prefix=True,full_OR_metric_instances=6162,
            unique_new_vdb=True,duplicate_ELF=False,full_scalar_ISA=True,scalar_retired=193080,
            full_scalar_memory_instructions=19857,checks=8378,scalar_faults=5,actual_updates=56,
            actual_slots_per_phase=16,vector_status='UNOBSERVABLE_ZERO_REQUESTS',vector_comparison_PASS=False,
            scoped_DTLB_new_toggle_positions=len(positions),attribute_new_positions=gain['attribute_new_positions'],
            raw_delta=delta['metrics'],new_simulation=False,RTL_changed=False,
            official_percentage_claimed=False,retained_prior_gain_not_recounted=True)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    namespace=dict(publish.main.__globals__,evaluate=evaluate,BASE=BASE,BASE_SHA=BASE_SHA,
                   QUAL=QUAL,Q_SHA=Q_SHA,C_SHA=None)
    FunctionType(publish.main.__code__,namespace)()


if __name__=='__main__':main()
