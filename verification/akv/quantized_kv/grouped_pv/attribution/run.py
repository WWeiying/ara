#!/usr/bin/env python3
"""Reuse the accepted same ELF/image, adding architectural retirement evidence."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.dont_write_bytecode=True


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value)
    return value


fresh=module('attribution_fresh_helpers',HERE.parent/'fresh_pair/run.py')
analysis=module('attribution_checked_analysis',HERE/'analyze.py')
original,accepted,s=fresh.original,fresh.accepted,fresh.s


def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();build=args.build.resolve(strict=True)
    output=original.fresh_output(args.output,[HERE,build,accepted.SOC_BUILD])
    output.mkdir(parents=True);work=output/'work';work.mkdir();owner=original.Execution(output)
    owner.env.update(PATH='/usr/bin:/bin',READELF='/usr/bin/readelf',LC_ALL='C')
    for key in ('BASH_ENV','ENV','PYTHONHOME','PYTHONSTARTUP','PYTHONINSPECT'):owner.env.pop(key,None)
    result=dict(state='PREFLIGHT',simulations_launched=0,retirement_proven=False,whole_model=False,
                performance_acceptance=False)
    try:
        report=json.loads((build/'build.json').read_text());elf=Path(report['elf'])
        review_path=ROOT/'verification/akv/results/grouped-pv-fresh-pair-review-20261027.json'
        review=json.loads(review_path.read_text())
        s.require(review['state']=='FUNCTIONAL_PASS_PERFORMANCE_REGRESSION' and
                  review['elf_sha256']==report['elf_sha256']==s.digest(elf) and
                  report['state']=='FRESH_GNU_BUILT_NOT_EXECUTED','Need the accepted identical ELF')
        receipt=ROOT/review['source_result']
        s.require(s.digest(receipt)==review['source_result_sha256'],'Original acceptance identity')
        pins=json.loads((build/'source-pins.json').read_text())
        s.require(s.digest(build/'source-pins.json')==report['source_pins_sha256'],'Build pin map identity')
        s.merge_pins(pins,report['artifacts'])
        s.merge_pins(pins,s.hashes([build/'build.json',review_path,receipt]))
        instructions=analysis.base.disassembly_map((build/'disassemble.log').read_text(),analysis.base.LinkedELF(elf.read_bytes()))
        boundaries=[row['pc'] for row in report['api_evidence']['rdcycle_sites']]
        s.require(len(boundaries)==2 and {pc for pc,item in instructions.items() if analysis.base.is_cycle_read(item)}==set(boundaries),
                  'Reviewed exact CSR boundaries')
        mapping=analysis.phase_map(instructions);analysis.base.phase_classifier(mapping,instructions)
        s.atomic_json(output/'phase-map.json',mapping)
        soc,sources,image=accepted.canonical.checked_soc(accepted.SOC_BUILD,accepted.SOC_SHA)
        s.merge_pins(pins,sources);s.merge_pins(pins,image)
        helpers=[Path(__file__),HERE/'test_analyze.py',output/'phase-map.json',
                 ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',*s.script_files()]
        for item in tuple(sys.modules.values()):
            path=getattr(item,'__file__',None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):helpers.append(Path(path).resolve())
        s.merge_pins(pins,s.hashes(helpers));s.verify_pins(pins);s.atomic_json(output/'source-pins.json',pins)
        simv=Path(soc['simv'])
        def identity():
            s.verify_pins(pins);s.require(s.hashes(s.image_files(simv))==image,'Image drift')
        def manifest(stage):
            identity()
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],output/(stage+'.log'),300,stage.upper())
            identity()
        result.update(build=str(build),elf_sha256=report['elf_sha256'],measurement_pcs=boundaries)
        if args.execute_reviewed:
            manifest('manifest-before')
            owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                          output/'image-contract.log',180,'IMAGE_CONTRACT')
            command=fresh.helper.simulation_command(simv,elf,work)+['+COMMIT_TRACE='+str(work/'commit_trace.csv')]
            result['simulations_launched']=1
            owner.execute(command,work/'console.log',10800,'RUNNING')
            calls=fresh.helper.check.check_log((work/'run.vcs.log').read_text(),Path(report['golden']).read_bytes(),
                                             accepted.RTL.read_text(),command)
            owner.execute(original.uvm_command(simv,elf,work),work/'checker.log',600,'UVM_CHECK')
            accepted.protocol(work,report['elf_sha256'],image)
            # Count only architectural retire events. Never filter/truncate first.
            with (work/'commit_trace.csv').open() as stream:
                attributed=analysis.analyze(instructions,stream,calls['trials'],boundaries,mapping)
            s.atomic_json(output/'attribution.json',attributed)
            manifest('manifest-after')
            result.update(state='PASS',retirement_proven=True,call_checks=calls,
                          attribution_sha256=s.digest(output/'attribution.json'),
                          evidence=s.hashes([work/'run.vcs.log',work/'commit_trace.csv',work/'vector_trace.csv',work/'uvm_result.json']))
        else:result['state']='PREFLIGHT_NOT_RUN'
        identity();result['post_pins_match']=True
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        s.atomic_json(output/'result.json',result);owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    def interrupted(signum,_frame):raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    main()
