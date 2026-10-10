"""One bounded host/native and ELF preflight; no VCS or custom Spike fiction."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
import build_gap38_i8_f16_lane3 as common
import gap110_q3_r4_contract as static
import audit_gap110_q3_r4 as audit

ROOT=static.ROOT
APP=ROOT/'apps/qbs_gap110_q3_r4_tail'
NAME=APP.name
require,save,sha,pins,verify=common.require,common.save,common.sha,common.pins,common.verify
MUTATIONS=('dest','tail','register','unused','initial','source','activation','padding','descriptor',
    'guard','sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip','cancel','sourcecancel')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.absolute()
    require(out.parent==ROOT/'verification/out' and out.resolve()==out and not out.exists() and
            out.name.startswith('gap110-q3-r4-preflight-732-'),'Fresh independent output required')
    prediction=static.contract();protected=prediction['pins']
    old=static.mapping.qualifier.runner.PRE/'preflight-manifest.json'
    prior=static.life.read_bound(old,static.mapping.qualifier.runner.PRE_SEAL)
    helper=Path(common.__file__).resolve()
    require(prior['input_pins'][str(helper)]==sha(helper),'Frozen build helper differs')
    protected=static.life.merge_pins(protected,{str(helper):prior['input_pins'][str(helper)],
        str(old):static.mapping.qualifier.runner.PRE_SEAL})
    verify(protected);out.mkdir();b=common.Build(out)
    b.sources=pins([Path(__file__),Path(static.__file__),Path(audit.__file__),helper,
        Path(__file__).with_name('test_build_gap110_q3_r4.py'),*[p for p in APP.iterdir() if p.is_file()]])
    b.tools.update(pins([Path(shutil.which(n)).resolve(strict=True) for n in ('as','ld')]))
    for name in ('cc1','collect2'):
        tool=b.run([b.host,'-print-prog-name='+name],'host-'+name).stdout.decode().strip()
        b.tools.update(pins([Path(tool).resolve(strict=True)]))
    try:
        save(out/'target-static-contract.json',prediction)
        for source,label in [('oracle_tests.c','host-oracle-tests'),('host_reference.c','host-reference')]:
            obj=b.compile(APP/source,label,host=True);exe=out/label;b.link([b.host,obj,'-o',exe],label+'.link')
            raw=b.run([exe],label,timeout=20).stdout.decode()
            if label=='host-oracle-tests':require(raw.strip()=='GAP110 independent native tests=12 PASS','Native negative oracle tests')
            else:
                rows=[json.loads(line) for line in raw.splitlines()];require(len(rows)==2,'Two independent references required')
                for phase,row in enumerate(rows):
                    w,a=static.fixtures(phase)
                    require(row==static.unpack_oracle(w,a,7 if phase==0 else 5),'C/Python native unpack differs')
                    save(out/('oracle-command%d.json'%phase),row)
                    (out/('weight-native%d.bin'%phase)).write_bytes(w)
                    (out/('activation-native%d.bin'%phase)).write_bytes(a)
        inc=[f'-I{APP}','-Wall','-Wextra']
        obj=b.compile(APP/'main.c','host-app',[*inc,'-DGAP110_HOST=1'],host=True)
        host=out/'host-app';b.link([b.host,obj,'-o',host],'host-app.link')
        lines=b.run([host],'host-app',timeout=30).stdout.decode().splitlines()
        require(lines==['GAP110 command=0 checks=18 errors=0','GAP110 command=1 checks=18 errors=0',
            'GAP110 inspected vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24',
            'PASSED: '+NAME+' checks=44 errors=0'],'Full host VRF/CSR/guard checks')
        negatives=[]
        for phase in (0,1):
            for mutation in MUTATIONS:
                result=subprocess.run([host,mutation,str(phase)],cwd=ROOT,capture_output=True,timeout=10)
                require(result.returncode==1 and b'FAILED: '+NAME.encode() in result.stdout and
                    b'PASSED:' not in result.stdout and b'unknown fault' not in result.stdout,'Escaped mutation: '+mutation)
                log=out/('negative-%d-%s.log'%(phase,mutation));log.write_bytes(result.stdout+result.stderr)
                negatives.append(dict(phase=phase,mutation=mutation,log=str(log),sha256=sha(log)))
        save(out/'host-negative-tests.json',negatives)
        objects=[b.compile(b.common/n,'dut-'+n) for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
        objects += [b.compile(APP/'main.c','dut-main',inc),b.compile(APP/'execute.S','dut-execute')]
        elf=out/(NAME+'.elf');b.bind_sources([b.common/'link.ld',ROOT/'verification/coverage/check_elf_fit.py'])
        b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
            f'-Wl,-Map={out/(NAME+".map")}',f'-T{b.common/"link.ld"}',*objects,'-lm',
            f'-L{b.llvm/"lib/generic"}','-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
        proof=audit.elf_proof(b,elf)
        python=ROOT/'verification/tools/soc-venv/bin/python';b.tools.update(pins([python.resolve()]))
        b.run([python,ROOT/'verification/coverage/check_elf_fit.py','--elf',elf,'--ram-bytes','0x200000',
            '--output',out/'elf-fit.json'],'elf-fit')
        inputs={}
        for value in (protected,b.sources,b.tools,b.link_inputs):
            verify(value);inputs=static.life.merge_pins(inputs,value)
        for name,value in [('source_hashes',b.sources),('tool_hashes',b.tools),('link-inputs',b.link_inputs),('protected-inputs',protected)]:save(out/(name+'.json'),value)
        save(out/'artifact_hashes.json',pins(p for p in out.iterdir() if p.is_file()))
        record=dict(status='GAP110_HOST_NATIVE_STATIC_ELF_READY_NOT_RTL_PASS',name=NAME,binary=str(elf),binary_sha256=sha(elf),
            baseline=str(static.BASE),baseline_seal=static.BASE_SEAL,input_pins=inputs,
            output_pins=pins([out/'artifact_hashes.json']),targets=prediction['targets'],
            commands=2,host_checks=44,dut_checks=41,host_negative_tests=len(negatives),budget_s=600,
            expected_bits_per_command=[row['bits'] for row in rows],expected_fflags=[0,0],expected_csr_fflags=[8,8],
            elf_proof=proof,spike=dict(status='NOT_EXECUTED_CUSTOM_UNSUPPORTED',custom_isa_pass=False,full_scalar_isa_verified=False),
            oracle_scope='independent Q3/Q8 native unpack; unit scales, separately exact integer/FMA stages',
            full_vrf_words_per_command=1024,native_runtime_qualification_required=True,
            measured_gain=None,vcs_launched=False,rtl_changed=False,coverage_admitted=False)
        save(out/'preflight-manifest.json',record)
        print(json.dumps(dict(manifest=str(out/'preflight-manifest.json'),seal=sha(out/'preflight-manifest.json'),elf_sha256=sha(elf))))
    except Exception as error:
        save(out/'build-failure.json',dict(status='BUILD_REJECTED',reason=type(error).__name__+': '+str(error)));raise


if __name__=='__main__':main()
