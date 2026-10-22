"""One bounded GAP108 RISC-V/host build; no Spike custom execution, no VCS."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
import build_gap38_i8_f16_lane3 as common
import gap108_static_contract as static
import audit_gap108_subnormal as audit

ROOT=static.ROOT
APP=ROOT/'apps/qbs_gap108_subnormal'
NAME=APP.name
MUTATIONS=('dest','tail','register','initial','source','activation','descriptor','guard',
    'sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip',
    'byte:weights:799','byte:activation:2495','byte:descriptor:143',
    'byte:initial:4223','byte:actual:4223','byte:csr:159')
require,save,sha,pins,verify=common.require,common.save,common.sha,common.pins,common.verify


def fixtures(phase):
    require(type(phase) is int and phase in (0,1), 'Only two reviewed phases')
    weight=(struct.pack('<HH',0x3c00 if phase==0 else 0x3800,0)+
            bytes([1]*4+[0]*4+[1]*4)+bytes(32)+bytes([0x11]*128))
    activation=(struct.pack('<I',1 if phase==0 else 3)+
                bytes([1]*256)+struct.pack('<16h',*([16]*16)))
    require(len(weight)==176 and len(activation)==292, 'Native Q5/Q8 sizes differ')
    return weight,activation


def oracle_expected(phase):
    from fractions import Fraction
    require(type(phase) is int and phase in (0,1), 'Only two reviewed phases')
    # Exact quantities expressed in units of 2^-149; each FP uop rounds separately.
    units = Fraction(1) if phase == 0 else Fraction(3,2)
    floor = units.numerator // units.denominator
    remainder = units - floor
    rounded = floor + int(remainder > Fraction(1,2) or
                          (remainder == Fraction(1,2) and floor & 1))
    flags = 3 if Fraction(rounded) != units else 0
    stages = [0x43800000,0,rounded,0,rounded*256,rounded*256]
    return dict(phase=phase,scope='bounded-native-IEEE-host-only',dot=256,correction=0,
                bits=stages[-1],flags=flags,csr_flags=8|flags,stage_bits=stages,
                stage_flags=[0,0,flags,0,0,0])


def oracle_check(row, phase):
    require(row==oracle_expected(phase),'Independent per-stage integer/RNE oracle differs')
    total=0
    for value in row['stage_flags']:total|=value
    require(total==row['flags'] and (8|total)==row['csr_flags'], 'Flags must accumulate by OR')


SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')


def spike_check(trace, symbols):
    import re
    require('exception ' not in trace, 'Standard FP32 probe trapped')
    stores={}
    for address,value in re.findall(r'\bmem (0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)', trace):
        address=int(address,16)
        require(address not in stores, 'Duplicate numeric probe store')
        stores[address]=int(value,16)
    expected=[]
    for phase in (0,1):
        row=oracle_expected(phase)
        for bits,flags in zip(row['stage_bits'],row['stage_flags']):expected.extend((bits,flags))
        expected.extend((row['csr_flags'],2))
    require([stores.get(symbols['probe_ledger']+8*i) for i in range(28)]==expected,
            'Exact staged standard FP32 bits/flags/CSR differ')
    require(stores.get(symbols['tohost'])==1 and len(stores)==29,'Standard FP32 probe did not complete exactly')
    return dict(status='STANDARD_FP32_STAGED_NUMERIC_PASS_NOT_CUSTOM_APP',ledger=expected,
        stage_operations=12,phase_oracles=[oracle_expected(0),oracle_expected(1)],
        custom_isa_pass=False,qbs_app_spike_executed=False,full_scalar_isa_verified=False)


def spike_probe(b):
    source=Path(__file__).with_name('gap108_spike_numeric.S')
    b.bind_sources([source])
    oldpre=static.mapping.mapping.qualifier.runner.PRE/'preflight-manifest.json'
    old=static.mapping.life.read_bound(oldpre,static.mapping.mapping.qualifier.runner.PRE_SEAL)
    require(old['input_pins'][str(SPIKE)]==sha(SPIKE), 'Frozen Spike tool differs')
    b.sources.update({str(oldpre):static.mapping.mapping.qualifier.runner.PRE_SEAL})
    b.tools.update(pins([SPIKE]))
    obj=b.compile(source,'spike-numeric')
    elf=b.out/'spike-numeric.elf'
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles',f'-T{b.common/"link.ld"}',
            obj,'-o',elf],'spike-numeric.link')
    raw=b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--symbols',elf],
              'spike-numeric.metadata')
    symbols={r['Symbol']['Name']['Name']:r['Symbol']['Value'] for r in json.loads(raw.stdout)[0]['Symbols']}
    command=[str(SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','-l','--log-commits',str(elf)]
    result=b.run(command,'spike-numeric',timeout=15)
    trace=b.out/'spike-numeric.stderr.log'
    proof=spike_check(trace.read_text(),symbols)
    proof.update(command=command,timeout_s=15,returncode=result.returncode,elf=str(elf),
                 elf_sha256=sha(elf),trace_sha256=sha(trace))
    save(b.out/'spike-preflight.json',proof)
    return proof


class Build(common.Build):
    def __init__(self,out):
        super().__init__(out)
        self.sources=pins([Path(__file__),Path(common.__file__),Path(static.__file__),Path(audit.__file__),
            ROOT/'verification/tests/test_build_gap108_subnormal.py',
            ROOT/'verification/tests/test_gap108_static_contract.py',*[p for p in APP.iterdir() if p.is_file()]])
        self.tools.update(pins([Path(shutil.which(n)).resolve(strict=True) for n in ('as','ld')]))
        for name in ('cc1','collect2'):
            path=self.run([self.host,'-print-prog-name='+name],'host-'+name).stdout.decode().strip()
            self.tools.update(pins([Path(path).resolve(strict=True)]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.absolute()
    require(out.parent==ROOT/'verification/out' and out.resolve()==out and
            out.name.startswith('gap108-subnormal-preflight-729-') and not out.exists(), 'Fresh direct output required')
    prediction=static.contract();protected=prediction['pins']
    # Keep the inherited compiler helper tied to its reviewed GAP107 identity.
    old=static.mapping.qualifier.runner.PRE/'preflight-manifest.json'
    prior=static.mapping.life.read_bound(old,static.mapping.qualifier.runner.PRE_SEAL)
    helper=Path(common.__file__).resolve()
    require(prior['input_pins'][str(helper)]==sha(helper), 'Frozen compiler helper differs')
    protected=static.mapping.life.merge_pins(protected,{str(old):static.mapping.qualifier.runner.PRE_SEAL,
        str(helper):prior['input_pins'][str(helper)]})
    verify(protected);out.mkdir();b=Build(out)
    try:
        save(out/'target-static-contract.json',prediction)
        unit_obj=b.compile(APP/'oracle_tests.c','host-oracle-tests',host=True)
        unit=out/'host-oracle-tests'
        b.link([b.host,unit_obj,'-o',unit],'host-oracle-tests.link')
        require(b.run([unit],'host-oracle-tests',timeout=15).stdout.decode().strip()==
                'GAP108 integer dyadic/RNE oracle tests=14 PASS','Host integer rounding tests differ')
        oracle_obj=b.compile(APP/'host_reference.c','host-independent',host=True)
        oracle=out/'host-reference';b.link([b.host,oracle_obj,'-o',oracle],'host-reference.link')
        rows=[json.loads(line) for line in b.run([oracle],'host-reference',timeout=30).stdout.decode().splitlines()]
        require(len(rows)==2,'Exactly two independent oracle phases required')
        for phase,row in enumerate(rows):
            oracle_check(row,phase);save(out/('oracle-command%d.json'%phase),row)
            w,a=fixtures(phase)
            (out/('weight-native%d.bin'%phase)).write_bytes(w)
            (out/('activation-native%d.bin'%phase)).write_bytes(a)
        inc=[f'-I{APP}','-Wall','-Wextra']
        host_obj=b.compile(APP/'main.c','host-app',[*inc,'-DGAP108_HOST=1'],host=True)
        host=out/'host-app';b.link([b.host,host_obj,'-o',host],'host-app.link')
        lines=b.run([host],'host-app',timeout=30).stdout.decode().splitlines()
        require(lines==['GAP108 command=0 checks=18 errors=0','GAP108 command=1 checks=18 errors=0',
            'GAP108 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
            'PASSED: '+NAME+' checks=44 errors=0'], 'Complete host contract differs')
        negatives=[]
        for phase in (0,1):
            for mutation in MUTATIONS:
                result=subprocess.run([host,mutation,str(phase)],cwd=ROOT,capture_output=True,timeout=10)
                require(result.returncode==1 and b'FAILED: '+NAME.encode() in result.stdout and
                        b'PASSED:' not in result.stdout and b'unknown fault' not in result.stdout,
                        'Host mutation escaped: '+mutation)
                log=out/('negative-%d-%s.log'%(phase,mutation));log.write_bytes(result.stdout+result.stderr)
                negatives.append(dict(phase=phase,mutation=mutation,sha256=sha(log),log=str(log)))
        save(out/'host-negative-tests.json',negatives)
        objects=[b.compile(b.common/n,'dut-'+n) for n in
                 ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
        objects += [b.compile(APP/'main.c','dut-main',inc),b.compile(APP/'execute.S','dut-execute')]
        elf=out/(NAME+'.elf')
        b.bind_sources([b.common/'link.ld',ROOT/'verification/coverage/check_elf_fit.py'])
        b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
            f'-Wl,-Map={out/(NAME+".map")}',f'-T{b.common/"link.ld"}',*objects,'-lm',
            f'-L{b.llvm/"lib/generic"}','-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
        proof=audit.elf_proof(b,elf)
        python=ROOT/'verification/tools/soc-venv/bin/python';b.tools.update(pins([python.resolve()]))
        b.run([python,ROOT/'verification/coverage/check_elf_fit.py','--elf',elf,'--ram-bytes','0x200000',
               '--output',out/'elf-fit.json'],'elf-fit')
        spike=spike_probe(b)
        numeric=dict(scope='bounded-integer-dyadic-RNE-not-RTL-execution',phase_oracles=rows,
            arithmetic='six separately rounded I2F/MUL/FMA stages; no whole-expression fusion',
            rounding='RNE numerical contract; architectural frm preserved2',
            underflow='tininess after rounding AND inexact',flags_combination='bitwise OR',
            architectural_seed=8,architectural_after=[8,11],host_float_used=False)
        save(out/'numeric-proof.json',numeric)
        for value in (b.sources,b.tools,b.link_inputs,protected):verify(value)
        inputs={}
        for value in (protected,b.sources,b.tools,b.link_inputs):inputs=static.mapping.life.merge_pins(inputs,value)
        for name,value in [('source_hashes',b.sources),('tool_hashes',b.tools),
                           ('link-inputs',b.link_inputs),('protected-inputs',protected)]:save(out/(name+'.json'),value)
        save(out/'artifact_hashes.json',pins(p for p in out.iterdir() if p.is_file()))
        record=dict(status='GAP108_HOST_ORACLE_STATIC_ELF_READY_NOT_RTL_PASS',name=NAME,
            binary=str(elf),binary_sha256=sha(elf),baseline=str(static.BASE),baseline_seal=static.BASE_SEAL,
            input_pins=inputs,output_pins=pins([out/'artifact_hashes.json']),host_checks=44,dut_checks=41,
            commands=2,host_negative_tests=len(negatives),budget_s=600,
            expected_bits_per_command=[[0x100],[0x200]],expected_fflags=[0,3],
            expected_csr_fflags=[8,11],elf_proof=proof,numeric_proof=numeric,targets=prediction['targets'],
            full_vrf_words_per_command=1024,spike=spike,
            native_runtime_qualification_required=True,measured_gain=None,vcs_launched=False,
            rtl_changed=False,coverage_admitted=False)
        save(out/'preflight-manifest.json',record)
        print(json.dumps(dict(manifest=str(out/'preflight-manifest.json'),seal=sha(out/'preflight-manifest.json'),
            elf=str(elf),elf_sha256=sha(elf))))
    except Exception as error:
        save(out/'build-failure.json',dict(status='BUILD_REJECTED_NOT_RTL_PASS',reason=type(error).__name__+': '+str(error)))
        raise


if __name__=='__main__':main()
