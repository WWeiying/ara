#!/usr/bin/env python3
"""Bind offline semantic checks to a fresh pinned FSDB export, without resimulation."""
import argparse
from pathlib import Path
import os
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import audit_completed as core
s=core.s


def compare_export(original,reproduced):
    s.require(original.is_file() and reproduced.is_file() and
              s.digest(original)==s.digest(reproduced),'Re-exported cycles differ from semantically checked cycles')


def audit(args):
    run,replay,out=(p.resolve() for p in (args.run,args.replay,args.output))
    s.require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (run,replay)), 'Independent audit output required')
    out.mkdir(parents=True,exist_ok=False)
    try:
        checked=core.audit(run,replay,out/'semantic-check',args.protocol)
        pins=s.read_json(out/'semantic-check/source-pins.json')
        s.require(checked['state']=='FUNCTIONAL_AND_SETTLED_WAVE_AUDIT_PASS' and
                  checked['original_worker_state']=='FAIL' and checked['clean_original_worker_pass'] is False,
                  'Wrong semantic predecessor')
        fsdb=run/'work/reader.fsdb'
        build=Path(s.read_json(run/'status.json')['build'])
        profile=build/'profile.json'
        exporter=ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py'
        tool_pins=s.hashes(core.producer.exporter_files(args.fsdbreport))
        s.merge_pins(pins,tool_pins)
        s.merge_pins(pins,s.hashes([Path(__file__),HERE/'test_audit_completed_v2.py',exporter,
                                  out/'semantic-check/result.json',out/'semantic-check/source-pins.json']))
        s.verify_pins(pins)
        command=[sys.executable,'-B',str(exporter),'--fsdb',str(fsdb),'--profile',str(profile),
                 '--begin','0ns','--end','500000ns','--output',str(out/'reexport'),
                 '--fsdbreport',str(args.fsdbreport)]
        s.atomic_json(out/'export-command.json',dict(argv=command,cwd=str(out),timeout_seconds=180))
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        env.pop('LD_PRELOAD',None)
        def started(pid):
            s.atomic_json(out/'export-child.json',dict(child_pid=pid))
        try:
            code=s.run_command(command,out/'export.log',180,env,started)
            s.require(code==0,'Fresh exporter returned nonzero')
        finally:
            s.atomic_json(out/'export-child.json',dict(child_pid=None))
        s.require(s.hashes(core.producer.exporter_files(args.fsdbreport))==tool_pins,'Exporter inventory drift')
        s.verify_pins(pins)
        compare_export(replay/'cycles/cycles.csv',out/'reexport/cycles.csv')
        metadata=s.read_json(out/'reexport/metadata.json')
        s.require(Path(metadata['fsdb'])==fsdb and Path(metadata['profile'])==profile and
                  metadata['cycle_count']==checked['wave_evidence']['rows'] and
                  not metadata['missing_signals'],'Fresh exporter receipt differs')
        evidence=[out/'export-command.json',out/'export-child.json',out/'export.log',out/'reexport/metadata.json',
                  out/'reexport/fsdbreport.raw.csv',out/'reexport/fsdbreport.log',out/'reexport/cycles.csv',
                  out/'semantic-check/result.json',out/'semantic-check/source-pins.json']
        s.merge_pins(pins,s.hashes(evidence))
        s.atomic_json(out/'source-pins.json',pins)
        result=dict(checked)
        result.update(state='REEXPORTED_FUNCTIONAL_AND_SETTLED_WAVE_AUDIT_PASS',
                      export_derivation_checked=True,reexport_cycles_byte_exact=True,
                      fresh_export=dict(fsdb_sha256=s.digest(fsdb),profile_sha256=s.digest(profile),
                                        exporter_sha256=s.digest(exporter),tool_sha256=tool_pins,
                                        command_sha256=s.digest(out/'export-command.json')),
                      source_pins_sha256=s.digest(out/'source-pins.json'),
                      evidence_sha256={**checked['evidence_sha256'],**s.hashes(evidence)})
        s.atomic_json(out/'result.json',result)
        print(result['state'],'commands=71 samples='+str(checked['wave_evidence']['rows']),
              'original_worker=FAIL new_simulation=0')
        return result
    except BaseException as exc:
        s.atomic_json(out/'result.json',dict(state='FAIL',original_worker_state='FAIL',error=repr(exc)))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('run','replay','output','protocol'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--fsdbreport',type=Path,default=Path(
        '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1/bin/fsdbreport'))
    args=parser.parse_args()
    args.protocol=args.protocol.resolve(strict=True)
    args.fsdbreport=args.fsdbreport.absolute()
    audit(args)
