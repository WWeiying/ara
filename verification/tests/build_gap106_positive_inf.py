"""Independent finite/+Inf Q5_K native preflight; never launches VCS."""
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
from audit_gap106_positive_inf import elf_proof
sys.path.insert(0, str(common.ROOT/'verification/coverage'))
import closure_point_inventory as inventory

ROOT = common.ROOT
APP = ROOT/'apps/qbs_gap106_positive_inf'
NAME = APP.name
BASE = ROOT/'verification/out/gap105-offline-admitted-725-parent-20261006-01'
BASE_SEAL = '0f49638e8cea36b28b5832e7eaeea39ee9b5249a162de3f3732c0fcd13a5a397'
DESIGN = ROOT/'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_fp_accumulator'
DISPATCHER = ROOT/'verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv'
DISPATCHER_SHA = '9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'
REF = ROOT/'verification/qbs/qbs_ref.c'
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
require, save, sha, pins, verify = common.require, common.save, common.sha, common.pins, common.verify
MUTATIONS = ('dest','tail','register','initial','source','activation','descriptor',
             'guard','sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip')


def bound(path, expected):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'bound bytes differ: '+str(path))
    return json.loads(raw)


def source_targets():
    manifest = bound(BASE/'admission-manifest.json', BASE_SEAL)
    book_path = BASE/'evidence-pins.json'
    book = bound(book_path, manifest['output_pins'][str(book_path)])
    bits_path = BASE/'combined-bits.json'
    bits = bound(bits_path, manifest['output_pins'][str(bits_path)])
    require(len(bits['tests']) == len(set(bits['tests'])) == 725, 'not formal725')
    protected = {str(BASE/'admission-manifest.json'):BASE_SEAL,
                 str(book_path):manifest['output_pins'][str(book_path)],
                 str(bits_path):manifest['output_pins'][str(bits_path)],
                 str(DISPATCHER):DISPATCHER_SHA}
    sources = ['hardware/src/ara.sv','hardware/src/ara_sequencer.sv',
               'hardware/src/segment_sequencer.sv','hardware/src/vlsu/vlsu.sv',
               'hardware/include/qbs_pkg.sv',
               *['hardware/src/vlsu/qbs/'+n+'.sv' for n in
                 ('qbs_engine','qbs_descriptor_decoder','qbs_block_adapter',
                  'qbs_payload_buffer','qbs_read_engine','qbs_compute_engine',
                  'qbs_profile_decoder','qbs_profile_engine_int','qbs_fp_accumulator','qbs_commit')]]
    for relative in sources:
        path = ROOT/relative
        require(str(path) in book, 'missing old source pin: '+relative)
        protected[str(path)] = book[str(path)]
    db = DESIGN/'snps/coverage/db'
    for relative, expected in bits['design'].items():
        protected[str(db/relative)] = expected
    for relative in ('shape/cond.verilog.info.xml','auxiliary/verilog.sourceinfo.xml'):
        path=db/relative
        require(str(path) in book, 'missing compiled identity pin')
        protected[str(path)]=book[str(path)]
    verify(protected)
    metric = bits['metrics']['cond'][SCOPE]
    require(metric['width'] == 876 and str(metric['checksum']) == '3394658800', 'target shape differs')
    info={n.get('name'):n.get('chksum') for n in
          inventory.read_xml(db/'shape/cond.verilog.info.xml').iter('instance_data')}
    require(info.get(SCOPE)=='3394658800', 'native instance identity differs')
    files={n.get('id'):n.get('name') for n in
           inventory.read_xml(db/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    require(files.get('574')==str(ROOT/'hardware/src/vlsu/qbs/qbs_fp_accumulator.sv'),
            'native file ownership differs')
    shape = inventory.read_xml(db/'shape/cond.verilog.shape.xml')
    defs = [n for n in shape if n.get('chksum') == '3394658800']
    require(len(defs) == 1, 'ambiguous target definition')
    points = {p['raw_index']:p for p in inventory.points('cond',defs[0],876)}
    targets = [points[i] for i in (4,7)]
    require([(p['native_id'],p['line'],p['vector'],p['file_id']) for p in targets] ==
            [('3','180','1','574'),('4','183','0','574')], 'exact native targets differ')
    require(all(not (int(metric['bits'],16) >> (875-p['raw_index']) & 1)
                for p in targets), 'target already hit')
    dispatcher = DISPATCHER.read_text()
    qb = dispatcher.split('end else if (is_qbexec) begin',1)[1].split('end else if',1)[0]
    require('ara_req.vl = vlen_t\'(qbs_m * (VLEN / 32));' in qb and
            'qbs_funct7[6:3]' in qb and 'QbsDescriptorAlignmentLog2' in qb and
            'QbsActivationBaseAlignmentLog2' in qb, 'reviewed QBEXEC gate differs')
    fp = (ROOT/'hardware/src/vlsu/qbs/qbs_fp_accumulator.sv').read_text()
    require("else if (exponent == 5'h1f)" in fp and
            'fp16_to_fp32(request_weight_d_i)' in fp and
            'fp_operands[1] = entry_dot_value_q[entry];' in fp and
            "entry_first_block_q[fp_tag_out]\n                  ? '0" in fp,
            'numeric pipeline differs')
    return protected, targets


def fixtures(scale):
    require(scale in (0x3c00,0x7c00), 'only finite control / positive-Inf')
    weight = (struct.pack('<HH',scale,0)+bytes([1]*4+[0]*4+[1]*4)+
              bytes(32)+bytes([0x11]*128))
    activation = struct.pack('<f',1.0)+bytes([1]*256)+struct.pack('<16h',*([16]*16))
    require(len(weight)==176 and len(activation)==292, 'fixture ABI')
    return weight, activation


def oracle_check(oracle, command):
    require(oracle['scope']=='host-reference-only' and oracle['independent_native_decode'] is True and
            oracle['row_major_bytes_checked'] is True and oracle['m']==1 and oracle['n']==1 and
            oracle['custom_instruction_execution_prechecked'] is False and oracle['fflags']==0,
            'oracle scope/flags differ')
    require(oracle['integer_dot']==[256] and oracle['integer_correction']==[0] and
            oracle['expected_bits']==[[0x43800000],[0x7f800000]][command] and
            bytes.fromhex(oracle['activation_hex'])==fixtures(0x3c00)[1], 'independent arithmetic differs')


def header(out, oracles):
    lines = ['#ifndef GAP106_DATA_H','#define GAP106_DATA_H','#include "contract.h"',
             '_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "little endian ABI");']
    for command, scale in enumerate((0x3c00,0x7c00)):
        w,a = fixtures(scale)
        for name,blob in {'weights':bytes([0xa5])*64+w+bytes([0xa5])*(800-64-176),
                          'activation':bytes([0x5a])*64+a+bytes([0x5a])*(2496-64-292)}.items():
            values = [int.from_bytes(blob[i:i+8],'little') for i in range(0,len(blob),8)]
            lines.append('static const uint64_t gap106_%s%d[] = {'%(name,command))
            for i in range(0,len(values),8):
                lines.append('  '+', '.join(hex(v) for v in values[i:i+8])+',')
            lines.append('};')
        lines.append('static const uint32_t gap106_expected%d[] = {%s};'%
                     (command,hex(oracles[command]['expected_bits'][0])))
    lines.append('static const gap106_case_t gap106_cases[GAP106_COMMANDS] = {')
    for command in (0,1):
        lines.append('  {1,1,4,1,0,176,292,0,gap106_weights%d,gap106_activation%d,gap106_expected%d},'%
                     (command,command,command))
    lines += ['};','#endif']
    (out/'gap106_data.h').write_text('\n'.join(lines)+'\n')


class Build(common.Build):
    def __init__(self,out):
        super().__init__(out)
        self.sources = pins([Path(__file__),Path(common.__file__),Path(inventory.__file__),
            ROOT/'verification/tests/audit_gap106_positive_inf.py',
            ROOT/'verification/tests/test_build_gap106_positive_inf.py',REF,
            *[APP/n for n in ('main.c','execute.S','contract.h','host_reference.c')]])
        self.tools.update(pins([Path(shutil.which(n)).resolve() for n in ('as','ld')]))
        for name in ('cc1','collect2'):
            p=self.run([self.host,'-print-prog-name='+name],'host-'+name).stdout.decode().strip()
            self.tools.update(pins([Path(p).resolve(strict=True)]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.absolute()
    require(out.parent.resolve()==ROOT/'verification/out' and
            out.name.startswith('gap106-positive-inf-') and not out.exists(), 'fresh output required')
    protected,targets=source_targets()
    out.mkdir()
    b=Build(out)
    ref_obj=b.compile(REF,'host-qbs-ref',host=True)
    oracle_obj=b.compile(APP/'host_reference.c','host-independent',host=True)
    exe=out/'host-reference'
    b.link([b.host,oracle_obj,ref_obj,'-lm','-o',exe],'host-reference.link')
    oracles=[]
    for command,scale in enumerate((0x3c00,0x7c00)):
        w,a=fixtures(scale)
        (out/('weight-native%d.bin'%command)).write_bytes(w)
        (out/'activation-row-native.bin').write_bytes(a)
        oracle=json.loads(b.run([exe,4,1,1,1,out/('weight-native%d.bin'%command),
                               out/'activation-row-native.bin'],'host-reference%d'%command,timeout=30).stdout)
        oracle_check(oracle,command)
        save(out/('oracle-command%d.json'%command),oracle)
        oracles.append(oracle)
    header(out,oracles)
    inc=[f'-I{out}',f'-I{APP}','-Wall','-Wextra']
    host_obj=b.compile(APP/'main.c','host-app',[*inc,'-DGAP106_HOST=1'],host=True)
    host=out/'host-app'
    b.link([b.host,host_obj,ref_obj,'-lm','-o',host],'host-app.link')
    lines=b.run([host],'host-app',timeout=30).stdout.decode().splitlines()
    require(lines==['GAP106 command=0 checks=18 errors=0','GAP106 command=1 checks=18 errors=0',
        'GAP106 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
        'PASSED: '+NAME+' checks=44 errors=0'], 'full host contract differs')
    negatives=[]
    for command in (0,1):
        for mutation in MUTATIONS:
            result=subprocess.run([host,mutation,str(command)],cwd=ROOT,capture_output=True,timeout=30)
            require(result.returncode==1 and b'FAILED: '+NAME.encode() in result.stdout and
                    b'PASSED:' not in result.stdout and b'unknown fault' not in result.stdout,
                    'mutation escaped: '+mutation)
            log=out/('negative-%d-%s.log'%(command,mutation))
            log.write_bytes(result.stdout+result.stderr)
            negatives.append(dict(command=command,mutation=mutation,log=str(log),sha256=sha(log)))
    save(out/'host-negative-tests.json',negatives)
    objects=[b.compile(b.common/n,'dut-'+n) for n in
             ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects += [b.compile(APP/'main.c','dut-main',inc),b.compile(APP/'execute.S','dut-execute')]
    elf=out/(NAME+'.elf')
    b.bind_sources([b.common/'link.ld',ROOT/'verification/coverage/check_elf_fit.py'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
        f'-Wl,-Map={out/(NAME+".map")}',f'-T{b.common/"link.ld"}',*objects,'-lm',
        f'-L{b.llvm/"lib/generic"}','-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    proof=elf_proof(b,elf)
    fit_python=ROOT/'verification/tools/soc-venv/bin/python'
    b.tools.update(pins([fit_python.resolve()]))
    b.run([fit_python,ROOT/'verification/coverage/check_elf_fit.py','--elf',elf,
           '--ram-bytes','0x200000','--output',out/'elf-fit.json'],'elf-fit')
    # Only reuse the frozen support probe; it does not execute this custom app.
    from gap105_spike_capability import probe
    b.sources.update(pins([ROOT/'verification/tests/gap105_spike_capability.py',
                          ROOT/'verification/tests/gap105_spike_capability_probe.S']))
    b.tools.update(pins([SPIKE.resolve()]))
    spike=probe(b,SPIKE)
    numeric=dict(weight_d=[0x3c00,0x7c00],activation_d=0x3f800000,
        dot=256,correction=0,dmin=0,first_block_accumulator=0,
        stages=['I2F(256)','I2F(0)','d * 1','0 * 1','FMA(scaled_d,256,+0)',
                'FMA(-0,0,positive)'],expected_bits=[0x43800000,0x7f800000],
        generated_fflags=0,architectural_fflags_seed=8,architectural_fflags_after=8,
        inf_times_zero=False,inf_minus_inf=False,spike_custom_pass=False)
    save(out/'numeric-proof.json',numeric)
    for value in (b.sources,b.tools,b.link_inputs,protected):verify(value)
    for name,value in [('source_hashes',b.sources),('tool_hashes',b.tools),
                       ('link-inputs',b.link_inputs),('protected-inputs',protected)]:save(out/(name+'.json'),value)
    artifacts=pins(p for p in out.iterdir() if p.is_file())
    save(out/'artifact_hashes.json',artifacts)
    record=dict(status='HOST_ORACLE_ELF_READY_SPIKE_CUSTOM_ISA_UNSUPPORTED_NOT_RTL_PASS',
        name=NAME,binary=str(elf),binary_sha256=sha(elf),baseline=str(BASE),baseline_seal=BASE_SEAL,
        input_pins={**protected,**b.sources,**b.tools,**b.link_inputs},
        output_pins=pins([out/'artifact_hashes.json']),host_checks=44,dut_checks=41,commands=2,
        phase_order=[0,0],host_negative_tests=34,full_vrf_words_per_command=1024,
        expected_bits_per_command=[o['expected_bits'] for o in oracles],numeric_proof=numeric,
        elf_proof=proof,spike=spike,targets=targets,scope=SCOPE,
        measured_gain=None,vcs_launched=False,rtl_changed=False,coverage_admitted=False)
    save(out/'preflight-manifest.json',record)
    print(json.dumps(dict(output=str(out/'preflight-manifest.json'),seal=sha(out/'preflight-manifest.json'),
                         elf=str(elf),elf_sha256=sha(elf))))


if __name__=='__main__':main()
