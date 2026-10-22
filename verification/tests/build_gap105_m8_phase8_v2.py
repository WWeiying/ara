#!/usr/bin/env python3
"""Build one QBS pattern with phase4 control + phase8 target; no VCS/RTL edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
import build_gap38_i8_f16_lane3 as common
from audit_gap105_m8_phase8_v2 import elf_proof

ROOT = common.ROOT
APP = ROOT/'apps/qbs_gap105_m8_phase8'
NAME = APP.name
STATIC = ROOT/'verification/out/qbs-m8-phase8-payload-static-preflight-723-20261006-01/preflight.json'
STATIC_SEAL = 'd0a9cc19b1fc671f23dd7f58d47a4f8e0b8c66bdc16b09fb50f55cde7b0505fb'
REF = ROOT/'verification/qbs/qbs_ref.c'
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
require, save, sha, pins, verify = common.require, common.save, common.sha, common.pins, common.verify


def oracle_check(oracle, static):
    require(oracle['scope'] == 'host-reference-only' and oracle['independent_native_decode'] is True
            and oracle['m8_packing_checked'] is True and oracle['m'] == 8 and oracle['n'] == 1
            and oracle['fflags'] == 0 and oracle['custom_instruction_execution_prechecked'] is False,
            'oracle scope/shape/flags differs')
    require(oracle['expected_bits'] == static['expected_bits'] and
            oracle['integer_dot'] == [256*c for c in range(1,9)] and
            oracle['integer_correction'] == [0]*8, 'oracle arithmetic differs')
    require(len(bytes.fromhex(oracle['activation_hex'])) == 2336, 'M8 native length differs')


def header(out, weight, oracle):
    activation = bytes.fromhex(oracle['activation_hex'])
    lines = ['#ifndef GAP105_DATA_H', '#define GAP105_DATA_H', '#include "contract.h"',
             '_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "native little endian ABI");']
    for command, phase in enumerate((4,8)):
        images = dict(weights=bytes([0xa5])*64+weight+bytes([0xa5])*(800-64-len(weight)),
            activation=bytes([0x5a])*(64+phase)+activation+bytes([0x5a])*(2496-64-phase-len(activation)))
        for name, blob in images.items():
            values = [int.from_bytes(blob[i:i+8], 'little') for i in range(0,len(blob),8)]
            lines.append('static const uint64_t gap105_'+name+str(command)+'[] = {')
            for i in range(0,len(values),8):
                lines.append('  '+', '.join(hex(v) for v in values[i:i+8])+',')
            lines.append('};')
        lines.append('static const uint32_t gap105_expected%d[] = {%s};' %
                     (command, ', '.join(hex(v) for v in oracle['expected_bits'])))
    lines.append('static const gap105_case_t gap105_cases[GAP105_COMMANDS] = {')
    for command, phase in enumerate((4,8)):
        lines.append('  {8, 1, 4, 3, %d, 176, 2336, 0, gap105_weights%d, gap105_activation%d, gap105_expected%d},' %
                     (phase,command,command,command))
    lines += ['};', '#endif']
    (out/'gap105_data.h').write_text('\n'.join(lines)+'\n')


class Build(common.Build):
    def __init__(self, out):
        super().__init__(out)
        self.sources = pins([Path(__file__), Path(common.__file__),
            ROOT/'verification/tests/audit_gap105_m8_phase8_v2.py',
            ROOT/'verification/tests/test_build_gap105_m8_phase8_v2.py', REF,
            *[APP/n for n in ('main.c','execute.S','contract.h','host_reference.c')]])
        self.tools.update(pins([Path(shutil.which(n)).resolve() for n in ('as','ld')]))
        for name in ('cc1','collect2'):
            path = self.run([self.host, '-print-prog-name='+name], 'host-'+name).stdout.decode().strip()
            self.tools.update(pins([Path(path).resolve(strict=True)]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent.resolve() == ROOT/'verification/out' and out.name.startswith('gap105-m8-phase8-')
            and not out.exists(), 'fresh independent output required')
    raw = STATIC.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == STATIC_SEAL, 'static preflight seal differs')
    static = json.loads(raw)
    protected = {**static['input_pins'], **static['fixture_pins'], str(STATIC):STATIC_SEAL}
    verify(protected)
    require(static['latest_target_zero_rechecked'] == 723 and len(static['targets']) == 12,
            'static target binding differs')
    out.mkdir()
    save(out/'static-plan.json', static)
    fixture_root = Path(next(k for k in static['fixture_pins'] if k.endswith('weight-native.bin'))).parent
    for name in ('weight-native.bin','activation-row-native.bin'):
        (out/name).write_bytes((fixture_root/name).read_bytes())
    b = Build(out)
    ref_obj = b.compile(REF, 'host-qbs-ref', host=True)
    oracle_obj = b.compile(APP/'host_reference.c', 'host-independent', host=True)
    oracle_exe = out/'host-reference'
    b.link([b.host, oracle_obj, ref_obj, '-lm', '-o', oracle_exe], 'host-reference.link')
    oracle = json.loads(b.run([oracle_exe,4,8,1,3,out/'weight-native.bin',out/'activation-row-native.bin'],
                            'host-reference', timeout=30).stdout)
    oracle_check(oracle, static)
    require(bytes.fromhex(oracle['activation_hex']) == (fixture_root/'activation-m8-native.bin').read_bytes(),
            'C/Python independent packing differs')
    save(out/'oracle-command0.json', oracle)
    header(out, (out/'weight-native.bin').read_bytes(), oracle)
    inc = [f'-I{out}',f'-I{APP}','-Wall','-Wextra']
    host_obj = b.compile(APP/'main.c','host-app',[*inc,'-DGAP105_HOST=1'],host=True)
    host = out/'host-app'
    b.link([b.host,host_obj,ref_obj,'-lm','-o',host],'host-app.link')
    lines = b.run([host],'host-app',timeout=30).stdout.decode().splitlines()
    require(lines == ['GAP105 command=0 checks=18 errors=0', 'GAP105 command=1 checks=18 errors=0',
        'GAP105 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
        'PASSED: '+NAME+' checks=44 errors=0'], 'host complete contract differs')
    negatives = []
    for command in (0,1):
        for mutation in ('dest','tail','register','initial','source','activation','descriptor',
                         'guard','sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip'):
            result = subprocess.run([host,mutation,str(command)],cwd=ROOT,capture_output=True,timeout=30)
            require(result.returncode == 1 and b'FAILED: '+NAME.encode() in result.stdout
                    and b'PASSED:' not in result.stdout and b'unknown fault' not in result.stdout,
                    'mutation escaped: '+mutation)
            log = out/('negative-%d-%s.log' % (command,mutation))
            log.write_bytes(result.stdout+result.stderr)
            negatives.append(dict(command=command,mutation=mutation,log=str(log),sha256=sha(log)))
    save(out/'host-negative-tests.json',negatives)
    objects = [b.compile(b.common/n,'dut-'+n) for n in
               ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects += [b.compile(APP/'main.c','dut-main',inc), b.compile(APP/'execute.S','dut-execute')]
    elf = out/(NAME+'.elf')
    b.bind_sources([b.common/'link.ld',ROOT/'verification/coverage/check_elf_fit.py'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
        f'-Wl,-Map={out/(NAME+".map")}',f'-T{b.common/"link.ld"}',*objects,'-lm',
        f'-L{b.llvm/"lib/generic"}','-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    proof = elf_proof(b,elf)
    fit_python = ROOT/'verification/tools/soc-venv/bin/python'
    b.tools.update(pins([fit_python.resolve()]))
    b.run([fit_python,ROOT/'verification/coverage/check_elf_fit.py','--elf',elf,
           '--ram-bytes','0x200000','--output',out/'elf-fit.json'],'elf-fit')
    # Preserve Spike's actual failure rather than interpreting unsupported custom ISA as a PASS.
    b.tools.update(pins([SPIKE.resolve()]))
    cmd = [str(SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','-l','--log-commits',str(elf)]
    result = subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=30)
    (out/'spike.stdout').write_bytes(result.stdout)
    (out/'spike.trace').write_bytes(result.stderr)
    spike = dict(command=cmd,timeout_s=30,returncode=result.returncode,
                 trace_sha256=sha(out/'spike.trace'),stdout_sha256=sha(out/'spike.stdout'),
                 status='NOT_FUNCTIONALLY_VERIFIED',custom_isa_pass=False)
    trace = result.stderr.decode(errors='replace')
    require('trap_illegal_instruction' in trace and
            ('0x%016x' % proof['qbinfo_pc']) in trace, 'unexpected Spike outcome; inspect preserved trace')
    spike.update(status='QBS_CUSTOM_ISA_UNSUPPORTED_QBINFO_ILLEGAL_NOT_PASS',qbinfo_pc=proof['qbinfo_pc'])
    save(out/'spike-preflight.json',spike)
    for bound in (b.sources,b.tools,b.link_inputs,protected):
        verify(bound)
    for name,value in [('source_hashes',b.sources),('tool_hashes',b.tools),
                       ('link-inputs',b.link_inputs),('protected-inputs',protected)]:
        save(out/(name+'.json'),value)
    artifacts = pins(path for path in out.iterdir() if path.is_file())
    save(out/'artifact_hashes.json',artifacts)
    record = dict(status='HOST_ORACLE_ELF_READY_SPIKE_CUSTOM_ISA_UNSUPPORTED_NOT_RTL_PASS',
        name=NAME,binary=str(elf),binary_sha256=sha(elf),baseline=static['baseline'],
        baseline_seal=static['baseline_seal'],input_pins={**protected,**b.sources,**b.tools,**b.link_inputs},
        output_pins=pins([out/'artifact_hashes.json']),host_checks=44,dut_checks=41,
        commands=2,phase_order=[4,8],host_negative_tests=len(negatives),
        full_vrf_words_per_command=1024,expected_bits_per_command=oracle['expected_bits'],
        elf_proof=proof,spike=spike,targets=static['targets'],scope=static['scope'],
        measured_gain=None,vcs_launched=False,rtl_changed=False,coverage_admitted=False)
    path = out/'preflight-manifest.json'
    save(path,record)
    print(json.dumps(dict(output=str(path),seal=sha(path),elf=str(elf),spike=spike['status'])))


if __name__ == '__main__':
    main()
