#!/usr/bin/env python3
"""Recheck saved evidence with the corrected counter contract; never relabel its producer."""
import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
from check_reader_handoff_v2 import check_log, check_cycles
import check_reader_handoff as original_checker
spec=importlib.util.spec_from_file_location('sealed_handoff_producer',HERE/'run.py')
producer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)
s=producer.s


def audit(run,replay,out,protocol_path=None):
    run,replay,out=run.resolve(strict=True),replay.resolve(strict=True),out.resolve()
    s.require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (run,replay)), 'Independent audit directory required')
    out.mkdir(parents=True,exist_ok=False)
    try:
        status=s.read_json(run/'status.json')
        failed=s.read_json(run/'result.json')
        error="ValueError('QBS context/atomic commit mismatch')"
        s.require(status.get('state')==failed.get('state')=='FAIL' and status.get('child_pid') is None and
                  status.get('running_exit_code')==0 and status.get('error')==failed.get('error')==error,
                  'This audit accepts only the proven original counter-checker failure')
        build=Path(status['build'])
        report,required=producer.checked_build(build)
        pins=s.read_json(run/'source-pins.json')
        s.require(all(pins.get(path)==sha for path,sha in required.items()) and
                  pins.get(str(HERE/'run.py'))==s.digest(HERE/'run.py'), 'Original producer/source binding differs')
        s.verify_pins(pins)
        image=report['accepted_image_pins']
        s.require(status['simv']==report['simv'] and status['elf']==report['elf'] and
                  s.hashes(s.image_files(Path(report['simv'])))==image,'Original image/ELF identity differs')
        log,trace,fsdb=(run/'work'/name for name in ('run.vcs.log','vector_trace.csv','reader.fsdb'))
        raw=log.read_text()
        try:
            original_checker.check_log(raw,(ROOT/'hardware/src/vlsu/vlsu.sv').read_text())
        except ValueError as exc:
            s.require(str(exc)=='QBS context/atomic commit mismatch','Original failure is not reproduced by checker')
        else:
            raise ValueError('Original checker unexpectedly accepts; evidence was changed')
        parsed=check_log(raw,(ROOT/'hardware/src/vlsu/vlsu.sv').read_text())
        metadata=s.read_json(replay/'cycles/metadata.json')
        s.require(Path(metadata['fsdb']).resolve()==fsdb.resolve() and
                  Path(metadata['profile']).resolve()==(build/'profile.json').resolve() and
                  metadata['clock']=='/ara_tb/clk' and metadata['edge']=='negedge' and
                  metadata['begin']=='0ns' and metadata['end']=='500000ns' and
                  metadata['raw_time_unit']=='100fs' and not metadata['missing_signals'] and
                  set(metadata['present_signals'])=={row['alias'] for row in producer.profile()['signals']},
                  'Offline export is not the original complete bounded waveform')
        waves=check_cycles(replay/'cycles/cycles.csv')
        s.require(waves['rows']==metadata['cycle_count'],'Wave row count differs from export receipt')
        protocol=(protocol_path if protocol_path is not None else replay/'uvm_result.json').resolve(strict=True)
        s.check_result(protocol,report['elf_sha256'],image)
        uvm=s.read_json(protocol)
        s.require(uvm['log_sha256']==s.digest(log) and uvm['vector_trace_sha256']==s.digest(trace),'Independent protocol input drift')
        evidence=[run/'status.json',run/'result.json',run/'source-pins.json',log,trace,fsdb,
                  replay/'cycles/metadata.json',replay/'cycles/cycles.csv',replay/'cycles/fsdbreport.raw.csv',protocol]
        own=[Path(__file__),HERE/'check_reader_handoff_v2.py',HERE/'test_check_reader_handoff_v2.py',
             HERE/'test_audit_completed.py',*s.script_files(),Path(sys.executable).resolve()]
        for module in tuple(sys.modules.values()):
            name=getattr(module,'__file__',None)
            if name:
                path=Path(name).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    own.append(path)
        s.merge_pins(pins,s.hashes([*own,*evidence]))
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json',pins)
        result=dict(state='FUNCTIONAL_AND_SETTLED_WAVE_AUDIT_PASS',original_worker_state='FAIL',
                    clean_original_worker_pass=False,original_error=error,original_run=str(run),
                    offline_replay=str(replay),log_evidence=parsed,wave_evidence=waves,
                    independent_protocol_checked=True,current_inputs_match=True,new_simulation=False,
                    counter_contract=dict(vlen_bits=1024,lanes=4,lane_word_bits=64,m=1,
                                          successful_commit_words=4,fault_commit_words=0),
                    source_pins_sha256=s.digest(out/'source-pins.json'),evidence_sha256=s.hashes(evidence),
                    physical_sharing_implemented=False,stalled_ar_fault_in_soc=False,performance=False)
        s.atomic_json(out/'result.json',result)
        print(result['state'],'commands=71 samples='+str(waves['rows']),'original_worker=FAIL new_simulation=0')
        return result
    except BaseException as exc:
        s.atomic_json(out/'result.json',dict(state='FAIL',original_worker_state='FAIL',error=repr(exc)))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('run','replay','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--protocol',type=Path,help='Separately generated absolute-path independent protocol report')
    args=parser.parse_args()
    audit(args.run,args.replay,args.output,args.protocol)
