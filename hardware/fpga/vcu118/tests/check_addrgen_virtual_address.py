#!/usr/bin/env python3
"""Reproduce canonical-address truncation; no RTL edits, Vivado or board access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New independent evidence directory')
    parser.add_argument('--package', type=Path, default=HERE.parent.parent / 'ara_dsa_vcu118')
    parser.add_argument('--vcs', default='vcs')
    parser.add_argument('--old-ref', default='50ace3fa', help='Archived pre-signoff FPGA commit')
    parser.add_argument('--addrgen-ref', default='7b9f3675', help='Archived faulty FPGA addrgen for forensic reproduction')
    args = parser.parse_args()
    out = args.output.resolve()
    pkg = args.package.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((pkg / 'manifest.json').read_text())
    rel = 'rtl/cva6/core/cva6_mmu/cva6_mmu.sv'
    old = subprocess.check_output([
        'git', 'show', args.old_ref + ':hardware/fpga/ara_dsa_vcu118/' + rel], cwd=REPO).decode()
    current = (pkg / rel).read_text()
    # The historical control must differ only in the canonical-check pipeline fix.
    start = current.index('    canonical_addr_check = ')
    end = current.index(';', start) + 1
    baseline = current[:start] + current[start:end].replace('lsu_req_q', 'lsu_req_i').replace(
        'lsu_vaddr_q', 'lsu_vaddr_i') + current[end:]
    if baseline != old:
        raise RuntimeError('Historical MMU has other differences; review the control before comparing')
    (out / 'old_mmu.sv').write_text(re.sub(r'\bcva6_mmu\b', 'old_cva6_mmu', old))
    (out / 'faulty_addrgen.sv').write_bytes(subprocess.check_output([
        'git', 'show', args.addrgen_ref + ':hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/vlsu/addrgen.sv'],
        cwd=REPO))
    tb = out / 'canonical_tb.sv'
    shutil.copyfile(HERE / 'addrgen_virtual_address_tb.sv', tb)
    prefix = [pkg / p for p in (
        'rtl/common_cells/src/cf_math_pkg.sv', 'rtl/axi/src/axi_pkg.sv',
        'rtl/fpnew/src/fpnew_pkg.sv', 'rtl/cva6/core/include/config_pkg.sv',
        'rtl/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
        'rtl/cva6/core/include/build_config_pkg.sv', 'rtl/cva6/core/include/riscv_pkg.sv',
        'rtl/cva6/core/include/ariane_pkg.sv', 'rtl/ara/hardware/include/rvv_pkg.sv',
        'rtl/ara/hardware/include/ara_pkg.sv')]
    packages = [pkg / p for p in manifest['files'] if p.startswith('rtl/common_cells/src/')
                and p.endswith('_pkg.sv') and pkg / p not in prefix]
    modules = [pkg / p for p in manifest['files'] if
               (p.startswith('rtl/common_cells/src/') and not p.endswith('_pkg.sv')) or
               p.startswith('rtl/cva6/core/cva6_mmu/') or p.startswith('rtl/cva6/core/pmp/src/')]
    # A behavioral SRAM supplies the unexercised shared-TLB/PTW storage, not a
    # replacement for the address/canonical-check logic under investigation.
    modules += [REPO / 'hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv',
                out / 'faulty_addrgen.sv', out / 'old_mmu.sv', tb]
    sources = prefix + packages + modules
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    command = [args.vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '+define+SYNTHESIS',
               *['+incdir+' + str(pkg / p) for p in manifest['include_dirs']],
               *map(str, sources), '-top', 'canonical_tb', '-o', str(out / 'simv')]
    with (out / 'compile.log').open('w') as log:
        subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                       timeout=180, check=True)
    with (out / 'run.log').open('w') as log:
        subprocess.run([str(out / 'simv')], cwd=out, stdout=log, stderr=subprocess.STDOUT,
                       timeout=20, check=True)
    text = (out / 'run.log').read_text()
    print(text)
    if 'CANONICAL_ROOTCAUSE_REPRO_PASS' not in text or text.count('CASE_PASS') != 4:
        raise RuntimeError('Missing discriminating completion')
    if any(hashlib.sha256(p.read_bytes()).hexdigest() != hashes[str(p)] for p in sources):
        raise RuntimeError('Source changed during simulation')
    result = {'passed': True, 'cases': 4,
              'faulty_addrgen_ref': args.addrgen_ref,
              'scope': 'actual exported addrgen/MMU; DTLB hit/PTE controlled; no full SoC or physical signoff',
              'historical_mmu_diff': 'canonical check uses live input instead of registered request/address',
              'sources': hashes}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
