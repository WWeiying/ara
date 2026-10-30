#!/usr/bin/env python3
"""Bounded complete-call ABBA on the freshly rebuilt current-source ELF."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('fresh_attention_worker_helpers',HERE.parent/'pair/run.py')
helper=importlib.util.module_from_spec(spec);sys.modules[spec.name]=helper;spec.loader.exec_module(helper)
original,accepted,s=helper.original,helper.accepted,helper.s


def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();build=args.build.resolve(strict=True)
    output=original.fresh_output(args.output,[HERE,build,accepted.SOC_BUILD])
    output.mkdir(parents=True);work=output/'work';work.mkdir()
    owner=original.Execution(output)
    owner.env.update(PATH='/usr/bin:/bin',READELF='/usr/bin/readelf',LC_ALL='C')
    for key in ('BASH_ENV','ENV','PYTHONHOME','PYTHONSTARTUP','PYTHONINSPECT'):owner.env.pop(key,None)
    result=dict(state='PREFLIGHT',simulations_launched=0,performance_measured=False,whole_model=False)
    try:
        report=json.loads((build/'build.json').read_text())
        pins=json.loads((build/'source-pins.json').read_text())
        s.require(report['state']=='FRESH_GNU_BUILT_NOT_EXECUTED' and report['rebuilt_objects']==17 and
                  report['reused_objects']==0 and s.digest(build/'source-pins.json')==report['source_pins_sha256'] and
                  s.digest(Path(report['elf']))==report['elf_sha256'] and s.digest(Path(report['golden']))==report['golden_sha256'],
                  'Fresh build identity')
        s.merge_pins(pins,report['artifacts']);s.merge_pins(pins,s.hashes([build/'build.json']))
        soc,sources,image=accepted.canonical.checked_soc(accepted.SOC_BUILD,accepted.SOC_SHA)
        s.merge_pins(pins,sources);s.merge_pins(pins,image)
        scripts=[Path(__file__),ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',*s.script_files()]
        for module in tuple(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):scripts.append(Path(path).resolve())
        s.merge_pins(pins,s.hashes(scripts));s.verify_pins(pins);s.atomic_json(output/'source-pins.json',pins)
        simv=Path(soc['simv']);elf=Path(report['elf'])
        def identity():
            s.verify_pins(pins);s.require(s.hashes(s.image_files(simv))==image,'Simulator inventory drift')
        def manifest(stage):
            identity()
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],output/(stage+'.log'),300,stage.upper())
            identity()
        result.update(build=str(build),elf_sha256=report['elf_sha256'])
        if args.execute_reviewed:
            manifest('manifest-before')
            owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                          output/'image-contract.log',180,'IMAGE_CONTRACT')
            command=helper.simulation_command(simv,elf,work)
            result['simulations_launched']=1
            owner.execute(command,work/'console.log',10800,'RUNNING')
            checked=helper.check.check_log((work/'run.vcs.log').read_text(),Path(report['golden']).read_bytes(),
                                         accepted.RTL.read_text(),command)
            owner.execute(original.uvm_command(simv,elf,work),work/'checker.log',600,'UVM_CHECK')
            accepted.protocol(work,report['elf_sha256'],image);manifest('manifest-after')
            result.update(state='PASS',measured=checked,performance_measured=True,independent_protocol_checked=True)
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
