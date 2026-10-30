#!/usr/bin/env python3
"""Current Decode full-call profile using existing monitor, no RTL rebuild."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import signal
import sys
from decode_pc_profile import check_output,profile
from early_guard import EarlyGuard

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('decode_profile_runner',HERE.parent/'grouped_pv/fresh_pair/run.py')
helpers=importlib.util.module_from_spec(spec);sys.modules[spec.name]=helpers;spec.loader.exec_module(helpers)
s,original,accepted=helpers.s,helpers.original,helpers.accepted


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();build=args.build.resolve(strict=True)
    out=original.fresh_output(args.output,[HERE,build,accepted.SOC_BUILD])
    out.mkdir(parents=True);work=out/'work';work.mkdir();owner=original.Execution(out)
    owner.env.update(PATH='/usr/bin:/bin',READELF='/usr/bin/readelf',LC_ALL='C')
    result=dict(state='PREFLIGHT',performance_measured=False)
    try:
        report=json.loads((build/'build.json').read_text())
        s.require(report['state']=='BUILT_NOT_EXECUTED' and report.get('current_decode_profile') is True and
            report['outputs_per_trial']==256 and report['trials']==1 and report['reused_objects']==0 and
            report.get('value_binding')=='shared_rvv_q8_0','Build contract')
        s.require(s.digest(build/'source-pins.json')==report['source_pins_sha256'],'Build pins')
        pins=json.loads((build/'source-pins.json').read_text());s.merge_pins(pins,report['artifacts'])
        s.merge_pins(pins,s.hashes([build/'build.json']))
        soc,sources,image=accepted.canonical.checked_soc(accepted.SOC_BUILD,accepted.SOC_SHA)
        s.merge_pins(pins,sources);s.merge_pins(pins,image)
        scripts=[Path(__file__),HERE/'decode_pc_profile.py',*s.script_files()]
        for module in tuple(sys.modules.values()):
            name=getattr(module,'__file__',None)
            if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):scripts.append(Path(name).resolve())
        s.merge_pins(pins,s.hashes(scripts));s.verify_pins(pins);s.atomic_json(out/'source-pins.json',pins)
        simv,elf=Path(soc['simv']),Path(report['elf'])
        s.require(s.digest(elf)==report['elf_sha256'],'ELF drift')
        owner.state.update(build=str(build),elf=str(elf),simv=str(simv));owner.save()
        def identity():
            s.verify_pins(pins);s.require(s.hashes(s.image_files(simv))==image,'Image drift')
        def manifest(stage):
            identity()
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
            identity()
        if args.execute_reviewed:
            manifest('manifest-before')
            owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                out/'image-contract.log',180,'IMAGE_CONTRACT')
            command=helpers.helper.simulation_command(simv,elf,work)
            s.require(not any(str(v).startswith('+COMMIT_TRACE=') for v in command),'Duplicate trace flag')
            command.append('+COMMIT_TRACE='+str(work/'commit.csv'))
            with EarlyGuard(owner,work/'console.log',s.atomic_json):
                owner.execute(command,work/'console.log',10800,'RUNNING')
            s.require(not (out/'early-failure.json').exists(),'Exception/contract error')
            text=(work/'run.vcs.log').read_text()
            golden=ROOT/'verification/out/quant-prefill-capture-20261028-01'/report['kind']/'prefill/block/kqv_out-0.bin'
            numerical=check_output(text,golden.read_bytes(),int(report['kind']=='q4_0'))
            with (work/'commit.csv').open() as stream:
                measured=profile(stream,(build/'symbols.log').read_text(),numerical['cycles'])
            qbs=[dict((k,int(v)) for k,v in re.findall(r'(\w+)=(\d+)',line))
                 for line in text.splitlines() if line.startswith('[QBS_PERF] ')]
            s.require(len(qbs)==1 and qbs[0]['success']==1 and qbs[0]['fault']==0 and
                qbs[0]['m']==2 and qbs[0]['n']==20 and 0<qbs[0]['busy_cycles']<numerical['cycles'],'QBS activity')
            owner.execute(original.uvm_command(simv,elf,work),work/'checker.log',600,'PROTOCOL_CHECK')
            accepted.protocol(work,report['elf_sha256'],image);manifest('manifest-after')
            result.update(state='PASS',numerical=numerical,measured=measured,qbs=qbs[0],
                performance_measured=True,independent_protocol_checked=True,value_binding=report['value_binding'])
        else:result['state']='PREFLIGHT_NOT_RUN'
        identity();result.update(post_pins_match=True,elf_sha256=report['elf_sha256'])
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        s.atomic_json(out/'result.json',result);owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    def interrupted(signum,_frame):raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    main()
