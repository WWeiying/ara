#!/usr/bin/env python3
"""Run bounded native Prefill ABBA with the accepted canonical SoC checker."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys
from check_prefill_native import check_log
sys.path.append(str(Path(__file__).resolve().parent.parent/'prefill'))
from early_guard import EarlyGuard

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.dont_write_bytecode = True
path = HERE.parent / 'grouped_pv/fresh_pair/run.py'
spec = importlib.util.spec_from_file_location('prefill_accepted_runner', path)
helpers = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helpers
spec.loader.exec_module(helpers)
s, original, accepted = helpers.s, helpers.original, helpers.accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-reviewed', action='store_true')
    args = parser.parse_args()
    build = args.build.resolve(strict=True)
    out = original.fresh_output(args.output,[HERE,build,accepted.SOC_BUILD])
    out.mkdir(parents=True); work=out/'work'; work.mkdir()
    owner=original.Execution(out)
    owner.env.update(PATH='/usr/bin:/bin',READELF='/usr/bin/readelf',LC_ALL='C')
    result=dict(state='PREFLIGHT',performance_measured=False)
    try:
        report=json.loads((build/'build.json').read_text())
        s.require(report['state']=='BUILT_NOT_EXECUTED' and report['commands_per_trial']==4 and
            report['outputs_per_trial']==1024 and report['reused_objects']==0 and report.get('register_prefill') is True and
            report.get('value_binding')=='shared_rvv_q8_0' and report.get('rebuilt_objects')==17, 'Build contract')
        s.require(s.digest(build/'source-pins.json')==report['source_pins_sha256'], 'Build pins')
        pins=json.loads((build/'source-pins.json').read_text())
        s.merge_pins(pins,report['artifacts']); s.merge_pins(pins,s.hashes([build/'build.json']))
        soc,sources,image=accepted.canonical.checked_soc(accepted.SOC_BUILD,accepted.SOC_SHA)
        s.merge_pins(pins,sources);s.merge_pins(pins,image)
        scripts=[Path(__file__),HERE/'check_prefill_native.py',*s.script_files()]
        for module in tuple(sys.modules.values()):
            name=getattr(module,'__file__',None)
            if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):
                scripts.append(Path(name).resolve())
        s.merge_pins(pins,s.hashes(scripts));s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json',pins)
        simv,elf=Path(soc['simv']),Path(report['elf'])
        s.require(s.digest(elf)==report['elf_sha256'],'ELF drift')
        owner.state.update(build=str(build),elf=str(elf),simv=str(simv));owner.save()
        def identity():
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv))==image,'Image drift')
        def manifest(stage):
            identity()
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
            identity()
        if args.execute_reviewed:
            manifest('manifest-before')
            owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                out/'image-contract.log',180,'IMAGE_CONTRACT')
            with EarlyGuard(owner,work/'console.log',s.atomic_json):
                owner.execute(helpers.helper.simulation_command(simv,elf,work),work/'console.log',10800,'RUNNING')
            s.require(not (out/'early-failure.json').exists(),'Unexpected exception/contract error')
            golden=ROOT/'verification/out/quant-prefill-capture-20261028-01'/report['kind']/'prefill/block/kqv_out-0.bin'
            measured=check_log((work/'run.vcs.log').read_text(),golden.read_bytes(),int(report['kind']=='q4_0'))
            owner.execute(original.uvm_command(simv,elf,work),work/'checker.log',600,'PROTOCOL_CHECK')
            accepted.protocol(work,report['elf_sha256'],image);manifest('manifest-after')
            result.update(state='PASS',measured=measured,performance_measured=True,
                          independent_protocol_checked=True)
        else: result['state']='PREFLIGHT_NOT_RUN'
        identity();result.update(post_pins_match=True,elf_sha256=report['elf_sha256'])
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        s.atomic_json(out/'result.json',result)
        owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    def interrupted(signum,_frame): raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,interrupted)
    main()
