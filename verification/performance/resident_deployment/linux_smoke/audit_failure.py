#!/usr/bin/env python3
"""Add a separate identity/relocation audit without changing the failed run."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    report = json.loads((out / 'result.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    assert report['state'] == 'FAIL' and not report['module_loaded']
    assert not (out / 'failure-audit.json').exists()
    log = (out / 'guest-1.log').read_text()
    assert 'CHECK name=finit_module rc=-22 expected=0 FAIL' in log
    assert "unexpected relocation type 'R_RISCV_ALIGN'" in log
    tool = '/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-readelf'
    module = out / 'inputs/ara_resident.ko'
    result = subprocess.run([tool, '-rW', str(module)], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=True, timeout=10)
    (out / 'module-relocations.log').write_bytes(result.stdout)
    relocations = re.findall(r'\bR_RISCV_[A-Z0-9_]+', result.stdout.decode())
    assert 'R_RISCV_ALIGN' in relocations
    drift = {path: {'expected': digest, 'actual': sha(path)} for path, digest in pins.items()
             if sha(path) != digest}
    artifact_names = ('result.json', 'commands.json', 'source-pins.json', 'guest-1.log', 'guest-1.trace',
                      'init.elf', 'initramfs.cpio', 'inputs/ara_resident.ko', 'virt-1.dtb',
                      'image-config.diff', 'image-config.log', 'module-relocations.log')
    audit = dict(state='UNAVAILABLE_FROZEN_MODULE_REJECTED_R_RISCV_ALIGN',
        original_run_state='FAIL', original_reports_preserved=True,
        module_loaded=False, driver_probed=False, kernel_compute_scope_executed=False,
        actual_info4_queried=False, client_v2_csr_executed=False, smp2_boot_executed=False,
        board_executed=False, qemu_exit_status=0, finit_module_errno=-22,
        source_pins_match=not drift, source_drift=drift,
        relocation_counts={name: relocations.count(name) for name in sorted(set(relocations))},
        artifacts={name: sha(out / name) for name in artifact_names},
        audit_source=str(Path(__file__).resolve()), audit_source_sha256=sha(__file__))
    (out / 'failure-audit.json').write_text(json.dumps(audit, indent=2, sort_keys=True) + '\n')
    print(json.dumps(audit, sort_keys=True))
    return int(bool(drift))


if __name__ == '__main__':
    raise SystemExit(main())
