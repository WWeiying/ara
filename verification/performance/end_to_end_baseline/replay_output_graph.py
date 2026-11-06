#!/usr/bin/env python3
"""Replay unchanged graph ELF with the audited native-QBS QEMU enabled."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from audit import digest,require,verify_pins
from check_output_graph import check

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
VERIFY=Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_ggml_segmented import verify_native_build


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();require(out.is_relative_to(VERIFY/'verification/out'),'Verification output required')
    out.mkdir(parents=True,exist_ok=False);build=a.build.resolve(strict=True)
    report=dict(state='PREPARING',functional_only=True,performance_measured=False)
    try:
        require(json.loads((build/'result.json').read_text())['state']=='FAIL','Expected preserved failed first run')
        pins=json.loads((build/'source-pins.json').read_text());verify_pins(pins)
        qemu=VERIFY/'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
        paths=verify_native_build(qemu)
        for path in (Path(__file__),HERE/'audit.py',HERE/'check_output_graph.py',
                     ROOT/'verification/qbs/run_ggml_segmented.py',build/'result.json',build/'commands.json',
                     build/'qemu.log',qemu,*paths):
            pins[str(path.resolve())]=digest(path)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        images=Path('/home/wangwy/llama/platforms/cva6-qemu/images')
        command=list(map(str,[qemu,'-M','virt','-cpu',
            'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
            '-smp','1','-m','512M','-display','none','-monitor','none','-serial','stdio',
            '-bios',images/'fw_dynamic.bin','-kernel',images/'Image',
            '-initrd',build/'initramfs.cpio','-append','console=ttyS0 rdinit=/init']))
        (out/'command.json').write_text(json.dumps(command,indent=2)+'\n')
        report.update(state='RUNNING',original_run=str(build),elf_sha256=digest(build/'build/output-graph'))
        (out/'status.json').write_text(json.dumps(report,indent=2)+'\n')
        verify_pins(pins)
        with (out/'qemu.log').open('wb') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=600,check=True)
        checked=check((out/'qemu.log').read_text())
        verify_native_build(qemu);verify_pins(pins)
        report.update(state='GRAPH_FUNCTIONAL_AND_DISPATCH_PASS',checked=checked,
                      log_sha256=digest(out/'qemu.log'),source_pins_sha256=digest(out/'source-pins.json'),
                      original_failed_run_preserved=True,elf_rebuilt=False,production_changed=False)
    except BaseException as exc:report.update(state='FAIL',error=repr(exc));raise
    finally:
        (out/'status.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
