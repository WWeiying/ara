"""Window-qualified custom identity permits finite CVX ID reuse between phases."""
import argparse
import csv
import json
from pathlib import Path

import qualify_gap105_native_v2 as parent
import qualify_gap105_native_v3 as predecessor

frozen,life,require = parent.frozen,parent.life,parent.require
PREDECESSOR_SEAL = '09391bc1089ecf0731711ca918c3d80c5a96273c7ad331b6005c1dc1dc143f98'


def bind_custom(seq, pc, key, start, retire, matches, claimed):
    require(len(matches)==1,'Custom window does not identify one response')
    begin,end = matches[0]
    require(start<=begin<=end<=retire,'Custom response outside architecture window')
    transaction = (key,begin,end)
    require(transaction not in claimed,'Custom response window already claimed')
    claimed.add(transaction)
    return dict(arch_seq=seq,pc=pc,trans_id=key,arch_start=start,request=begin,response=end,retire=retire)


def runtime(run, symbols, data, sites, native):
    contract = frozen.software(run/'run.vcs.log')
    trace = frozen.validate_trace(run/'commit_trace.csv')
    with (run/'commit_trace.csv').open() as stream: rows = list(csv.DictReader(stream))
    retires = [r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retires]==list(range(len(retires))) and
            all(not int(r['trap']) for r in retires),'Incomplete/trapped retirement prefix')
    pending = {}; starts = {}; responses = {}; request_count = response_count = 0
    for row in rows:
        event = row['event']; key = int(row['trans_id']); cycle = int(row['cycle'])
        if event=='arch_start':
            seq = int(row['order']); require(seq not in starts,'Duplicate arch_start')
            starts[seq] = (int(row['insn'],16),key,cycle)
        elif event=='cvx_req':
            require(key not in pending,'Duplicate transaction')
            pending[key] = (int(row['insn'],16),cycle); request_count += 1
        elif event=='cvx_resp':
            require(key in pending and not int(row['trap']),'Orphan/trapped response')
            word,begin = pending.pop(key); require(begin<=cycle,'Response before request')
            responses.setdefault((word,key),[]).append((begin,cycle)); response_count += 1
    require(not pending and request_count==response_count==contract['requests'],
            'Complete request/response/contract conservation differs')
    arch,retired_vector,trapped = frozen._parse_architecture_mapping(run/'commit_trace.csv')
    mapping = frozen._map_architecture_retires(arch,retired_vector,trapped)
    lanes,vlen,activities = frozen._parse_vector_trace(run/'vector_trace.csv')
    require((lanes,vlen)==(4,1024),'Wrong vector configuration')
    wanted = []
    for phase in (0,1):
        wanted += [s['pc'] for s in sites[phase][:4]]+[symbols['gap105_qbexec_site%d'%phase][0]]
        wanted += [s['pc'] for s in sites[phase][4:]]
    selected = sorted(activities,key=lambda s:starts[s][2])
    require(len(selected)==18 and [mapping[s].pc for s in selected]==wanted,
            'Unexpected/missing seed/custom/snapshot activities')
    seed_sequences = {s for p in (0,1) for s in selected[p*9:p*9+4]}
    retire_cycles = {}
    for seq in selected:
        matched = [r for r in retires if int(r['pc'],16)==mapping[seq].pc and
                   int(r['insn'],16)==mapping[seq].instruction]
        require(len(matched)==1,'Ambiguous site retirement')
        retire_cycles[seq] = int(matched[0]['cycle'])
    owners = {}; done = set(); windows = {}
    with (run/'vector_trace.csv').open() as stream: vector_rows = list(csv.DictReader(stream))
    for row in vector_rows:
        if row['event']=='config': continue
        require(row['event'] in ('alloc','write','done'),'Unexpected vector event/reset')
        seq,vid,cycle = int(row['arch_seq']),int(row['vid']),int(row['cycle'])
        require(seq in activities,'Unbound vector activity')
        if row['event']=='alloc':
            require(seq not in owners and seq not in done,'Duplicate vector allocation')
            require(starts[seq][2]<=cycle,'Allocation precedes architecture start')
            owners[seq] = (vid,cycle)
        else:
            require(seq in owners and owners[seq][0]==vid and owners[seq][1]<=cycle,
                    'Vector event outside lifecycle')
            if row['event']=='done':
                if seq not in seed_sequences:
                    require(cycle<=retire_cycles[seq],'Custom/store completion after retirement')
                windows[seq] = (owners[seq][1],cycle)
                owners.pop(seq); done.add(seq)
    require(not owners and done==set(selected),'Incomplete vector lifecycle')
    commit_uops = [(r['event'],int(r['order']),int(r['port']),int(r['cycle'])) for r in rows
                  if r['event'] in ('uop_alloc','uop_done')]
    vector_uops = [('uop_'+r['event'],int(r['arch_seq']),int(r['vid']),int(r['cycle']))
                   for r in vector_rows if r['event'] in ('alloc','done')]
    require(sorted(commit_uops)==sorted(vector_uops),'Commit/vector lifecycle probes differ')
    bindings = []; claimed_custom_responses = set()
    for phase in (0,1):
        group = selected[phase*9:(phase+1)*9]; custom_seq = group[4]
        custom_alloc = windows[custom_seq][0]
        require(all(windows[s][1]<custom_alloc for s in group[:4]),
                'Seed completion crosses custom consumer allocation')
        for i,seq in enumerate(group):
            a = activities[seq]; word,key,start = starts[seq]; retired = mapping[seq]
            require(a.instruction==word==retired.instruction,'Opcode/activity/retirement differs')
            match = [(begin,end) for begin,end in responses.get((word,key),[])
                     if start<=begin<=end<=retire_cycles[seq]]
            require(len(match)==1,'Ambiguous/missing activity response')
            begin,end = match[0]; alloc,completion = windows[seq]
            if i<4:
                reg = i*8; seed = frozen.seed_image(phase)
                require(a.vd==reg and a.vl==256,'Complete seed load configuration differs')
                expected = {(r,b):seed[r*128+b] for r in range(reg,reg+8) for b in range(128)}
                frozen.activity_bytes(a,expected,alloc,completion)
            elif i==4:
                expected = {(8+c,b):value for c,bits in enumerate(native[2])
                            for b,value in enumerate(frozen.struct.pack('<I',bits))}
                require(completion<=end,'Custom completion after terminal response')
                frozen.activity_bytes(a,expected,alloc,completion,custom=True)
                custom_binding = bind_custom(seq,retired.pc,key,start,retire_cycles[seq],
                                             match,claimed_custom_responses)
            else:
                require(completion<=end,'Store completion after terminal response')
                require(not a.writes and a.allocations==a.completions==1,'Snapshot store wrote VRF/incomplete')
        require(all(retire_cycles[s]<=starts[custom_seq][2] for s in group[:4]) and
                all(retire_cycles[custom_seq]<=starts[s][2] for s in group[5:]),
                'Seed/custom/snapshot ordering differs')
        if phase:
            require(retire_cycles[selected[8]]<starts[group[0]][2],'Commands overlap')
        start = retire_cycles[custom_seq]
        end = starts[selected[9]][2] if phase==0 else max(int(r['cycle']) for r in rows)+1
        # All dependent scalar readbacks must occur after the seed data is complete.
        require(all(windows[s][1]<=start for s in group[:4]),'Seed completion crosses readback window')
        evidence = frozen.phase_readback(rows,start,end,symbols,frozen.regions(phase,symbols,data,native))
        bindings.append(dict(phase=4+4*phase,arch_seq=custom_seq,pc=mapping[custom_seq].pc,
            backend_vl=256,software_vl=1,native_active_write_bytes=32,readback_bytes=evidence,
            custom_binding=custom_binding,
            seed_windows=[dict(arch_seq=s,alloc=windows[s][0],done=windows[s][1],
                               retire=retire_cycles[s]) for s in group[:4]],custom_alloc=custom_alloc))
    require(sum(a.instruction==frozen.WORD for a in activities.values())==2,'Custom population differs')
    return dict(status='COMPLETE_SOFTWARE_NATIVE_QUALIFIER_V4_PASS_NOT_FULL_SCALAR_ISA',
        contract=contract,trace=trace,bindings=bindings,custom_write_bytes=64,full_vrf_bytes=8192,
        initial_vrf_bytes=8192,csr_values=24,source_guard_bytes=6880,checks=41,
        full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False)


def prepare(run, reviewed_seal):
    config = predecessor.prepare(run,reviewed_seal)
    pins = life.merge_pins(config['pins'],{str(Path(predecessor.__file__).resolve()):PREDECESSOR_SEAL})
    build = life.read_bound(parent.BUILD,parent.BUILD_SEAL)
    interface = life.ROOT/'hardware/include/ara/intf_typedef.svh'
    pins = life.merge_pins(pins,{str(interface):build[str(interface)]})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_qualify_gap105_native_v4.py')):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    require('logic [CVA6Cfg.TRANS_ID_BITS-1:0] trans_id;' in interface.read_text(),
            'Finite-width transaction ID interface differs')
    config = dict(config,status='GAP105_NATIVE_QUALIFIER_V4_PREPARED_NOT_EXECUTED',pins=pins,
        custom_identity='arch_seq/retired PC/start/request/response/retire window; no global ID uniqueness')
    life.check(pins)
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','collect'))
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--prepared-seal',required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--config-seal')
    args = parser.parse_args(argv)
    require((args.mode=='collect')==bool(args.config_seal),'Collect alone requires reviewed qualifier seal')
    output = args.output.absolute()
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(),'Fresh independent sidecar required')
    config = prepare(args.run,args.prepared_seal)
    path = output.with_name(output.name+'.prepared.json')
    if args.mode=='prepare':
        life.save(path,config)
        print(json.dumps(dict(config=str(path),seal=life.digest(path),pins=len(config['pins'])))); return
    require(life.read_bound(path,args.config_seal)==config,'Reviewed qualifier config differs')
    run = Path(config['run']); pins = life.merge_pins(config['pins'],{str(path):args.config_seal})
    status_path = run/'simulation-status.json'; status_hash = life.digest(status_path)
    status = life.read_bound(status_path,status_hash)
    require(status.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and status.get('returncode')==0 and
            status.get('coverage_admitted') is False,'Not a clean terminal run')
    pins = life.merge_pins(pins,{str(status_path):status_hash})
    required = [run/n for n in ('manifest.json','started.json','console.log','run.vcs.log',
                               'commit_trace.csv','vector_trace.csv')]
    required += [p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    require(any(p.name=='cond.verilog.data.xml' for p in required),'Missing raw condition bitmap')
    for p in required: pins = life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    reviewed = life.read_bound(run.with_name(run.name+'.prepared.json'),args.prepared_seal)
    require(life.read_bound(run/'manifest.json',pins[str(run/'manifest.json')])==reviewed,'Runtime manifest differs')
    output.mkdir(); life.save(output/'evidence-pins.json',pins)
    try:
        symbols,data,sites = frozen.elf_view()
        audit = runtime(run,symbols,data,sites,frozen.independent_native())
        life.check(pins)
        life.save(output/'runtime-audit.json',audit)
        life.save(output/'qualification.json',dict(status='GAP105_SOFTWARE_NATIVE_V4_QUALIFIED_NOT_ADMITTED',
            audit_sha256=life.digest(output/'runtime-audit.json'),pins_sha256=life.digest(output/'evidence-pins.json'),
            full_scalar_isa_verified=False,coverage_admitted=False,coverage_increment_measured=False,
            gain_requires_latest_formal_baseline=True,simulation_rerun=False,rtl_changed=False))
    except Exception as error:
        life.save(output/'qualification.json',dict(status='GAP105_NATIVE_QUALIFIER_V4_REJECTED',
            reason=type(error).__name__+': '+str(error),coverage_admitted=False))
        raise
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'qualification.json'))))


if __name__=='__main__': main()
