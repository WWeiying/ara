#!/usr/bin/env python3
"""Freeze compact SDK and build three-mode Attention firmware. Never runs RTL."""
import argparse
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
from contract import (HERE, ROOT, OUT, REV, CC, SDK_OVERLAYS, FORBIDDEN, ORACLE,
                      GEOMETRY, LEGACY, ELF, MODES, cases, load, require, save, sha, verify)
from capture import read_capture, model_error, ORIGINAL
from expf_audit import audit_expf

REVIEWED = OUT / "resident_direct_model_20261114_03"
FREEZE_SHA = "641fdb65dca29dd3410bb2b96c4729c4e48a883aa7560d9caf78c158df2f61e9"
OWN = ("contract.py", "prepare.py", "check.py", "capture.py", "oracle.py",
       "main.c", "rvv.c", "memory.S", "replay_rotation.S", "replay_wrap.S",
       "check_activity.py", "expf_audit.py", "test_real.py", "DERIVATION.json", "README.md")


def fixture(case, data, capture_pins, output, order):
    f = load(ORACLE, "attention_checked_oracle")
    pins = dict(capture_pins)
    result = f.reference(case, data)
    comparison = model_error(result['bits'],data['model_golden'])
    require(comparison['all_outputs_within_tolerance'], 'Independent oracle/model mismatch: '+str(comparison))
    pins.update(result["oracle_pins"])
    query = bytearray(b"\xa5"*(8*128*2))
    active = bytes.fromhex(result["query_half"])
    d, h, rows = case["dimension"], case["heads"], case["heads"]//case["kv_heads"]
    for head in range(h):
        query[head*256:head*256+d*2] = active[head*d*2:(head+1)*d*2]
    count = 8*64+(8*128-h*d)*6+rows*(256-d)*2+(8-rows)*(512+256+12)+32
    memory = dict(query_hash=f.fnv(query), guard_bytes=count,
                  guard_hash=f.fnv(b"\xa5"*count))
    payload = bytearray()
    assembly = ['.section .rodata.attention,"a",@progbits', '.balign 64',
                '.global data_guard_before', 'data_guard_before:', '.fill 64,1,0xa5',
                '.global data_begin', 'data_begin:']
    header = ['#ifndef OP_ATTN_FIXTURE_H', '#define OP_ATTN_FIXTURE_H']
    for role, width in (("query",32), ("key",16), ("value",16), ("mask",16), ("golden",32), ("model_golden",32)):
        raw = f.pack(result["bits"],32) if role == "golden" else data[role]
        path = output/(role+".bin")
        path.write_bytes(raw)
        payload += bytes(-len(payload) % 64)+raw
        symbol = "fixture_"+role
        assembly += ['.balign 64', '.global '+symbol, symbol+':', '.incbin '+json.dumps(str(path))]
        typename = "float" if role in ("query","model_golden") else "uint%d_t" % width
        header.append('extern const %s %s[%d];' % (typename,symbol,len(raw)//(width//8)))
    assembly += ['.global data_end', 'data_end:', '.global data_guard_after', 'data_guard_after:',
                 '.fill 64,1,0xa5', '.section .note.GNU-stack,"",@progbits']
    values = dict(DIM=d, HEADS=h, KVHEADS=case["kv_heads"], TOKENS=case["tokens"],
                  CAPACITY=case["capacity"], CALLS=len(order), INITIAL_FLAGS=case["initial_flags"],
                  EXPECT_FLAGS=result["expected_fcsr"], DATA_BYTES=len(payload), DATA_HASH=f.fnv(payload),
                  **{k.upper():v for k,v in memory.items()})
    header += ['#define ATTN_%s UINT64_C(0x%x)' % item for item in values.items()]
    header += ['static const unsigned attention_order[ATTN_CALLS] = {'+
               ','.join(map(str,order))+'};',
               '#define ATTN_SCALE '+f.float32(case['scale_bits']).hex()+'f',
               '#define ATTN_PRINT_VALUES 64', '#endif']
    (output/'data.S').write_text('\n'.join(assembly)+'\n')
    (output/'fixture.h').write_text('\n'.join(header)+'\n')
    receipt = dict(case=case, order=order, result=result, memory=memory,
                   data_bytes=len(payload), data_hash=f.fnv(payload),
                   provenance=case["provenance"],
                   primary_model_performance_eligible=True,model_comparison=comparison,
                   output_hash=f.fnv(f.pack(result['bits'],32)),printed_values=64,
                   scalar_expf_contract='Installed newlib ef_exp FMA schedule, independently evaluated with SoftFloat; audited |x|<88')
    save(output/'fixture.json',receipt)
    return receipt, pins


def build(output, capture, heads, order):
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == OUT.resolve() and
            re.fullmatch(r"operator_attention_real_prepare_20261115_[A-Za-z0-9_.-]+",output.name)
            and not output.exists(), "Fresh owned signoff output required")
    for key in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "LD_PRELOAD",
                "LD_LIBRARY_PATH", "GCC_EXEC_PREFIX", "COMPILER_PATH", "CFLAGS", "LDFLAGS"):
        require(not os.environ.get(key), "Compiler environment injection: "+key)
    output.mkdir()
    inputs = output/'inputs'
    inputs.mkdir()
    pins, commands = {}, []
    env = dict(PATH='/usr/bin:/bin', HOME=str(output), LC_ALL='C', TZ='UTC',
               PYTHONDONTWRITEBYTECODE='1')

    def pin(p):
        p = Path(p).resolve(strict=True)
        digest = sha(p)
        require(str(p) not in pins or pins[str(p)] == digest, "Input changed: "+str(p))
        pins[str(p)] = digest

    def run(label, argv):
        argv = list(map(str,argv))
        proc = subprocess.run(argv,cwd=output,env=env,stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,timeout=180)
        (output/(label+'.log')).write_bytes(proc.stdout)
        commands.append(dict(label=label,argv=argv,returncode=proc.returncode))
        require(proc.returncode == 0, "Command failed: "+label+"; "+proc.stdout[-1500:].decode(errors='replace'))
        return proc.stdout.decode().strip()

    report = dict(state='FAIL', schema='real-context-attention-firmware-v1',
                  target_executed=False,rtl_executed=False,performance_measured=False)
    try:
        for name in OWN:
            pin(HERE/name)
            shutil.copyfile(HERE/name,inputs/name)
        derivation = json.loads((HERE/'DERIVATION.json').read_text())
        for label in ('expf_anchor','expf_source','expf_elf'):
            p = Path(derivation[label])
            require(sha(p) == derivation[label+'_sha256'], 'Expf contract drift: '+label)
            pin(p)
        for rel,digest in derivation['snapshots'].items():
            require(sha(HERE/rel) == digest, 'Ancestor snapshot drift: '+rel)
            pin(HERE/rel)
        require(sha(HERE/'replay_rotation.S') == derivation['replay_rotation_sha256'],
                'Established rotating-register implementation drift')
        for p in (ORACLE, GEOMETRY, LEGACY, ELF,
                  ROOT/'verification/performance/resident_rvv/qk_shared/geometry.py',
                  ROOT/'verification/performance/akv_pair_eval/build.py',
                  ROOT/'verification/fpnew_upstream_20261009/oracle.py', Path(sys.executable), CC):
            pin(p)
        reviewed = REVIEWED/'freeze.json'
        # The receipt fixes every approved overlay independently of today's tree.
        require(sha(reviewed) == FREEZE_SHA, "Compact approval receipt drift")
        freeze = json.loads(reviewed.read_text())
        approved = {e['path']:e['sha256'] for e in freeze['ara']['overlays'] if e['path'] in SDK_OVERLAYS}
        require(set(approved) == set(SDK_OVERLAYS), "Reviewed compact whitelist incomplete")
        pin(reviewed)
        archive = subprocess.check_output(['git','-C',str(ROOT),'archive',REV,'software/akv','apps/common'],timeout=60)
        (inputs/'sdk.tar').write_bytes(archive)
        sdkroot = inputs/'sdk'
        sdkroot.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                        '..' not in Path(m.name).parts for m in tar.getmembers()), "Unsafe SDK archive")
            tar.extractall(sdkroot)
        assembly_sha = sha(sdkroot/FORBIDDEN)
        require(assembly_sha == freeze['ara']['archive_native_assembly_sha256'], "Archived native assembly drift")
        for rel in SDK_OVERLAYS:
            source = REVIEWED/'inputs/sdk'/rel
            require(sha(source) == approved[rel], "Reviewed overlay drift: "+rel)
            pin(source)
            shutil.copyfile(source,sdkroot/rel)
        require(sha(sdkroot/FORBIDDEN) == assembly_sha, "Dirty AKV assembly imported")
        case, data, capture_pins = read_capture(capture,heads)
        result, fixture_pins = fixture(case,data,capture_pins,inputs,order)
        pins.update(fixture_pins)
        sdk, common = sdkroot/'software/akv', sdkroot/'apps/common'
        link = (common/'arch.link.ld').read_text()
        require(link.count('LENGTH = 0x00100000') == 1, "Linker template drift")
        (inputs/'link.ld').write_text(link.replace('ALIGNMENT','16').replace(
            'LENGTH = 0x00100000','LENGTH = 0x01000000'))
        for p in inputs.rglob('*'):
            if p.is_file(): pin(p)
        flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax',
            '-O3','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-fno-ipa-cp',
            '-fno-optimize-sibling-calls','-ffunction-sections','-fdata-sections',
            '-std=gnu11','-Wall','-Wextra','-Wno-unknown-pragmas',
            '-DNR_LANES=4','-DVLEN=1024','-DAKV_REFILL_OVERLAP=0',
            '-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1','-DAKV_RESIDENT_COMPACT_COEFFICIENTS=1',
            '-I'+str(sdk/'include'),'-I'+str(sdk/'experimental'),'-I'+str(sdk/'src'),
            '-I'+str(common),'-I'+str(inputs)]
        for library in ('libm.a','libc.a','libgcc.a','libnosys.a'):
            pin(Path(run('locate-'+library,[CC,*flags[:2],'-print-file-name='+library])))
        for tool in ('cc1','as','ld'):
            pin(Path(run('locate-'+tool,[CC,'-print-prog-name='+tool])))
        sources = [inputs/'main.c', inputs/'rvv.c', inputs/'memory.S',
            inputs/'replay_rotation.S', inputs/'replay_wrap.S', inputs/'data.S',
            *[common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')],
            *[sdk/'src'/n for n in ('akv_runtime.c','akv_decode.c','akv_features.c',
                'akv_prefill_reference.c','akv_native_riscv.c','akv_v2_attention_rvv.S','akv_attention_rvv.S')],
            *[sdk/'experimental/resident_attention'/n for n in ('qk.S','pv.S','pv_compact.S')]]
        for i,source in enumerate(sources):
            dep = output/('%02d.d' % i)
            run('deps-%02d' % i,[CC,*flags,'-M','-MF',dep,source])
            for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
                path = Path(name).resolve()
                require(not path.is_relative_to(ROOT/'software'), "Live SDK compiler input")
                pin(path)
        objects = []
        verify(pins)
        for i,source in enumerate(sources):
            obj = output/('%02d_%s.o' % (i,source.stem))
            extra = ['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns'] if source.name == 'string.c' else []
            if source.name == 'replay_rotation.S':
                extra += ['-D__wrap_akv_experimental_pv_f16_pair=attention_replay_pv_rotation',
                          '-Dresident_pv_rotation_selected=attention_replay_rotation_always',
                          '-D__real_akv_experimental_pv_f16_pair=akv_experimental_pv_f16_pair']
            run('compile-%02d' % i,[CC,*flags,*extra,'-c',source,'-o',obj])
            objects.append(obj)
        elf = output/'attention.elf'
        run('link',[CC,*flags[:4],'-static','-nostdlib','-nostartfiles',*objects,
            '-Wl,--gc-sections','-Wl,--wrap=akv_experimental_pv_f16_pair',
            '-Wl,-Map='+str(output/'link.map'),'-T',inputs/'link.ld',
            '-Wl,--start-group','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
        for name,args in (('objdump',['-d','-M','no-aliases,numeric']),('readelf',['-lW'])):
            tool = CC.with_name(CC.name.replace('gcc',name)); pin(tool)
            run(name,[tool,*args,elf])
        reader = load(ELF,'attention_elf')
        parsed = reader.contract(elf.read_bytes())
        symbols = ('attention_full_call','attention_rvv_group','attention_rvv_pack',
                   'attention_memory_qk_panel4','attention_memory_pv_rotation','akv_decode_execute',
                   'akv_experimental_qk_f16_pair_panel4','attention_replay_pv_rotation',
                   'akv_attention_execute_v2_native_auto','akv_experimental_attention_execute_v2_native',
                   'akv_experimental_resident_qk_prepared','akv_experimental_resident_pv_compact')
        ranges = {name:reader.extent(parsed,name) for name in symbols}
        expf_contract = audit_expf(output,derivation)
        require({n for n in parsed['symbols'] if n.startswith('__wrap_')} ==
                {'__wrap_akv_experimental_pv_f16_pair'}, 'Only explicit replay-PV baseline wrapper allowed')
        verify(pins)
        save(output/'source-pins.json',pins)
        save(output/'commands.json',commands)
        manifest = dict(cases=[dict(id=case['id'],category='attention',elf=str(elf),elf_sha256=sha(elf),
            source_pins=str(output/'source-pins.json'),timeout_seconds=10800,
            checker=[str(Path(sys.executable).resolve()),'-B',str(HERE/'check_activity.py'),
                '--build',str(output),'--log','{log}','--vector','{run}/vector.csv',
                '--commit','{run}/commit.csv','--output','{result}'],
            plusargs=['+AKV_PERF','+AKV_SUMMARY','+RESIDENT_QK_PERF','+RESIDENT_PV_PERF',
                      '+RESIDENT_PV_WATCHDOG'])])
        save(output/'run-plan.json',manifest)
        report.update(state='BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=sha(elf),
            sdk_commit=REV,sdk_overlays=approved,archive_native_assembly_sha256=assembly_sha,
            dirty_asm_excluded=True,post_pins_match=True,source_pins_sha256=sha(output/'source-pins.json'),
            fixture=result,elf_ranges=ranges,order=order,modes=MODES,
            scalar_expf_audit=expf_contract,
            baseline_classification='Established full_call panel4 QK + rotating-register PV replay arm AND separately labeled ordinary-memory load adaptation; strict same math',
            rvv_speedup_primary_eligible=True,
            scope='Complete SDK Decode-group Attention, not GGML or board acceptance; parent owns protocol/image checking')
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p):sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'build.json',report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--capture',type=Path,default=ORIGINAL)
    parser.add_argument('--heads',default='0,1')
    parser.add_argument('--order',choices=('calibration','balanced'),default='calibration')
    args = parser.parse_args()
    heads = tuple(map(int,args.heads.split(',')))
    report = build(args.output,args.capture,heads,[0,1,4,2,3] if args.order == 'calibration' else [0,1,4,2,3,3,2,4,1,0])
    print(json.dumps({k:report[k] for k in ('state','error','elf','elf_sha256') if k in report}))
    return report['state'] != 'BUILT_NOT_EXECUTED'


if __name__ == '__main__':
    raise SystemExit(main())
