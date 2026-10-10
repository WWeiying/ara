"""Exact frozen771 plus the one diagnosed PASS VDB. Offline, no admission/EDA."""
import argparse
import csv
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import diagnose_scalar_fpu_backpressure_v2 as reviewed
import targeted_toggle_evidence_v2 as t
import rank_cva6_scalar_data767 as typed

p=reviewed.p
life,require=p.life,p.require
DIAG=reviewed.OUT/'diagnostic.json'
DIAG_SHA='43cd1797e92381af7e9a87fa8d6ec41b1d2d6fd9d86dc5eabce2583c4184be3a'
BINDING=reviewed.OUT/'reviewed-consumer-binding.json'
BINDING_SHA='6f7f8adec7e82c73f1b836a1540ace88b5410e81cba05dd5d7ea18dc31660ed5'
CACHE=typed.CACHE
CACHE_SHA=typed.CACHE_SHA
DESIGN=Path(str(life.IMAGE)+'.vdb')


def contract(q):
    require(q['status']=='OFFLINE_ARCHITECTURE_AND_BACKPRESSURE_DIAGNOSED_NOT_ADMITTED' and
        q['checks']==22 and q['coverage_admitted'] is False and q['simulation_repeated'] is False and
        q['original_artifacts_modified'] is False, 'Exact reviewed functional diagnosis')
    require(q['scalar_counts']==dict(matched_instructions=285,matched_scalar_writes=114,
        matched_floating_writes=40,matched_scalar_memory_accesses=96), 'Full reference counts')
    require(q['contract']==dict(requests=0,responses=0,exceptions=0,mmu_request_cycles=0,
        protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0), 'Complete zero protocol')
    wave=q['backpressure']
    require(wave['observed'] is True and wave['captured_released']==12 and wave['stall_cycles']==64
        and len(wave['witnesses'])==12 and wave['idle_ownerless_flush_times']==[1145000,3485000,6575000],
        'Actual closed capture/hold/release ledger')
    require(q['vector_status']=='UNOBSERVABLE_ZERO_DATA_REQUESTS', 'No fabricated vector PASS')


def pair_coordinates(shape,before,after):
    nodes,arrays=typed.typed_nodes(shape,before)
    require((before['width'],before['checksum'])==(after['width'],after['checksum']), 'Target shape changed')
    gain=t.gains({'s':before},{'s':after})['s'];found=[]
    for n in nodes:
        start=n['serialized_offset'];end=start+2*n['logical_width']
        positions=[i for i in gain if start<=i<end]
        if positions:
            found.append(dict(name=n['name'],declaration_file=n['file'],declaration_line=n['line_num'],
                logical_width=n['logical_width'],left=n.get('left'),right=n.get('right'),
                positions=positions,field_relative_positions=[i-start for i in positions],
                coordinate_semantics='Exact serialized pair slots, physical bit/direction labels not inferred'))
    require(sum(len(r['positions']) for r in found)==len(gain), 'Unmapped binary gain')
    return found,arrays


def positive(four,toggle):
    require(sum(four.values())+toggle>0,'Zero gain cannot justify population append')


def collect(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh direct output')
    binding=life.read_bound(BINDING,BINDING_SHA);q=life.read_bound(DIAG,DIAG_SHA);contract(q)
    require(binding['status']=='OFFLINE_STRICT_IDLE_FLUSH_GATE_BOUND_NOT_ADMITTED' and
        binding['pins'].get(str(DIAG))==DIAG_SHA, 'Exact reviewed strict consumer binding')
    base=life.read_bound(p.BASE/'admission-manifest.json',p.BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(p.BASE),'Formal771 predecessor')
    pins=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(pins,life.merge_pins(q['input_pins'],q['output_pins']))
    pins=life.merge_pins(pins,binding['pins'])
    pins=life.merge_pins(pins,{str(DIAG):DIAG_SHA,str(BINDING):BINDING_SHA,
        str(p.BASE/'admission-manifest.json'):p.BASE_SHA,str(CACHE):CACHE_SHA})
    for module in tuple(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and str(life.ROOT/'verification') in file and Path(file).is_file():
            path=Path(file).resolve();pins=life.merge_pins(pins,{str(path):t.digest(path)})
    own=Path(__file__).resolve()
    pins=life.merge_pins(pins,{str(own):t.digest(own),str(own.with_name('test_collect_scalar_fpu_backpressure_gain771.py')):
        t.digest(own.with_name('test_collect_scalar_fpu_backpressure_gain771.py'))})
    life.check(pins)
    before=life.read_bound(p.BASE/'combined-bits.json',pins[str(p.BASE/'combined-bits.json')])
    ledger=(p.BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(DESIGN),*before['tests']] and len(ledger)==len(set(ledger))==772,
            'Exact771 design/test prefix')
    require(str(p.RUN/'code.vdb') not in ledger,'Duplicate VDB')
    # Recheck the actual sealed scalar and wave results rather than trust status strings.
    scalar=p.old.architecture.spike_trace.compare_commit_prefix(p.PRE/'spike.trace',p.RUN/'commit_trace.csv',
        0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    p.old.architecture.scalar_exact(scalar,q['scalar_counts'])
    require(scalar==json.loads((reviewed.OUT/'scalar-comparison.json').read_bytes()),'Scalar saved/replayed difference')
    require(reviewed.checked_wave_function()(reviewed.OUT/'probe.vcd')==q['backpressure'], 'Wave saved/replayed difference')
    cache=life.read_bound(CACHE,CACHE_SHA)
    prefix=next(Path(x) for x in cache['input_pins'] if x.endswith('/inputs.txt'))
    require(ledger[:742]==life.read_bound(prefix,cache['input_pins'][str(prefix)])
        if prefix.suffix=='.json' else ledger[:742]==prefix.read_text().splitlines(), 'Exact741 cache prefix')
    require(t.digest(prefix)==cache['input_pins'][str(prefix)],'Sealed741 prefix hash')
    pins=life.merge_pins(pins,cache['input_pins'])
    scopes=list(cache['instances'])
    old_t={s:{k:r[k] for k in ('width','checksum','bits')} for s,r in cache['instances'].items()}
    for name in ledger[742:]:
        files=list((Path(name)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique suffix Toggle member')
        rows,sha=t.rows(files[0],scopes)
        require(pins.get(str(files[0]))==sha,'Sealed suffix Toggle SHA')
        old_t=t.union(old_t,rows)
    candidate_files=list((p.RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(candidate_files)==1,'One actual candidate Toggle member')
    candidate,sha=t.rows(candidate_files[0],scopes)
    require(pins.get(str(candidate_files[0]))==sha,'Candidate Toggle already bound by diagnosis')
    new_t=t.union(old_t,candidate);gains=t.gains(old_t,new_t)
    all_gains=[dict(scope=s,width=old_t[s]['width'],checksum=old_t[s]['checksum'],positions=coords,
        new_serialized_positions=len(coords)) for s,coords in gains.items() if coords]
    db=DESIGN/'snps/coverage/db'
    paths=[db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    require(all(str(path) in pins for path in paths),'Compiled Toggle binding missing')
    checks,defs=t.definitions(*(t.xml(path) for path in paths),[p.SCOPE])
    require(checks[p.SCOPE]==old_t[p.SCOPE]['checksum']=='397086886','Exact wrapper checksum')
    mapped,arrays=pair_coordinates(defs[p.SCOPE]['shape'],old_t[p.SCOPE],new_t[p.SCOPE])
    out.mkdir()
    try:
        with (out/'candidate-inputs.txt').open('x') as f:f.write(str(DESIGN)+'\n'+str(p.RUN/'code.vdb')+'\n')
        single=p.bitmap.collect(out/'candidate-inputs.txt')
        require(all(pins.get(path)==sha for path,sha in single['input_hashes'].items()),'Candidate four-metric pins')
        require(all(pins.get(str(db/path))==sha for path,sha in single['design'].items()),'Design/metric shape pins')
        after=p.bitmap.combine(before,single);delta=p.bitmap.delta(before,after)
        require(len(after['tests'])==772 and after['tests'][:771]==before['tests'] and
            sum(len(rows) for rows in after['metrics'].values())==6162,'Full6162 OR/exact771 prefix')
        total=sum(len(v) for v in gains.values())
        report=dict(schema='SCALAR_FPU_BACKPRESSURE_771_GAIN_V1',status='MEASURED_NOT_ADMITTED',
            baseline=771,proposed_population=772,raw_four_metrics=delta['metrics'],
            whole_design_new_serialized_toggle_positions=total,system_new_serialized_toggle_positions=
                sum(len(c) for s,c in gains.items() if s.startswith('ara_tb.dut.i_ara_soc.i_system.')),
            binary_toggle_instances=len(scopes),toggle_instances=all_gains,wrapper_scope=p.SCOPE,
            wrapper_typed_gains=mapped,wrapper_arrays_preserved_not_flattened=arrays,
            official_percentage_claimed=False,native_direction_labels_inferred=False,coverage_admitted=False,
            positive_gain=sum(delta['metrics'].values())+total>0)
        values={'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,'gain.json':report}
        for name,value in values.items():life.save(out/name,value)
        with (out/'combined-inputs.txt').open('x') as f:f.write('\n'.join([str(DESIGN),*after['tests']])+'\n')
        life.check(pins)
        life.save(out/'collection-seal.json',dict(schema='SCALAR_FPU_BACKPRESSURE_GAIN771_SEAL_V1',
            input_pins=pins,output_pins={str(f):t.digest(f) for f in out.iterdir()},
            diagnostic=str(DIAG),diagnostic_seal=DIAG_SHA,consumer_seal=BINDING_SHA,
            baseline_seal=p.BASE_SHA,coverage_admitted=False))
        print(json.dumps(dict(seal=t.digest(out/'collection-seal.json'),four=delta['metrics'],
            toggle=total,wrapper=[(r['name'],len(r['positions'])) for r in mapped])),flush=True)
    except Exception as error:
        life.save(out/'failure.json',dict(reason=str(error),coverage_admitted=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output.absolute())
