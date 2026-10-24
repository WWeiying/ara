#!/usr/bin/env python3
"""Bounded unchanged-SoC owner-transfer evidence, not an area/performance test."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE.parent/'quantized_kv'))
from run_strided_attention import s, Execution
from check_reader_handoff import check_log, check_cycles
from wave_profile import profile, script


def exporter_files(entry):
    entry=entry.absolute()
    s.require(entry.name=='fsdbreport' and entry.is_file(),'Use the fsdbreport entry, not its basename-sensitive wrapper')
    paths={entry,entry.resolve(strict=True)}
    with entry.open('rb') as handle:
        direct_elf=handle.read(4)==b'\x7fELF'
    if not direct_elf:
        candidates=sorted((entry.parent.parent/'platform').glob('*/bin/fsdbreport'))
        s.require(candidates,'No platform exporter implementation found')
        for path in candidates:
            s.require(path.is_file(),'Broken platform exporter entry')
            paths.update((path,path.resolve(strict=True)))
    return sorted(paths)


def checked_build(build):
    report=s.read_json(build/'build.json')
    wanted=dict(state='READER_HANDOFF_BUILT_NOT_EXECUTED',execution='NOT_RUN',
                qbs_commands=6,akv_commands=65,expected_traps=1,fault_cause=5,expected_tval=0,
                capture_bound_ns=500000,required_signals=134,performance=False,post_pins_match=True)
    s.require(all(type(report.get(k)) is type(v) and report[k]==v for k,v in wanted.items()),'Wrong handoff fixture')
    s.require(s.digest(build/'source-pins.json')==report['source_pins_sha256'],'Build manifest drift')
    pins=s.read_json(build/'source-pins.json')
    s.merge_pins(pins,report['artifact_sha256'])
    s.require(pins.get(report['elf'])==report['elf_sha256']==s.digest(Path(report['elf'])),'ELF drift')
    s.require(s.read_json(build/'profile.json')==profile() and (build/'probe.tcl').read_text()==script(500000),
              'Capture plan does not match fixture')
    s.merge_pins(pins,s.hashes([build/'build.json',build/'source-pins.json']))
    s.verify_pins(pins)
    return report,pins


def run(args):
    s.require(1<=args.timeout<=900,'Wall-time bound must be 1..900 seconds')
    build,out=args.build.resolve(strict=True),args.output.resolve()
    s.require(not out.is_relative_to(build) and not build.is_relative_to(out),'Use an independent fresh output')
    out.mkdir(parents=True,exist_ok=False)
    work=out/'work'
    work.mkdir()
    owner=Execution(out)
    owner.state.update(build=str(build),performance=False)
    owner.save()
    try:
        report,pins=checked_build(build)
        exporter=ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py'
        tool_pins=s.hashes(exporter_files(args.fsdbreport))
        own=[Path(__file__),HERE/'test_run_reader_handoff.py',HERE/'check_reader_handoff.py',
             HERE/'test_check_reader_handoff.py',exporter,
             *s.script_files(),Path(sys.executable).resolve()]
        for module in tuple(sys.modules.values()):
            name=getattr(module,'__file__',None)
            if name:
                path=Path(name).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    own.append(path)
        s.merge_pins(pins,s.hashes(own))
        s.merge_pins(pins,tool_pins)
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json',pins)
        receipt=s.digest(out/'source-pins.json')
        image=report['accepted_image_pins']
        simv,elf=Path(report['simv']),Path(report['elf'])
        owner.state.update(simv=str(simv),elf=str(elf))

        def identity():
            s.require(s.digest(out/'source-pins.json')==receipt,'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(exporter_files(args.fsdbreport))==tool_pins,'Exporter implementation inventory drift')
            s.require(s.hashes(s.image_files(simv))==image,'Image inventory drift')

        def manifest(stage):
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                           simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())

        identity()
        manifest('manifest-before')
        owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                      out/'image-contract.log',180,'IMAGE_CONTRACT')
        identity()
        log,trace=work/'run.vcs.log',work/'vector_trace.csv'
        owner.execute([simv,'-no_save','-ucli','-do',build/'probe.tcl','-l',log,
                       '+PRELOAD='+str(elf),'+TESTCASE=reader_handoff_boundary',
                       '+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF','+AKV_PERF',
                       '+VECTOR_TRACE='+str(trace),'+ARA_CONTRACT_TRACE_LIMIT=2000000',
                       '+ARA_UVM_TRACE_LIMIT=2000000'],work/'console.log',args.timeout,'RUNNING')
        parsed=check_log(log.read_text(),(ROOT/'hardware/src/vlsu/vlsu.sv').read_text())
        owner.execute([sys.executable,'-B',exporter,'--fsdb',work/'reader.fsdb',
                       '--profile',build/'profile.json','--begin','0ns','--end','500000ns',
                       '--output',out/'cycles','--fsdbreport',args.fsdbreport],out/'extract.log',180,'EXTRACTING')
        metadata=s.read_json(out/'cycles/metadata.json')
        s.require(metadata.get('edge')=='negedge' and metadata.get('cycle_count',0)>10 and
                  set(metadata.get('present_signals',[]))=={row['alias'] for row in profile()['signals']} and
                  not metadata.get('missing_signals',[]),'Incomplete capture/extraction')
        waves=check_cycles(out/'cycles/cycles.csv')
        owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
                       '--require-axi','--require-axi-write','--vector-trace',trace,'--log',log,
                       '--simv',simv,'--elf',elf,'--output',work/'uvm_result.json'],work/'checker.log',600,'CHECKING')
        s.check_result(work/'uvm_result.json',report['elf_sha256'],image)
        uvm=s.read_json(work/'uvm_result.json')
        s.require(uvm['log_sha256']==s.digest(log) and uvm['vector_trace_sha256']==s.digest(trace),'Protocol input drift')
        manifest('manifest-after')
        identity()
        parsed.update(state='PASS',wave_evidence=waves,post_pins_match=True,simulator_exit_code=0,
                      independent_protocol_checked=True,source_pins_sha256=receipt,elf_sha256=report['elf_sha256'],
                      evidence_sha256=s.hashes([log,trace,work/'reader.fsdb',work/'uvm_result.json',
                          out/'source-pins.json',out/'cycles/cycles.csv',out/'cycles/metadata.json',
                          out/'cycles/fsdbreport.raw.csv',out/'extract.log',out/'image-contract.log',
                          out/'manifest-before.log',out/'manifest-after.log']))
        s.atomic_json(out/'result.json',parsed)
        owner.state['state']='PASS'
    except BaseException as exc:
        state='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else \
              'INTERRUPTED' if isinstance(exc,InterruptedError) else 'FAIL'
        owner.state.update(state=state,error=repr(exc))
        s.atomic_json(out/'result.json',dict(state=state,error=repr(exc)))
        raise
    finally:
        owner.state.update(child_pid=None,finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=900)
    parser.add_argument('--fsdbreport',type=Path,default=Path(
        '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1/bin/fsdbreport'))
    args=parser.parse_args()

    def interrupted(sig,_frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,interrupted)
    run(args)
