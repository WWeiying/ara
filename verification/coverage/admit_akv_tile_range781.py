"""Thin offline780+one tile-range admission, reusing entropy777 OR/dedup/publisher."""
import json
from pathlib import Path
import shlex
from types import FunctionType

import admit_akv_entropy777 as safe
import run_akv_tile_range_capture as runner
import collect_akv_tile_range_capture as case

life,require=runner.life,runner.require
BASE,BASE_SHA,RUN=runner.BASE,runner.BASE_SHA,life.OUT/'akv-tile-range-old-image780-agent-20261008-01'
QUAL=life.OUT/'akv-tile-range-qualified780-parent-20261008-01'
Q_SHA='2b504347a58f57693de2476b5765d8e41e317bf32d8b9e5402702870df02eab2'
RUN_SHA='569ea772b7e53268aa5276ff1b4f1aa1e4ce7e546bd9d138cccc8149e5f46623'
ELF_SHA='4b7aaefe11b7bbff78f55e98b4e4690575a30ffb25798abee65c4f85b45f3ca0'


def qualification(q,scalar,vector,contract,native,arch,perf):
    require(q['status']=='AKV_TILE_RANGE_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED' and q['baseline_tests']==780
            and q['scalar_model_skips']==0 and q['native_Spike_comparison'] is False and q['coverage_admitted'] is False,'Exact native qualification')
    require(scalar['status']=='INDEPENDENT_NATIVE_ISA_MODEL_MATCH' and scalar['steps']==67122
            and scalar['matched_retirements']==67119 and scalar['GPR_writes']==48703 and scalar['skipped_retirements']==0
            and scalar['traps']==3 and scalar['native_Spike_comparison'] is False,'Complete native ISA zero skips')
    require(vector==dict(seed_bytes=4096,custom_bytes=128,snapshot_bytes=24576,full_frames=6,rejected_write_bytes=0),'Full VRF/guards and rejected no-writes')
    require(contract==dict(requests=270,responses=270,exceptions=3,mmu_request_cycles=0,protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0),'Native terminal protocol')
    require(native['accepted64_indices']==case.case.INDICES and native['validation_errors']==[11,11,11]
            and native['rejected_payload_AR']==0 and len(native['commands'])==6,'Actual full64 capture and TILE_RANGE')
    require(len(arch['commands'])==6 and [c['validation_error'] for c in arch['commands']]==[11,11,11,0,0,0]
            and [c['write_bytes'] for c in arch['commands']]==[0,0,0,0,128,0],'Native per-command ownership')
    require(len(perf)==6 and [p['validation_error'] for p in perf]==[11,11,11,0,0,0]
            and [p['read_payload_bytes'] for p in perf]==[64,64,64,448,0,0]
            and [p['replay_bytes'] for p in perf]==[0,0,0,0,128,0],'Exact observed ranges/recovery')


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==780 and single['tests']==[str(RUN/'code.vdb')]
            and single['tests'][0] not in before['tests'],'Exact780 prefix plus distinct single candidate')
    require(set(before['metrics'])==set(single['metrics'])==set(safe.bitmap.METRICS)
            and sum(len(v) for v in before['metrics'].values())==6162,'All6162 instances/four metrics')
    after=safe.bitmap.combine(before,single); safe.case.independent_or(before,single,after)
    return after


def gain_gate(g):
    b,s,a=g['before'],g['single'],g['after']
    require(g['baseline']==780 and all(r['width']==12374 and r['checksum']=='4015856550' for r in (b,s,a)),'Exact AKV Toggle identity')
    require(int(a['bits'],16)==int(b['bits'],16)|int(s['bits'],16),'Actual Toggle OR')
    fresh=int(a['bits'],16)&~int(b['bits'],16)
    expected=[4238+2*bit+d for bit in range(64) if bit not in (0,1,3,6) for d in (0,1)]
    actual=[i for i in range(b['width']) if fresh>>(b['width']-1-i)&1]
    require(actual==expected==g['requested_tile_new_indices'] and g['requested_tile_new_directions']==g['new_positions']==120
            and g['official_percentage_claimed'] is False and g['coverage_admitted'] is False,'Positive measured120 exact directions')


def typed_target(nodes,g):
    rows=[n for n in nodes if n['name']=='requested_tile_start_q']
    require(len(rows)==1,'Unique exact requested tile object')
    row=rows[0]
    require((row['left'],row['right'],row['serialized_offset'],row['logical_width'],row['portnode'],row['excluded'])==
            ('63','0',4238,64,'0','0') and row['missing_coordinates']==g['requested_tile_new_indices'],
            'Compiled type/offset/source target missing-coordinate binding')
    return row


def native_identity(sim,args,command,design):
    require(sim.tag=='test' and len(sim.findall('srctest'))==1,'One native test')
    row=sim.find('srctest')
    require(shlex.split(row.get('cmdline',''))==command and row.get('workdir')==str(RUN)
            and row.get('seed')=='1' and row.get('teststatus')=='unknown'
            and row.get('starttime')=='1791451712699973' and row.get('finishtime')=='1791451988390044','Exact actual completed native run identity')
    require(args.tag=='vcm_args' and args.get('compvdbpath')==design and
        sorted(n.get('vcm_opt') for n in args.findall('vcm_arg_data') if n.get('vcm_opt'))==
        ['-cm branch','-cm cond','-cm fsm','-cm line','-cm tgl'],'Compatible native five metrics')
    return dict(workdir=str(RUN),command=command,compvdb=design,seed=1,starttime=row.get('starttime'),
        finishtime=row.get('finishtime'),XML_teststatus='unknown',functional_PASS_authority='sealed independent native qualification')


def evaluate():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal780 identity')
    q=life.read_bound(QUAL/'qualification.json',Q_SHA)
    def product(name): return life.read_bound(QUAL/name,q['output_pins'][str(QUAL/name)])
    def previous(name): return life.read_bound(BASE/name,base['output_pins'][str(BASE/name)])
    qualification(q,*(product(n) for n in ('scalar.json','vector.json','contract.json','native-capture.json','lifecycle.json','perf.json')))
    pins=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(pins,q['input_pins']); pins=life.merge_pins(pins,q['output_pins'])
    m=life.read_bound(RUN/'manifest.json',RUN_SHA)
    record=RUN.with_name(RUN.name+'.prepared.json')
    require(m==life.read_bound(record,RUN_SHA) and m['baseline_sha256']==BASE_SHA and m['baseline_tests']==780
            and m['pins'][str(runner.ELF)]==ELF_SHA and pins[str(runner.ELF)]==ELF_SHA
            and m['command']==runner.command(RUN),'Same prepared/executed image/ELF/baseline')
    case.old.terminal_gate(json.loads((RUN/'simulation-status.json').read_bytes()),json.loads((RUN/'started.json').read_bytes()),m,RUN,life.IMAGE,runner.ELF)
    before=previous('combined-bits.json'); ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(len(ledger)==len(set(ledger))==781 and ledger[1:]==before['tests'],'Exact780 input order')
    status=previous('status.json'); require(status['aggregate_passed']==780 and status['coverage_admitted'] is True,'Full prior780 retained')
    single_inputs=QUAL/'single-inputs.txt'
    require(single_inputs.read_text().splitlines()==[ledger[0],str(RUN/'code.vdb')],'Pinned qualified singleton')
    life.check(pins)
    # Fresh singleton extraction only, not a simulation or architecture replay.
    single=safe.bitmap.collect(single_inputs)
    require(single==product('single-bits.json') and all(pins.get(p)==h for p,h in single['input_hashes'].items()),'Fresh singleton equals qualified data')
    for rel,h in single['design'].items(): require(pins.get(str(Path(ledger[0])/'snps/coverage/db'/rel))==h,'Compiled design/hash bound')
    after=full_union(before,single)
    require(after==product('combined-bits-diagnostic.json'),'Qualified exact780 raw union')
    delta=safe.bitmap.delta(before,after); require(delta==product('raw-delta.json'),'All raw metric deltas')
    folder=RUN/'code.vdb/snps/coverage/db/testdata'/runner.NAME
    require(list(folder.parent.iterdir())==[folder],'One native test folder')
    def xml(name):
        path=folder/name; require(pins.get(str(path))==life.digest(path),'Native XML pin')
        data=path.read_bytes(); return safe.ET.fromstring(safe.gzip.decompress(data) if data[:2]==b'\x1f\x8b' else data)
    identity=native_identity(xml('siminfo.xml'),xml('vcmArguments.xml'),m['command'],ledger[0])
    gain=product('toggle-gain780.json'); gain_gate(gain)
    db=Path(ledger[0])/'snps/coverage/db'
    checks,defs=safe.toggle.definitions(*(safe.toggle.xml(db/p) for p in
        ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')),[case.SCOPE])
    require(checks[case.SCOPE]=='4015856550','Exact compiled Toggle definition')
    nodes,_=case.case.old.typed_nodes(defs[case.SCOPE]['shape'],gain['before'])
    target=typed_target(nodes,gain)
    rows,h=safe.toggle.rows(folder/'tgl.verilog.data.xml',[case.SCOPE])
    require(pins.get(str(folder/'tgl.verilog.data.xml'))==h and rows[case.SCOPE]==gain['single'],'Native Toggle single exact')
    hp,dedup=runner.historical(ledger,base,ELF_SHA); pins=life.merge_pins(pins,hp)
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):Q_SHA,
        str(record):RUN_SHA,str(RUN/'manifest.json'):RUN_SHA,str(Path(__file__).resolve()):life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_admit_akv_tile_range781.py').resolve()):life.digest(Path(__file__).with_name('test_admit_akv_tile_range781.py'))})
    for module in (safe,runner,case,safe.bitmap,safe.toggle,life):
        p=Path(module.__file__).resolve(); pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    # Preserve every already-admitted gain record, including ITLB/DTLB, without recounting.
    products={Path(p).name:previous(Path(p).name) for p in base['output_pins'] if Path(p).parent==BASE and 'toggle-gain' in Path(p).name and Path(p).suffix=='.json'}
    products.update({'combined-bits.json':after,'single-bits.json':single,'raw-delta.json':delta,
        'akv-tile-range-toggle-gain780.json':gain,'native-vdb-identity.json':identity,'typed-toggle-target.json':target,'elf-ledger-dedup.json':dedup,
        'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=781,baseline=780,
            new_passed=1,coverage_admitted=True,exact780_prefix=True,full_OR_metric_instances=6162,unique_new_vdb=True,
            duplicate_ELF=False,scoped_toggle_new_serialized_positions=120,raw_delta=delta['metrics'],
            prior_gain_records_retained_not_recounted=True,native_Spike_comparison=False,independent_native_qualification=True,
            official_percentage_claimed=False,new_simulation=False,RTL_changed=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    # Keep the reviewed777 publication/verify/explicit-parent authorization body unchanged.
    def display(*args,**kwargs):
        labels={'PREPARED777_NOT_ADMITTED':'PREPARED781_NOT_ADMITTED','ADMITTED777':'ADMITTED781'}
        print(*(labels.get(x,x) if isinstance(x,str) else x for x in args),**kwargs)
    globals_=dict(safe.main.__globals__,evaluate=evaluate,BASE=BASE,BASE_SHA=BASE_SHA,QUAL=QUAL,Q_SHA=Q_SHA,
                  C_SHA=None,print=display)
    FunctionType(safe.main.__code__,globals_)()


if __name__=='__main__': main()
