#!/usr/bin/env python3
"""Independent full-call VCS pair on the accepted archived single-core image."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys

from audit import digest,require
from check_output_native import check_log
from early_guard import EarlyGuard

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
VERIFY=Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
sys.dont_write_bytecode=True
path=VERIFY/'verification/akv/quantized_kv/grouped_pv/fresh_pair/run.py'
spec=importlib.util.spec_from_file_location('output_residency_vcs_helpers',path)
h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
s,original,accepted=h.s,h.original,h.accepted


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--soc-build',type=Path,default=accepted.SOC_BUILD)
    p.add_argument('--soc-sha256',default=accepted.SOC_SHA,
                   help='Exact accepted build result.json hash; never infer it from a mismatched image')
    p.add_argument('--execute-reviewed',action='store_true')
    a=p.parse_args(); build=a.build.resolve(strict=True); out=a.output.resolve()
    require(out.is_relative_to(VERIFY/'verification/out'),'Use verification output area')
    out=original.fresh_output(out,[HERE,build,a.soc_build]); out.mkdir(parents=True)
    work=out/'work';work.mkdir();owner=original.Execution(out)
    owner.env.update(PATH='/usr/bin:/bin',READELF='/usr/bin/readelf',LC_ALL='C',
                     PYTHONPATH=str(VERIFY/'verification'))
    result=dict(state='PREFLIGHT',performance_measured=False,whole_model=False,
                current_main_rtl_acceptance=False)
    try:
        r=json.loads((build/'build.json').read_text())
        require(r['state']=='BUILT_NOT_EXECUTED' and r['baseline']=='register_pv' and
                r['candidate']=='output_tile' and r['rebuilt_objects']==18,'Build contract')
        require(digest(build/'source-pins.json')==r['source_pins_sha256'],'Build pin map')
        pins=json.loads((build/'source-pins.json').read_text())
        s.merge_pins(pins,r['artifacts']);s.merge_pins(pins,s.hashes([build/'build.json']))
        soc,sources,image=accepted.canonical.checked_soc(a.soc_build.resolve(strict=True),a.soc_sha256)
        s.merge_pins(pins,sources);s.merge_pins(pins,image)
        scripts=[Path(__file__),HERE/'audit.py',HERE/'check_output_native.py',
                 VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',*s.script_files()]
        for module in tuple(sys.modules.values()):
            name=getattr(module,'__file__',None)
            if name and Path(name).is_file() and any(Path(name).resolve().is_relative_to(root) for root in (ROOT,VERIFY)):
                scripts.append(Path(name).resolve())
        s.merge_pins(pins,s.hashes(scripts))
        golden=VERIFY/'verification/out/quant-prefill-capture-20261028-01'/r['kind']/'prefill/block/kqv_out-0.bin'
        require(str(golden) in pins,'Golden not pinned by build')
        s.verify_pins(pins);s.atomic_json(out/'source-pins.json',pins)
        simv,elf=Path(soc['simv']),Path(r['elf'])
        owner.state.update(elf=str(elf),simv=str(simv),build=str(build));owner.save()
        def identity():
            s.verify_pins(pins);require(s.hashes(s.image_files(simv))==image,'Image inventory drift')
        def manifest(stage):
            identity()
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                           simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
            identity()
        if a.execute_reviewed:
            manifest('manifest-before')
            owner.execute(['bash',VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                          out/'image-contract.log',180,'IMAGE_CONTRACT')
            with EarlyGuard(owner,work/'console.log',s.atomic_json):
                owner.execute(h.helper.simulation_command(simv,elf,work),work/'console.log',10800,'RUNNING')
            require(not (out/'early-failure.json').exists(),'Unexpected architectural exception')
            measured=check_log((work/'run.vcs.log').read_text(),golden.read_bytes(),int(r['kind']=='q4_0'))
            owner.execute(original.uvm_command(simv,elf,work),work/'checker.log',600,'PROTOCOL_CHECK')
            accepted.protocol(work,r['elf_sha256'],image);manifest('manifest-after')
            result.update(state='PASS',performance_measured=True,measured=measured,independent_protocol_checked=True)
        else: result['state']='PREFLIGHT_NOT_RUN'
        identity();result.update(post_pins_match=True,elf_sha256=r['elf_sha256'],image=image)
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        s.atomic_json(out/'result.json',result);owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    def interrupted(sig,_frame):raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    main()
