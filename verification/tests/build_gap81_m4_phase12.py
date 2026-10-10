#!/usr/bin/env python3
"""Compile one independent M4 phase12 app and host oracle; never run EDA."""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import sys

sys.dont_write_bytecode = True
import build_gap38_i8_f16_lane3 as common
import analyze_gap81_m4_phase12 as analysis

ROOT = common.ROOT
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import coverage_evidence as evidence

NAME = 'qbs_gap81_m4_phase12'
APP = ROOT / 'apps' / NAME
REF = ROOT / 'verification/qbs/qbs_ref.c'
SCRIPT = Path(__file__).resolve()
save, read, pins, verify, require = common.save, common.read, common.pins, common.verify, common.require


class Build(common.Build):
    def __init__(self, out):
        super().__init__(out)
        self.sources = pins([SCRIPT, Path(common.__file__), Path(analysis.__file__),
                             *[APP / n for n in ('main.c', 'execute.S', 'contract.h', 'host_reference.c')],
                             REF, Path(evidence.__file__),
                             ROOT / 'verification/tests/audit_gap81_m4_phase12.py',
                             ROOT / 'verification/tests/admit_gap81_m4_phase12.py'])
        self.tools.update(pins([Path(shutil.which(n)).resolve() for n in ('as', 'ld')]))
        for program in ('cc1', 'collect2'):
            result = self.run([self.host, '-print-prog-name=' + program], 'host-' + program)
            self.tools.update(pins([Path(result.stdout.decode().strip()).resolve(strict=True)]))


def fixtures(out):
    # Q5_K: d=1, dmin=0, every 6-bit scale=1, min=0, every 5-bit quant=1.
    weight = struct.pack('<HH', 0x3c00, 0) + bytes([1]*4+[0]*4+[1]*4) + bytes(32) + bytes([0x11]*128)
    require(len(weight) == 176, 'Q5_K native fixture length')
    activation = b''.join(struct.pack('<f', 1.0) + bytes([c]*256)
                          + struct.pack('<16h', *([16*c]*16)) for c in range(1, 5))
    require(len(activation) == 1168, 'Q8_K native fixture length')
    (out/'weight-native.bin').write_bytes(weight)
    (out/'activation-row-native.bin').write_bytes(activation)
    return weight


def header(out, weight, oracle):
    require(oracle['scope'] == 'host-reference-only' and oracle['independent_native_decode'] is True
            and oracle['m4_packing_checked'] is True and oracle['m'] == 4 and oracle['n'] == 1
            and oracle['fflags'] == 0 and oracle['custom_instruction_execution_prechecked'] is False,
            'independent oracle scope/shape/flags differs')
    expected = [int.from_bytes(struct.pack('<f', float(256*c)), 'little') for c in range(1, 5)]
    require(oracle['expected_bits'] == expected and oracle['integer_dot'] == [256,512,768,1024]
            and oracle['integer_correction'] == [0]*4, 'independent fixture arithmetic differs')
    activation = bytes.fromhex(oracle['activation_hex'])
    require(len(activation) == 1168, 'packed M4 bytes differ')
    images = dict(weights=bytes([0xa5])*64+weight+bytes([0xa5])*(800-64-len(weight)),
                  activation=bytes([0x5a])*76+activation+bytes([0x5a])*(2496-76-len(activation)))
    lines = ['#ifndef GAP81_DATA_H', '#define GAP81_DATA_H', '#include "contract.h"',
             '_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "native little endian ABI");']
    for name, blob in images.items():
        values = [int.from_bytes(blob[i:i+8], 'little') for i in range(0,len(blob),8)]
        lines.append('static const uint64_t gap81_'+name+'0[] = {')
        for i in range(0,len(values),8):
            lines.append('  '+', '.join(hex(v) for v in values[i:i+8])+',')
        lines.append('};')
    lines.append('static const uint32_t gap81_expected0[] = {'+', '.join(hex(v) for v in expected)+'};')
    lines += ['static const gap81_case_t gap81_cases[GAP81_COMMANDS] = {',
              '  {4, 1, 4, 2, 12, 176, 1168, 0, gap81_weights0, gap81_activation0, gap81_expected0},',
              '};', '#endif']
    (out/'gap81_data.h').write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent.resolve() == ROOT/'verification/out' and out.name.startswith('gap81-m4-phase12-')
            and not out.exists(), 'fresh independent gap81 output required')
    legality = analysis.analyze()
    out.mkdir()
    save(out/'static-plan.json', legality)
    weight = fixtures(out)
    b = Build(out)
    inc = [f'-I{out}', f'-I{APP}', '-Wall', '-Wextra']
    ref_obj = b.compile(REF, 'host-qbs-ref', host=True)
    oracle_obj = b.compile(APP/'host_reference.c', 'host-independent', host=True)
    oracle_exe = out/'host-reference'
    b.link([b.host, oracle_obj, ref_obj, '-lm', '-o', oracle_exe], 'host-reference.link')
    oracle = json.loads(b.run([oracle_exe, 4, 4, 1, 2, out/'weight-native.bin',
                             out/'activation-row-native.bin'], 'host-reference', timeout=30).stdout)
    save(out/'oracle-command0.json', oracle)
    header(out, weight, oracle)
    host_obj = b.compile(APP/'main.c', 'host-app', [*inc, '-DGAP81_HOST=1'], host=True)
    host = out/'host-app'
    b.link([b.host, host_obj, ref_obj, '-lm', '-o', host], 'host-app.link')
    lines = b.run([host], 'host-app', timeout=30).stdout.decode().splitlines()
    require(len(lines) == 3 and re.fullmatch(r'GAP81 command=0 checks=18 errors=0', lines[0])
            and lines[1] == 'GAP81 inspected vrf_words=1024 initial_words=1024 source_bytes=3440 csr_words=12'
            and lines[2] == 'PASSED: '+NAME+' checks=26 errors=0', 'host complete contract differs')
    mutations = ['dest','tail','register','initial','source','activation','descriptor','guard',
                 'sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip',
                 'cancel','sourcecancel','caps-vlen','caps-abi','caps-q5']
    regions = dict(weights=800, activation=2496, descriptor=144, initial=4224, actual=4224, csr=160)
    mutations += [f'byte:{region}:{offset}' for region,size in regions.items()
                  for offset in (0,7,size//2,size-8,size-1)]
    negatives = []
    import subprocess
    for mutation in mutations:
        result = subprocess.run([host,mutation,'0'], cwd=ROOT, capture_output=True, timeout=30)
        require(result.returncode == 1 and b'FAILED: '+NAME.encode() in result.stdout
                and b'PASSED:' not in result.stdout and not any(x in result.stdout for x in
                    (b'unknown fault injection',b'mutation syntax',b'mutation range')), 'mutation escaped: '+mutation)
        log = out/('negative-'+mutation.replace(':','-')+'.log')
        log.write_bytes(result.stdout+result.stderr)
        negatives.append(dict(mutation=mutation, returncode=1, log=str(log), log_sha256=common.sha(log)))
    save(out/'host-negative-tests.json', negatives)
    objects = [b.compile(b.common/n, 'dut-'+n) for n in
               ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects += [b.compile(APP/'main.c','dut-main',inc), b.compile(APP/'execute.S','dut-execute')]
    elf = out/(NAME+'.elf')
    b.bind_sources([b.common/'link.ld', ROOT/'verification/coverage/check_elf_fit.py'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
            f'-Wl,-Map={out/(NAME+".map")}',f'-T{b.common/"link.ld"}',*objects,'-lm',
            f'-L{b.llvm/"lib/generic"}','-lclang_rt.builtins-riscv64','-o',elf], 'dut.link')
    from audit_gap81_m4_phase12 import elf_proof
    proof = elf_proof(b, elf)
    fit_python = ROOT/'verification/tools/soc-venv/bin/python'
    b.tools.update(pins([fit_python.resolve()]))
    b.run([fit_python,ROOT/'verification/coverage/check_elf_fit.py','--elf',elf,
           '--ram-bytes','0x200000','--output',out/'elf-fit.json'],'elf-fit')
    for bound in (b.sources,b.tools,b.link_inputs,legality['source_hashes']):
        verify(bound)
    for name,value in [('source_hashes',b.sources),('tool_hashes',b.tools),
                       ('link-inputs',b.link_inputs),('protected-inputs',legality['source_hashes'])]:
        save(out/(name+'.json'),value)
    record = dict(name=NAME,binary=str(elf),binary_sha256=common.sha(elf),
        sources=sorted(b.sources),source_hashes=b.sources,host_reference=str(APP/'host_reference.c'),
        host_result='\n'.join(lines),host_log=str(out/'host-app.log'),host_log_sha256=common.sha(out/'host-app.log'),
        host_checks=26,dut_checks=24,host_fault_injections_rejected=len(negatives),elf_proof=proof,
        custom_instruction_execution_prechecked=False,vcs_launched=False)
    record_path = out/(NAME+'.precheck.json')
    save(record_path,record)
    artifacts = pins(p for p in out.iterdir() if p.is_file())
    save(out/'artifact_hashes.json',artifacts)
    item = dict(name='app:'+NAME,binary=str(elf),binary_sha256=common.sha(elf),sources=sorted(b.sources),
        evidence=sorted([*artifacts,str(out/'artifact_hashes.json')]),timeout_s=600,
        source_audit='Independent Q5_K raw-byte MAC + Q8_K bsums and independent M4 packing; full VRF/CSR/source guards',
        rationale='One M4 DIRECT Q8_K activation pointer mod16=12; raw400 is predicted, not measured',
        targets=[analysis.SCOPE],precheck=dict(format='accel-host-v1',record=str(record_path),log=str(out/'host-app.log')))
    draft = out/'selection.checked-draft.json'
    save(draft,dict(status='CHECKED_DRAFT_HOST_ONLY_NOT_SUBMITTED',baseline=str(analysis.BASELINE),
        baseline_bits=str(analysis.BASELINE/'combined-bits.json'),cases=[item],vcs_launched=False,
        measured_candidate_gain=None))
    checked = evidence.Evidence()
    checked.pin(draft)
    for name in ('tool_hashes','link-inputs','protected-inputs','artifact_hashes'):
        checked.hashes(checked.read(out/(name+'.json')))
    result = evidence.precheck(item,checked)
    save(out/'checked-precheck.json',dict(status='PASS',scope='host-reference-only',
        read_only_validation=True,result=result,checked_files=checked.files,vcs_launched=False))
    save(out/'draft.sha256.json',pins([draft,out/'checked-precheck.json',out/'artifact_hashes.json']))
    from admit_gap81_m4_phase12 import preflight
    preflight(out)
    print('HOST PREFLIGHT PASS: one command, 4 outputs, full VRF/CSR/guards; '+str(len(negatives))+' mutations rejected')
    print(draft)


if __name__ == '__main__':
    main()
