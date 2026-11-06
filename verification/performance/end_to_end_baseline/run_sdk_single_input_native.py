#!/usr/bin/env python3
"""Run the same-ELF real Decode SDK ABBA pair on the unchanged audited SoC."""
import argparse
import json
from pathlib import Path
import signal
import sys

from audit import digest,require,verify_pins
from collect_matrix_soc import audit_build
from check_sdk_single_input import check,verify_oracle_inputs
from run_decode_native import oracle
from run_output_native import h,s,original,accepted,EarlyGuard,ROOT,VERIFY


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true');args=parser.parse_args()
    build=args.build.resolve(strict=True);out=args.output.absolute()
    require(out==out.resolve() and out.is_relative_to(VERIFY/'verification/out'),'Fresh verification output')
    out.mkdir(parents=True,exist_ok=False);work=out/'work';work.mkdir();owner=original.Execution(out)
    owner.env.update(PATH='/usr/bin:/bin',READELF='/usr/bin/readelf',LC_ALL='C',PYTHONPATH=str(VERIFY/'verification'))
    result=dict(state='PREFLIGHT',performance_measured=False,whole_model=False,wide=0)
    try:
        receipt=ROOT/'verification/performance/evidence/matrix_soc_20261106_01/result.json'
        pair=json.loads(receipt.read_text());audit_dir=Path(pair['run'])
        require(digest(audit_dir/'result.json')==pair['result_sha256'],'SoC audit identity')
        recorded=json.loads((audit_dir/'result.json').read_text())['builds'][0]
        soc=audit_build(Path(recorded['build']));require(soc==recorded and soc['wide']==0,'SoC baseline differs')
        report=json.loads((build/'build.json').read_text())
        require(report['state']=='REAL_QWEN3_SDK_SINGLE_INPUT_ABBA_BUILT_NOT_EXECUTED' and
                report['commands']==112 and report['outputs']==3584 and report['order']==[0,1,1,0] and
                not report['production_sdk_changed'] and digest(build/'source-pins.json')==report['source_pins_sha256'] and
                digest(report['elf'])==report['elf_sha256'],'ABBA program identity')
        pins=json.loads((build/'source-pins.json').read_text())
        for more in (report['artifacts'],soc['image_pins'],soc['artifact_pins'],
                     json.loads((Path(soc['build'])/'source-pins.json').read_text())):s.merge_pins(pins,more)
        for module in tuple(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(root) for root in (ROOT,VERIFY)):
                s.merge_pins(pins,s.hashes([Path(path).resolve()]))
        for path in (receipt,audit_dir/'result.json',build/'build.json',
            VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',*s.script_files()):s.merge_pins(pins,s.hashes([path]))
        verify_pins(pins);verify_oracle_inputs(report,pins);s.atomic_json(out/'source-pins.json',pins)
        simv,elf=Path(soc['simv']),Path(report['elf']);owner.state.update(simv=str(simv),elf=str(elf));owner.save()
        def identity():
            verify_pins(pins);verify_oracle_inputs(report,pins)
            require(s.hashes(s.image_files(simv))==soc['image_pins'],'Image drift')
        def manifest(stage):
            identity();owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
        if args.execute_reviewed:
            manifest('manifest-before')
            owner.execute(['bash',VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                out/'image-contract.log',180,'IMAGE_CONTRACT')
            command=[str(v).replace('+TESTCASE=quant_grouped_pv_pair','+TESTCASE=qwen3_sdk_single_input_abba')
                     for v in h.helper.simulation_command(simv,elf,work)]
            with EarlyGuard(owner,work/'console.log',s.atomic_json):owner.execute(command,work/'console.log',10800,'RUNNING')
            require(not (out/'early-failure.json').exists(),'Architectural failure')
            measured=check((work/'run.vcs.log').read_text(),*oracle(Path(report['oracle_build'])))
            owner.execute(original.uvm_command(simv,elf,work),work/'checker.log',600,'PROTOCOL_CHECK')
            accepted.protocol(work,report['elf_sha256'],soc['image_pins']);manifest('manifest-after')
            result.update(state='PASS',measured=measured,performance_measured=True,independent_protocol_checked=True)
        else:result['state']='PREFLIGHT_NOT_RUN'
        identity();result.update(post_pins_match=True,elf_sha256=report['elf_sha256'],image_pins=soc['image_pins'],
            source_pins_sha256=digest(out/'source-pins.json'),build=str(build))
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:
        s.atomic_json(out/'result.json',result);owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    def interrupted(sig,_frame):raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    main()
